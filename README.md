# rsi-doc: a self-improving diagnosis harness

An AI doctor interviews simulated patients and submits a diagnosis, and the diagnosis is scored
against the answer key. A Claude Code meta-agent then studies the failures and rewrites the doctor's
harness (prompt, lessons, skills, subagents, budgets). A new version is kept only if it diagnoses
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
uv run rsi episode --case mqx-000         # watch one consultation
uv run rsi eval --split dev --limit 5     # quick sanity check
uv run rsi eval --split dev               # baseline on all 40 dev cases
uv run rsi improve --generations 3        # the self-improvement loop
uv run rsi report                         # runs/report.html
uv run rsi eval --split test --final      # once, at the end
uv run pytest                             # offline tests, no model calls
```

`improve` options: `--train-batch 30` (failures shown to the optimizer), `--dev-limit N` (faster,
noisier gate), `--candidates K` (parallel proposals per generation), `--min-confidence 0.75`
(required bootstrap P(candidate beats parent)), `--commit` (git commit + tag each promoted version).

## Layout

| Path | What |
|---|---|
| `harnesses/vNNN/` | One harness version: `system.md`, `lessons.md`, `config.json`, optional `.claude/skills/`, `.claude/agents/` |
| `harnesses/registry.json` | Every version and rejected candidate, with scores and hypotheses |
| `src/rsi/clinic.py` | Frozen environment: patient and examiner prompts, the doctor's clinic tools (in-process MCP) |
| `src/rsi/judge.py` | Frozen grader: exact match, then an LLM judge |
| `src/rsi/runner.py` | Runs episodes and evals, with traces cached per harness digest in `runs/cache/` |
| `src/rsi/optimize.py` | Evidence builder, optimizer session, dev gate, registry |
| `src/rsi/report.py` | Static HTML report |
| `runs/` | Episode traces, eval summaries, optimizer workspaces (gitignored) |

## Guardrails against the loop cheating

- The doctor gets only the four clinic tools. File, shell and web tools are disabled
  (`permission_mode="dontAsk"`), and its working directory is a temporary copy of the harness.
- The optimizer can read only its workspace (the harness copy plus train-split evidence). A
  `PreToolUse` hook blocks writes outside the editable harness files.
- The doctor model is locked across versions, so gains come from the harness, not a model swap.
- The patient, examiner and judge live in code the optimizer never sees. Episodes where a frozen
  role says the answer out loud are flagged as `leak`.
- Promotion is decided on dev cases the optimizer never sees. Test is scored once with `--final`.

## Models

| Role | Default | Override |
|---|---|---|
| Doctor | `claude-haiku-5-5` | `harnesses/v000/config.json` (before the first improve run) |
| Patient, examiner | `claude-haiku-5-5` | `RSI_PATIENT_MODEL`, `RSI_EXAMINER_MODEL` |
| Judge | `claude-sonnet-5-5` | `RSI_JUDGE_MODEL` |
| Optimizer | `claude-opus-5-5` | `RSI_OPTIMIZER_MODEL` |

## Data

AgentClinic MedQA-extended cases (MIT), see `data/agentclinic/README.md`. The Kaggle simulated
OSCE interviews can be added as another source in `src/rsi/cases.py` once they have diagnosis labels.
