"""Tests that need no model calls."""

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from rsi import optimize, runner
from rsi.cases import all_cases, splits
from rsi.clinic import Budget, Episode, build_clinic_tools
from rsi.harness import Harness, diff, is_editable
from rsi.judge import mentions, normalize, quick_match
from rsi.optimize import _check_candidate, _failure_md, _guard
from rsi.runner import EvalResult
from rsi.stats import paired_bootstrap, wilson


def test_splits_are_disjoint_and_complete():
    s = splits()
    ids = set(all_cases())
    assert len(ids) == 215
    assert set(s["train"]) | set(s["dev"]) | set(s["test"]) == ids
    assert not set(s["train"]) & set(s["dev"]) and not set(s["dev"]) & set(s["test"]) and not set(s["train"]) & set(s["test"])
    assert (len(s["dev"]), len(s["test"])) == (40, 60)


def test_judge_quick_match():
    assert quick_match("Myasthenia Gravis", "Myasthenia gravis") is True
    assert quick_match("Graves' disease", "Graves disease") is True
    assert quick_match(None, "Myasthenia gravis") is False
    assert quick_match("Lambert-Eaton syndrome", "Myasthenia gravis") is None  # needs the LLM judge
    assert normalize("Acute MI (STEMI)") == "acute mi stemi"
    assert mentions("I think it might be myasthenia gravis?", "Myasthenia gravis")
    assert not mentions("my eyes feel heavy", "Myasthenia gravis")
    assert mentions("looks like chronic lymphocytic leukemia", "Chronic lymphocytic leukemia (CLL)")


def test_judge_never_strips_the_prediction():
    assert quick_match("Myasthenia gravis (ruled out; it is botulism)", "Myasthenia gravis") is None
    assert quick_match("Myasthenia gravis (ocular)", "Myasthenia gravis") is None
    # The answer key's own parenthetical is optional.
    assert quick_match("Chronic lymphocytic leukemia", "Chronic lymphocytic leukemia (CLL)") is True
    assert quick_match("Chronic lymphocytic leukemia (CLL)", "Chronic lymphocytic leukemia (CLL)") is True
    # More than one answer always goes to the LLM judge.
    for pred in ("Myasthenia gravis or botulism", "Myasthenia gravis/botulism", "Myasthenia gravis; botulism", "Myasthenia gravis vs LEMS"):
        assert quick_match(pred, "Myasthenia gravis") is None, pred


def test_stats():
    lo, hi = wilson(20, 40)
    assert lo < 0.5 < hi
    assert paired_bootstrap([0] * 20, [1] * 20) == 1.0
    assert paired_bootstrap([1] * 20, [0] * 20) == 0.0
    assert paired_bootstrap([0, 1] * 10, [0, 1] * 10) == 0.5


def test_baseline_harness_is_valid():
    h = Harness.load("v000")
    assert h.validate(locked_model=h.config["model"]) == []
    assert "submit_diagnosis" in h.system_prompt()


def test_editable_paths():
    assert is_editable("system.md")
    assert is_editable(".claude/skills/chest-pain/SKILL.md")
    assert not is_editable(".claude/settings.json")
    assert not is_editable("CLAUDE.md")
    assert not is_editable(".claude/skills/../../x.md")
    assert not is_editable(".claude/agents/helper.md")
    assert not is_editable(".claude/skills/chest-pain/run.sh")
    assert not is_editable(".claude/skills/chest-pain/refs/SKILL.md")


def _candidate(tmp_path) -> Harness:
    shutil.copytree(Harness.load("v000").path, tmp_path / "harness")
    return Harness(name="cand", path=tmp_path / "harness")


def test_skill_validation(tmp_path):
    cand = _candidate(tmp_path)
    skill = tmp_path / "harness/.claude/skills/chest-pain/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: chest-pain\ndescription: >\n  Workup for chest pain\n---\nAsk about onset.\n")
    assert cand.validate() == []

    skill.write_text("---\nname: x\ndescription: y\nmodel: claude-opus-5-5\nhooks:\n  PreToolUse:\n    - command: cat /etc/passwd\n---\nbody\n")
    problems = cand.validate()
    assert any("'model'" in p for p in problems) and any("'hooks'" in p for p in problems)
    skill.write_text("---\nname: x\ndescription: y\n---\nContext: !`cat ~/.env`\n")
    assert any("!`command`" in p for p in cand.validate())
    skill.write_text("no frontmatter\n")
    assert any("frontmatter" in p for p in cand.validate())

    skill.write_text("---\nname: x\ndescription: y\n---\nbody\n")
    (skill.parent / "run.sh").write_text("#!/bin/sh\n")
    (tmp_path / "harness/.claude/agents").mkdir()
    (tmp_path / "harness/.claude/agents/helper.md").write_text("---\nname: h\nmodel: opus\n---\n")
    problems = cand.validate()
    assert any("chest-pain/run.sh" in p for p in problems) and any("agents/helper.md" in p for p in problems)


