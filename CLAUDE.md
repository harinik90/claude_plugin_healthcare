# CLAUDE.md — Project Rules for claude_healthcare

## MCP Server URL Policy

**MCP server URLs MUST NEVER be hardcoded in source code.**

All MCP server endpoints used by this project are provided by Claude Code plugins
installed on this machine. The code must discover them at runtime by reading
Claude Code's plugin registry:

```
~/.claude/plugins/installed_plugins.json       ← registry of installed plugins
~/.claude/plugins/cache/<marketplace>/<plugin>/<sha>/
    <subpackage>/.claude-plugin/plugin.json    ← per-package MCP server definitions
```

The function `load_plugin_mcp_servers()` in [pa_chatbot.py](pa_chatbot.py) is the
single, authoritative place where MCP servers are discovered. It must:

1. Read `installed_plugins.json` to find every installed plugin's `installPath`.
2. Walk each `installPath` recursively for `.claude-plugin/plugin.json` files.
3. Extract the `mcpServers` block from each file.
4. Return those servers to the caller — no filtering, no overrides.

**Rationale:** Plugins are the source of truth for which MCP servers are available
and what their URLs are. If a plugin is updated or replaced, the code automatically
picks up the new endpoint without any code change. Hardcoding URLs bypasses this
infrastructure and creates drift between what is installed and what the code uses.

### Enforcement

- Do not add MCP server URL constants to any source file in this project.
- Do not add MCP server URLs to `.env` or any config file.
- If `load_plugin_mcp_servers()` returns no servers, exit with a clear error
  telling the user to install the required plugin.
- If any plugin-registered MCP server fails the startup availability probe,
  exit with a clear error — do not continue with partial MCP coverage.
- There is no REST API fallback. All data must come through plugin-registered
  MCP servers. Removing this requirement requires an explicit project decision
  documented here in CLAUDE.md.

---

## Required Claude Code Plugins

This project depends on the following plugins being installed in Claude Code:

| Plugin | Provides | Install command |
|--------|----------|-----------------|
| `healthcare/fhir-developer` | NPI Registry MCP, ICD-10 Codes MCP, CMS Coverage MCP | `claude plugin install healthcare/fhir-developer` |
| `healthcare/prior-auth-review` | Prior Auth skill & sample data | `claude plugin install healthcare/prior-auth-review` |

---

## Python Environment

**Required conda environment: `payerai-gpt`**

All development, testing, and execution of this project must use the
`payerai-gpt` conda environment. Do not run the chatbot in the base
environment or any other virtual environment.

### First-time setup

```bash
# Activate the required environment
conda activate payerai-gpt

# Install dependencies into payerai-gpt
pip install -r requirements.txt
```

### Running the Chatbot

```bash
conda activate payerai-gpt
cd claude_healthcare
python pa_chatbot.py
```

The chatbot will print which MCP servers it discovered from the plugin registry
and confirm their availability before starting the chat loop.

### Environment Enforcement

- Always verify the active environment before running: `conda info --envs`
- If `payerai-gpt` does not exist, create it first:
  ```bash
  conda create -n payerai-gpt python=3.11
  conda activate payerai-gpt
  pip install -r requirements.txt
  ```
- Do not add a `conda activate` call inside `pa_chatbot.py` — environment
  activation is the caller's responsibility, not the script's.
