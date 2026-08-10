# Frontend Plan — Wellington Emergency Information Triage

Two separate frontends, one build (per `BUILD_PLAN.md`'s "Deployment map" — same project, separate routes, not two separate apps). Both work against the local backend first, then get deployed once working end-to-end locally.

**✅ Deploy target, decided: both, at all times** — **GitHub Pages is primary** (the organisers'
preference, and what gets shown/linked during judging), **Vercel is a live backup**, not an
emergency-only manual step — both get deployed on every push, so if GitHub Pages has an issue
during the live demo slot, the Vercel URL is already up to date and ready, not something built on
the fly under pressure. Nothing has been built yet, so this is designed in from the start rather
than retrofitted — see "Hosting: dual-platform design" below for the concrete decisions that make
the same build output work on both hosts with no code differences.

## 1. Public report submission

**Who:** a member of the public reporting a possible hazard. No login, no install, works on any phone.

**Route:** `/` (or `/report` — pick whichever reads better once the dashboard route is also decided)

**Phase 1 (build this first — matches the backend's current default flow):**
- A single form: free-text report + optional suburb
- On load, request the browser's Geolocation API (`navigator.geolocation.getCurrentPosition()`) —
  if granted, send `lat`/`lon` alongside the form instead of (or in addition to) the suburb field;
  if declined or unsupported, fall back to the manual suburb field exactly as before. No backend
  changes needed for this — `CommunityReport` already accepts optional `lat`/`lon`, and
  `context.resolve_location()` already prefers real coordinates over the suburb centroid whenever
  both are present
- Submit → `POST /events/community-report` → show a simple "thanks, we've got it" confirmation
- No question, no answer, no actions, no contact field — this is what's actually wired up in the
  backend today, and stays intentionally minimal/low-friction as the fallback flow

**Phase 2 (behind a feature flag, built once the Clarifier is actually fine-tuned):**
- Same initial form (including the geolocation prompt above), but submit calls
  `POST /events/community-report/clarify` instead
- Show the returned `clarification_question`, collect an answer
- **Final step**: alongside the answer, show an *optional* contact field (email or phone, free
  text, no validation) — deliberately placed here, not on the first form, to keep initial friction
  low; only ask once the submitter is already invested in the exchange. Submit both together to
  `POST /events/{event_id}/clarification-answer`
- Show the returned `actions` (1-2 suggested next steps) as the actionable response — this is the
  "genuine two-way exchange" the pitch describes
- **⚠️ Open decision, not yet made:** the query-param name that toggles Phase 2 on (flagged in `BUILD_PLAN.md`'s API section — needs picking, e.g. `?clarify=1`, before this gets built)
- **⚠️ Open decision, not yet made:** whether a static "if this is a life-threatening emergency, call 111" banner is always shown regardless of the model's suggested actions (deferred from an earlier discussion — see `FINETUNE_PLAN.md`'s Clarifier limitation note). **New evidence since that discussion**: the hackathon organisers' own README states this as a ground rule for the whole event — *"These are hazard-planning layers, not live emergency information. In an emergency, call 111"* — applied to the underlying GIS data, not our Clarifier specifically, but it's the organisers' own house style for this exact kind of disclaimer. Doesn't resolve the decision on its own, but is a real data point in favour of including it, and suggests matching their wording rather than inventing our own if we do.
- **⚠️ Open decision, not yet made — location privacy:** real GPS coordinates can be precise enough
  to identify a submitter's home address. Currently no rounding/fuzzing planned — see
  `BUILD_PLAN.md`'s API section for the full tradeoff (accuracy vs. identifiability), needs a
  decision (and probably Sara's community-sensitivity review) before this reaches real users.

**Why not push notifications for the council-follow-up need:** considered and deliberately not
built for this pass — real push requires a service worker, explicit permission UX, push
subscription storage tied to a specific report, and a new backend push-sending dependency (none of
which exist today), plus a staff-facing "notify this submitter" trigger. The optional contact field
above achieves the same underlying goal (council can reach back out) with none of that
infrastructure. Real push notifications are a reasonable roadmap item, not this build — see
`PITCH.md`'s Slide 9 (2-3 months tier) for the pitched version: an installable PWA with push to
either a single submitter or a group of users in an affected area, positioned as a two-way
complement to NEMA's one-way Emergency Mobile Alert, not a duplicate of it.

**UI:** one screen, minimal — a text area, a suburb field (with geolocation as the preferred,
auto-filled alternative), a submit button, and (Phase 2) a second step for the
question/answer/contact/actions exchange. No map, no feed, nothing staff-facing.

## 2. Staff dashboard

**Who:** WCC emergency management staff during an activation. No login for the demo (per `BUILD_PLAN.md`).

**Route:** `/dashboard` (or `/staff`)

**Layout — three panels** (already specified in `BUILD_PLAN.md`'s "Frontend" section, restated here as the frontend-specific brief):
- **Map** — Wellington suburbs, pins coloured by `severity`
- **Feed panel** — cards grouped by `location` (not by source — official-source data never appears standalone, only inside a report's `official_context`), each card showing `hazard_type`, `severity`, and time
- **Detail panel** — `raw_text`/`clarified_text`, the `clarification_question`/`clarification_answer` exchange, the suggested `actions` (Phase 2), the Triage Classifier's `rationale` (on hover), and the `official_context` list

**Data flow:** `GET /events` polled every 10-15s (`setInterval`), no push mechanism needed — same design as documented.

## Tech stack

Svelte 5 (runes) + Tailwind + Vite, per the original project stack decision. **SvelteKit with
`adapter-static`**, not a plain Vite SPA — see "Hosting" below for why this specific choice is
what makes GitHub Pages work without a client-side-routing hack.

## Hosting: dual-platform design

**The `vercel.json` rewrite-proxy pattern from the OIA project is deliberately not used here** —
GitHub Pages has no server-side rewrite capability at all (it's pure static file hosting), so
anything relying on that pattern wouldn't be portable. Instead:

- **Direct `fetch()` to the full backend URL**, not a relative path proxied through the host. This
  works because `CORSMiddleware` (`allow_origins=["*"]`) is already on the backend (see
  `BUILD_PLAN.md`'s API section) — no proxy is needed to avoid CORS issues, which was the actual
  reason the Vercel rewrite pattern existed in the OIA project. The backend's full URL gets baked
  in at build time via `VITE_API_URL`, read the same way regardless of host.
- **`adapter-static` with prerendering** for both routes (`/` and `/dashboard`) — generates real
  static HTML files per route (`index.html`, `dashboard/index.html`), not a client-side-routed SPA
  that needs a fallback trick. GitHub Pages 404s on direct navigation/refresh to a client-routed
  path with no fallback configured; prerendered routes sidestep the problem entirely because each
  one is a genuine file at a real path. Works identically well on Vercel — not a tradeoff between
  the two hosts, just the right choice for two known, simple routes.
- **`base` path set via env var at build time** — blank for Vercel (serves from its assigned
  root) or a custom domain, `/wellington-impact-lab/` (or whatever the repo is named) for a GitHub
  Pages *project* site, since those serve from a subpath unless a custom domain is configured.
  Needs deciding once the actual repo/org name for the demo is confirmed.
- **Deploy mechanism differs, code doesn't**: Vercel's git integration builds automatically;
  GitHub Pages needs a GitHub Actions workflow that runs the build and publishes the output to the
  `gh-pages` branch (or the newer "deploy from Actions" Pages source) — a pipeline difference, not
  a frontend code difference.

**Both hosts deploy on every push, not just GitHub Pages** — since Vercel is a *live* backup, not
a break-glass manual step, it needs to stay genuinely current. Concretely: Vercel's own git
integration keeps doing its normal thing unmodified; a `.github/workflows/deploy-pages.yml`
workflow builds the same repo with `base=/wellington-impact-lab/` (GitHub Pages) instead of
Vercel's blank `base`, and publishes to Pages — two build jobs, same source, different `base`/
`VITE_API_URL` values, both triggered by the same push. Both URLs should be checked as part of the
integration-test pass in the Hour-by-hour plan, not just the primary one, so a Pages-specific
issue (e.g. the subpath `base` being wrong) doesn't surface for the first time during judging.

## Local-first workflow

1. **Backend running locally first**, both frontends point at it:
   ```
   cd backend && uvicorn app.main:app --reload --port 8000
   ```
2. **Frontend dev server**, `VITE_API_URL` pointed at `http://localhost:8000` for local dev — same
   direct-fetch approach used in both deployed hosts, not a dev-only proxy that diverges from prod
3. Build and test **both** frontends against the real local backend — including the actual Phase 1 submission flow and, once Phase 2 exists, the full clarify/answer/action exchange — before anything gets deployed
4. **Then deploy to Vercel and/or GitHub Pages**, each with `VITE_API_URL` set to the deployed Cloud Run URL and `base` set appropriately for that host (see "Hosting" above)

## Proposed project structure

```
wellington-impact-lab/
├── backend/        (exists)
├── frontend/        (new)
│   ├── src/
│   │   ├── routes/
│   │   │   ├── +page.svelte           # public submission (Phase 1 + Phase 2)
│   │   │   └── dashboard/+page.svelte  # staff dashboard
│   │   └── lib/                       # shared API client, types matching Event schema
│   └── svelte.config.js               # adapter-static config
├── .github/workflows/deploy-pages.yml # new — GitHub Pages build+publish
└── docs/
```

## Open questions before/while building

- Phase 2 query-param flag name (see above)
- Static 111 banner — always shown or not (deferred, see above)
- Location precision/privacy — store real GPS coordinates as given, or round before persisting (see above)
- Exact route names (`/report` vs `/`, `/dashboard` vs `/staff`)
- Whether the public form and staff dashboard are one project with two routes (as drafted here, matching `BUILD_PLAN.md`) or genuinely separate projects — no reason found yet to deviate from the one-project design, flagging only because it hasn't been explicitly re-confirmed since the two-call Clarifier work changed the public form's shape
- Whether a custom domain gets set up for GitHub Pages — would remove the subpath `base`
  complication entirely, but isn't required (the subpath approach works fine without one)

**Resolved this pass:** council-follow-up mechanism — optional contact field on the final step, not push notifications (see above for why). Geolocation — build it, cheap and already supported end-to-end by the backend. Dual-host portability (Vercel + GitHub Pages) — direct-fetch + `adapter-static` + build-time `base`/`VITE_API_URL`, no platform-specific rewrite tricks (see "Hosting" above). **GitHub Pages is primary, Vercel is a live backup** — both deploy on every push, both get checked during integration testing, not just the primary.