@pytest.mark.parametrize(
    "cfg, needle",
    [
        ({"builtin_tools": None}, "builtin_tools"),
        ({"builtin_tools": [1]}, "builtin_tools"),
        ({"builtin_tools": ["Agent"]}, "Agent"),
        ({"max_questions": True}, "max_questions"),
        ({"max_turns": 20.0}, "max_turns"),
        ({"effort": ["high"]}, "effort"),
        ({"model": None}, "model"),
        ([], "JSON object"),
        (None, "JSON object"),
    ],
)
def test_config_types_are_problems_not_crashes(tmp_path, cfg, needle):
    cand = _candidate(tmp_path)
    (tmp_path / "harness/config.json").write_text(json.dumps(cfg))
    assert any(needle in p for p in cand.validate(locked_model="claude-haiku-5-5"))


def test_candidate_checks(tmp_path):
    parent = Harness.load("v000")
    shutil.copytree(parent.path, tmp_path / "harness")
    cand = Harness(name="cand", path=tmp_path / "harness")
    assert _check_candidate(cand, parent, "claude-haiku-5-5") == ["no changes"]

    (tmp_path / "harness/lessons.md").write_text("# Lessons\n- Ask about timing.\n")
    assert _check_candidate(cand, parent, "claude-haiku-5-5") == []
    assert "+- Ask about timing." in diff(parent, cand)

    cfg = json.loads((tmp_path / "harness/config.json").read_text())
    cfg.update(model="claude-opus-5-5", builtin_tools=["Bash"])
    (tmp_path / "harness/config.json").write_text(json.dumps(cfg))
    problems = _check_candidate(cand, parent, "claude-haiku-5-5")
    assert any("locked" in p for p in problems) and any("Bash" in p for p in problems)


class FakeSpeaker:
    def __init__(self, prefix):
        self.prefix = prefix
        self.heard = []

    async def say(self, text):
        self.heard.append(text)
        return f"{self.prefix}: reply to {text}"


def _run(handler, args):
    return asyncio.run(handler(args))["content"][0]["text"]


def test_clinic_tools_enforce_budget_and_end_episode():
    case = all_cases()["mqx-000"]
    ep = Episode(case=case, budget=Budget(max_questions=2, max_requests=1))
    patient, examiner = FakeSpeaker("pt"), FakeSpeaker("ex")
    tools = {t.name: t.handler for t in build_clinic_tools(ep, patient, examiner)}

    assert "1 questions left" in _run(tools["ask_patient"], {"question": "What brings you in?"})
    _run(tools["ask_patient"], {"question": "When did it start?"})
    assert "budget used up" in _run(tools["ask_patient"], {"question": "Anything else?"})
    assert len(patient.heard) == 2

    assert examiner.heard == [] and "ex:" in _run(tools["order_test"], {"test": "AChR antibodies"})
    assert examiner.heard == ["Test ordered: AChR antibodies"]
    assert "budget used up" in _run(tools["examine"], {"exam": "cranial nerves"})

    _run(tools["submit_diagnosis"], {"diagnosis": " Myasthenia gravis ", "differential": ["LEMS", "botulism"]})
    assert ep.diagnosis == "Myasthenia gravis" and ep.differential == ["LEMS", "botulism"]
    assert "over" in _run(tools["ask_patient"], {"question": "One more?"})
    assert [e["kind"] for e in ep.events] == ["ask_patient", "ask_patient", "order_test", "submit_diagnosis"]


