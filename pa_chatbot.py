"""
Healthcare Prior Authorization Chatbot
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Combines:
  • Claude remote MCP for live healthcare data
  • NPI Registry MCP   — NPPES provider lookup
  • ICD-10 Codes MCP   — diagnosis code search & validation
  • CMS Coverage MCP   — NCD/LCD Medicare coverage policies
  • Prior Auth skill guidance (from the prior-auth-review-skill plugin)

MCP server URLs are NEVER hardcoded. They are read at runtime from
Claude Code's plugin registry (~/.claude/plugins/installed_plugins.json).
See CLAUDE.md for the governing policy.

Setup
-----
    pip install -r requirements.txt
    Add ANTHROPIC_API_KEY to .env
    python pa_chatbot.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import textwrap
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

# Force UTF-8 on Windows consoles (avoids cp1252 UnicodeEncodeError for box/emoji chars).
# PYTHONUTF8=1 env var or -Xutf8 flag achieves the same at interpreter level.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure") and getattr(_stream, "encoding", "utf-8").lower() != "utf-8":
        _stream.reconfigure(encoding="utf-8", errors="replace")

# ─────────────────────────── config ───────────────────────────────────────────
MODEL      = os.environ.get("CLAUDE_MODEL",      "claude-sonnet-4-6")
MAX_TOKENS = int(os.environ.get("CLAUDE_MAX_TOKENS", "2048"))

# ─────────────────────────── plugin registry loader ───────────────────────────
# MCP server URLs are sourced exclusively from Claude Code's plugin registry.
# See CLAUDE.md — "MCP Server URL Policy".

INSTALLED_PLUGINS_FILE = pathlib.Path.home() / ".claude" / "plugins" / "installed_plugins.json"


def load_plugin_mcp_servers() -> list[dict]:
    """
    Walk Claude Code's installed plugin registry and collect every MCP server
    defined in .claude-plugin/plugin.json files.

    Returns a list of server dicts ready for the Anthropic SDK:
        [{"type": "url", "url": "https://...", "name": "npi_registry",
          "_plugin": "...", "_label": "..."}, ...]

    Raises RuntimeError if the registry file is missing or no servers are found.
    """
    if not INSTALLED_PLUGINS_FILE.exists():
        raise RuntimeError(
            f"Claude Code plugin registry not found at {INSTALLED_PLUGINS_FILE}.\n"
            "Ensure Claude Code is installed and at least one plugin is registered."
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

                    # Convert plugin.json type ("http") → Anthropic SDK type ("url")
                    sdk_type = "url"

                    # Derive a clean snake_case name from the server label
                    name = server_label.lower().replace(" ", "_").replace("-", "_")

                    mcp_servers.append({
                        "type": sdk_type,
                        "url":  url,
                        "name": name,
                        "_plugin": plugin_key,   # metadata — stripped before API call
                        "_label":  server_label,
                    })

    if not mcp_servers:
        raise RuntimeError(
            "No MCP servers found in the Claude Code plugin registry.\n"
            "Install the required plugin:\n"
            "  claude plugin install healthcare/fhir-developer"
        )

    return mcp_servers


def _api_safe(servers: list[dict]) -> list[dict]:
    """Strip internal metadata keys before passing servers to the Anthropic API."""
    return [{"type": s["type"], "url": s["url"], "name": s["name"]} for s in servers]


# ─────────────────────────── system prompt ────────────────────────────────────
SYSTEM_PROMPT = """\
You are a knowledgeable Healthcare Prior Authorization (PA) assistant serving \
clinicians, billers, and payer staff.

You have live access to three data sources via MCP connectors:

1. NPI Registry (NPPES)
   Tools: npi_lookup_provider, npi_search_providers, npi_verify_credentials
   Use to: verify a provider's NPI, specialty, address, and active status.

2. ICD-10 Codes
   Tools: icd10_search_codes, icd10_get_details, icd10_validate, icd10_hierarchy,
          icd10_category, icd10_chapters
   Use to: find diagnosis codes, validate codes, get coding guidance.

3. CMS Medicare Coverage (NCDs & LCDs)
   Tools: cms_search_all, cms_search_ncds, cms_search_lcds, cms_lcd_details,
          cms_search_articles, cms_whats_new
   Use to: find Medicare coverage policies and medical necessity criteria.

Prior Authorization guidance:
• Explain what clinical documentation, diagnosis codes, and provider credentials
  are typically required for a prior auth request.
• Walk the user through what an insurer looks for when reviewing a PA.
• If a user provides member, provider, diagnosis, or procedure details, analyze
  them and explain what is likely needed for authorization.

