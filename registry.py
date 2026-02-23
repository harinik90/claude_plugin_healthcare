"""
MCP server registry loader
---------------------------
Reads Claude Code's plugin registry (~/.claude/plugins/installed_plugins.json)
to discover all MCP server endpoints at runtime.

Policy: URLs are NEVER hardcoded — they come exclusively from the plugin registry.
See the parent project's CLAUDE.md for the governing rule.
"""
from __future__ import annotations

import json
import pathlib

import requests

from .config import MCP_PROBE_TIMEOUT

INSTALLED_PLUGINS_FILE = pathlib.Path.home() / ".claude" / "plugins" / "installed_plugins.json"


# ── Step 2: Discover MCP servers from the plugin registry ────────────────────

def load_plugin_mcp_servers() -> list[dict]:
    """
    Walk Claude Code's installed plugin registry and collect every MCP server.

    Returns a list of server dicts ready for the Anthropic SDK:
        [{"type": "url", "url": "https://...", "name": "npi_registry",
          "_plugin": "...", "_label": "..."}, ...]

    Raises RuntimeError if the registry is missing or no servers are found.
    """
    if not INSTALLED_PLUGINS_FILE.exists():
        raise RuntimeError(
            f"Plugin registry not found: {INSTALLED_PLUGINS_FILE}\n"
            "Install Claude Code and run: claude plugin install healthcare/fhir-developer"
        )

    registry = json.loads(INSTALLED_PLUGINS_FILE.read_text(encoding="utf-8"))
    mcp_servers: list[dict] = []
    seen_urls: set[str] = set()

    for plugin_key, installs in registry.get("plugins", {}).items():
        for install in installs:
            install_path = pathlib.Path(install.get("installPath", ""))
            if not install_path.exists():
                continue
            for plugin_json in install_path.rglob(".claude-plugin/plugin.json"):
                try:
                    meta = json.loads(plugin_json.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                for server_label, server_cfg in meta.get("mcpServers", {}).items():
                    url = server_cfg.get("url", "").strip()
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    name = server_label.lower().replace(" ", "_").replace("-", "_")
                    mcp_servers.append({
                        "type":    "url",
                        "url":     url,
                        "name":    name,
                        "_plugin": plugin_key,
                        "_label":  server_label,
                    })

    if not mcp_servers:
        raise RuntimeError(
            "No MCP servers found in the plugin registry.\n"
            "Run: claude plugin install healthcare/fhir-developer"
        )

    return mcp_servers


def api_safe(servers: list[dict]) -> list[dict]:
    """Strip internal metadata keys before passing to the Anthropic API."""
    return [{"type": s["type"], "url": s["url"], "name": s["name"]} for s in servers]


# ── Step 3: Probe MCP server availability ────────────────────────────────────

def probe_servers(servers: list[dict]) -> dict[str, bool]:
    """HEAD-probe each MCP server. Returns {name: is_reachable}."""
    status: dict[str, bool] = {}
    for srv in servers:
        try:
            r = requests.head(srv["url"], timeout=MCP_PROBE_TIMEOUT)
            status[srv["name"]] = r.status_code < 500
        except Exception:
            status[srv["name"]] = False
    return status


def load_and_verify_servers(verbose: bool = True) -> list[dict]:
    """
    Full startup sequence:
      1. Load servers from plugin registry
      2. Probe each for reachability
      3. Raise if any are unreachable

    Returns API-safe server list ready for client.beta.messages.create().
    """
    if verbose:
        print("Loading MCP servers from plugin registry...", flush=True)

    discovered = load_plugin_mcp_servers()

    if verbose:
        print(f"  Found {len(discovered)} MCP server(s):")
        for srv in discovered:
            print(f"    • [{srv['_plugin']}] {srv['_label']} → {srv['url']}")
        print()
        print("Probing MCP server availability...", flush=True)

    status = probe_servers(discovered)
    unreachable = [name for name, up in status.items() if not up]

    if verbose:
        for srv in discovered:
            icon = "✅" if status.get(srv["name"]) else "❌"
            print(f"  {icon} {srv['name']}")
        print()

    if unreachable:
        raise RuntimeError(
            f"Unreachable MCP servers: {', '.join(unreachable)}\n"
            "Check that the healthcare plugins are installed and the network is reachable."
        )

    return api_safe(discovered)
