# rsi-doc — results summary (hackathon submission, 2026-10-11)

## What it is
A Darwin-Gödel-Machine-style self-improving diagnostic agent. A frozen simulated patient + examiner
and a frozen judge wrap an editable **doctor harness** (prompt, lessons, config, skills). A Claude Opus
meta-agent reads the doctor's failures on train cases, proposes one hypothesis-driven diff, and the
candidate is promoted only if it beats its parent on a held-out dev set (paired bootstrap). Test is
scored once, at the end. Everything runs on the Claude Agent SDK (doctor: `claude-haiku-5-5`, locked).

Data: 215 AgentClinic MedQA-extended OSCE cases → train 115 / dev 40 / test 60 (hash split, frozen).

## Results

| harness | change | dev (40) | test (60, scored once) |
|---|---|---|---|
| v000 | baseline prompt | 77.5% [62–88] | – |
| **v001** | optimizer gen 1: "abnormal findings are deliberate clues" + mandatory pre-submit check + 3 lessons (prompt-only, 41-line diff) | **85.0%** (+3 cases, P(better)=0.92) | **81.7%** [70–89], 0 leaks, 0 errors |
| v001-search | v001 + `max_lookups: 5` (Exa, medical domains only) | 9/10 vs 8/10 on the 10-case screen (preliminary) | – |

Generation 1 ran 4 candidates in parallel from the same evidence: one was screened out after 10
cases, one was +0, two beat the parent (82.5%, 85%); the best was promoted. Every candidate's
hypothesis, diff and scores are in `experiments/` and `harnesses/registry.json`.

Cost/latency: ~37 s and ~$0.012 per consultation; a full dev eval ≈ $0.47.

## Attribution
Each candidate is one diff from one written hypothesis, scored on the *same* 40 dev cases as its
parent. Promotion requires a net gain and P(better) from a paired bootstrap (gen 1: ≥+1, P≥0.75;
exploit phase: ≥+2, P≥0.85), at ≤1.5× the parent's cost. With 40 cases the noise floor is ±1–2
cases, so v001's +3 (P=0.92) is a real but modest signal; the test score (81.7% on 60 untouched
cases) is the honest estimate.

## Guardrails that made the numbers trustworthy
- Doctor has only the clinic tools (+ optional `lookup`); no file/shell/web access.
- Answer key is **redacted** from everything the patient/examiner say (the dataset names the
  diagnosis inside test results in ~15% of cases); any residual leak scores the episode wrong.
- Judge: exact/alias match, else an LLM judge that treats the submission as untrusted text;
  hedged "A / B" answers are scored wrong without asking the judge.
- Optimizer is sandboxed by a PreToolUse hook to its workspace and the editable harness files;
  skills are validated (name/description only, no hooks); subagents/model overrides disallowed.
- Web lookup results are checked for 8-gram overlap with the case file and for off-allowlist
  URLs; a hit disqualifies the episode. 0 contaminated episodes in the A/B.
- Independent Codex audits (3 rounds) are in the repo history / `experiments/`.

## What didn't happen (time)
- Only one optimizer generation ran: the VM (2 CPU / 3.8 GB) crashed under concurrency 6, was
  resized mid-run, and the exploit generation was skipped by the `--deadline` guard.
- Search A/B is 10 cases; the doctor used lookup in 2 of them.

## Next steps
1. Exploit phase from v001: one variable per candidate, `--min-gain 2 --min-confidence 0.85`.
2. Let the optimizer enable `max_lookups` itself and see whether it learns *when* to search.
3. More data: AgentClinic-NEJM (120), MedQA-train→OSCE (~1k, deduped), DDXPlus — see the
   dataset report. Bigger dev set → tighter gate.
