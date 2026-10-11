# rsi-doc: a self-improving diagnosis harness

An AI doctor interviews simulated patients and submits a diagnosis, and the diagnosis is scored
against the answer key. A Claude Code meta-agent then studies the failures and rewrites the doctor's
harness (prompt, lessons, skills, budgets). A new version is kept only if it diagnoses
more held-out patients correctly.

Everything runs on the **Claude Agent SDK**, so it can use a Claude subscription.

```
case bank (AgentClinic MedQA, 215 cases: train 115 / dev 40 / test 60)
   │ hidden case
   ▼
patient sim (frozen) ⇄ doctor harness (vNNN) ──► judge (frozen) ──► traces + scores
                                ▲                                       │
                                │ promote if dev improves               ▼
                       dev gate ◄── candidate ◄── optimizer (Claude Code, edits harness/ only)
```

## Setup

```bash
uv sync
cp .env.example .env          # then paste your token from: claude setup-token
uv run rsi auth               # should print "reply: OK"
```

## Commands

```bash
uv run rsi cases                          # case counts per split
uv run rsi episode --case mqx-001         # watch one consultation (a train case)
uv run rsi eval --split dev --limit 5     # quick sanity check
uv run rsi eval --split dev               # baseline on all 40 dev cases
uv run rsi improve --generations 3        # the self-improvement loop
uv run rsi report                         # runs/report.html
uv run rsi eval --split test --final      # once, at the end (locked by runs/test-final.json)
uv run pytest                             # offline tests, no model calls
```

`improve` options: `--train-batch 30` (failures shown to the optimizer), `--dev-limit N` (faster,
noisier gate), `--candidates K` (parallel proposals per generation), `--min-confidence 0.75`
(required bootstrap P(candidate beats parent)), `--min-gain 1` (required net dev cases gained),
`--screen 10`, `--max-slowdown 1.5`, `--deadline HH:MM` (see below), `--commit` (git commit + tag
each promoted version).

## Time-boxed runs

Each candidate is first screened on the first `--screen` dev cases (0 disables). If it scores more
than 1 below the parent there, it is rejected without running the full dev set. The parent's screen
score comes from its cached full-dev eval, and the candidate's screen episodes are cached, so a
survivor runs only the remaining dev cases. A candidate that gains enough is still discarded if its
mean episode time is over `--max-slowdown` × the parent's, or its dev cost over 1.5× the parent's.

`--deadline HH:MM` (24h, machine local time; a time already past today means tomorrow) skips any
generation, or candidate full-dev eval, projected to end after it. Projections use the parent's
measured dev `mean_duration_s` (120 s until known) and the last optimizer round's wall time. Check
the per-episode figures first (cached episodes keep the duration they were measured with; add
`--no-cache` to re-measure):

```bash
uv run rsi eval --split dev --limit 8 --label calib    # last line: seconds and $ per episode
# explore: several ideas, one generation
uv run rsi improve --generations 1 --candidates 5 --screen 10 --train-batch 20
# exploit: one idea per generation, a stricter gate, stop in time
uv run rsi improve --generations 6 --candidates 1 --screen 10 --min-confidence 0.9 --min-gain 2 \
  --train-batch 20 --deadline 23:30
```

## Web lookup (Exa)

A harness with `"max_lookups": N` (0-10, default 0) in `config.json` gives the doctor a fifth clinic
tool, `lookup(query)`: an [Exa](https://exa.ai) search restricted to trusted medical references
(StatPearls/PubMed, Merck, MedlinePlus, NICE, CDC, ...; `ALLOWED_DOMAINS` in `src/rsi/lookup.py`),
returning the top 5 results with highlights. It needs `EXA_API_KEY` in `.env`; `eval`, `episode` and
`improve` refuse to start without it.

- Results are redacted like the patient and examiner (the answer key is never spelled out).
- An episode is **contaminated**, scored wrong without calling the judge and never cached, if any
  result comes from outside the allowed domains or shares 3+ distinct word 8-grams with the case file
  (i.e. the doctor found the vignette itself). `summary.json` counts them under `contaminated`.

The optimizer may turn it on through `config.json`. For a controlled A/B, copy a harness folder,
set `max_lookups`, and `rsi eval --harness <copy>` both on the same split.

## Layout

| Path | What |
|---|---|
| `harnesses/vNNN/` | One harness version: `system.md`, `lessons.md`, `config.json`, optional `.claude/skills/<name>/SKILL.md` |
| `harnesses/registry.json` | Every version and rejected candidate, with scores and hypotheses |
| `src/rsi/clinic.py` | Frozen environment: patient and examiner prompts, the doctor's clinic tools (in-process MCP) |
| `src/rsi/lookup.py` | Frozen environment: the doctor's Exa web lookup and its domain allowlist |
| `src/rsi/judge.py` | Frozen grader: exact match, then an LLM judge |
| `src/rsi/runner.py` | Runs episodes and evals, with traces cached per harness + environment digest in `runs/cache/` |
| `src/rsi/optimize.py` | Evidence builder, optimizer session, dev gate, registry |
| `src/rsi/report.py` | Static HTML report |
| `runs/` | Episode traces, eval summaries, optimizer workspaces (gitignored) |

## Guardrails against the loop cheating

- The doctor gets only the four clinic tools (five with `lookup`, see above), plus `Skill`/`TodoWrite`
  if the harness enables them. File, shell, built-in web and subagent tools are disabled (`permission_mode="dontAsk"`), and its working
  directory is a temporary copy of the harness.
- Skills are plain instructions: one `SKILL.md` per skill, frontmatter limited to `name` and
  `description` (no hooks, `allowed-tools`, `model`, ...), no supporting files, no `` !`command` ``.
  This is a narrow allowlist, not a sandbox.
- The optimizer can read only its workspace (the harness copy plus train-split evidence). A
  `PreToolUse` hook blocks reads (including Glob/Grep patterns) outside it and writes outside the
  editable harness files.
- The doctor model is locked across versions, so gains come from the harness, not a model swap.
- The patient, examiner and judge live in code the optimizer never sees. Episodes where a frozen
  role says the answer out loud are flagged as `leak`, scored wrong and rerun next time (never cached).
- Promotion is decided on dev cases the optimizer never sees, and only when both the parent and the
  candidate scored every dev case (no errors). `improve` stops if the parent's dev eval has errors.
- Cached episodes are keyed by the harness digest and an environment digest (role models,
  `clinic.py`, `judge.py`, `lookup.py`, case file), so changing the frozen environment invalidates the cache.
- Test is scored once with `--final`; `runs/test-final.json` records it and blocks a second run.

## Models

| Role | Default | Override |
|---|---|---|
| Doctor | `claude-haiku-5-5` | `harnesses/v000/config.json` (before the first improve run) |
| Patient, examiner | `claude-haiku-5-5` | `RSI_PATIENT_MODEL`, `RSI_EXAMINER_MODEL` (env or `.env`) |
| Judge | `claude-sonnet-5-5` | `RSI_JUDGE_MODEL` |
| Optimizer | `claude-opus-5-5` | `RSI_OPTIMIZER_MODEL` |

## Data

AgentClinic MedQA-extended cases (MIT), see `data/agentclinic/README.md`. The Kaggle simulated
OSCE interviews can be added as another source in `src/rsi/cases.py` once they have diagnosis labels.
