"""
Healthcare Agent — CLI Entry Point  (Step 7)
=============================================

Startup sequence:
  1. Load API key from .env
  2. Discover MCP servers from Claude Code plugin registry
  3. Probe each MCP server for availability
  4. Instantiate Anthropic client
  5. Instantiate OrchestratorAgent (which creates all four specialist sub-agents)
  6. Run interactive chat loop

Run:
    conda activate payerai-gpt
    python -m healthcare_agent.main
  or
    python healthcare_agent/main.py
"""
from __future__ import annotations

import sys
import textwrap

import anthropic

from .config   import API_KEY, ORCHESTRATOR_MODEL, SPECIALIST_MODEL, PA_MODEL
from .registry import load_and_verify_servers
from .agents.orchestrator import OrchestratorAgent


BANNER = """
╔════════════════════════════════════════════════════════════════════╗
║          Healthcare Prior Authorization — Agent SDK                ║
║  Orchestrator → NPI Agent | ICD-10 Agent | CMS Agent | PA Agent  ║
╠════════════════════════════════════════════════════════════════════╣
║  Commands:  quit/exit  ·  clear (reset history)                    ║
╠════════════════════════════════════════════════════════════════════╣
║  Example queries:                                                  ║
║  • "Look up NPI 1003000126"                                        ║
║  • "What ICD-10 code is used for community-acquired pneumonia?"    ║
║  • "What does Medicare cover for CT-guided lung biopsy?"           ║
║  • "Walk me through a PA for CPT 32408, ICD R91.1, NPI 1003000126"║
╚════════════════════════════════════════════════════════════════════╝
"""


def _wrap(text: str, width: int = 90) -> str:
    lines = []
    for line in text.splitlines():
        if len(line) <= width:
            lines.append(line)
        else:
            lines.extend(textwrap.wrap(line, width=width, subsequent_indent="  "))
    return "\n".join(lines)


def main() -> None:
    # ── Step 1: Validate API key ──────────────────────────────────────────────
    if not API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set. Add it to .env and retry.")
        sys.exit(1)

    print(BANNER)
    print(f"Orchestrator : {ORCHESTRATOR_MODEL}")
    print(f"Specialists  : {SPECIALIST_MODEL}")
    print(f"PA agent     : {PA_MODEL}\n")

    # ── Step 2 & 3: Discover + probe MCP servers ──────────────────────────────
    try:
        mcp_servers = load_and_verify_servers(verbose=True)
    except RuntimeError as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)

    # ── Step 4: Anthropic client ──────────────────────────────────────────────
    client = anthropic.Anthropic(api_key=API_KEY)

    # ── Step 5: Orchestrator (creates all specialist sub-agents internally) ───
    agent   = OrchestratorAgent(client, mcp_servers)
    history: list[dict] = []

    print("Ready. Type your question below.\n")

    # ── Step 6: Interactive chat loop ─────────────────────────────────────────
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

        # Run the orchestrator; it routes to specialist agents internally
        answer = agent.run(user_input, history=history)

        # Update conversation history with this turn
        history.append({"role": "user",      "content": user_input})
        history.append({"role": "assistant", "content": answer})

        print(f"\nAssistant:\n{_wrap(answer)}\n")


if __name__ == "__main__":
    main()
