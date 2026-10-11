"""Paths, model choices and the environment handed to Claude Code subprocesses."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
HARNESSES = ROOT / "harnesses"
RUNS = ROOT / "runs"
REGISTRY = HARNESSES / "registry.json"

# Frozen roles. The optimizer never sees or edits these.
PATIENT_MODEL = os.environ.get("RSI_PATIENT_MODEL", "claude-haiku-5-5")
EXAMINER_MODEL = os.environ.get("RSI_EXAMINER_MODEL", "claude-haiku-5-5")
JUDGE_MODEL = os.environ.get("RSI_JUDGE_MODEL", "claude-sonnet-5-5")
# The meta-agent that rewrites the doctor harness.
OPTIMIZER_MODEL = os.environ.get("RSI_OPTIMIZER_MODEL", "claude-opus-5-5")

# Variables set by a parent Claude Code session that must not leak into ours.
_KEEP = {"CLAUDE_CODE_OAUTH_TOKEN"}


def load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ[key.strip()] = value.strip().strip("'\"")


def prepare_environment() -> None:
    """Load .env and scrub inherited state so Claude Code uses the subscription token."""
    load_dotenv()
    for key in list(os.environ):
        if key in _KEEP:
            continue
        inherited_session = key.startswith("CLAUDE_CODE_") or key in {"CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT"}
        empty_provider = key.startswith("ANTHROPIC_") and not os.environ[key]
        if inherited_session or empty_provider:
            del os.environ[key]
    # Subscription auth wins only if no API key is present.
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") and os.environ.get("RSI_PREFER_SUBSCRIPTION", "1") == "1":
        for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            os.environ.pop(key, None)
