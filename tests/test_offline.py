"""Tests that need no model calls."""

import asyncio
import json
import shutil
from pathlib import Path


from rsi.cases import all_cases, splits
from rsi.clinic import Budget, Episode, build_clinic_tools
from rsi.harness import Harness, diff, is_editable
from rsi.judge import mentions, normalize, quick_match
from rsi.optimize import _check_candidate, _failure_md, _guard
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
    assert normalize("Acute MI (STEMI)") == "acute mi"
    assert mentions("I think it might be myasthenia gravis?", "Myasthenia gravis")
    assert not mentions("my eyes feel heavy", "Myasthenia gravis")


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

    def decision(tool, path):
        out = asyncio.run(hook({"tool_name": tool, "tool_input": {"file_path": str(path)}}, None, None))
        return out.get("hookSpecificOutput", {}).get("permissionDecision", "allow")

    assert decision("Edit", tmp_path / "harness/system.md") == "allow"
    assert decision("Write", tmp_path / "harness/.claude/skills/x/SKILL.md") == "allow"
    assert decision("Read", tmp_path / "evidence/README.md") == "allow"
    assert decision("Write", tmp_path / "evidence/README.md") == "deny"
    assert decision("Write", tmp_path / "harness/.claude/settings.json") == "deny"
    assert decision("Read", Path("/home/atmos/projects/rsi-doc/data/splits.json")) == "deny"
    assert decision("Read", tmp_path / "harness/../../etc/passwd") == "deny"


def test_failure_evidence_contains_hidden_case():
    case = all_cases()["mqx-000"]
    r = {
        "case_id": case.id, "objective": case.objective, "gold": case.diagnosis, "diagnosis": "Lambert-Eaton syndrome",
        "differential": [], "judge_rationale": "different disease", "questions": 3, "requests": 1,
        "events": [{"kind": "ask_patient", "question": "Q?", "answer": "A."}],
    }
    md = _failure_md(r, case)
    assert "**Correct diagnosis: Myasthenia gravis**" in md and "Acetylcholine" in md and "**Doctor:** Q?" in md
