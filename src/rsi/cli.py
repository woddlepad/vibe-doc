"""Command line entry point: `uv run rsi <command>`."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .config import prepare_environment


def cmd_auth(args) -> None:
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, SystemMessage, query

    from .llm import _ISOLATED_CWD

    async def run() -> bool:
        options = ClaudeAgentOptions(model="claude-haiku-5-5", tools=[], setting_sources=[], skills=[], max_turns=1, cwd=_ISOLATED_CWD)
        ok = False
        async for msg in query(prompt="Reply with the single word OK.", options=options):
            if isinstance(msg, SystemMessage) and msg.subtype == "init":
                print(f"auth source: {msg.data.get('apiKeySource')}  model: {msg.data.get('model')}")
            elif isinstance(msg, ResultMessage):
                print("error:" if msg.is_error else "reply:", msg.result or msg.errors)
                ok = not msg.is_error
        return ok

    if not asyncio.run(run()):
        sys.exit("Not authenticated. Put CLAUDE_CODE_OAUTH_TOKEN (from `claude setup-token`) in .env")


def cmd_cases(args) -> None:
    from .cases import all_cases, build_splits, splits

    s = build_splits() if args.rebuild else splits()
    cases = all_cases()
    print(f"{len(cases)} cases: " + ", ".join(f"{k} {len(v)}" for k, v in s.items()))
    if args.show:
        c = cases[args.show]
        print(json.dumps(c.__dict__, indent=1))


def cmd_episode(args) -> None:
    from .cases import all_cases
    from .harness import Harness
    from .runner import run_episode

    r = asyncio.run(run_episode(Harness.load(args.harness), all_cases()[args.case], verbose=True))
    verdict = "CORRECT" if r["correct"] else "WRONG"
    print(f"\n{verdict}: said {r['diagnosis']!r}, answer {r['gold']!r} ({r['judge_rationale']})")
    print(f"{r['questions']} questions, {r['requests']} exam/test requests, {r['duration_s']}s, ${r['cost_usd']} API-equivalent")


def cmd_eval(args) -> None:
    from .cases import split_cases
    from .harness import Harness
    from .optimize import load_registry, record_eval
    from .runner import run_eval

    if args.split == "test" and not args.final:
        sys.exit("The test split is locked. Score it once at the end with --final.")
    h = Harness.load(args.harness or load_registry()["best"])
    problems = h.validate()
    if problems:
        sys.exit(f"invalid harness: {problems}")
    ev = asyncio.run(run_eval(h, split_cases(args.split, args.limit), args.split, args.concurrency, use_cache=not args.no_cache))
    print(json.dumps(ev.summary(), indent=1))
    print(f"saved to {ev.out_dir}")
    if args.limit is None and args.split in ("dev", "test"):
        reg = load_registry()
        if any(v["name"] == h.name for v in reg["versions"]):
            record_eval(reg, h.name, ev, args.split)


def cmd_improve(args) -> None:
    from .optimize import improve
    from .report import build_report

    asyncio.run(
        improve(
            generations=args.generations,
            train_batch=args.train_batch,
            dev_limit=args.dev_limit,
            candidates=args.candidates,
            concurrency=args.concurrency,
            min_confidence=args.min_confidence,
            commit=args.commit,
        )
    )
    print(f"report: {build_report()}")


def cmd_report(args) -> None:
    from .report import build_report

    print(build_report())


def main() -> None:
    prepare_environment()
    p = argparse.ArgumentParser(prog="rsi", description="Self-improving diagnostic harness")
    sub = p.add_subparsers(required=True)

    s = sub.add_parser("auth", help="check that Claude Code can authenticate (subscription or key)")
    s.set_defaults(fn=cmd_auth)

    s = sub.add_parser("cases", help="case bank and splits")
    s.add_argument("--rebuild", action="store_true")
    s.add_argument("--show", metavar="CASE_ID")
    s.set_defaults(fn=cmd_cases)

    s = sub.add_parser("episode", help="run one consultation and print it")
    s.add_argument("--harness", default="v000")
    s.add_argument("--case", default="mqx-000")
    s.set_defaults(fn=cmd_episode)

    s = sub.add_parser("eval", help="score a harness on a split")
    s.add_argument("--harness", help="defaults to the current best")
    s.add_argument("--split", choices=["train", "dev", "test"], default="dev")
    s.add_argument("--limit", type=int)
    s.add_argument("--concurrency", type=int, default=4)
    s.add_argument("--no-cache", action="store_true")
    s.add_argument("--final", action="store_true", help="required to score the locked test split")
    s.set_defaults(fn=cmd_eval)

    s = sub.add_parser("improve", help="run the self-improvement loop")
    s.add_argument("--generations", type=int, default=3)
    s.add_argument("--train-batch", type=int, default=30)
    s.add_argument("--dev-limit", type=int, help="use only the first N dev cases (faster, noisier)")
    s.add_argument("--candidates", type=int, default=1, help="optimizer proposals per generation")
    s.add_argument("--concurrency", type=int, default=4)
    s.add_argument("--min-confidence", type=float, default=0.75, help="required P(candidate beats parent)")
    s.add_argument("--commit", action="store_true", help="git commit + tag each promoted version")
    s.set_defaults(fn=cmd_improve)

    s = sub.add_parser("report", help="write runs/report.html")
    s.set_defaults(fn=cmd_report)

    args = p.parse_args()
    args.fn(args)
