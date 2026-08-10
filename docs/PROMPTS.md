# Build Prompts — Wellington Emergency Information Triage

**Status, updated from the original version of this doc:** the backend is built, tested
end-to-end against real live data, and running — this is no longer "paste into a fresh session to
build from scratch." The frontend hasn't been started. This doc now serves two purposes: a
self-contained context block for a fresh session (paste-ready, doesn't require the other docs to
be loaded), and the actual build prompt for the one thing still genuinely unbuilt — the frontend.

## Project context (paste this into a fresh session for full context fast)

```
"Wellington Emergency Information Triage" — a triage system for Wellington City Council (WCC)
emergency management staff, built for a one-day civic AI hackathon (Impact Lab Wellington, Team
10, problem statement 04).

## What it does

A public report → an AI clarifier asks a follow-up question, then (after the answer) suggests 1-2
actions → that triggers a check against 5 live official NZ data sources for the same location →
a second AI model triages the report's severity in light of that official context → staff see one
prioritised, location-grouped item on a dashboard.

## The two models (both Phi-3.5-mini-instruct, fully fused GGUF, not LoRA adapters swapped on a
shared base — that was the original plan, tried, and dropped; see BUILD_PLAN.md)

- Clarifier: one model, two inference calls, task-conditioned via system prompt (not two models).
  Call 1 ("ask"): report -> a clarifying question, always produced. Call 2 ("act", after the
  submitter answers): report + question + answer -> 1-2 action items from a fixed vocabulary
  (check_neighbours / monitor_situation / document_further / call_111 / evacuate / none).
- Triage Classifier: clarified report + official context + (optional) one related public report ->
  ONLY severity + rationale (fixed template output). hazard_type is never model output —
  deterministic, set by code from the matched official source.

## The event schema (three distinct shapes, not one flat schema — see backend/app/schema.py)

- Event: a triaged public report — the only thing ever stored/displayed. Fields include raw_text,
  clarified_text, clarification_question, clarification_answer, actions, contact (optional,
  collected only on the final step), location {suburb, lat, lon}, official_context,
  related_report_id, hazard_type, severity, rationale, status.
- OfficialEvent: a normalized item from an official source, used only transiently to build
  context. Never stored, never displayed standalone.
- OfficialContextItem: the small deterministic summary of a relevant OfficialEvent shown to staff
  and handed to the Triage Classifier as input.

## The 5 official data sources (all live, all polled on-demand + cached, not always-on background
polling — see "Public-submission-triggered flow" in BUILD_PLAN.md for why)

GeoNet (earthquakes), MetService (severe weather CAP feed, no coordinates — Wellington gazetteer
keyword match instead of distance), NZTA (road events), NEMA (Emergency Mobile Alert CAP
polygons), GWRC (river levels + rainfall telemetry). One module each in backend/app/sources/.

## The API (backend/app/main.py — all implemented, tested)

- GET /health, GET /events (query params: suburb, hazard_type, source_type)
- POST /events/community-report — Phase 1, single-step, no clarifier call
- POST /events/community-report/clarify — Phase 2 step 1 (Clarifier Call 1)
- POST /events/{event_id}/clarification-answer — Phase 2 step 2 (Clarifier Call 2), triggers triage
- CORS is open (allow_origins=["*"]) — no auth on this API by design (see BUILD_PLAN.md "Hosting")

## Deployment

Backend: Google Cloud Run (Always Free tier), model artifacts stored in a private Hugging Face
repo, fetched at Cloud Build build time. Frontend: GitHub Pages (primary, per the hackathon
organisers' preference) + Vercel (live backup) — both deploy on every push, same build output,
different base path / API URL env vars. See BUILD_PLAN.md "Deployment map v2" and
FRONTEND_PLAN.md "Hosting: dual-platform design".

## Authoritative docs, if available in this project

BUILD_PLAN.md (system flow, API, event schema, deployment, fine-tuning commands),
FINETUNE_PLAN.md (what each model trains on, dataset plans, instruction contract),
FRONTEND_PLAN.md (the two frontends' full design — this is what's still unbuilt), PITCH.md (demo
narrative). Everything essential is in this context block already — consult the docs for more
detail, don't block on finding them.
```