ALWAYS call the relevant MCP tool(s) to retrieve live data before answering \
questions about specific providers, codes, or coverage policies.
Cite data sources. Note when data could not be retrieved.
Be concise. Use bullet points for lists."""


# ─────────────────────────── MCP availability probe ───────────────────────────
def _check_mcp_servers(servers: list[dict]) -> dict[str, bool]:
    """HEAD-probe each MCP server. Returns {name: is_reachable}."""
    status = {}
    for srv in servers:
        try:
            r = requests.head(srv["url"], timeout=5)
            status[srv["name"]] = r.status_code < 500
        except Exception:
            status[srv["name"]] = False
    return status


# ─────────────────────────── chat helpers ─────────────────────────────────────
def _wrap(text: str, width: int = 90) -> str:
    lines = []
    for line in text.splitlines():
        if len(line) <= width:
            lines.append(line)
        else:
            lines.extend(textwrap.wrap(line, width=width, subsequent_indent="  "))
    return "\n".join(lines)


BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║       Healthcare Prior Authorization Chatbot                     ║
║  Claude + NPI Registry + ICD-10 Codes + CMS Coverage (MCPs)    ║
╠══════════════════════════════════════════════════════════════════╣
║  Commands:  quit/exit  ·  clear (reset history)                  ║
╠══════════════════════════════════════════════════════════════════╣
║  Try asking:                                                     ║
║  • "Look up NPI 1003000126"                                      ║
║  • "Search for cardiologists named Smith in Texas"               ║
║  • "What ICD-10 code is used for community-acquired pneumonia?"  ║
║  • "Validate ICD-10 codes J18.9, E11.9, and Z87.891"            ║
║  • "What does Medicare cover for CT-guided lung biopsy?"         ║
║  • "What prior auth is typically needed for knee MRI?"           ║
║  • "Walk me through a prior auth for CPT 32408, ICD R91.1"       ║
╚══════════════════════════════════════════════════════════════════╝
"""


# ─────────────────────────── main chat loop ───────────────────────────────────
def chat():
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set. Add it to .env and retry.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    history: list[dict] = []

    print(BANNER)

    # ── Step 1: Load MCP servers from Claude Code plugin registry ─────────────
    print("Loading MCP servers from Claude Code plugin registry...", flush=True)
    try:
        discovered = load_plugin_mcp_servers()
    except RuntimeError as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)

    print(f"  Found {len(discovered)} MCP server(s):")
    for srv in discovered:
        print(f"    • [{srv['_plugin']}] {srv['_label']} → {srv['url']}")
    print()

    # ── Step 2: Confirm all registered servers are reachable ──────────────────
    print("Checking MCP server availability...", flush=True)
    mcp_status = _check_mcp_servers(discovered)
    unreachable = [name for name, up in mcp_status.items() if not up]

    for srv in discovered:
        icon = "✅" if mcp_status.get(srv["name"]) else "❌"
        print(f"  {icon} {srv['name']}")

    if unreachable:
        print(f"\nERROR: The following plugin MCP servers are unreachable: {', '.join(unreachable)}")
        print("Ensure the healthcare plugins are correctly installed and the MCP endpoints are accessible.")
        sys.exit(1)

    print()
    mcp_servers = _api_safe(discovered)

    # ── Chat loop ──────────────────────────────────────────────────────────────
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break
        if user_input.lower() == "clear":
            history.clear()
            print("Conversation cleared.\n")
            continue

        history.append({"role": "user", "content": user_input})

        # ── Agentic loop — Claude may chain multiple MCP calls ────────────────
        while True:
            response = client.beta.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                betas=["mcp-client-2025-04-04"],
                mcp_servers=mcp_servers,
                messages=history,
            )

            text_parts: list[str] = []
            tool_calls: list[Any] = []

            for block in response.content:
                block_type = getattr(block, "type", "")
                if block_type == "text":
                    text_parts.append(block.text)
                elif block_type == "mcp_tool_use":
                    tool_calls.append(block)

            # Print any interim text Claude produced before requesting tools
            if text_parts and tool_calls:
                print(f"\nAssistant: {_wrap(' '.join(text_parts))}")

            if response.stop_reason == "mcp_tool_use":
                history.append({"role": "assistant", "content": response.content})
                for tc in tool_calls:
                    label = getattr(tc, "server_name", tc.name)
                    print(f"\n  [mcp:{label}/{tc.name}]", flush=True)
                # Loop — Anthropic API handles the MCP call; next turn has the result.

            else:
                # end_turn — Claude's final answer
                final = " ".join(text_parts) if text_parts else "(no response)"
                history.append({"role": "assistant", "content": final})
                print(f"\nAssistant: {_wrap(final)}\n")
                break


if __name__ == "__main__":
    chat()
