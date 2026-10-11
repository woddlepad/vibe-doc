"""Frozen grader: compares the submitted diagnosis with the correct one."""

from __future__ import annotations

import re

from .config import JUDGE_MODEL
from .llm import ask_json

JUDGE_SYSTEM = """You grade diagnoses from a clinical simulation against the answer key.

A prediction is CORRECT if it names the same condition as the answer key: synonyms,
abbreviations, eponyms and more specific subtypes of the key all count. It is NOT correct
if it is a broader category, a related but different condition, a complication, or a cause
of the key condition rather than the condition itself.

Also report the first position (1-based) in the differential that matches the key, or 0."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "correct": {"type": "boolean"},
        "differential_match": {"type": "integer"},
        "rationale": {"type": "string"},
    },
    "required": ["correct", "differential_match", "rationale"],
    "additionalProperties": False,
}


def normalize(s: str) -> str:
    s = s.lower().replace("'s", "")
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return " ".join(s.split())


def quick_match(pred: str | None, gold: str, aliases: tuple[str, ...] = ()) -> bool | None:
    """True on an exact normalized match, None when an LLM has to decide."""
    if not pred:
        return False
    p = normalize(pred)
    return True if any(p == normalize(g) for g in (gold, *aliases)) else None


def mentions(text: str, gold: str) -> bool:
    """Leak check: did a frozen role say the answer out loud?"""
    g = normalize(gold)
    return len(g) >= 5 and g in normalize(text)


async def grade(pred: str | None, differential: list[str], gold: str, aliases: tuple[str, ...] = ()) -> dict:
    quick = quick_match(pred, gold, aliases)
    if quick is not None:
        return {"correct": quick, "differential_match": 0, "rationale": "exact match" if quick else "no diagnosis submitted", "judge_cost_usd": 0.0}
    ddx = "\n".join(f"{i}. {d}" for i, d in enumerate(differential, 1)) or "(none)"
    prompt = f"Answer key: {gold}\n\nPredicted diagnosis: {pred}\n\nDifferential:\n{ddx}"
    verdict, cost = await ask_json(JUDGE_SYSTEM, prompt, JUDGE_SCHEMA, JUDGE_MODEL)
    return {**verdict, "judge_cost_usd": cost}