---

## Frontend build prompt (paste into a fresh Claude Code session, working in `frontend/`)

```
You are building the frontend for "Wellington Emergency Information Triage" — see the project
context above for what the system does and the full API/schema. The backend is done, tested, and
running; your job is the two views below, against the real API (not a mock — it already exists
and works).

## Repo layout

Work inside a new `frontend/` folder at the repo root, sibling to `backend/`. Don't touch
`backend/` — it's finished. See docs/FRONTEND_PLAN.md if present for the full design; this prompt
has everything essential, but that doc has more detail on open questions (query-param flag name,
static 111 banner, location-precision privacy) that are genuinely undecided, not just omitted here.

## Tech stack

Svelte 5 (runes) + Tailwind + SvelteKit with `adapter-static` (prerendered, not a plain
client-routed SPA — this specifically avoids a GitHub Pages routing problem, see below). TypeScript.

## Two views

1. Public report submission (`/` or `/report`) — Phase 1: a single form (report text + optional
   suburb), with geolocation requested on load (`navigator.geolocation.getCurrentPosition()`,
   fall back to the manual suburb field if declined/unsupported) -> POST /events/community-report
   -> simple confirmation. Phase 2 (behind a feature flag, once the Clarifier is actually
   fine-tuned): same form -> POST .../clarify -> show the question, collect an answer -> on the
   SAME final step, also show an optional contact field (email/phone, free text, no validation) ->
   POST .../clarification-answer with both -> show the returned actions.
2. Staff dashboard (`/dashboard` or `/staff`) — three panels: map (pins by severity), feed (cards
   grouped by location, not by source), detail panel (raw_text/clarified_text, the
   question/answer exchange, actions, rationale on hover, official_context list). Poll GET /events
   every 10-15s.

## Hosting: build for both GitHub Pages (primary) and Vercel (backup), not just one

- Direct fetch() to the full backend URL (baked in at build time via VITE_API_URL) — CORS is
  already open on the backend, so no rewrite-proxy trick is needed, and this works identically on
  both hosts.
- adapter-static with prerendering for both routes — generates real static HTML per route, which
  is what avoids GitHub Pages 404ing on direct navigation/refresh to a client-routed path (it has
  no SPA-fallback by default, unlike Vercel).
- `base` path set via env var — blank for Vercel, a subpath for a GitHub Pages project site unless
  a custom domain is set up.
- Two deploy pipelines, same source: Vercel's git integration (unmodified), plus a GitHub Actions
  workflow that builds with the GitHub Pages base/env values and publishes to Pages.

## Definition of done

- Both views work against the real deployed backend, tested on both hosts, not just one.
- Phase 1 flow works end to end, including a submission with real geolocation coordinates.
- README covering: local dev setup, how to switch API target, how each host is deployed.
```

---

## Backend (for reference — already built, not a prompt to re-run)

The backend is done: FastAPI, all 5 official sources live and tested, both models stubbed with
the final decided interface (real fine-tuned weights not wired in yet — see FINETUNE_PLAN.md "Next
steps" for dataset/training status), deployed pipeline validated end-to-end on Cloud Run via the
OIA project's proven fuse → GGUF → quantize → Cloud Build → Cloud Run path. If further backend
work is needed, start from BUILD_PLAN.md and FINETUNE_PLAN.md directly rather than this doc — they
reflect the current, detailed state; this doc is a summary, not the source of truth.

---

## Integration checklist (once the frontend has working output)

- [ ] Point the frontend's `VITE_API_URL` at the real deployed Cloud Run backend URL, on both hosts
- [ ] Confirm both GitHub Pages and Vercel deployments work, not just one — check both during the integration-test pass in `BUILD_PLAN.md`'s hour-by-hour plan
- [ ] Confirm timestamps display correctly in NZ local time end-to-end
- [ ] Reseed/re-submit fresh community-report examples before recording the demo video — the event store is ephemeral, resets on any Cloud Run cold start
- [ ] Run through the full demo storyboard (see `PITCH.md`) end-to-end against the real integrated system
- [ ] Remove all references to the OIA project from every doc before the final commit (see `BUILD_PLAN.md`'s hour-by-hour plan for the checklist item)
