# Healthcare Prior Authorization Agent

A single AI agent that automates prior authorization (PA) workflows for
clinicians, billers, and payer staff. Built on the Claude Agent SDK using
three live MCP data sources.

---

## How It Works

```
User query
    │
    ▼
HealthcareAgent.run()
    │
    │  Claude decides which MCP tool(s) to call
    ├──► npi_lookup_provider       (NPI Registry MCP)
    ├──► icd10_validate            (ICD-10 Codes MCP)
    └──► cms_lcd_details           (CMS Coverage MCP)
    │
    ▼
Final answer (single API response cycle)
```

For a simple NPI lookup, Claude calls one tool.
For a full PA scenario, Claude chains all three MCP servers automatically —
no routing layer or orchestrator needed.

---

## MCP Data Sources

| MCP Server | Tools | Used for |
|---|---|---|
| **NPI Registry** | `npi_lookup_provider`, `npi_search_providers`, `npi_verify_credentials` | Provider identity & credentials |
| **ICD-10 Codes** | `icd10_search_codes`, `icd10_get_details`, `icd10_validate`, `icd10_hierarchy` | Diagnosis code search & validation |
| **CMS Coverage** | `cms_search_all`, `cms_search_ncds`, `cms_search_lcds`, `cms_lcd_details` | Medicare NCD/LCD policy lookup |

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
# 1. Activate the conda environment
conda create -n payerai-gpt python=3.11   # skip if already exists
conda activate payerai-gpt

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure API key
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

---

## Running

```bash
conda activate payerai-gpt
python run_agent.py
```

Or:

```bash
python -m healthcare_agent
```

Expected startup:

```
Loading MCP servers from plugin registry...
  Found 4 MCP server(s):
    • [prior-auth-review@healthcare] CMS Coverage  → https://...
    • [prior-auth-review@healthcare] ICD10 Codes   → https://...
    • [prior-auth-review@healthcare] NPI Registry  → https://...
    • [prior-auth-review@healthcare] PubMed        → https://...

Probing MCP server availability...
  ✅ cms_coverage
  ✅ icd10_codes
  ✅ npi_registry
  ✅ pubmed

Ready. Type your question below.
```

---

## Example Queries

**Provider lookup**
```
Look up NPI 1003000126
Search for cardiologists named Smith in Texas
```

**Diagnosis coding**
```
What ICD-10 code is used for community-acquired pneumonia?
Validate ICD-10 codes J18.9, E11.9, and Z87.891
```

**Medicare coverage**
```
What does Medicare cover for CT-guided lung biopsy?
What prior auth documentation does Medicare require for knee MRI?
```

**Full PA walkthrough** *(chains all three MCP servers)*
```
Walk me through a prior authorization request for:
  Member:    Jane Doe, DOB 05/14/1968
  Procedure: CT-guided transbronchial lung biopsy (CPT 32408)
  Diagnosis: R91.1 (solitary pulmonary nodule)
  Provider:  NPI 1003000126
```

---

## As a Python Library

```python
import anthropic
from healthcare_agent import HealthcareAgent
from healthcare_agent.registry import load_and_verify_servers

client      = anthropic.Anthropic(api_key="sk-ant-...")
mcp_servers = load_and_verify_servers(verbose=False)
agent       = HealthcareAgent(client, mcp_servers)

# Single query — Claude chains whatever MCP tools are needed
answer = agent.run("Walk me through a PA for CPT 32408, ICD R91.1, NPI 1003000126")

# Multi-turn conversation
history = []
a1 = agent.run("What ICD-10 code is used for community-acquired pneumonia?", history)
history += [{"role": "user", "content": "..."}, {"role": "assistant", "content": a1}]
a2 = agent.run("Is that code billable for FY 2025?", history)
```

---

## File Reference

| File | Purpose |
|------|---------|
| [`agent.py`](agent.py) | `HealthcareAgent` — single agent with MCP agentic loop |
| [`main.py`](main.py) | CLI entry point — startup, MCP probe, chat loop |
| [`registry.py`](registry.py) | MCP server discovery from Claude Code plugin registry |
| [`config.py`](config.py) | Model, token limit, API key loaded from `.env` |
| [`run_agent.py`](../run_agent.py) | Top-level runner script (avoids `-m` flag) |
| [`requirements.txt`](requirements.txt) | Python dependencies |
| [`.env.example`](.env.example) | Environment variable template |
| [`CLAUDE.md`](CLAUDE.md) | Project governance and coding rules |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Plugin registry not found` | Install Claude Code, then run `claude plugin install healthcare/fhir-developer` |
| `No MCP servers found` | Run `claude plugin install healthcare/fhir-developer` |
| `Unreachable MCP servers` | Check network; verify plugins are correctly installed |
| `ANTHROPIC_API_KEY not set` | Add key to `.env` |
| `anthropic` version error | `pip install anthropic --upgrade` (requires `>=0.50.0`) |
| `attempted relative import` | Run via `python run_agent.py`, not `python main.py` directly |
| Wrong conda environment | `conda activate payerai-gpt` before running |
