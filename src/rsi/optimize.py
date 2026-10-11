"""Outer loop: study train failures, let a Claude Code meta-agent edit the harness, gate on dev."""

from __future__ import annotations

import asyncio
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher, ResultMessage, query

from .cases import split_cases
from .config import HARNESSES, OPTIMIZER_MODEL, REGISTRY, ROOT, RUNS
from .harness import BUILTIN_WHITELIST, CONFIG_DEFAULTS, Harness, diff, is_editable
from .runner import EvalResult, run_eval
from .stats import paired_bootstrap

MAX_PROMPT_CHARS = 16_000  # system.md + lessons.md, keeps the harness from bloating
MAX_COST_RATIO = 1.5  # a candidate costing more than this x the parent on dev is discarded
DEFAULT_EPISODE_S = 120.0  # episode duration guess until the parent's dev eval has measured one

# ---------------------------------------------------------------- registry


def load_registry() -> dict:
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text())
    base = Harness.load("v000")
    reg = {
        "best": "v000",
        "locked_model": base.config["model"],
        "versions": [{"name": "v000", "parent": None, "created": time.strftime("%F %T"), "hypothesis": "baseline"}],
        "rejected": [],
    }
    save_registry(reg)
    return reg


def save_registry(reg: dict) -> None:
    REGISTRY.write_text(json.dumps(reg, indent=1) + "\n")


def _version(reg: dict, name: str) -> dict:
    return next(v for v in reg["versions"] if v["name"] == name)


def record_eval(reg: dict, name: str, ev: EvalResult, split: str) -> None:
    for v in reg["versions"]:
        if v["name"] == name:
            v[split] = ev.summary() | {"run": str(ev.out_dir.relative_to(ROOT))}
    save_registry(reg)


# ---------------------------------------------------------------- evidence for the optimizer


def _transcript(r: dict) -> str:
    lines = []
    for e in r["events"]:
        k = e["kind"]
        if k == "ask_patient":
            lines += [f"**Doctor:** {e['question']}", f"**Patient:** {e['answer']}"]
        elif k in ("examine", "order_test"):
            lines.append(f"**[{k}]** {e['request']} → {e['result']}")
        elif k == "lookup":
            lines.append(f"**[lookup]** {e['query']} → " + "; ".join(r["title"] for r in e["results"]))
        elif k == "doctor_note":
            lines.append(f"_(doctor's own note)_ {e['text']}")
        elif k == "builtin_tool":
            lines.append(f"_(used {e['name']})_ {json.dumps(e['input'])[:300]}")
        elif k == "submit_diagnosis":
            lines.append(f"**Submitted:** {e['diagnosis']} | differential: {', '.join(e['differential']) or '-'}")
            if e.get("reasoning"):
                lines.append(f"Reasoning: {e['reasoning']}")
    return "\n\n".join(lines)


def _failure_md(r: dict, case) -> str:
    cfg_q = f"{r['questions']} questions, {r['requests']} exam/test requests"
    return f"""# {r['case_id']}: WRONG

- Reason for visit: {r['objective']}
- **Correct diagnosis: {r['gold']}**
- Submitted: {r['diagnosis'] or '(none)'}
- Differential: {', '.join(r['differential']) or '-'}
- Judge: {r['judge_rationale']}
- Used: {cfg_q}

## Transcript

{_transcript(r)}

## Hidden case file (what the doctor could have uncovered)

Patient script:
```json
{json.dumps(case.patient, indent=1)}
```
Exam findings:
```json
{json.dumps(case.exam, indent=1)}
```
Test results:
```json
{json.dumps(case.tests, indent=1)}
```
"""


