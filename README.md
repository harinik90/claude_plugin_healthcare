# Healthcare Prior Authorization Agent

A multi-agent system built on the **Claude Agent SDK pattern** that automates
prior authorization (PA) workflows for clinicians, billers, and payer staff.

Built on top of [`claude_healthcare/pa_chatbot.py`](../claude_healthcare/pa_chatbot.py),
this package restructures the single-script chatbot into a proper agent hierarchy
with an orchestrator routing queries to domain-specialist sub-agents.

---

## Architecture

```
User query
    │
    ▼
OrchestratorAgent          ← classifies intent, delegates to specialists
    │
    ├── ask_npi_agent   ──► NPIAgent    ──► NPI Registry MCP
    │                                       npi_lookup_provider
    │                                       npi_search_providers
    │                                       npi_verify_credentials
    │
    ├── ask_icd10_agent ──► ICD10Agent  ──► ICD-10 Codes MCP
    │                                       icd10_search_codes
    │                                       icd10_validate
    │                                       icd10_get_details
    │
    ├── ask_cms_agent   ──► CMSAgent    ──► CMS Coverage MCP
    │                                       cms_search_all
    │                                       cms_lcd_details
    │                                       cms_search_ncds / lcds
    │
    └── ask_pa_agent    ──► PAAgent     ──► All three MCPs
                                            (full PA workflow)
```

### How the Claude Agent SDK pattern works

The orchestrator defines each specialist as a **Python tool** (JSON Schema).
Claude picks the right tool based on query intent. The orchestrator executes the
Python function — which runs the specialist's own MCP agentic loop — and feeds
the result back to Claude as a `tool_result`. Claude then synthesises a final answer.

**Agents calling other agents through typed tool definitions** is the core pattern.

---

## Prerequisites

- Python 3.11+
- Conda environment `payerai-gpt`
- Claude Code with plugins installed:

```bash
claude plugin install healthcare/fhir-developer
claude plugin install healthcare/prior-auth-review
```

- Anthropic API key at [console.anthropic.com](https://console.anthropic.com)

---

## Setup

```bash
# 1. Activate (or create) the conda environment
conda create -n payerai-gpt python=3.11   # skip if already exists
conda activate payerai-gpt

# 2. Install dependencies
pip install -r healthcare_agent/requirements.txt

# 3. Configure API key
cp claude_healthcare/.env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

---

## Running

### Interactive CLI

```bash
conda activate payerai-gpt
python -m healthcare_agent.main
```

Expected startup output:

```
Loading MCP servers from plugin registry...
  Found 3 MCP server(s):
    • [fhir-developer@healthcare] NPI Registry  → https://...
    • [fhir-developer@healthcare] ICD-10 Codes  → https://...
    • [fhir-developer@healthcare] CMS Coverage  → https://...

Probing MCP server availability...
  ✅ npi_registry
  ✅ icd10_codes
  ✅ cms_coverage

Ready. Type your question below.
```

### As a Python library

```python
import anthropic
from healthcare_agent import OrchestratorAgent
from healthcare_agent.registry import load_and_verify_servers

client      = anthropic.Anthropic(api_key="sk-ant-...")
mcp_servers = load_and_verify_servers(verbose=False)
agent       = OrchestratorAgent(client, mcp_servers)

# Single query
answer = agent.run("Look up NPI 1003000126")

# Multi-turn with history
history = []
answer1 = agent.run("What ICD-10 code is used for community-acquired pneumonia?", history)
history += [{"role": "user", "content": "..."}, {"role": "assistant", "content": answer1}]
answer2 = agent.run("Is that code billable for FY 2025?", history)
```

---

## Example Queries

### Provider lookup (routed to NPIAgent)

```
Look up NPI 1003000126
Search for cardiologists named Smith in Texas
Is NPI 1003000126 actively credentialed?
```

### Diagnosis coding (routed to ICD10Agent)

```
What ICD-10 code is used for community-acquired pneumonia?
Validate ICD-10 codes J18.9, E11.9, and Z87.891
What are the child codes under J18?
```

### Medicare coverage (routed to CMSAgent)

```
What does Medicare cover for CT-guided lung biopsy?
Find the LCD for continuous glucose monitoring
What prior auth documentation does Medicare require for knee MRI?
```

### Full PA walkthrough (routed to PAAgent)

```
Walk me through a prior authorization request for:
  Member:    Jane Doe, DOB 05/14/1968
  Procedure: CT-guided transbronchial lung biopsy (CPT 32408)
  Diagnosis: R91.1 (solitary pulmonary nodule)
  Provider:  NPI 1003000126
```

---

## File Reference

| File | Purpose |
|------|---------|
| [`main.py`](main.py) | CLI entry point — startup, MCP probe, chat loop |
| [`config.py`](config.py) | Model, token limit, API key from `.env` |
| [`registry.py`](registry.py) | MCP server discovery from Claude Code plugin registry |
| [`agents/base.py`](agents/base.py) | Core agentic MCP tool-call loop (inherited by all agents) |
| [`agents/orchestrator.py`](agents/orchestrator.py) | Top-level router — Python tool definitions + dispatch |
| [`agents/npi_agent.py`](agents/npi_agent.py) | NPI Registry specialist |
| [`agents/icd10_agent.py`](agents/icd10_agent.py) | ICD-10 coding specialist |
| [`agents/cms_agent.py`](agents/cms_agent.py) | CMS Medicare coverage specialist |
| [`agents/pa_agent.py`](agents/pa_agent.py) | Full prior authorization workflow specialist |
| [`requirements.txt`](requirements.txt) | Python dependencies |
| [`CLAUDE.md`](CLAUDE.md) | Project governance and coding rules |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Plugin registry not found` | Install Claude Code and run `claude plugin install healthcare/fhir-developer` |
| `No MCP servers found` | Run `claude plugin install healthcare/fhir-developer` |
| `Unreachable MCP servers` | Check network access; verify plugins are correctly installed |
| `ANTHROPIC_API_KEY not set` | Add `ANTHROPIC_API_KEY=sk-ant-...` to `.env` |
| `anthropic` version error | Run `pip install anthropic --upgrade` (requires `>=0.50.0`) |
| Wrong conda environment | Run `conda activate payerai-gpt` before starting |

---

## Relationship to `claude_healthcare`

| | `claude_healthcare/pa_chatbot.py` | `healthcare_agent/` |
|---|---|---|
| Pattern | Single-script chatbot | Multi-agent package |
| Routing | Flat — one Claude call | Orchestrator → specialist agents |
| Reuse | CLI only | Importable as a library |
| Extensibility | Edit one file | Add a new agent class + tool definition |
| MCP policy | Plugin registry (CLAUDE.md) | Same policy, same `registry.py` logic |