def test_optimizer_guard(tmp_path):
    (tmp_path / "harness").mkdir()
    hook = _guard(tmp_path)

    def decision(tool, file=None, **args):
        tool_input = {"file_path": str(file)} if file is not None else args
        out = asyncio.run(hook({"tool_name": tool, "tool_input": tool_input}, None, None))
        return out.get("hookSpecificOutput", {}).get("permissionDecision", "allow")

    assert decision("Edit", tmp_path / "harness/system.md") == "allow"
    assert decision("Write", tmp_path / "harness/.claude/skills/x/SKILL.md") == "allow"
    assert decision("Read", tmp_path / "evidence/README.md") == "allow"
    assert decision("Write", tmp_path / "evidence/README.md") == "deny"
    assert decision("Write", tmp_path / "harness/.claude/settings.json") == "deny"
    assert decision("Read", Path("/home/atmos/projects/rsi-doc/data/splits.json")) == "deny"
    assert decision("Read", tmp_path / "harness/../../etc/passwd") == "deny"
    assert decision("Write", tmp_path / "harness/.claude/agents/x.md") == "deny"
    assert decision("Edit", tmp_path / "harness/system.md") == "allow"
    assert decision("Edit", file_path=str(tmp_path / "harness/system.md"), old_string="/x", new_string="/etc/passwd") == "allow"

    # Real Glob/Grep argument shapes.
    assert decision("Glob", pattern="evidence/failures/*.md") == "allow"
    assert decision("Glob", pattern="**/*.md", path=str(tmp_path / "evidence")) == "allow"
    assert decision("Glob", pattern="/home/atmos/projects/rsi-doc/data/**/*") == "deny"
    assert decision("Glob", pattern="../../**/*.jsonl") == "deny"
    assert decision("Glob", pattern="~/**/*") == "deny"
    assert decision("Grep", pattern="Correct diagnosis", path="evidence", output_mode="content") == "allow"
    assert decision("Grep", pattern="diagnosis", path="/home/atmos/projects/rsi-doc/data") == "deny"
    assert decision("Grep", pattern="diagnosis", glob="../../data/*.jsonl") == "deny"
    assert decision("Grep", pattern="diagnosis", path="evidence", glob="/etc/*") == "deny"


def test_failure_evidence_contains_hidden_case():
    case = all_cases()["mqx-000"]
    r = {
        "case_id": case.id, "objective": case.objective, "gold": case.diagnosis, "diagnosis": "Lambert-Eaton syndrome",
        "differential": [], "judge_rationale": "different disease", "questions": 3, "requests": 1,
        "events": [{"kind": "ask_patient", "question": "Q?", "answer": "A."}],
    }
    md = _failure_md(r, case)
    assert "**Correct diagnosis: Myasthenia gravis**" in md and "Acetylcholine" in md and "**Doctor:** Q?" in md


class FakePersona:
    cost_usd = 0.0

    def __init__(self, system, model):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass

    async def say(self, text):
        return "Honestly, I read online that it's myasthenia gravis."


def test_leaked_episode_is_wrong_and_skips_judge(monkeypatch):
    tools = {}

    def fake_server(ep, patient, examiner):
        tools.update({t.name: t.handler for t in build_clinic_tools(ep, patient, examiner)})

    async def fake_query(prompt, options):
        await tools["ask_patient"]({"question": "What do you think it is?"})
        await tools["submit_diagnosis"]({"diagnosis": "Myasthenia gravis"})
        return
        yield

    async def no_judge(*args, **kwargs):
        raise AssertionError("the judge must not run on a leaked episode")

    monkeypatch.setattr(runner, "Persona", FakePersona)
    monkeypatch.setattr(runner, "build_clinic_server", fake_server)
    monkeypatch.setattr(runner, "query", fake_query)
    monkeypatch.setattr(runner, "grade", no_judge)
    r = asyncio.run(runner.run_episode(Harness.load("v000"), all_cases()["mqx-000"]))
    assert r["leak"] and not r["correct"] and r["judge_rationale"] == "simulator leak"
    assert r["env_digest"] == runner.env_digest()


def _result(case_id, correct=True, leak=False):
    return {
        "case_id": case_id, "harness": "h", "gold": "g", "diagnosis": "d", "differential": [], "correct": correct,
        "differential_match": 0, "judge_rationale": "", "questions": 1, "requests": 1, "leak": leak,
        "duration_s": 1.0, "cost_usd": 0.0, "objective": "o", "events": [],
    }


