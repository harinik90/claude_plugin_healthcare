"""
Healthcare Agent — CLI Entry Point
====================================
Run:
    python run_agent.py
  or
    python -m healthcare_agent
"""
from __future__ import annotations

import sys
import textwrap

import anthropic

from .config   import API_KEY, ORCHESTRATOR_MODEL
from .registry import load_and_verify_servers
from .agent    import HealthcareAgent


BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║        Healthcare Prior Authorization Agent                      ║
║   NPI Registry · ICD-10 Codes · CMS Coverage (via MCP)         ║
╠══════════════════════════════════════════════════════════════════╣
║  Commands:  quit/exit  ·  clear (reset history)                  ║
╠══════════════════════════════════════════════════════════════════╣
║  Try asking:                                                     ║
║  • "Look up NPI 1003000126"                                      ║
║  • "What ICD-10 code is used for community-acquired pneumonia?"  ║
║  • "What does Medicare cover for CT-guided lung biopsy?"         ║
║  • "Walk me through a PA for CPT 32408, ICD R91.1, NPI 1003000126"║
╚══════════════════════════════════════════════════════════════════╝
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
    if not API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set. Add it to .env and retry.")
        sys.exit(1)

    print(BANNER)
    print(f"Model: {ORCHESTRATOR_MODEL}\n")

    try:
        mcp_servers = load_and_verify_servers(verbose=True)
    except RuntimeError as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)

    client  = anthropic.Anthropic(api_key=API_KEY)
    agent   = HealthcareAgent(client, mcp_servers)
    history: list[dict] = []

    print("Ready. Type your question below.\n")

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
