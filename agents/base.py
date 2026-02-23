"""
Base Agent
-----------
Step 4 — Core Agent SDK pattern:

  Every specialist agent:
    1. Holds a reference to the shared Anthropic client + MCP server list
    2. Exposes a `run(query, history)` method that drives the agentic loop
    3. Returns a plain string — the final model answer after all MCP tool calls
       have been chained and resolved by the Anthropic platform.

  The agentic loop works like this:
    ┌─────────────────────────────────────────────────────┐
    │  while True:                                        │
    │    response = client.beta.messages.create(...)      │
    │    if stop_reason == "mcp_tool_use":                │
    │       append response to history → loop again       │
    │    elif stop_reason == "end_turn":                  │
    │       return final text → break                     │
    └─────────────────────────────────────────────────────┘

  The Anthropic platform transparently calls the MCP server, appends the
  tool result to the conversation, and returns control so we can loop.
"""
from __future__ import annotations

from typing import Any

import anthropic

from ..config import SPECIALIST_MODEL, MAX_TOKENS


class BaseAgent:
    """
    Minimal agentic execution loop backed by Claude + remote MCP servers.

    Subclasses set:
      • system_prompt  — role / capabilities / instructions for this specialist
    """

    system_prompt: str = "You are a helpful assistant."
    model:         str = SPECIALIST_MODEL   # subclasses can override per-agent

    def __init__(self, client: anthropic.Anthropic, mcp_servers: list[dict]) -> None:
        self.client      = client
        self.mcp_servers = mcp_servers        # API-safe: [{type, url, name}, ...]

    # ── Public interface ────────────────────────────────────────────────────

    def run(self, query: str, history: list[dict] | None = None) -> str:
        """
        Run the agentic loop for a single user query.

        Args:
            query:   The user's question or request.
            history: Optional prior conversation turns (for multi-turn sessions).

        Returns:
            The agent's final text response as a plain string.
        """
        messages = list(history or [])
        messages.append({"role": "user", "content": query})
        return self._agentic_loop(messages)

    # ── Internal agentic loop ───────────────────────────────────────────────

    def _agentic_loop(self, messages: list[dict]) -> str:
        """Drive the MCP tool-call loop until Claude produces an end_turn."""
        while True:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=self.system_prompt,
                betas=["mcp-client-2025-04-04"],
                mcp_servers=self.mcp_servers,
                messages=messages,
            )

            text_parts: list[str] = []
            tool_calls: list[Any] = []

            for block in response.content:
                block_type = getattr(block, "type", "")
                if block_type == "text":
                    text_parts.append(block.text)
                elif block_type == "mcp_tool_use":
                    tool_calls.append(block)

            if response.stop_reason == "mcp_tool_use":
                # Claude wants to call an MCP tool — append response and loop.
                # The platform handles the actual call; next turn has the result.
                messages.append({"role": "assistant", "content": response.content})
                if tool_calls:
                    names = [f"{getattr(tc, 'server_name', tc.name)}/{tc.name}" for tc in tool_calls]
                    print(f"  [tool] {', '.join(names)}", flush=True)
            else:
                # stop_reason == "end_turn" — Claude is done.
                return " ".join(text_parts) if text_parts else "(no response)"