def write_evidence(dest: Path, train: EvalResult, reg: dict, parent: str) -> None:
    from .cases import all_cases

    cases = all_cases()
    fail_dir = dest / "failures"
    fail_dir.mkdir(parents=True)
    scored = train.scored
    fails = [r for r in scored if not r["correct"]]
    oks = [r for r in scored if r["correct"]]
    for r in fails:
        (fail_dir / f"{r['case_id']}.md").write_text(_failure_md(r, cases[r["case_id"]]))

    def avg(rs, key):
        return round(sum(x[key] for x in rs) / len(rs), 1) if rs else "-"

    s = train.summary()
    (dest / "README.md").write_text(
        f"""# Evidence for improving harness {parent}

Train batch: {s['scored']} cases, {s['correct']} correct ({s['accuracy']:.0%}).

| | correct | wrong |
|---|---|---|
| cases | {len(oks)} | {len(fails)} |
| mean questions | {avg(oks, 'questions')} | {avg(fails, 'questions')} |
| mean exam/test requests | {avg(oks, 'requests')} | {avg(fails, 'requests')} |
| no diagnosis submitted | - | {sum(1 for r in fails if not r['diagnosis'])} |

## Wrong answers (one file each in failures/)

"""
        + "\n".join(f"- {r['case_id']}: said **{r['diagnosis'] or '(none)'}**, correct **{r['gold']}**" for r in fails)
        + "\n\n## Correct answers\n\n"
        + "\n".join(f"- {r['case_id']}: {r['gold']} ({r['questions']} q, {r['requests']} req)" for r in oks)
        + "\n"
    )
    (dest / "history.md").write_text(_history_md(reg))


def _history_md(reg: dict) -> str:
    out = ["# Previous attempts\n"]
    for v in reg["versions"]:
        dev = v.get("dev", {})
        out.append(f"- ACCEPTED {v['name']} (parent {v['parent']}), dev {dev.get('accuracy', '?')}: {v.get('hypothesis', '')}")
    for r in reg["rejected"]:
        out.append(f"- REJECTED {r['id']} (parent {r['parent']}), dev {r.get('dev_accuracy', '?')}: {r.get('hypothesis', '')} [{r['reason']}]")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- the meta-agent

OPTIMIZER_SYSTEM = """You improve an AI doctor's harness: the prompts, skills and settings that steer
a language model through a simulated clinical consultation. You edit files; you never run the doctor.
Work like a careful ML engineer: read the evidence, find the most common fixable failure pattern,
make one focused change that should generalize to unseen patients, and explain it."""

TASK = """# Task

Improve the doctor harness in `harness/` so it diagnoses more unseen patients correctly.

## How the doctor runs

Each consultation, the doctor model ({model}) gets `harness/system.md` + `harness/lessons.md` as its
system prompt, plus the reason for the visit. Its only clinic tools are:
- `ask_patient(question)`: a simulated patient answers in lay terms, only what is asked
- `examine(exam)` / `order_test(test)`: returns findings; anything not in the case file comes back normal
- `submit_diagnosis(diagnosis, differential, reasoning)`: ends the consultation
- `lookup(query)`: only when `max_lookups` > 0. Searches trusted medical references only
  (StatPearls, PubMed, Merck, MedlinePlus, ...) and returns top results with highlights. Results are
  checked against the case file and any match disqualifies the episode, so use it to look up
  differentials/discriminating features, not to find the case.

Scoring: the single submitted diagnosis must match the answer key (synonyms are fine, a broader
category is wrong). Cases are USMLE-style vignettes across all specialties.

## What you may change (everything else is rejected)

- `harness/system.md`: the doctor's core instructions
- `harness/lessons.md`: distilled, general lessons from past failures
- `harness/config.json`: keys {config_keys}. `model` is locked to {model}.
  Ranges: max_questions 3-40, max_requests 0-30, max_turns 10-150, max_lookups 0-10 (needs EXA_API_KEY);
  effort one of low/medium/high/xhigh/max.
  `builtin_tools` may only contain {whitelist}.
- `harness/.claude/skills/<name>/SKILL.md`: Claude Code skills the doctor can load on demand
  (frontmatter with only `name` and `description`, then plain instructions). Good for specialty
  workups. One SKILL.md per skill folder and no other files; other frontmatter keys are rejected.

Keep system.md + lessons.md under {max_chars} characters total.

## Evidence (read-only)

- `evidence/README.md`: train-batch results for the current harness
- `evidence/failures/*.md`: every wrong case with the full transcript and the hidden case file
- `evidence/history.md`: earlier accepted and rejected changes; do not repeat rejected ideas

## Rules

- Your change is accepted only if accuracy improves on held-out patients you never see. Do not
  memorize these cases' diagnoses; fix the reasoning or interviewing behaviour that caused them.
- Prefer one coherent hypothesis per round over many scattered tweaks.
- When done, reply with the hypothesis, the files you changed, and the effect you expect.
"""

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "hypothesis": {"type": "string", "description": "The failure pattern and why the change fixes it"},
        "changes": {"type": "array", "items": {"type": "string"}},
        "expected_effect": {"type": "string"},
    },
    "required": ["hypothesis", "changes", "expected_effect"],
}


