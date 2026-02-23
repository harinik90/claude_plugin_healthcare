"""
Healthcare Prior Authorization Agent
======================================
Single-file agent. Run directly:
    python agent.py

Connects to three live MCP servers (NPI Registry, ICD-10 Codes, CMS Coverage).
Claude decides which tool(s) to call and chains them as needed.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import textwrap
from typing import Any

import requests
import anthropic
from dotenv import load_dotenv

# ── Config ────────────────────────────────────────────────────────────────────

load_dotenv(dotenv_path=pathlib.Path(__file__).parent / ".env")

# Force UTF-8 on Windows
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure") and getattr(_s, "encoding", "utf-8").lower() != "utf-8":
        _s.reconfigure(encoding="utf-8", errors="replace")

API_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL      = os.environ.get("CLAUDE_MODEL",      "claude-sonnet-4-6")
MAX_TOKENS = int(os.environ.get("CLAUDE_MAX_TOKENS", "4096"))
MCP_PROBE_TIMEOUT = int(os.environ.get("MCP_PROBE_TIMEOUT", "5"))

# ── MCP server discovery ──────────────────────────────────────────────────────

PLUGINS_FILE = pathlib.Path.home() / ".claude" / "plugins" / "installed_plugins.json"


def load_mcp_servers() -> list[dict]:
    """Discover MCP servers from the Claude Code plugin registry."""
    if not PLUGINS_FILE.exists():
        raise RuntimeError(
            f"Plugin registry not found: {PLUGINS_FILE}\n"
            "Run: claude plugin install healthcare/fhir-developer"
        )

    registry = json.loads(PLUGINS_FILE.read_text(encoding="utf-8"))
    servers: list[dict] = []
    seen: set[str] = set()

    for plugin_key, installs in registry.get("plugins", {}).items():
        for install in installs:
            path = pathlib.Path(install.get("installPath", ""))
            for pjson in path.rglob(".claude-plugin/plugin.json"):
                try:
                    meta = json.loads(pjson.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                for label, cfg in meta.get("mcpServers", {}).items():
                    url = cfg.get("url", "").strip()
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    servers.append({
                        "type":    "url",
                        "url":     url,
                        "name":    label.lower().replace(" ", "_").replace("-", "_"),
                        "_plugin": plugin_key,
                        "_label":  label,
                    })

    if not servers:
        raise RuntimeError(
            "No MCP servers found.\n"
            "Run: claude plugin install healthcare/fhir-developer"
        )
    return servers


def probe_servers(servers: list[dict]) -> list[dict]:
    """HEAD-probe each server; raise if any are unreachable."""
    unreachable = []
    for srv in servers:
        try:
            ok = requests.head(srv["url"], timeout=MCP_PROBE_TIMEOUT).status_code < 500
        except Exception:
            ok = False
        icon = "✅" if ok else "❌"
        print(f"  {icon} {srv['name']}")
        if not ok:
            unreachable.append(srv["name"])

    if unreachable:
        raise RuntimeError(f"Unreachable MCP servers: {', '.join(unreachable)}")

    return [{"type": s["type"], "url": s["url"], "name": s["name"]} for s in servers]


# ── Agent ─────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a Healthcare Prior Authorization (PA) assistant serving clinicians,
billers, and payer staff.

You have live access to three data sources via MCP connectors:

1. NPI Registry (NPPES)
   Tools: npi_lookup_provider, npi_search_providers, npi_verify_credentials
   Use to: verify a provider's NPI, specialty, address, and active status.

2. ICD-10 Codes
   Tools: icd10_search_codes, icd10_get_details, icd10_validate,
          icd10_hierarchy, icd10_category, icd10_chapters
   Use to: find diagnosis codes, validate codes, get coding guidance.

3. CMS Medicare Coverage (NCDs & LCDs)
   Tools: cms_search_all, cms_search_ncds, cms_search_lcds, cms_lcd_details,
          cms_search_articles, cms_whats_new
   Use to: find Medicare coverage policies and medical necessity criteria.

For a full PA scenario (provider + diagnosis + procedure):
  1. Verify provider via npi_lookup_provider or npi_verify_credentials.
  2. Validate each diagnosis code via icd10_validate.
  3. Check coverage via cms_search_all then cms_lcd_details.
  4. Summarise: provider status, code validity, coverage determination,
     required documentation, and recommended decision.

ALWAYS call the relevant MCP tool(s) before answering. Never guess.
Cite data sources. Be concise. Use bullet points."""


class HealthcareAgent:
    def __init__(self, client: anthropic.Anthropic, mcp_servers: list[dict]) -> None:
        self.client      = client
        self.mcp_servers = mcp_servers

    def run(self, query: str, history: list[dict] | None = None) -> str:
        messages = list(history or [])
        messages.append({"role": "user", "content": query})

        while True:
            response = self.client.beta.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                betas=["mcp-client-2025-04-04"],
                mcp_servers=self.mcp_servers,
                messages=messages,
            )

            text_parts: list[str] = []
            tool_calls: list[Any] = []

            for block in response.content:
                if getattr(block, "type", "") == "text":
                    text_parts.append(block.text)
                elif getattr(block, "type", "") == "mcp_tool_use":
                    tool_calls.append(block)

            if response.stop_reason == "mcp_tool_use":
                messages.append({"role": "assistant", "content": response.content})
                for tc in tool_calls:
                    print(f"  [mcp:{getattr(tc, 'server_name', tc.name)}/{tc.name}]", flush=True)
            else:
                return " ".join(text_parts) if text_parts else "(no response)"


# ── CLI ───────────────────────────────────────────────────────────────────────

BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║        Healthcare Prior Authorization Agent                      ║
║   NPI Registry · ICD-10 Codes · CMS Coverage (via MCP)         ║
╠══════════════════════════════════════════════════════════════════╣
║  Commands:  quit/exit  ·  clear (reset history)                  ║
╠══════════════════════════════════════════════════════════════════╣
║  Try asking:                                                     ║
║  • "Look up NPI 1003000126"                                      ║
║  • "What ICD-10 code for community-acquired pneumonia?"          ║
║  • "What does Medicare cover for CT-guided lung biopsy?"         ║
║  • "Walk me through a PA for CPT 32408, ICD R91.1, NPI 1003000126"║
╚══════════════════════════════════════════════════════════════════╝
"""


def _wrap(text: str, width: int = 90) -> str:
    lines = []
    for line in text.splitlines():
        lines.extend(textwrap.wrap(line, width) if len(line) > width else [line])
    return "\n".join(lines)


def main() -> None:
    if not API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set. Add it to .env and retry.")
        sys.exit(1)

    print(BANNER)
    print(f"Model: {MODEL}\n")

    print("Loading MCP servers from plugin registry...", flush=True)
    try:
        discovered = load_mcp_servers()
    except RuntimeError as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)

    print(f"  Found {len(discovered)} MCP server(s):")
    for srv in discovered:
        print(f"    • [{srv['_plugin']}] {srv['_label']} → {srv['url']}")

    print("\nProbing MCP server availability...", flush=True)
    try:
        mcp_servers = probe_servers(discovered)
    except RuntimeError as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)

    client  = anthropic.Anthropic(api_key=API_KEY)
    agent   = HealthcareAgent(client, mcp_servers)
    history: list[dict] = []

    print("\nReady. Type your question below.\n")

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

        answer = agent.run(user_input, history=history)
        history.append({"role": "user",      "content": user_input})
        history.append({"role": "assistant", "content": answer})
        print(f"\nAssistant:\n{_wrap(answer)}\n")


if __name__ == "__main__":
    main()
