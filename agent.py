"""
Healthcare Agent
-----------------
A single agent with access to all three MCP servers.
Claude decides which tool(s) to call and chains them as needed.

For a full PA scenario, one run() call handles everything:
  NPI lookup → ICD-10 validation → CMS coverage → PA summary
"""
from __future__ import annotations

from typing import Any

import anthropic

from .config import ORCHESTRATOR_MODEL, MAX_TOKENS

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
    """
    Single healthcare PA agent backed by three MCP servers.

    Claude chains whichever MCP tools are needed for the query —
    a simple NPI lookup uses one tool; a full PA scenario chains all three.

    Usage:
        answer = agent.run("Walk me through a PA for CPT 32408, ICD R91.1, NPI 1003000126")
    """

    def __init__(self, client: anthropic.Anthropic, mcp_servers: list[dict]) -> None:
        self.client      = client
        self.mcp_servers = mcp_servers

    def run(self, query: str, history: list[dict] | None = None) -> str:
        """
        Run a query through the agentic MCP loop and return the final answer.

        Args:
            query:   The user's question or PA scenario.
            history: Optional prior conversation turns for multi-turn sessions.
        """
        messages = list(history or [])
        messages.append({"role": "user", "content": query})

        while True:
            response = self.client.beta.messages.create(
                model=ORCHESTRATOR_MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
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
                messages.append({"role": "assistant", "content": response.content})
                for tc in tool_calls:
                    server = getattr(tc, "server_name", tc.name)
                    print(f"  [mcp:{server}/{tc.name}]", flush=True)
            else:
                return " ".join(text_parts) if text_parts else "(no response)"