def test_run_eval_does_not_cache_leaks(tmp_path, monkeypatch):
    calls = []

    async def fake_episode(harness, case):
        calls.append(case.id)
        return _result(case.id, correct=False, leak=case.id == "mqx-000")

    monkeypatch.setattr(runner, "run_episode", fake_episode)
    monkeypatch.setattr(runner, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(runner, "RUNS", tmp_path)
    cases = [all_cases()["mqx-000"], all_cases()["mqx-001"]]
    h = Harness.load("v000")
    ev = asyncio.run(runner.run_eval(h, cases, "dev", quiet=True))
    asyncio.run(runner.run_eval(h, cases, "dev", quiet=True))
    assert calls == ["mqx-000", "mqx-001", "mqx-000"]
    assert (tmp_path / "cache" / f"{h.digest}-{runner.env_digest()}" / "mqx-001.json").exists()
    assert ev.summary()["env_digest"] == runner.env_digest() and ev.summary()["leaks"] == 1


def _fake_improve(monkeypatch, tmp_path, evals, edits):
    async def fake_run_eval(h, cases, label, concurrency=4, **kw):
        res = evals.get(h.name, lambda c: _result(c.id))
        if isinstance(res, Exception):
            raise res
        return EvalResult(harness=h.name, label=label, results=[res(c) for c in cases], out_dir=tmp_path)

    async def fake_propose(ws, locked_model):
        edits[ws.name](ws / "harness")
        return {"hypothesis": f"idea {ws.name}", "changes": [], "expected_effect": ""}

    reg = {"best": "v000", "locked_model": "claude-haiku-5-5", "versions": [{"name": "v000", "parent": None}], "rejected": []}
    monkeypatch.setattr(optimize, "run_eval", fake_run_eval)
    monkeypatch.setattr(optimize, "propose", fake_propose)
    monkeypatch.setattr(optimize, "load_registry", lambda: reg)
    monkeypatch.setattr(optimize, "save_registry", lambda r: None)
    monkeypatch.setattr(optimize, "record_eval", lambda *a: None)
    monkeypatch.setattr(optimize, "RUNS", tmp_path)
    return reg


def test_improve_rejects_bad_candidates_and_continues(tmp_path, monkeypatch):
    lessons = lambda h: (h / "lessons.md").write_text("- Ask about timing.\n")  # noqa: E731
    edits = {
        "gen1-cand1": lessons,
        "gen1-cand2": lambda h: (h / "config.json").write_text('{"builtin_tools": null}'),
        "gen1-cand3": lessons,
    }
    evals = {
        "cand-gen1-cand1": lambda c: {"case_id": c.id, "error": "TimeoutError"} if c.id == splits()["dev"][0] else _result(c.id),
        "cand-gen1-cand3": RuntimeError("boom"),
    }
    reg = _fake_improve(monkeypatch, tmp_path, evals, edits)
    asyncio.run(optimize.improve(generations=1, train_batch=2, dev_limit=3, candidates=3))
    reasons = {r["id"].split("/")[-1]: r["reason"] for r in reg["rejected"]}
    assert reasons["gen1-cand1"] == "eval incomplete: 1 errors"
    assert "builtin_tools must be a list of strings" in reasons["gen1-cand2"]
    assert "RuntimeError: boom" in reasons["gen1-cand3"]
    assert reg["best"] == "v000"


def test_improve_aborts_on_parent_eval_errors(tmp_path, monkeypatch):
    evals = {"v000": lambda c: {"case_id": c.id, "error": "LLMError: not logged in"}}
    _fake_improve(monkeypatch, tmp_path, evals, {})
    with pytest.raises(SystemExit, match="dev eval incomplete: 3 errors, 0 scored"):
        asyncio.run(optimize.improve(generations=1, dev_limit=3))


def test_final_test_eval_runs_once(tmp_path, monkeypatch):
    from argparse import Namespace

    from rsi import cli

    async def fake_run_eval(h, cases, label, concurrency=4, **kw):
        return EvalResult(harness=h.name, label=label, results=[_result(c.id) for c in cases], out_dir=tmp_path, env_digest="e")

    monkeypatch.setattr(cli, "TEST_LOCK", tmp_path / "test-final.json")
    monkeypatch.setattr(runner, "run_eval", fake_run_eval)
    monkeypatch.setattr(optimize, "load_registry", lambda: {"best": "v000", "versions": []})
    args = Namespace(split="test", final=True, harness="v000", limit=None, concurrency=1, no_cache=False)
    cli.cmd_eval(args)
    lock = json.loads((tmp_path / "test-final.json").read_text())
    assert lock["harness"] == "v000" and lock["digest"] == Harness.load("v000").digest and lock["timestamp"]
    with pytest.raises(SystemExit, match="already scored once"):
        cli.cmd_eval(args)
