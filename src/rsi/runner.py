"""Runs diagnosis episodes: doctor harness vs. simulated patient, then the judge."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import sys
import time
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from .cases import SOURCE, Case
from .clinic import CLINIC_TOOLS, TOOL_PREFIX, Budget, Episode, build_clinic_server, examiner_system, patient_system
from .config import EXAMINER_MODEL, JUDGE_MODEL, PATIENT_MODEL, RUNS
from .harness import Harness
from .judge import grade, mentions
from .llm import Persona
from .stats import wilson

CACHE = RUNS / "cache"
EPISODE_TIMEOUT_S = 20 * 60


@cache
def env_digest() -> str:
    """Identity of the frozen environment: role models, simulator and grader code, case data."""
    here = Path(__file__).parent
    h = hashlib.sha256()
    for part in (PATIENT_MODEL, EXAMINER_MODEL, JUDGE_MODEL, (here / "clinic.py").read_text(), (here / "judge.py").read_text()):
        h.update(part.encode() + b"\0")
    h.update(hashlib.sha256(SOURCE.read_bytes()).hexdigest().encode())
    return h.hexdigest()[:12]


def _doctor_options(harness: Harness, staged: Path, server) -> ClaudeAgentOptions:
    cfg = harness.config
    builtins = list(cfg["builtin_tools"])
    if harness.has_skills and "Skill" not in builtins:
        builtins.append("Skill")
    clinic = [TOOL_PREFIX + t for t in CLINIC_TOOLS]
    return ClaudeAgentOptions(
        system_prompt=harness.system_prompt(),
        model=cfg["model"],
        effort=cfg["effort"],
        max_turns=cfg["max_turns"],
        tools=builtins,
        allowed_tools=clinic + builtins,
        mcp_servers={"clinic": server},
        strict_mcp_config=True,
        setting_sources=["project"],  # loads .claude/skills from the staged harness
        skills="all" if harness.has_skills else [],
        permission_mode="dontAsk",  # anything not explicitly allowed is denied
        cwd=staged,
    )


def _fallback_diagnosis(text: str) -> str | None:
    m = re.search(r"DIAGNOSIS\s*[:\-]\s*(.+)", text, re.IGNORECASE)
    return m.group(1).strip().strip("*") if m else None


async def run_episode(harness: Harness, case: Case, verbose: bool = False) -> dict:
    cfg = harness.config
    ep = Episode(case=case, budget=Budget(cfg["max_questions"], cfg["max_requests"]))
    staged = harness.stage()
    result_msg: ResultMessage | None = None
    last_text = ""
    try:
        async with Persona(patient_system(case), PATIENT_MODEL) as patient, Persona(
            examiner_system(case), EXAMINER_MODEL
        ) as examiner:
            server = build_clinic_server(ep, patient, examiner)
            prompt = (
                "A new patient has arrived.\n"
                f"Reason for visit: {case.objective}\n\n"
                "Conduct the consultation with your clinic tools, then call submit_diagnosis."
            )
            async for msg in query(prompt=prompt, options=_doctor_options(harness, staged, server)):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock) and block.text.strip():
                            last_text = block.text
                            ep.log("doctor_note", text=block.text.strip())
                        elif isinstance(block, ToolUseBlock) and not block.name.startswith(TOOL_PREFIX):
                            ep.log("builtin_tool", name=block.name, input=block.input)
                    if verbose and ep.events:
                        _print_event(ep.events[-1])
                elif isinstance(msg, ResultMessage):
                    result_msg = msg
            persona_cost = patient.cost_usd + examiner.cost_usd
    finally:
        shutil.rmtree(staged, ignore_errors=True)

    if result_msg is not None and result_msg.is_error and not ep.submitted:
        raise RuntimeError(f"doctor run failed: {result_msg.subtype} {result_msg.errors or result_msg.result}")
    if not ep.submitted:
        ep.diagnosis = _fallback_diagnosis(last_text)
        if ep.diagnosis:
            ep.log("fallback_diagnosis", diagnosis=ep.diagnosis)

    spoken = " ".join(e.get("answer", "") + " " + e.get("result", "") for e in ep.events)
    leak = mentions(spoken, case.diagnosis, case.aliases)
    if leak:  # a frozen role gave the answer away: never credit it, and don't pay the judge
        verdict = {"correct": False, "differential_match": 0, "rationale": "simulator leak", "judge_cost_usd": 0.0}
    else:
        verdict = await grade(ep.diagnosis, ep.differential, case.diagnosis, case.aliases)
    return {
        "case_id": case.id,
        "harness": harness.name,
        "digest": harness.digest,
        "env_digest": env_digest(),
        "gold": case.diagnosis,
        "diagnosis": ep.diagnosis,
        "differential": ep.differential,
        "reasoning": ep.reasoning,
        "submitted_via_tool": any(e["kind"] == "submit_diagnosis" for e in ep.events),
        "correct": bool(verdict["correct"]),
        "differential_match": verdict["differential_match"],
        "judge_rationale": verdict["rationale"],
        "questions": ep.questions,
        "requests": ep.requests,
        "leak": leak,
        "num_turns": result_msg.num_turns if result_msg else None,
        "duration_s": round(time.time() - ep.started, 1),
        "cost_usd": round(
            ((result_msg.total_cost_usd or 0.0) if result_msg else 0.0) + persona_cost + verdict["judge_cost_usd"], 4
        ),
        "objective": case.objective,
        "events": ep.events,
    }


def _print_event(e: dict) -> None:
    k = e["kind"]
    if k == "ask_patient":
        print(f"  Dr: {e['question']}\n  Pt: {e['answer']}")
    elif k in ("examine", "order_test"):
        print(f"  [{k}] {e['request']}\n    {e['result']}")
    elif k == "submit_diagnosis":
        print(f"  => DIAGNOSIS: {e['diagnosis']}  (ddx: {', '.join(e['differential'])})")
    elif k == "doctor_note":
        print(f"  (doctor) {e['text'][:300]}")


@dataclass
class EvalResult:
    harness: str
    label: str
    results: list[dict]
    out_dir: Path
    env_digest: str = ""

    @property
    def scored(self) -> list[dict]:
        return [r for r in self.results if "error" not in r]

    def outcomes(self) -> dict[str, int]:
        return {r["case_id"]: int(r["correct"]) for r in self.scored}

    def summary(self) -> dict:
        s = self.scored
        k = sum(r["correct"] for r in s)
        lo, hi = wilson(k, len(s))
        mean = lambda key: round(sum(r[key] for r in s) / len(s), 2) if s else 0.0  # noqa: E731
        return {
            "harness": self.harness,
            "label": self.label,
            "env_digest": self.env_digest,
            "n": len(self.results),
            "scored": len(s),
            "errors": len(self.results) - len(s),
            "correct": k,
            "accuracy": round(k / len(s), 4) if s else 0.0,
            "ci95": [round(lo, 4), round(hi, 4)],
            "in_top3_differential": sum(1 for r in s if r["correct"] or 1 <= r["differential_match"] <= 2),
            "no_diagnosis": sum(1 for r in s if not r["diagnosis"]),
            "leaks": sum(1 for r in s if r["leak"]),
            "mean_questions": mean("questions"),
            "mean_requests": mean("requests"),
            "mean_duration_s": mean("duration_s"),
            "total_cost_usd": round(sum(r["cost_usd"] for r in s), 2),
        }


async def run_eval(
    harness: Harness,
    cases: list[Case],
    label: str,
    concurrency: int = 4,
    use_cache: bool = True,
    quiet: bool = False,
) -> EvalResult:
    """Run every case once (reusing cached episodes for an identical harness and environment) and save the results."""
    env = env_digest()
    cache_dir = CACHE / f"{harness.digest}-{env}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(concurrency)
    done = 0

    async def one(case: Case) -> dict:
        nonlocal done
        cached = cache_dir / f"{case.id}.json"
        if use_cache and cached.exists():
            r = json.loads(cached.read_text())
        else:
            async with sem:
                r = None
                for attempt in (1, 2):
                    try:
                        r = await asyncio.wait_for(run_episode(harness, case), EPISODE_TIMEOUT_S)
                        break
                    except Exception as e:  # noqa: BLE001 - one bad episode must not sink the eval
                        r = {"case_id": case.id, "harness": harness.name, "error": f"{type(e).__name__}: {e}"}
                        if attempt == 1:
                            await asyncio.sleep(5)
                if "error" not in r and not r["leak"]:  # leaked episodes rerun next time
                    cached.write_text(json.dumps(r, indent=1))
        done += 1
        if not quiet:
            mark = "ERR" if "error" in r else ("ok " if r["correct"] else "x  ")
            detail = r.get("error") or f"{r['diagnosis']!s:.60}  [gold: {r['gold']}]"
            print(f"[{done:>3}/{len(cases)}] {mark} {case.id}  {detail}", file=sys.stderr, flush=True)
        return r

    results = await asyncio.gather(*(one(c) for c in cases))
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = RUNS / "evals" / f"{stamp}-{harness.name}-{label}"
    out_dir.mkdir(parents=True, exist_ok=True)
    ev = EvalResult(harness=harness.name, label=label, results=list(results), out_dir=out_dir, env_digest=env)
    with (out_dir / "results.jsonl").open("w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    (out_dir / "summary.json").write_text(json.dumps(ev.summary(), indent=1) + "\n")
    return ev