_PAYLOAD_KEYS = {"content", "old_string", "new_string"}  # file text, not paths


def _guard(ws: Path):
    """PreToolUse hook: reads stay inside the workspace, writes stay inside editable harness files."""
    ws = ws.resolve()
    harness_dir = ws / "harness"

    def deny(reason: str) -> dict:
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}

    def resolve(raw: str) -> Path:
        p = Path(raw)
        return (p if p.is_absolute() else ws / p).resolve()

    async def hook(input_data: dict, tool_use_id, context) -> dict:
        name = input_data.get("tool_name", "")
        args = input_data.get("tool_input", {}) or {}
        p = resolve(args.get("file_path") or args.get("path") or str(ws))
        if not p.is_relative_to(ws):
            return deny(f"{p} is outside the workspace {ws}")
        for key in ("pattern", "glob") if name == "Glob" else ("glob",):
            g = args.get(key)
            if isinstance(g, str) and (g.startswith(("/", "~")) or ".." in g.replace("\\", "/").split("/")):
                return deny(f"{key} must be relative and stay inside the workspace {ws}")
        for key in ("file_path", "path"):
            if isinstance(args.get(key), str) and args[key].startswith("~"):
                return deny(f"{key} must not start with ~; use a path inside the workspace {ws}")
        for key, v in args.items():
            if key == "pattern" and name == "Grep":
                continue  # a regex, not a path
            if key not in _PAYLOAD_KEYS and isinstance(v, str) and v.startswith("/") and not resolve(v).is_relative_to(ws):
                return deny(f"{v} is outside the workspace {ws}")
        if name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            if not p.is_relative_to(harness_dir) or not is_editable(p.relative_to(harness_dir).as_posix()):
                return deny("You may only edit harness/system.md, harness/lessons.md, harness/config.json and harness/.claude/skills/<name>/SKILL.md")
        return {}

    return hook


async def propose(ws: Path, locked_model: str) -> dict:
    tools = ["Read", "Write", "Edit", "Glob", "Grep"]
    task = TASK.format(
        model=locked_model,
        config_keys=", ".join(CONFIG_DEFAULTS),
        whitelist=sorted(BUILTIN_WHITELIST),
        max_chars=MAX_PROMPT_CHARS,
    )
    (ws / "TASK.md").write_text(task)
    options = ClaudeAgentOptions(
        system_prompt=OPTIMIZER_SYSTEM,
        model=OPTIMIZER_MODEL,
        effort="high",
        cwd=ws,
        tools=tools,
        allowed_tools=tools,
        permission_mode="dontAsk",
        setting_sources=[],
        skills=[],
        max_turns=80,
        hooks={"PreToolUse": [HookMatcher(matcher="|".join(tools), hooks=[_guard(ws)])]},
        output_format={"type": "json_schema", "schema": RESULT_SCHEMA},
    )
    result = None
    async for msg in query(prompt=task + "\n\nStart by reading evidence/README.md.", options=options):
        if isinstance(msg, ResultMessage):
            result = msg
    if result is None or result.is_error:
        raise RuntimeError(f"optimizer failed: {result and (result.errors or result.result)}")
    out = result.structured_output if isinstance(result.structured_output, dict) else {"hypothesis": result.result or "", "changes": [], "expected_effect": ""}
    out["cost_usd"] = result.total_cost_usd or 0.0
    return out


