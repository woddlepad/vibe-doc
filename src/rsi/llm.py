"""Thin wrappers over the Claude Agent SDK for the tool-less roles (patient, examiner, judge)."""

from __future__ import annotations

import asyncio
import tempfile
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    query,
)

# Empty working dir so no CLAUDE.md, skills or settings get picked up.
_ISOLATED_CWD = tempfile.mkdtemp(prefix="rsi-isolated-")


class LLMError(RuntimeError):
    pass


def _plain_options(system: str, model: str, **extra: Any) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=system,
        model=model,
        tools=[],
        setting_sources=[],
        skills=[],
        cwd=_ISOLATED_CWD,
        **extra,
    )


def _check(result: ResultMessage | None) -> ResultMessage:
    if result is None:
        raise LLMError("no result message from Claude Code")
    if result.is_error:
        detail = result.errors or result.result or result.subtype
        raise LLMError(f"Claude Code error ({result.api_error_status or result.subtype}): {detail}")
    return result


class Persona:
    """A multi-turn role-player backed by one long-lived Claude Code process."""

    def __init__(self, system: str, model: str, effort: str = "low"):
        self._options = _plain_options(system, model, max_turns=1, effort=effort)
        self._client: ClaudeSDKClient | None = None
        self._lock = asyncio.Lock()  # the doctor may call tools in parallel
        self.cost_usd = 0.0

    async def __aenter__(self) -> Persona:
        self._client = ClaudeSDKClient(self._options)
        await self._client.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.disconnect()

    async def say(self, text: str) -> str:
        assert self._client is not None, "use Persona as an async context manager"
        async with self._lock:
            await self._client.query(text)
            parts: list[str] = []
            result = None
            async for msg in self._client.receive_response():
                if isinstance(msg, AssistantMessage):
                    parts += [b.text for b in msg.content if isinstance(b, TextBlock)]
                elif isinstance(msg, ResultMessage):
                    result = msg
            result = _check(result)
            self.cost_usd += result.total_cost_usd or 0.0
            return "".join(parts).strip()


async def ask_json(system: str, prompt: str, schema: dict, model: str, effort: str = "low") -> tuple[dict, float]:
    """One-shot structured answer. Returns (object, cost_usd)."""
    options = _plain_options(
        system,
        model,
        max_turns=4,
        effort=effort,
        output_format={"type": "json_schema", "schema": schema},
    )
    result = None
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, ResultMessage):
            result = msg
    result = _check(result)
    if not isinstance(result.structured_output, dict):
        raise LLMError(f"expected structured output, got: {result.result!r}")
    return result.structured_output, result.total_cost_usd or 0.0
