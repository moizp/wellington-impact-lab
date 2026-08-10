# Wellington Emergency Information Triage

## Introduction

A triage system for Wellington City Council (WCC) emergency management staff. A member of the
public reports a hazard → a fine-tuned AI clarifier asks a follow-up question, then suggests 1-2
actions → that triggers a check against 5 live official NZ data sources for the same location → a
second fine-tuned AI model triages the report's severity in light of that official context → staff
see one prioritised, location-grouped item on a live dashboard.

Built for Impact Lab Wellington (WCC Emergency Management × Claude Code Community NZ), problem
statement 04: *"Help emergency staff sort and prioritise incoming information."* See
[`docs/PITCH.md`](docs/PITCH.md) for the full pitch narrative and demo script,
[`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md) for the system design and API contract, and
[`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) for an honest list of what's incomplete or simplified.

Two small, fully fine-tuned models (Phi-3.5-mini) do the AI work — no third-party LLM API calls,
anywhere.

**Licence:** [Business Source License 1.1](LICENSE) — free to view, copy, and use for development,
testing, and demonstration; production use requires a commercial license from the licensor. The
license converts automatically to Apache License 2.0 on 2030-08-10.

## Prerequisites

- Python 3.10+ and `pip`
- Node.js and `pnpm`
- For local fine-tuning only (not required to run the system): a Mac with Apple Silicon and MLX
  (`mlx_lm`) — see [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md) "Fine-tuning commands" and
  [`.claude/skills/fine-tune-adapter`](.claude/skills/fine-tune-adapter/SKILL.md)
- A deployed backend to point the frontend at (either run one locally, or use an existing Cloud Run
  URL)

## Getting started

**Backend:**
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend** (public report form + staff dashboard, one project, two routes):
```bash
cd frontend
pnpm install
VITE_API_URL=http://localhost:8000 pnpm run dev
```
Open `http://localhost:5173/` for the report form (`?clarify=1` for the two-step Clarifier flow) or
`http://localhost:5173/dashboard/` for the staff dashboard.

**Regenerating training data** (after editing `backend/data/*_examples.csv`):
```bash
.venv/bin/python3 backend/scripts/generate_triage_dataset.py
.venv/bin/python3 backend/scripts/generate_clarifier_dataset.py
```

**Seeding demo reports** against a running backend: `scripts/seed_demo_reports.py`.

Full system design, event schema, and the fine-tune → GGUF → Cloud Run deployment pipeline:
[`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md). What each model is trained on:
[`docs/FINETUNE_PLAN.md`](docs/FINETUNE_PLAN.md). Frontend design:
[`docs/FRONTEND_PLAN.md`](docs/FRONTEND_PLAN.md).

## Benefits of this approach

**Small, self-hosted models, not a third-party API** (see [`docs/PITCH.md`](docs/PITCH.md) "The two
custom LLMs"):
- No per-token cost, no rate limits, no dependency on an external AI vendor's uptime during an
  actual emergency
- Purpose-built and narrow — each model does one job, so its behaviour is testable and its
  failures are traceable, which matters when the output feeds a real emergency-response decision
- Works with degraded connectivity — nothing depends on a live third-party connection, exactly
  when infrastructure is under stress
- Data sovereignty — sensitive emergency information never has to leave infrastructure WCC
  controls
- Financially and environmentally cheaper to run at council scale than routing every request
  through a large third-party model — and that efficiency runs through the whole stack, not just
  the backend: the frontend is built in Svelte rather than React, compiling away the framework
  instead of shipping a virtual-DOM runtime, for smaller downloads and less client-side compute on
  every device

**A long-term strategy, not just a point solution.** The technology choices above aren't only
about this one triage tool — they're what makes this a credible *first step* in WCC gradually
becoming an AI-capable organisation, rather than a one-off pilot that either stalls after the
hackathon or locks the Council into a vendor relationship it doesn't control:

- **Lean, one capability at a time.** Each roadmap step adds one small, well-scoped model or
  feature to the same proven pipeline — not a rebuild (see [`docs/PITCH.md`](docs/PITCH.md)'s
  roadmap). That's a deliberate lean approach: prove a narrow thing works, learn from it, extend
  it, rather than committing to a large upfront platform bet.
- **Socially sustainable, not a black box.** Because the models are small enough to fine-tune
  in-house on a single machine, WCC staff can go through preparing training data, validating
  results, and fine-tuning themselves — real, transferable AI skills built inside the organisation,
  not handed over by an external vendor. The same team keeps iterating as their own understanding
  matures, instead of being permanently dependent on someone else's system.
- **A foundation, not a ceiling.** The architecture is explicitly designed to generalise: the
  national data sources are already NZ-wide (any other council plugs in directly), the two LLMs are
  retrain-not-rebuild for a new region, and the pattern of "one fine-tuned model, one narrow job"
  is the same one used to add the next capability. Every future addition compounds on skills and
  infrastructure the organisation already owns.
- **Honest about limits, by design.** The dashboard always shows the official context and
  plain-language rationale behind a triage judgement — reasoning is visible, never a hidden score.
  [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) exists for the same reason: an organisation adopting AI
  incrementally needs to trust what it's shown, including where the current build falls short.

This is the pitch for why an emergency-triage prototype is also an argument for how WCC could adopt
AI more broadly: start small, keep control, build real capability in-house, and let each step earn
the next one.
