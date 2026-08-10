# Wellington Emergency Information Triage — Claude Code Project Instructions

## Event context

Impact Lab Wellington, Team 10, problem statement 04 ("Help emergency staff sort and prioritise
incoming information"). One-day build with Wellington City Council Emergency Management, Saturday
8 August 2026, Waimanga Room, WCC. Ten teams, five problem statements, two teams per statement.

| Time | What |
|---|---|
| 08:00 | Arrival and mingle |
| 09:00 | Opening address & problem briefing |
| 09:30 | Build begins |
| 12:30 | Lunch + lightning talks |
| 16:00 | Submissions close (2-minute video + repo) |
| 16:30 | Live demo (4 minutes) + judging |
| 17:45 | Awards + next steps |

Judging rewards a narrow thing that works over a broad thing that doesn't demo. Each prototype is
meant to be a module in a shared **common operating picture** — prefer outputs that compose
(a feed, an API) over a closed-off UI nothing else can read. `GET /events` already satisfies this.

## What this system does

Public reports a hazard → an AI clarifier asks a follow-up question, then suggests 1-2 actions →
that triggers a check against 5 live official NZ data sources for the same location → a second AI
model triages the report's severity in light of that official context → staff see one prioritised,
location-grouped item on a dashboard. See `docs/BUILD_PLAN.md` ("System summary",
"Public-submission-triggered flow") for the full flow, and `docs/FINETUNE_PLAN.md` for what each
model is actually trained on.

**Two fine-tuned models, not one, and not adapters swapped on a shared base** — two fully-fused
GGUF models loaded simultaneously in one Cloud Run service:
- **Clarifier**: one model, two inference calls (task-conditioned via system prompt, not two
  models) — Call 1 asks a question, Call 2 (after the answer) suggests actions. See
  `docs/FINETUNE_PLAN.md` "Model 1 — Clarifier".
- **Triage Classifier**: outputs *only* `severity` + `rationale`. `hazard_type` is always
  deterministic (set by code from the matched official source), never model output. See
  `docs/FINETUNE_PLAN.md` "Model 2 — Triage Classifier" for why.

## Tech stack

- **Backend**: Python, FastAPI, `httpx` for source fetching, Pydantic schemas. No database —
  in-memory store, ephemeral by design for this prototype.
- **Frontend**: Svelte 5 (runes) + Tailwind + SvelteKit (`adapter-static`, prerendered — not a
  plain SPA, see `docs/FRONTEND_PLAN.md` for why). Not yet built.
- **Fine-tuning**: MLX (`mlx_lm.lora`) on Apple Silicon, base model `microsoft/Phi-3.5-mini-instruct`.
- **Deployment**: backend on Google Cloud Run (Always Free tier); frontend on **GitHub Pages
  (primary) + Vercel (live backup)**, both deployed on every push.

## Key commands

```bash
cd backend && uvicorn app.main:app --reload --port 8000    # run backend locally
.venv/bin/python3 scripts/generate_triage_dataset.py       # regenerate Triage Classifier dataset
.venv/bin/python3 scripts/generate_clarifier_dataset.py    # regenerate Clarifier dataset
```

Fine-tuning commands (run manually, one per terminal, not automated) are in `docs/BUILD_PLAN.md`
"Fine-tuning commands" — they require the `myenv` venv where `mlx_lm` is actually installed
(`source /Users/moiz/Documents/Courses+Trainings/Understanding-Open-AI-Workspaces/jupyter/myenv/bin/activate`),
not this repo's own `.venv`.

## Architecture conventions

- **Deterministic vs. model-inferred, kept strictly separate.** `hazard_type` is always code, never
  a model. Only judgement calls that genuinely need inference (is this report serious, what
  question should we ask) go to a model. See `app/context.py`'s docstring.
- **Canonical render functions.** The exact same function that renders context into text for
  training data must be used at live-serving time (`context.render_context_text()`,
  `classifier.build_user_message()`, `clarifier.build_act_user_message()`) — never hand-type an
  approximation in two places. This discipline exists because a composite-input model (report +
  context) has a training/serving drift risk a raw-text-only model doesn't.
- **Every new official data source gets verified against live data before its rules are trusted** —
  not assumed from documentation. This project has hit real bugs this way more than once (NZTA's
  recency filter, GWRC's NZ-local-time-not-UTC timestamps, a live "TEST MESSAGE" alert with
  `severity: Severe` that would have been dangerously misleading if surfaced as real). See
  `.claude/skills/add-data-source`.
- **CSV-driven training datasets, not hand-authored JSONL.** Non-engineers can add rows directly;
  a generation script builds the actual JSONL via the canonical functions above and round-trip
  validates every row before accepting it. See `.claude/skills/fine-tune-adapter`.

## Important paths

- `docs/BUILD_PLAN.md` — the master build plan: system flow, API contract, event schema, hour-by-hour schedule, deployment map, fine-tuning commands
- `docs/FINETUNE_PLAN.md` — what each model is trained on: instruction contract, dataset plan, taxonomy, official-context format
- `docs/FRONTEND_PLAN.md` — the two frontends' design, not yet built
- `docs/PITCH.md` — the pitch/demo narrative, including the video storyboard and the still-unplanned 4-minute live demo slot
- `backend/app/sources/` — one module per official data source (`geonet.py`, `metservice.py`, `nzta.py`, `nema.py`, `gwrc.py`)
- `backend/app/context.py` — the aggregator (deterministic context-building, never an LLM call)
- `backend/app/classifier.py` / `backend/app/clarifier.py` — the two models' interfaces (currently stubs with the decided contract, real fine-tuned models not wired in yet)
- `backend/data/*_examples.csv` + `backend/scripts/generate_*_dataset.py` — training data source + generation

## Constraints that matter here

- **Hazard-planning data, not live emergency information.** Never present anything this system
  infers or aggregates as confirmed fact. In an emergency, 111 — this is the organisers' own ground
  rule, relevant to the still-open "static 111 banner" decision (see `docs/FRONTEND_PLAN.md`).
- **This repo must stay free of personal information** — no participant names, contact details, or
  application material. Note this is a different, stricter bar than the in-app `contact` field
  submitters can optionally provide (that's user data in the running system, not repo content).
- **Data attribution** — the 5 official sources belong to their publishers (MetService, GeoNet,
  NZTA, NEMA, GWRC); licence terms vary, check before publishing anything derived.
- **Remove all references to the OIA project** (this build's internal validation reference) from
  every doc before the final commit — see the checklist item in `docs/BUILD_PLAN.md`'s
  hour-by-hour plan.

## Skills

- `.claude/skills/add-data-source` — adding/modifying an official-source poller
- `.claude/skills/fine-tune-adapter` — preparing data for, training, or exporting either model
