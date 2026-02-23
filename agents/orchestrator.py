"""
Orchestrator Agent  — Step 6
------------------------------
The top-level agent in the multi-agent system.

Architecture (Claude Agent SDK pattern):
─────────────────────────────────────────
                  ┌──────────────────┐
     user query ──►  Orchestrator    │
                  │  (this file)     │
                  └────────┬─────────┘
                           │ calls Python tools
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼                ▼
     NPIAgent        ICD10Agent        CMSAgent          PAAgent
   (provider)      (diagnosis)       (coverage)      (full PA flow)

How routing works:
  1. Orchestrator receives the user query.
  2. It calls `client.messages.create()` with four Python tool definitions
     (one per specialist agent).
  3. Claude decides which specialist(s) to call based on the query intent.
  4. When Claude emits a `tool_use` block, the orchestrator executes the
     corresponding Python function, which internally runs the specialist
     agent's own agentic MCP loop and returns a string result.
  5. The result is fed back to Claude as a `tool_result` message.
  6. Claude synthesises a final answer from all specialist responses.

This is the key Claude Agent SDK pattern:
  agents call other agents through typed Python tool definitions.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic

from ..config import ORCHESTRATOR_MODEL, MAX_TOKENS, MAX_PARALLEL_AGENTS
from .npi_agent   import NPIAgent
from .icd10_agent import ICD10Agent
from .cms_agent   import CMSAgent
from .pa_agent    import PAAgent


# ── Tool definitions (JSON Schema) passed to the orchestrator Claude call ─────
# Each tool maps 1-to-1 with a specialist agent.

ROUTING_TOOLS = [
    {
        "name": "ask_npi_agent",
        "description": (
            "Route a question about provider identity, NPI numbers, credentials, "
            "specialty, or active status to the NPI Registry specialist agent. "
            "Use when the user mentions a provider name, NPI number, or asks "
            "about provider verification."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The provider-related question to answer.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "ask_icd10_agent",
        "description": (
            "Route a question about ICD-10-CM diagnosis codes, symptom-to-code "
            "mapping, code validation, or coding hierarchy to the ICD-10 specialist. "
            "Use when the user mentions symptoms, diagnoses, or asks about codes "
            "like R91.1 or J18.9."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The diagnosis-coding question to answer.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "ask_cms_agent",
        "description": (
            "Route a question about Medicare coverage policies, NCDs, LCDs, or "
            "medical necessity criteria to the CMS Coverage specialist agent. "
            "Use when the user asks what Medicare covers, whether a procedure is "
            "covered, or what documentation is needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The Medicare coverage policy question to answer.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "ask_pa_agent",
        "description": (
            "Route a full prior authorization (PA) scenario to the PA specialist "
            "agent. Use when the user provides member details, a provider NPI, "
            "diagnosis codes, and/or a procedure CPT code and wants a complete "
            "PA analysis covering provider verification, code validation, and "
            "coverage determination."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The full PA scenario description.",
                }
            },
            "required": ["query"],
        },
    },
]

# ── Orchestrator system prompt ────────────────────────────────────────────────

ORCHESTRATOR_SYSTEM = """\
You are the Healthcare Prior Authorization Orchestrator — the entry point for a \
multi-agent healthcare AI system.

You have four specialist agents available as tools:
  • ask_npi_agent   — provider identity, NPI lookup, credential verification
  • ask_icd10_agent — ICD-10-CM diagnosis code search and validation
  • ask_cms_agent   — Medicare NCD/LCD coverage policy lookup
  • ask_pa_agent    — complete prior authorization workflow (all three domains)

Routing rules:
1. For questions about a provider or NPI number → call ask_npi_agent.
2. For questions about diagnosis codes or symptoms → call ask_icd10_agent.
3. For questions about Medicare coverage or medical necessity → call ask_cms_agent.
4. For complete PA scenarios (member + provider + diagnosis + procedure) → call ask_pa_agent.
5. For multi-domain questions, call multiple specialist tools in parallel.
6. Synthesise the specialist responses into a single, coherent answer.

Always delegate to a specialist — never answer healthcare data questions yourself \
without calling the appropriate tool first."""


class OrchestratorAgent:
    """
    Top-level agent that routes queries to specialist sub-agents.

    Usage:
        agent = OrchestratorAgent(client, mcp_servers)
        answer = agent.run("Look up NPI 1003000126")
        answer = agent.run("Walk me through a PA for CPT 32408, ICD R91.1, NPI 1003000126")
    """

    def __init__(self, client: anthropic.Anthropic, mcp_servers: list[dict]) -> None:
        self.client      = client
        self.mcp_servers = mcp_servers

        # Instantiate specialist agents (all share the same client + MCP servers)
        self._specialists: dict[str, object] = {
            "ask_npi_agent":   NPIAgent(client, mcp_servers),
            "ask_icd10_agent": ICD10Agent(client, mcp_servers),
            "ask_cms_agent":   CMSAgent(client, mcp_servers),
            "ask_pa_agent":    PAAgent(client, mcp_servers),
        }

    # ── Public interface ────────────────────────────────────────────────────

    def run(self, query: str, history: list[dict] | None = None) -> str:
        """
        Route a user query through the orchestrator and return the final answer.

        Args:
            query:   The user's question or PA scenario.
            history: Optional prior conversation turns.

        Returns:
            Synthesised final answer from orchestrator + specialist agents.
        """
        messages = list(history or [])
        messages.append({"role": "user", "content": query})
        return self._orchestration_loop(messages)

    # ── Internal orchestration loop ─────────────────────────────────────────

    def _orchestration_loop(self, messages: list[dict]) -> str:
        """
        Drive the tool-call loop:
          - If Claude calls a routing tool → run the specialist agent → feed result back
          - If Claude is done (end_turn) → return final text
        """
        while True:
            response = self.client.messages.create(
                model=ORCHESTRATOR_MODEL,
                max_tokens=MAX_TOKENS,
                system=ORCHESTRATOR_SYSTEM,
                tools=ROUTING_TOOLS,
                messages=messages,
            )

            text_parts: list[str] = []
            tool_uses: list       = []

            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_uses.append(block)

            if response.stop_reason == "tool_use":
                # Append Claude's response (with tool_use blocks) to history
                messages.append({"role": "assistant", "content": response.content})

                # Run all requested specialist agents in parallel
                def _call_specialist(tu) -> dict:
                    specialist_name = tu.name
                    query = tu.input.get("query", "")
                    print(f"  [orchestrator → {specialist_name}] {query[:80]}", flush=True)
                    specialist = self._specialists.get(specialist_name)
                    result = specialist.run(query) if specialist else f"Unknown specialist: {specialist_name}"  # type: ignore[attr-defined]
                    return {
                        "type":        "tool_result",
                        "tool_use_id": tu.id,
                        "content":     result,
                    }

                tool_results = [None] * len(tool_uses)
                with ThreadPoolExecutor(max_workers=min(len(tool_uses), MAX_PARALLEL_AGENTS)) as pool:
                    future_to_index = {pool.submit(_call_specialist, tu): i for i, tu in enumerate(tool_uses)}
                    for future in as_completed(future_to_index):
                        tool_results[future_to_index[future]] = future.result()

                # Feed all tool results back to Claude in one user turn
                messages.append({"role": "user", "content": tool_results})

            else:
                # end_turn — orchestrator has its final synthesised answer
                return " ".join(text_parts) if text_parts else "(no response)"
