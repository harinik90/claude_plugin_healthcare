"""
Healthcare Prior Authorization Agent
=====================================
A multi-agent system built with the Claude Agent SDK pattern.

Agents:
  • Orchestrator  — routes queries to the right specialist
  • NPI Agent     — provider lookup via NPI Registry MCP
  • ICD-10 Agent  — diagnosis code search & validation via ICD-10 MCP
  • CMS Agent     — Medicare coverage policy lookup via CMS MCP
  • PA Agent      — full prior authorization workflow (chains all three)
"""

from .agents.orchestrator import OrchestratorAgent

__all__ = ["OrchestratorAgent"]
