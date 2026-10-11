"""A harness version is a folder. This module loads, validates, hashes and stages one."""

from __future__ import annotations

import difflib
import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import HARNESSES

# Built-in Claude Code tools the doctor may be given. File, shell and web tools are never
# allowed: the doctor must not be able to read case data or look answers up.
BUILTIN_WHITELIST = {"Skill", "Agent", "Task", "TodoWrite"}
CONFIG_DEFAULTS = {
    "model": "claude-haiku-5-5",
    "effort": "medium",
    "max_questions": 15,
    "max_requests": 10,
    "max_turns": 60,
    "builtin_tools": [],
}
EFFORTS = {"low", "medium", "high", "xhigh", "max"}
# Paths the optimizer may create or edit, relative to the harness folder.
EDITABLE_FILES = {"system.md", "lessons.md", "config.json"}
EDITABLE_DIRS = (".claude/skills/", ".claude/agents/")


class HarnessError(ValueError):
    pass


def is_editable(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    return ".." not in rel.split("/") and (rel in EDITABLE_FILES or rel.startswith(EDITABLE_DIRS))


@dataclass(frozen=True)
class Harness:
    name: str
    path: Path

    @classmethod
    def load(cls, name_or_path: str | Path) -> Harness:
        p = Path(name_or_path)
        if not p.is_dir():
            p = HARNESSES / str(name_or_path)
        if not (p / "system.md").exists():
            raise HarnessError(f"{p} is not a harness (no system.md)")
        return cls(name=p.name, path=p)

    def files(self) -> dict[str, str]:
        out = {}
        for f in sorted(self.path.rglob("*")):
            if f.is_file():
                out[f.relative_to(self.path).as_posix()] = f.read_text(errors="replace")
        return out

    @property
    def digest(self) -> str:
        h = hashlib.sha256()
        for rel, text in self.files().items():
            h.update(rel.encode() + b"\0" + text.encode() + b"\0")
        return h.hexdigest()[:16]

    @property
    def config(self) -> dict:
        cfg = dict(CONFIG_DEFAULTS)
        f = self.path / "config.json"
        if f.exists():
            cfg.update(json.loads(f.read_text()))
        return cfg

    def system_prompt(self) -> str:
        system = (self.path / "system.md").read_text().strip()
        lessons = self.path / "lessons.md"
        if lessons.exists() and lessons.read_text().strip():
            system += "\n\n" + lessons.read_text().strip()
        return system

    @property
    def has_skills(self) -> bool:
        return any((self.path / ".claude/skills").glob("*/SKILL.md"))

    def validate(self, locked_model: str | None = None) -> list[str]:
        """Return a list of problems; empty means the harness is runnable."""
        problems = []
        for rel in self.files():
            if not is_editable(rel):
                problems.append(f"unexpected file: {rel}")
        try:
            cfg = self.config
        except json.JSONDecodeError as e:
            return problems + [f"config.json is not valid JSON: {e}"]
        unknown = set(cfg) - set(CONFIG_DEFAULTS)
        if unknown:
            problems.append(f"unknown config keys: {sorted(unknown)}")
        if locked_model and cfg["model"] != locked_model:
            problems.append(f"model is locked to {locked_model}")
        if cfg["effort"] not in EFFORTS:
            problems.append(f"effort must be one of {sorted(EFFORTS)}")
        for key, lo, hi in (("max_questions", 3, 40), ("max_requests", 0, 30), ("max_turns", 10, 150)):
            if not isinstance(cfg[key], int) or not lo <= cfg[key] <= hi:
                problems.append(f"{key} must be an integer in [{lo}, {hi}]")
        bad = set(cfg["builtin_tools"]) - BUILTIN_WHITELIST
        if bad:
            problems.append(f"builtin_tools not allowed: {sorted(bad)} (allowed: {sorted(BUILTIN_WHITELIST)})")
        if not (self.path / "system.md").read_text().strip():
            problems.append("system.md is empty")
        return problems

    def stage(self) -> Path:
        """Copy into a fresh temp dir so the doctor's cwd holds nothing but the harness."""
        dest = Path(tempfile.mkdtemp(prefix=f"rsi-{self.name}-"))
        shutil.copytree(self.path, dest, dirs_exist_ok=True)
        return dest


def diff(a: Harness, b: Harness) -> str:
    fa, fb = a.files(), b.files()
    out = []
    for rel in sorted(set(fa) | set(fb)):
        out += difflib.unified_diff(
            fa.get(rel, "").splitlines(keepends=True),
            fb.get(rel, "").splitlines(keepends=True),
            fromfile=f"{a.name}/{rel}",
            tofile=f"{b.name}/{rel}",
        )
    return "".join(out)
