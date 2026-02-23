# CLAUDE.md — Project Rules for healthcare_agent

## Overview

`healthcare_agent` is a multi-agent system built on the **Claude Agent SDK pattern**.
It mirrors the functionality of the sibling project `../claude_healthcare/pa_chatbot.py`
but restructures it into a proper agent hierarchy:

```
OrchestratorAgent
    ├── NPIAgent    (NPI Registry MCP)
    ├── ICD10Agent  (ICD-10 Codes MCP)
    ├── CMSAgent    (CMS Coverage MCP)
    └── PAAgent     (all three MCPs — full PA workflow)
```

---

## MCP Server URL Policy

**MCP server URLs MUST NEVER be hardcoded in any source file.**

All MCP endpoints are discovered at runtime from Claude Code's plugin registry:

```
~/.claude/plugins/installed_plugins.json          ← registry of installed plugins
~/.claude/plugins/cache/<marketplace>/<plugin>/<sha>/
    <subpackage>/.claude-plugin/plugin.json       ← per-package MCP server definitions
```

The function `load_and_verify_servers()` in [registry.py](registry.py) is the single,
authoritative place for MCP server discovery. It must:

1. Read `installed_plugins.json` to find every plugin's `installPath`.
2. Recursively walk each `installPath` for `.claude-plugin/plugin.json` files.
3. Extract the `mcpServers` block from each file.
4. HEAD-probe each discovered server for availability.
5. Raise `RuntimeError` if any server is unreachable — do not proceed with partial coverage.

### Enforcement

- Do not add MCP server URLs to any `.py`, `.env`, or config file.
- If `load_and_verify_servers()` finds no servers, exit with a clear error.
- If a probe fails, exit — no fallback, no partial operation.
- There is no REST API fallback. All healthcare data must come through plugin-registered MCP servers.

---

## Required Claude Code Plugins

| Plugin | Provides | Install |
|--------|----------|---------|
| `healthcare/fhir-developer` | NPI Registry MCP, ICD-10 Codes MCP, CMS Coverage MCP | `claude plugin install healthcare/fhir-developer` |
| `healthcare/prior-auth-review` | PA skill guidance | `claude plugin install healthcare/prior-auth-review` |

---

## Python Environment

**Required conda environment: `payerai-gpt`**

All development, testing, and execution must use the `payerai-gpt` conda environment.

```bash
# First-time setup
conda create -n payerai-gpt python=3.11   # if it doesn't exist
conda activate payerai-gpt
pip install -r requirements.txt
```

Do not activate the environment from inside Python scripts — that is the caller's responsibility.

---

## Agent SDK Architecture Rules

### 1. One Agent Per Domain
Each specialist agent (`NPIAgent`, `ICD10Agent`, `CMSAgent`, `PAAgent`) is responsible
for exactly one data domain. Do not merge domain logic across agents.

### 2. BaseAgent Is the Only Agentic Loop
The MCP tool-call loop lives exclusively in [agents/base.py](agents/base.py).
Specialist agents must not re-implement the loop — they only set `system_prompt`.

### 3. Orchestrator Routes via Python Tool Definitions
The `OrchestratorAgent` in [agents/orchestrator.py](agents/orchestrator.py) routes
queries to specialists using Claude's `tool_use` mechanism with Python tool definitions
(`ROUTING_TOOLS`). This is the canonical Agent SDK pattern — **agents calling other
agents through typed tool definitions**.

Do not add business logic to the orchestrator. It classifies and delegates only.

### 4. Specialist Agents Are Reusable As Libraries
Every specialist agent exposes `run(query, history=None) -> str`. They can be called
directly (without the orchestrator) from other Python code.

### 5. No State in Agent Classes
Agent instances are stateless between `run()` calls. Conversation history is passed
in by the caller and not stored on the agent object.

---

## File Ownership

| File | Responsibility | Change with care |
|------|----------------|-----------------|
| `registry.py` | MCP discovery — source of truth for server URLs | Yes — affects all agents |
| `agents/base.py` | Core agentic loop | Yes — affects all agents |
| `agents/orchestrator.py` | Routing tool definitions + loop | Yes — routing changes break dispatch |
| `agents/npi_agent.py` | NPI system prompt | Low risk — prompt only |
| `agents/icd10_agent.py` | ICD-10 system prompt | Low risk — prompt only |
| `agents/cms_agent.py` | CMS system prompt | Low risk — prompt only |
| `agents/pa_agent.py` | PA workflow system prompt | Medium — chains all MCPs |
| `config.py` | Model, token, API key config | Low risk |
| `main.py` | CLI entry point | Low risk |

---

## Adding a New Specialist Agent

1. Create `agents/<domain>_agent.py` — subclass `BaseAgent`, set `system_prompt`.
2. Add the class to `agents/__init__.py`.
3. Add a routing tool entry to `ROUTING_TOOLS` in `agents/orchestrator.py`.
4. Instantiate the new agent in `OrchestratorAgent.__init__` and add it to `_specialists`.
5. Document the MCP tools it uses in its docstring.

---

## Running

```bash
conda activate payerai-gpt
python -m healthcare_agent.main
```

Or as a library:

```python
from healthcare_agent import OrchestratorAgent
from healthcare_agent.registry import load_and_verify_servers
import anthropic

client      = anthropic.Anthropic(api_key="...")
mcp_servers = load_and_verify_servers(verbose=False)
agent       = OrchestratorAgent(client, mcp_servers)
answer      = agent.run("Walk me through a PA for CPT 32408, ICD R91.1")
```