def _check_candidate(cand: Harness, parent: Harness, locked_model: str) -> list[str]:
    problems = cand.validate(locked_model=locked_model)
    size = len(cand.system_prompt())
    if size > MAX_PROMPT_CHARS + 200:
        problems.append(f"system.md + lessons.md is {size} chars (limit {MAX_PROMPT_CHARS})")
    if not diff(parent, cand):
        problems.append("no changes")
    if cand.config.get("max_lookups") and not os.environ.get("EXA_API_KEY"):
        problems.append("max_lookups > 0 needs EXA_API_KEY, which is not set")
    return problems


# ---------------------------------------------------------------- the loop


def _next_name(reg: dict) -> str:
    return f"v{max(int(v['name'][1:]) for v in reg['versions']) + 1:03d}"


def _git_commit(name: str, message: str) -> None:
    subprocess.run(["git", "add", "harnesses"], cwd=ROOT, check=True)
    subprocess.run(["git", "commit", "-q", "-m", f"harness {name}: {message[:200]}"], cwd=ROOT, check=True)
    subprocess.run(["git", "tag", f"harness-{name}"], cwd=ROOT, check=True)


def _log(msg: str) -> None:
    print(f"\n== {msg}", file=sys.stderr, flush=True)


def _clock(ts: float) -> str:
    return time.strftime("%H:%M", time.localtime(ts))


def _too_costly(parent: dict, cand: dict, max_slowdown: float) -> str | None:
    pd, cd, pc, cc = parent["mean_duration_s"], cand["mean_duration_s"], parent["total_cost_usd"], cand["total_cost_usd"]
    if (pd and cd > max_slowdown * pd) or (pc and cc > MAX_COST_RATIO * pc):
        return f"too slow/expensive: {cd:.0f}s vs {pd:.0f}s per episode (max x{max_slowdown}), ${cc:.2f} vs ${pc:.2f} total (max x{MAX_COST_RATIO})"
    return None


async def _dev_gate(
    cand: Harness, dev: list, screen_ids: list[str], parent_screen: int, t: float, concurrency: int, deadline: float | None, base: dict
) -> tuple[str | None, EvalResult | None]:
    """Screen on the first dev cases, then run the full dev set (screen episodes come from the cache)."""
    n = len(screen_ids)
    if n:
        ev = await run_eval(cand, dev[:n], "screen", concurrency)
        if ev.summary()["errors"]:
            return f"eval incomplete: {ev.summary()['errors']} errors", None
        cs = sum(ev.outcomes().values())
        base["screen"] = {"n": n, "parent": parent_screen, "candidate": cs}
        _log(f"{cand.name}: screen {cs}/{n} vs parent {parent_screen}/{n}")
        if cs < parent_screen - 1:
            return f"screened out: {cs}/{n} vs parent {parent_screen}/{n}", None
    est = (len(dev) - n) * t / concurrency
    if deadline and time.time() + est > deadline:
        return "deadline", None
    _log(f"{cand.name}: full dev, est. {est / 60:.0f} min, projected finish {_clock(time.time() + est)}")
    return None, await run_eval(cand, dev, "dev", concurrency)


