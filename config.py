"""
Agent configuration — loads from environment / .env

Precedence (first match wins):
  1. healthcare_agent/.env       — package-level config (recommended)
  2. ../.env                     — parent project root fallback
  3. Shell environment variables
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

_pkg_dir = os.path.dirname(__file__)

# Load package-level .env first; fall back to parent project root
load_dotenv(dotenv_path=os.path.join(_pkg_dir, ".env"))
load_dotenv(dotenv_path=os.path.join(_pkg_dir, "..", ".env"))

# Force UTF-8 on Windows consoles
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure") and getattr(_stream, "encoding", "utf-8").lower() != "utf-8":
        _stream.reconfigure(encoding="utf-8", errors="replace")

# ── API ───────────────────────────────────────────────────────────────────────
API_KEY             = os.environ.get("ANTHROPIC_API_KEY",         "")

# ── Models ────────────────────────────────────────────────────────────────────
# Orchestrator: routes queries and synthesises specialist answers
ORCHESTRATOR_MODEL  = os.environ.get("CLAUDE_ORCHESTRATOR_MODEL", "claude-sonnet-4-6")

# Specialists: NPI, ICD-10, CMS domain agents
SPECIALIST_MODEL    = os.environ.get("CLAUDE_SPECIALIST_MODEL",   "claude-sonnet-4-6")

# PA agent: full prior-auth workflow — multi-step clinical reasoning
PA_MODEL            = os.environ.get("CLAUDE_PA_MODEL",           "claude-sonnet-4-6")

# ── Token limits ──────────────────────────────────────────────────────────────
MAX_TOKENS          = int(os.environ.get("CLAUDE_MAX_TOKENS",     "4096"))

# ── Parallel execution ────────────────────────────────────────────────────────
MAX_PARALLEL_AGENTS = int(os.environ.get("MAX_PARALLEL_AGENTS",  "4"))

# ── MCP probe ─────────────────────────────────────────────────────────────────
MCP_PROBE_TIMEOUT   = int(os.environ.get("MCP_PROBE_TIMEOUT",    "5"))
