# CLAUDE.md — Project Rules for healthcare_agent

## Overview

`healthcare_agent` is a single-agent healthcare PA assistant built on the
Claude Agent SDK. It mirrors the functionality of the sibling project
`../claude_healthcare/pa_chatbot.py` as a proper Python package.

```
HealthcareAgent.run(query)
    └── Claude chains MCP tools as needed:
          npi_lookup_provider      (NPI Registry MCP)
          icd10_validate           (ICD-10 Codes MCP)
          cms_lcd_details          (CMS Coverage MCP)
```

One agent. One `run()` call. Claude decides which tool(s) to invoke.

---

## MCP Server URL Policy

**MCP server URLs MUST NEVER be hardcoded in any source file.**

All MCP endpoints are discovered at runtime from Claude Code's plugin registry:

```
~/.claude/plugins/installed_plugins.json          ← registry of installed plugins
~/.claude/plugins/cache/<marketplace>/<plugin>/<sha>/
    <subpackage>/.claude-plugin/plugin.json       ← per-package MCP server definitions
```

`load_and_verify_servers()` in [registry.py](registry.py) is the single
authoritative place for MCP server discovery. It must:

1. Read `installed_plugins.json` to find every plugin's `installPath`.
2. Recursively walk each `installPath` for `.claude-plugin/plugin.json` files.
3. Extract the `mcpServers` block from each file.
4. HEAD-probe each discovered server for availability.
5. Raise `RuntimeError` if any server is unreachable.

### Enforcement

- Do not add MCP server URLs to any `.py`, `.env`, or config file.
- If no servers are found, exit with a clear error.
- If a probe fails, exit — no fallback, no partial operation.
- There is no REST API fallback. All data must come through plugin-registered MCP servers.

---

## Required Claude Code Plugins

| Plugin | Provides | Install |
|--------|----------|---------|
| `healthcare/fhir-developer` | NPI Registry MCP, ICD-10 Codes MCP, CMS Coverage MCP | `claude plugin install healthcare/fhir-developer` |
| `healthcare/prior-auth-review` | PA skill guidance | `claude plugin install healthcare/prior-auth-review` |

---

## Python Environment

**Required conda environment: `payerai-gpt`**

```bash
conda create -n payerai-gpt python=3.11   # if it doesn't exist
conda activate payerai-gpt
pip install -r requirements.txt
```

Do not activate the environment from inside Python scripts.

---

## Architecture Rules

### 1. Single Agent
All query types (NPI lookup, ICD-10 validation, CMS coverage, full PA) are
handled by the one `HealthcareAgent` class in [agent.py](agent.py).
Do not split into specialist agents or add an orchestrator.

### 2. System Prompt Is the Only Configuration
Behaviour is controlled entirely by the `SYSTEM_PROMPT` in [agent.py](agent.py).
To change how the agent handles a query type, edit the system prompt.

### 3. No State in the Agent Class
`HealthcareAgent` is stateless between `run()` calls. Conversation history
is passed in by the caller, not stored on the instance.

### 4. MCP Loop Lives in `agent.py`
The `while True` agentic loop that drives MCP tool calls is in `run()` inside
[agent.py](agent.py). Do not duplicate it elsewhere.

---

## File Ownership

| File | Responsibility | Change with care |
|------|----------------|-----------------|
| `registry.py` | MCP discovery — source of truth for server URLs | Yes — affects startup |
| `agent.py` | Agent class + system prompt + MCP loop | Yes — core behaviour |
| `config.py` | Model, token limit, probe timeout | Low risk |
| `main.py` | CLI entry point | Low risk |
| `run_agent.py` | Top-level script runner | Low risk |

---

## Running

```bash
conda activate payerai-gpt
python run_agent.py
```

Or as a library:

```python
import anthropic
from healthcare_agent import HealthcareAgent
from healthcare_agent.registry import load_and_verify_servers

client      = anthropic.Anthropic(api_key="...")
mcp_servers = load_and_verify_servers(verbose=False)
agent       = HealthcareAgent(client, mcp_servers)
answer      = agent.run("Walk me through a PA for CPT 32408, ICD R91.1, NPI 1003000126")
```
