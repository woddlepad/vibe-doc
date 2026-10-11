"""Case bank: one format for every source, plus fixed train/dev/test splits."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from functools import cache

from .config import DATA

SOURCE = DATA / "agentclinic" / "agentclinic_medqa_extended.jsonl"
SPLITS = DATA / "splits.json"
SPLIT_SIZES = {"dev": 40, "test": 60}  # everything else is train


@dataclass(frozen=True)
class Case:
    id: str
    objective: str
    patient: dict  # what the patient knows and can say
    exam: dict  # physical exam findings, revealed only on request
    tests: dict  # test results, revealed only on request
    diagnosis: str
    aliases: tuple[str, ...] = field(default=())


def _load_source() -> list[Case]:
    cases = []
    for i, line in enumerate(l for l in SOURCE.read_text().splitlines() if l.strip()):
        osce = json.loads(line)["OSCE_Examination"]
        cases.append(
            Case(
                id=f"mqx-{i:03d}",
                objective=osce["Objective_for_Doctor"],
                patient=osce["Patient_Actor"],
                exam=osce.get("Physical_Examination_Findings", {}),
                tests=osce.get("Test_Results", {}),
                diagnosis=osce["Correct_Diagnosis"],
            )
        )
    return cases


def build_splits() -> dict[str, list[str]]:
    """Deterministic split by hashed id, so it never depends on file order or RNG versions."""
    ids = sorted((c.id for c in _load_source()), key=lambda i: hashlib.sha256(f"rsi:{i}".encode()).hexdigest())
    n_test, n_dev = SPLIT_SIZES["test"], SPLIT_SIZES["dev"]
    splits = {
        "test": sorted(ids[:n_test]),
        "dev": sorted(ids[n_test : n_test + n_dev]),
        "train": sorted(ids[n_test + n_dev :]),
    }
    SPLITS.write_text(json.dumps(splits, indent=1) + "\n")
    return splits


@cache
def all_cases() -> dict[str, Case]:
    return {c.id: c for c in _load_source()}


@cache
def splits() -> dict[str, list[str]]:
    if not SPLITS.exists():
        return build_splits()
    return json.loads(SPLITS.read_text())


def split_cases(name: str, limit: int | None = None) -> list[Case]:
    ids = splits()[name]
    if limit is not None:
        ids = ids[:limit]
    cases = all_cases()
    return [cases[i] for i in ids]
