# rsi-doc: a self-improving diagnosis harness

An AI doctor interviews simulated patients and submits a diagnosis, and the diagnosis is scored
against the answer key. A Claude Code meta-agent then studies the failures and rewrites the doctor's
harness (prompt, lessons, skills, budgets). A new version is kept only if it diagnoses
more held-out patients correctly.

Everything runs on the **Claude Agent SDK**, so it can use a Claude subscription.

## Doctor Live voice demo

Talk to the doctor yourself while acting as a fictional patient. The web app provides a patient
role card, suggested phrases, a microphone visualization, a live transcript, and a reference
diagnosis visible only to you. The OpenAI doctor asks follow-up questions, can request recorded
exam/test findings, and submits an assessment to compare with the answer key.

```bash
uv sync
cp .env.example .env     # if you do not already have .env
# Add OPENAI_API_KEY to .env when ready; the UI and scripted text preview work without it.
uv run rsi live
```

Open **http://localhost:8000**, select a patient, and click **Start voice visit**. Allow microphone
access, then talk naturally; the doctor opens the conversation and pauses for your answers. You
can interrupt, mute, type replies, reveal the reference diagnosis, and export the transcript.
Click **End consultation** to release the microphone. A new visit clears the previous transcript.
Use the **text preview** to explore the interface without a key; it uses explicitly labeled,
scripted questions and does not generate or grade a diagnosis.

The key is read only by the Python server, never returned to the browser. This demo needs an OpenAI
API project with billing and access to the configured model; it does not use a ChatGPT subscription
or the Claude token. The voice model defaults to `gpt-realtime` (`RSI_REALTIME_MODEL` overrides it).
The separate findings selector and grader use `gpt-4.1-mini` (`RSI_LIVE_HELPER_MODEL` overrides it).
After adding or changing the key in `.env`, restart the server. You can choose another port with
`uv run rsi live --port 8001`.

The app binds to loopback by default. Microphone access requires localhost or HTTPS. For a remote
demo, set `RSI_LIVE_PASSWORD` in `.env`, restart the server, and use an HTTPS tunnel or reverse proxy.
The shared password protects the app and every API endpoint. Sign-in uses an HttpOnly session
cookie (Secure over HTTPS) and rate limits wrong-password attempts. Leave the password blank for
local-only use. Voices are sent to OpenAI over WebRTC. Transcript and
patient UI state stay in the browser; per-visit tool and assessment state is held in server memory.
Visits expire after an hour and are removed on the next access/new visit or server restart.
Export downloads a local text file; no audio is recorded
by the app.

Only **training cases** are offered. The doctor receives demographics and the promoted harness's
lessons, not the patient notes, symptom hints, or reference answer. Physical findings are returned
only on request by a separate record selector; the server supplies the original selected values
with diagnosis names/acronyms redacted. Unrecorded results are labeled unavailable. Ten exam/test
requests are allowed. Assessment grading runs separately, and its answer/score goes only to the UI,
never back into the doctor conversation. A person can still intentionally reveal the answer by
saying it aloud; the demo does not filter human speech.

Implementation: `src/rsi/live.py` and `src/rsi/live_static/`. Run `uv run pytest` for offline API,
privacy, error handling and tool lifecycle checks. Voice media and real model behavior require
a microphone, network access and an API key for a live smoke test. This adapts the doctor harness
for an OpenAI voice model; it does not represent the Claude harness's benchmark accuracy.

For the browser integration checks, start the server, install Playwright in a temporary folder,
and run the script below. It uses local Chromium and synthetic media/mocked Realtime events;
it makes no OpenAI requests and does not access your physical microphone.

```bash
npm install --prefix /tmp/rsi-browser playwright
NODE_PATH=/tmp/rsi-browser/node_modules node tests/browser_live.cjs
```

Set `CHROMIUM_PATH` if Chromium is elsewhere, `RSI_DEMO_URL` for a different URL, and
`RSI_DEMO_PASSWORD` when testing a password-protected demo.

API references: [WebRTC sessions](https://developers.openai.com/api/docs/guides/voice-webrtc),
[Realtime conversations and tools](https://developers.openai.com/api/docs/guides/realtime-conversations),
and [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

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
