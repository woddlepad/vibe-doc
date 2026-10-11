"""A harness version is a folder. This module loads, validates, hashes and stages one."""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import HARNESSES

# Built-in Claude Code tools the doctor may be given. File, shell and web tools are never
# allowed: the doctor must not be able to read case data or look answers up. No subagents either:
# they can name their own model, which would break the doctor model lock.
BUILTIN_WHITELIST = {"Skill", "TodoWrite"}
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
EDITABLE_DIRS = (".claude/skills/",)
# Skills are one SKILL.md each with plain-text frontmatter; hooks, allowed-tools, model etc. are executable.
SKILL_FILE = re.compile(r"\.claude/skills/[A-Za-z0-9_-]+/SKILL\.md")
SKILL_KEYS = {"name", "description"}
# One `key: value` per line at column 0; values are plain single-line strings (no block, flow,
# anchor, alias or tag syntax, no trailing ':' that would open a nested mapping).
SKILL_LINE = re.compile(r"^(name|description):\s*([^\s\[{&*!|>].*)$")


class HarnessError(ValueError):
    pass


def is_editable(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    if ".." in rel.split("/"):
        return False
    return rel in EDITABLE_FILES or (rel.startswith(EDITABLE_DIRS) and SKILL_FILE.fullmatch(rel) is not None)


def skill_problems(text: str) -> list[str]:
    """Frontmatter may hold only `name` and `description`; the body may not run commands."""
    lines = text.replace("\r", "").splitlines()
    fences = [i for i, line in enumerate(lines) if line.strip() == "---"]
    if len(fences) < 2 or fences[0] != 0:
        return ["missing --- frontmatter ---"]
    problems, seen = [], []
    for line in lines[1 : fences[1]]:
        if not line.strip() or line.startswith("#"):
            continue
        m = SKILL_LINE.match(line)
        if not m or m[2].rstrip().endswith(":"):
            problems.append(f"frontmatter line not allowed: {line!r} (only `name: text` and `description: text`)")
        else:
            seen.append(m[1])
    for key in sorted(SKILL_KEYS):
        if seen.count(key) != 1:
            problems.append(f"frontmatter needs exactly one {key!r} (found {seen.count(key)})")
    if "!`" in text:
        problems.append("dynamic !`command` not allowed")
    return problems


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
        for rel, text in self.files().items():
            if not is_editable(rel):
                problems.append(f"unexpected file: {rel}")
            elif rel.startswith(EDITABLE_DIRS):
                problems += [f"{rel}: {p}" for p in skill_problems(text)]
        f = self.path / "config.json"
        try:
            raw = json.loads(f.read_text()) if f.exists() else {}
        except json.JSONDecodeError as e:
            return problems + [f"config.json is not valid JSON: {e}"]
        if not isinstance(raw, dict):
            return problems + ["config.json must be a JSON object"]
        cfg = CONFIG_DEFAULTS | raw
        unknown = set(cfg) - set(CONFIG_DEFAULTS)
        if unknown:
            problems.append(f"unknown config keys: {sorted(unknown)}")
        if not isinstance(cfg["model"], str) or (locked_model and cfg["model"] != locked_model):
            problems.append(f"model is locked to {locked_model}" if locked_model else "model must be a string")
        if not isinstance(cfg["effort"], str) or cfg["effort"] not in EFFORTS:
            problems.append(f"effort must be one of {sorted(EFFORTS)}")
        for key, lo, hi in (("max_questions", 3, 40), ("max_requests", 0, 30), ("max_turns", 10, 150)):
            if type(cfg[key]) is not int or not lo <= cfg[key] <= hi:
                problems.append(f"{key} must be an integer in [{lo}, {hi}]")
        tools = cfg["builtin_tools"]
        if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
            problems.append("builtin_tools must be a list of strings")
        elif bad := set(tools) - BUILTIN_WHITELIST:
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