async def improve(
    generations: int = 3,
    train_batch: int = 30,
    dev_limit: int | None = None,
    candidates: int = 1,
    concurrency: int = 4,
    min_confidence: float = 0.75,
    commit: bool = False,
    screen: int = 10,
    max_slowdown: float = 1.5,
    min_gain: int = 1,
    deadline: float | None = None,
) -> None:
    reg = load_registry()
    if Harness.load(reg["best"]).config["max_lookups"] and not os.environ.get("EXA_API_KEY"):
        sys.exit(f"{reg['best']} has max_lookups > 0 but EXA_API_KEY is not set (.env)")
    dev = split_cases("dev", dev_limit)
    train_all = split_cases("train")
    session = time.strftime("%Y%m%d-%H%M%S")
    screen_ids = [c.id for c in dev[:max(0, screen)]]
    optimizer_s = 0.0  # measured wall time of the last optimizer round
    if deadline:
        _log(f"deadline {time.strftime('%F %H:%M', time.localtime(deadline))} ({(deadline - time.time()) / 60:.0f} min from now)")

    for gen in range(1, generations + 1):
        parent = Harness.load(reg["best"])
        t = _version(reg, parent.name).get("dev", {}).get("mean_duration_s") or DEFAULT_EPISODE_S
        # train batch + every candidate's screen and rest of dev (= the full dev set), plus the optimizer
        est = (min(train_batch, len(train_all)) + candidates * len(dev)) * t / concurrency + optimizer_s
        now = time.time()
        if deadline and now + est > deadline:
            _log(f"deadline: skipping generation {gen} (est. {est / 60:.0f} min, {(deadline - now) / 60:.0f} min left)")
            break
        _log(f"generation {gen}/{generations}: parent {parent.name}, est. {est / 60:.0f} min, projected finish {_clock(now + est)}")

        parent_dev = await run_eval(parent, dev, "dev", concurrency)
        record_eval(reg, parent.name, parent_dev, "dev")
        ps = parent_dev.summary()
        if ps["errors"] or not ps["scored"]:
            raise SystemExit(
                f"{parent.name} dev eval incomplete: {ps['errors']} errors, {ps['scored']} scored "
                f"(see {parent_dev.out_dir}). Fix the cause and rerun; finished episodes are cached."
            )
        t = ps["mean_duration_s"] or t
        parent_screen = sum(parent_dev.outcomes()[i] for i in screen_ids)
        rng = random.Random(f"{session}:{gen}")
        batch = rng.sample(train_all, min(train_batch, len(train_all)))
        train = await run_eval(parent, batch, f"train-g{gen}", concurrency)
        s = train.summary()
        _log(f"{parent.name}: dev {parent_dev.summary()['accuracy']:.0%}, train batch {s['accuracy']:.0%} ({s['scored'] - s['correct']} failures)")

        workspaces = []
        for k in range(1, candidates + 1):
            ws = RUNS / "improve" / session / f"gen{gen}-cand{k}"
            shutil.copytree(parent.path, ws / "harness")
            write_evidence(ws / "evidence", train, reg, parent.name)
            workspaces.append(ws)

        _log(f"optimizer ({OPTIMIZER_MODEL}) writing {candidates} candidate(s)")
        started = time.time()
        proposals = await asyncio.gather(*(propose(ws, reg["locked_model"]) for ws in workspaces), return_exceptions=True)
        optimizer_s = time.time() - started

        best: tuple[float, Path, dict, EvalResult] | None = None
        for ws, prop in zip(workspaces, proposals, strict=True):
            cid = f"{session}/{ws.name}"
            if isinstance(prop, BaseException):
                reg["rejected"].append({"id": cid, "parent": parent.name, "reason": f"optimizer error: {prop}"})
                save_registry(reg)
                continue
            base = {"id": cid, "parent": parent.name, "hypothesis": prop.get("hypothesis", "")}
            try:  # one malformed candidate must not sink the generation
                (ws / "proposal.json").write_text(json.dumps(prop, indent=1))
                cand = Harness(name=f"cand-{ws.name}", path=ws / "harness")
                (ws / "diff.patch").write_text(diff(parent, cand))
                _log(f"{ws.name}: {base['hypothesis'][:300]}")
                problems = _check_candidate(cand, parent, reg["locked_model"])
                if problems:
                    reason, cand_dev = "invalid: " + "; ".join(problems), None
                else:
                    reason, cand_dev = await _dev_gate(cand, dev, screen_ids, parent_screen, t, concurrency, deadline, base)
            except Exception as e:  # noqa: BLE001
                reason, cand_dev = f"invalid: candidate error: {type(e).__name__}: {e}", None
            # Compare on the full dev set only: a survivor subset would reward failing on hard cases.
            if reason is None and cand_dev.summary()["errors"]:
                reason = f"eval incomplete: {cand_dev.summary()['errors']} errors"
            if reason:
                reg["rejected"].append(base | {"reason": reason})
                save_registry(reg)
                _log(f"{ws.name} rejected: {reason}")
                continue

            a, b = parent_dev.outcomes(), cand_dev.outcomes()
            shared = sorted(set(a) & set(b))
            pa, pb = [a[i] for i in shared], [b[i] for i in shared]
            conf = paired_bootstrap(pa, pb)
            acc_a, acc_b = sum(pa) / max(1, len(shared)), sum(pb) / max(1, len(shared))
            gain = sum(pb) - sum(pa)
            entry = {
                "id": cid,
                "parent": parent.name,
                "hypothesis": base["hypothesis"],
                "changes": prop.get("changes", []),
                "dev_accuracy": round(acc_b, 4),
                "parent_dev_accuracy": round(acc_a, 4),
                "confidence": round(conf, 3),
                "paired_n": len(shared),
                "gain": gain,
                "diff": str((ws / "diff.patch").relative_to(ROOT)),
            } | ({"screen": base["screen"]} if "screen" in base else {})
            cs = cand_dev.summary()
            _log(
                f"{ws.name}: dev {acc_a:.0%} -> {acc_b:.0%} ({gain:+d}) on {len(shared)} paired cases, P(better)={conf:.2f}; "
                f"{cs['mean_duration_s']:.0f}s vs {ps['mean_duration_s']:.0f}s per episode, ${cs['total_cost_usd']:.2f} vs ${ps['total_cost_usd']:.2f}"
            )
            if not (acc_b > acc_a and conf >= min_confidence and gain >= min_gain):
                reason = f"not clearly better: {gain:+d} correct (need +{min_gain}), P(better)={conf:.2f} (need {min_confidence})"
            else:
                reason = _too_costly(ps, cs, max_slowdown)
            if reason:
                reg["rejected"].append(entry | {"reason": reason})
                _log(f"{ws.name} rejected: {reason}")
            elif best is None or acc_b > best[0]:
                if best is not None:
                    reg["rejected"].append(best[2] | {"reason": "another candidate scored higher"})
                best = (acc_b, ws, entry, cand_dev)
            else:
                reg["rejected"].append(entry | {"reason": "another candidate scored higher"})
            save_registry(reg)

        if best is None:
            _log(f"generation {gen}: no candidate promoted; {parent.name} stays best")
            continue
        _, ws, entry, cand_dev = best
        name = _next_name(reg)
        # Same file contents, same digest: the promoted copy reuses the candidate's cached episodes.
        shutil.copytree(ws / "harness", HARNESSES / name)
        reg["versions"].append(
            {
                "name": name,
                "parent": parent.name,
                "created": time.strftime("%F %T"),
                "hypothesis": entry["hypothesis"],
                "changes": entry["changes"],
                "confidence": entry["confidence"],
                "paired_n": entry["paired_n"],
                "gain": entry["gain"],
                "diff": entry["diff"],
                "dev": cand_dev.summary() | {"run": str(cand_dev.out_dir.relative_to(ROOT))},
            }
        )
        reg["best"] = name
        save_registry(reg)
        _log(f"PROMOTED {name}: dev {entry['parent_dev_accuracy']:.0%} -> {entry['dev_accuracy']:.0%}")
        if commit:
            _git_commit(name, entry["hypothesis"])
