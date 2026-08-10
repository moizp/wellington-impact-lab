# Pitch Draft — Wellington Emergency Information Triage

Slides are not required for submission. Only a 2-minute video (and source code) will be submitted. Slide sections below are meant for internal/team understanding and agreement of the solution and as content for making the 2-minute demo video (detailed at the end of this doc).

---

## Slide 1 — Title

**Wellington Emergency Information Triage**
*Turning public information into a working triage tool for emergency staff — before and during an emergency.*

Team 10: [Team name]

---

## Slide 2 — The problem

- WCC's emergency management team has run **10 activations in the past two years**
- During an activation, information arrives from many places at once: official warnings, sensor data, road incidents, and community reports — all in different formats, at different speeds, with different trust levels
- Staff don't have time to manually read, cross-reference, and prioritise every incoming item while an emergency is unfolding
- **Emergency decisions are only as good as the information flow behind them** — this is a triage and efficiency problem, not a data-availability or access problem

**Problem/Track:** "Help emergency staff sort and prioritise incoming information"
- Every public report is automatically checked against live official data (weather warnings, earthquakes, road events) and triaged by severity — turning a raw, unverified message into a prioritised, location-grouped item a staff member can act on

**Contributing to other tracks:** "Create a two-way information channel between communities and Council" and "​Identify and verify emerging local impacts from public information"
- Every public submission gets an immediate, AI-generated follow-up question and then a proposed action, from a custom fine-tuned LLM. A two-way exchange at scale, not a one-way form drop
- Information from the public is resulting in identification of emerging local impacts

**Solution Overview:** a member of the public submits a report → gets a clarifying follow-up immediately with potential action → that clarified report is checked against live official sources automatically for the same location → the system produces one triaged, prioritised item for staff to action.

---

## Slide 3 — Lean Canvas at a glance

Use this as a fast-orientation slide right after the problem statement — it forces the whole pitch to hang together and gives judges the shape of the business/adoption case in one view, not just the tech.

| Block | Content |
|---|---|
| **Problem** | Fragmented, high-volume, mixed-trust information during an emergency activation; no fast way to sort/prioritise it; no reliable two-way channel to trusted community groups |
| **Whose problem is it** | **WCC emergency management staff** during an activation (some of these might be in the room today). Secondary: **trusted community anchors** — marae, community centres, community patrol groups — who currently have no low-effort way to feed local, on-the-ground information back to Council |
| **Existing alternatives** | Manually monitoring multiple websites/feeds/radio/phone/email/social media by hand; GeoNet; MetService App; Emergency Mobile Alert (broadcast-only, one-way); NZ Flood Pics |
| **Unique value proposition** | A living, prioritised triage feed built from Wellington's own open data plus small custom-trained AI — so staff spend their time deciding, not searching and cross-referencing. Foundation to iteratively build more capability. |
| **Solution** | Every public report triggers immediate AI clarify, then a live check against official data for that location, then AI triage — prioritised staff dashboard grouped by location; roadmap to offline-capable hardware nodes |
| **Channels — how users access it** | Staff: a web dashboard, no install, any device with a browser (see Slide 6). Community reporters: a simple web submission form today; Future: SMS/radio hardware nodes in the resilience-layer roadmap for when connectivity is down |
| **Key metrics** | Time from public submission → clarified & triaged; % of triage judgements confirmed correct by staff feedback; number of official sources successfully checked per submission; % of submissions that receive a clarifying follow-up (target: 100%) |
| **Unfair advantage** | A proven, validated fine-tune-to-deploy pipeline (already tested end-to-end on real infrastructure), informed by domain expertise, user research, UX best practices, and a small-model architecture that avoids per-token cost and vendor lock-in |
| **Revenue Streams** | Phased: start with Wellington City Council as the founding/reference customer (pilot, likely grant or council-funded); once proven, can **licence the same system to other NZ councils** on a subscription/usage basis — the national-data layer and AI adapters already generalise (see Slide 10), so marginal cost per new council is low; longer-term, **market internationally** to other cities/regions facing the same emergency-information-triage problem, once local data integrations exist for that market |
| **Cost structure** | One-time fine-tuning compute (a MacBook Pro), free-tier hosting at pilot scale (Hugging Face Spaces + Google Cloud Run + Vercel/Github Pages); can be scaled up on demand; future costs are mainly the optional hardware resilience layer and paid hosting once usage outgrows free tiers |

---

## Slide 4 — What we built (components/show with roadmap)

A system where every public report is instantly followed up on, checked against live official data, and turned into a triaged, prioritised item for staff — with two small custom-trained AI models doing the work, on lean infrastructure that costs nothing at pilot scale.

- Frontend for public report: public submission → immediate AI-generated clarifying question → AI-generated proposed action → submission checked against 5 real live official data sources for the same location → triaged and prioritised automatically
- Two custom fine-tuned LLMs doing the clarify, action, and triage work
- A staff-facing dashboard: prioritised feed grouped by location, map, detail view showing exactly which official data informed each triage judgement (model reasoning shown, not hidden)
- Middleware: polling, aggregating/normalising

---

## Slide 5 — Data flow

[Diagram: public report → clarify LLM question → public more info → clarify LLM action → trigger poll of official sources (cached/throttled) → aggregator/normalise → classifier LLM → store → dashboard]

**The pipeline starts with a public report, not a background feed:**
1. A member of the public submits a report (form today; social media in a later phase)
2. The **clarifier** immediately generates a follow-up question — every submission gets one, not just ambiguous ones
3. Once the submitter answers, the same clarifier model runs again and suggests 1-2 concrete next steps, shown directly on the form as an immediate, actionable response
4. That exchange **triggers a check against live official data** for the same location — this is also what keeps our free-tier cloud hosting warm exactly when it's needed, rather than paying to keep it running 24/7
5. An aggregation step pulls just the officially-relevant context for that location
6. The **classifier** takes the clarified report plus that official context and produces one triage judgement — genuinely new information, not a restatement of what the official sources already say on their own
7. Staff see one prioritised, location-grouped item, with the official context that informed it fully visible

**Real official data sources checked against (live, not simulated):**
- MetService CAP (Common Alerting Protocol) feed — official severe weather warnings (same feed Civil Defence uses)
- GeoNet API — earthquake and volcanic alert data
- NZTA road events — real-time road incidents and closures
- NEMA Emergency Mobile Alert CAP polygons — the actual broadcast areas of declared civil defence emergencies (added after the hackathon organisers' data catalogue was released)
- GWRC river levels + rainfall telemetry — live flow/stage/rainfall readings across the region (also added from that catalogue; this is what our earlier GWRC gauge investigation was actually looking for, just via the wrong endpoint)

**Simulated layer:**
- Public reports — no public live channel exists yet for this hackathon build, so we simulate incoming reports to demonstrate the clarify and triage pipeline. (Also referenced in next steps/roadmap).

**Why triage the public report, not the official sources directly:** each official source already publishes its own severity signal (GeoNet's magnitude, NZTA's impact rating, MetService's warning level) — reclassifying that with an LLM would just be a slower, less reliable version of information already available for free. The genuinely hard, valuable problem is judging an *unverified public claim* in light of what's officially known — that's where the AI adds real value, and it's the only thing our classifier does.

---

## Slide 6 — Channels: how users actually reach this

*(Expands on the Lean Canvas "Channels" block)*

- **Emergency staff (primary user):** open a URL in any browser — no install, no account setup required for the pilot. Designed to sit alongside existing tools, not replace them; long-term integration target is pushing prioritised alerts into whatever system WREMO (Wellington Region Emergency Management Office) staff already operate from (see roadmap), rather than asking staff to watch a new screen
- **Community reporters (secondary user), today:** a simple public web form — low friction, works on any phone
- **Community reporters, future:** dedicated low-bandwidth hardware nodes (radio/SMS) at trusted anchor sites — marae, community centres, patrol groups — for when the web form itself isn't reachable
- **Council decision-makers, future:** a backup low-bandwidth device/view surfacing only the highest-severity items, for when the primary dashboard's connectivity path is degraded

---

## Slide 7 — The two custom LLMs (the core of the demo)

**Why custom fine-tuned models, not a generic large LLM API call:**

1. **Small and efficient** — each fine-tuned model is a 3-4B parameter model running on free/low-cost cloud CPU hosting; no per-token API cost, no rate limits, no dependency on an external AI vendor's uptime during an actual emergency
2. **Purpose-built, not one-size-fits-all** — each model is fine-tuned on the same small base architecture for one narrow job. Adding a new AI capability later means fine-tuning and deploying another small model on the same proven pipeline, not re-architecting anything
3. **Auditable at small scale** — each model is trained and evaluated on a specific, narrow task, so its behaviour is testable and its failures are traceable — important where the output feeds a real emergency-response decision
4. **Works with degraded connectivity** — a small self-hosted model doesn't require a live connection to a third-party AI provider, which matters exactly when infrastructure is under stress
5. **Socially sustainable** — because the models are small enough to fine-tune in-house, the staff can go through preparing the training dataset, validating results, and fine-tuning the models themselves, rather than being handed a black-box tool built and controlled elsewhere. That builds real, transferable AI skills in-house — dataset preparation, evaluation, fine-tuning — and means the same team keeps iterating and building further capability as their own understanding matures, helped by a provider, compared to being fully dependent on a third party AI system
6. **Efficient frontend too, not just the models** — both the public report form and the staff dashboard are built in Svelte, not React or another virtual-DOM framework. Svelte compiles away the framework itself at build time into small, dependency-light vanilla JS, rather than shipping a runtime library with the web app that also does virtual-DOM diffing in the browser — smaller downloads and less client-side CPU/battery use on every device that loads it, including the low-end phones the public-submission form specifically needs to work well on. The efficiency-and-sustainability angle runs through the whole stack, not just the backend models

**Model 1 — Clarify and action:** runs in two steps on every single public submission, not reserved for ambiguous reports only — that's what makes the two-way channel real rather than occasional. First, it generates a targeted follow-up question immediately, before anything else happens. Once the submitter answers, the same model runs a second time and suggests 1-2 concrete next steps — anything from checking on neighbours through to calling 111 — shown directly on the submission form as an immediate, actionable response, not just "thanks, we've logged it." *(Honesty about limits: at this stage the suggestion is based only on the report and the clarifying answer, not yet checked against official data — the roadmap includes a dedicated model for the highest-stakes suggestions, informed by official corroboration once that check has happened, rather than combining every stakes level into one early, unverified step long-term.)*

**Model 2 — Triage:** takes the clarified public report *together with* the relevant live official data for that location (weather warnings, earthquakes, road events) and any related recent public report nearby, and outputs a severity level plus a one-line rationale — nothing else. Hazard type is assigned by simple deterministic rules, not the model (each official source already implies one — an earthquake feed is an earthquake). Deliberately **not** used to re-classify official sources on their own: those already publish their own severity signal, so the AI is reserved for the one genuinely hard problem — judging an unverified public claim against official and community reality, with its reasoning shown in plain language, not a black-box score.

*(Demo moment: submit a public report live, watch the clarifying question appear immediately, answer it and watch a suggested next step appear, then watch the triaged result appear checked against real official data for that location.)*

---

## Slide 8 — What makes this credible, not just a demo

Address the judging criteria directly:

- **Usefulness to WCC:** fully addresses the primary track — every public report gets prioritised against real official data — and the secondary track (two-way community channel) is addressed on every single submission, not just ambiguous ones
- **Working with supplied data:** the official-data check is built against 5 real live feeds
- **Working demo:** live clarify + live triage against real official data, not a canned screenshot
- **Honesty about limits:** use simulated public reports (the public-submission channel itself, since no live public feed exists to test against yet) and why
- **Credible path to real use:** see roadmap — each step is small, concrete, and tied to a specific gap we already identified
- **Modular architecture:** different data sources can be added gradually, front-ends can be added/improved independently, back-end can scale on demand, more AI can be baked in iteratively

---

## Slide 9 — Roadmap (with estimated timeline)

**2 weeks:** harden the prototype — build a labeled evaluation set for the classifier, add duplicate/cluster detection so repeated reports don't flood the feed, move off in-memory storage, and stand up a **test → demo → production release cadence** so future changes to the classifier, clarifier, or dashboard can be validated in a safe environment before reaching real users. 

**1 month:** Add a **confidence signal alongside severity**: the Triage Classifier currently outputs severity + rationale only — extending its output to also infer how confident it is in that judgement (given how vague the report is, and how strong the official corroboration is) lets us combine the two into one **final priority score**, rather than treating every "high severity" call as equally trustworthy. A high-severity, high-confidence report (concrete detail, strong official match) should surface first; a high-severity but low-confidence one (vague, no corroboration) is exactly the case that should be flagged for a human to check rather than either auto-elevated or silently trusted. This is a genuinely small extension — same model, same training pipeline, one more field in the fixed-template output — not a new architecture, which is why it fits this early hardening phase rather than a later one.

**2-3 months:** pilot with WCC — replace the simulated public-submission channel with a real one (live form or existing channel; social media as a second input channel), add a manual/on-demand staff trigger for pulling official data on request (not just public-submission-triggered), retrain the triage model on real pilot data, add staff login. Note: verifying public reports against official context — originally planned as a future adapter — already ships as the core of the classifier's job from day one, so this phase is about refining that with real data, not building it from scratch. This phase also turns the public report form into a full **installable PWA with push notifications** allowing council staff to push a targeted follow-up back to a **single submitter** (closing the loop on their specific report) or to a **group of users** in an affected area (e.g. everyone who reported near a hazard, or everyone in a suburb) — a genuinely two-way, targeted channel that complements rather than duplicates NEMA's Emergency Mobile Alert, which is broadcast-only and one-way (see Slide 3's "Existing alternatives" row).

**4 months:** Split out a **dedicated third model for high-stakes action suggestions** (e.g. "call 111", "evacuate") — in the hackathon build these are combined with low-stakes suggestions (like "check on neighbours") into the Clarifier's second step, made before any official corroboration exists; a real pilot needs that judgement moved to *after* the Triage Classifier's context-informed severity check, with WCC's domain expert validating the suggestion set before anything reaches the public directly.

**5-6 months:** production readiness — move off free-tier hosting, add staff-briefing summarization and plain-language public alert adapters, integrate output into whatever system WREMO (Wellington Region Emergency Management Office) staff already use operationally.

**8 months:** scale — add 1-2 more multi-language models (te reo Māori, Samoan, and others relevant to Wellington's communities), expand beyond Wellington City to the wider region.

**10+ months — resilience layer (beyond-internet hardware):** the software system above assumes internet/cell connectivity. Real emergencies often don't have that. A mature version of this system extends to dedicated low-cost hardware:
- **Community input nodes** — simple LoRa (Long Range)/mesh devices (Meshtastic-style) or SMS-gateway units placed with trusted community anchors — marae, community centres, community patrol groups — so they can submit reports even when internet/cell data is disrupted
- **Council backup dashboard device** — a low-power, low-bandwidth receiver (e-ink or SMS-driven) for decision-makers that surfaces only critical/high-severity classified items, so the triage output still reaches Council even if the web dashboard's connectivity path is down
- This is explicitly a **future track, not a hackathon-day build** — it requires hardware procurement, field logistics, and partnership with existing networks (e.g. NZ LoRaWAN community networks, or Civil Defence's Emergency Mobile Alert infrastructure) that a one-day team can't validate. We show it in the demo as a **simulated UI concept only**, to demonstrate we've thought through what "real use in an actual emergency" requires beyond the software layer.

Each step tends to add one component/capability (e.g. one new small fine-tuned model to the same proven pipeline) — not a rebuild. That's the growth model: efficient and safe, one narrow capability at a time.

---

## Slide 10 — Scalability: beyond Wellington

**Yes, in tiers**

- **National layer — near drop-in:** MetService CAP, GeoNet, NZTA TREIS, and NEMA's Emergency Mobile Alert feed are all **NZ-wide feeds already**, not Wellington-specific. Any other NZ council plugs into the exact same four sources today, no rework needed
- **Regional layer — config change, not a redesign:** council-specific data (river/rainfall gauges, local hazard layers) differs per region — we've already proven this with GWRC's river-level and rainfall telemetry (live, not simulated). Most NZ councils publish through the same ArcGIS Hub pattern GWRC/WCC use, so the *integration approach* carries over, and adding a new council mostly means pointing at their endpoint and remapping fields
- **The two custom LLMs — retrain, don't rebuild:** hazard classification and clarification-question generation are generic tasks. Scaling to another region means retraining the same adapters on that region's suburb names and activation history — hours of work, not a new architecture
- **International — architecture transfers, data integrations don't:** CAP is an international alerting standard, so official-warnings ingestion could plug into another country's CAP feed. GeoNet, NZTA, and the regional-gauge pattern are NZ-specific systems — an overseas deployment would need equivalent local sources identified and integrated fresh

**Pitch for judges:** it's a system designed with some generalised parts where possible (e.g. national data, the AI adapters, the integration pattern and interface between the layers), while some parts need localised work (regional data mapping, any international deployment).

---

## Slide 11 — Ask / close

- What we'd want from WCC to take the next step: access to real (even historical/anonymized) community report data, and time with the domain expert to validate our classification categories against their actual activation taxonomy
- Repo link + demo video link
- Thank you

---

## Demo video storyboard (2 minutes)

No slide deck is required for submission — only a GitHub repo and this video — so the video may be almost entirely **live product footage**, not slides. Exceptions can be a brief architecture diagram, a data-flow diagram, visual roadmap, etc. Everything else (Lean Canvas, scalability) lives here as backup material for live judging Q&A.

**Five points to explicitly call out in narration** (point 5 added — ⚠️ not guaranteed to fit, see production notes):

1. **AI-first development** — this was built using an AI-first development workflow: reusable Claude skills that grow over time, Claude Projects as the working environment, and custom MCP servers used as needed. Called out during the architecture slide insert (0:15–0:25).
2. **Security and data sovereignty** — because the two LLMs are small, custom fine-tuned models running on infrastructure we control (not a third-party AI API), sensitive emergency data never has to leave our own environment. Called out during the full-dashboard beat (1:35–1:50).
3. **Enterprise-friendly, financially and environmentally sustainable** — the same small-model approach means no per-token API cost and far lower compute/energy use than routing every request through a large third-party model, which matters at real council/enterprise scale. The frontend carries the same ethos: both apps are built in Svelte rather than React, compiling away the framework instead of shipping a virtual-DOM runtime, for smaller downloads and lower client-side energy use on every device. Called out in the same beat as point 2 (1:35–1:50) — **the Svelte detail is an "if it fits" addition to this beat, same status as point 5 below; drop it first if the beat runs long, the model-efficiency framing alone still lands the point.**
4. **Release cadence roadmap** — the next concrete step includes standing up a test → demo → production pipeline, not just adding features. Called out in the closing beat (1:50–2:00), and also now reflected in Slide 9's roadmap.
5. **Socially sustainable** — because the models are small enough to fine-tune in-house, staff build real, transferable AI skills through preparing data, validating results, and fine-tuning themselves, rather than depending on a third-party black box. Intended for the closing beat (1:50–2:00), alongside point 4 — **needs rehearsal to confirm it actually fits; drop it before the release-cadence point if the closing beat runs long, rather than rushing either.**

| Time | Screen content | Voiceover / point |
|---|---|---|
| 0:00–0:15 | Live dashboard, sitting idle/live | One-sentence problem statement, mirroring the brief's own framing: 10 activations in 2 years, fragmented information, no fast way to triage it |
| 0:15–0:25 | **Slide insert — architecture diagram** (public report → clarify LLM question → public more info → clarify LLM action → triggers official-source check → aggregator → classifier → store → dashboard) | "Here's how it works — and how we built it: AI-first, using reusable skills, Claude Projects, and custom MCP servers to connect each data source" — **(point 1)** |
| 0:25–0:55 | Live: submit a real public report through the form on screen | Name a couple of the five real official data sources this will be checked against (MetService, GeoNet, NZTA, NEMA, GWRC — no need to list all five in the time available); emphasise this is a live submission, not canned |
| 0:55–1:25 | Live dashboard: the clarifying question appears immediately, submitter answers, a suggested action appears, then the triaged result appears once checked against live official data for that location | This is the differentiator beat — every submission gets an immediate two-way exchange *and* an actionable response, not just ambiguous ones; ties directly to both tracks (two-way channel + prioritised triage) in one moment |
| 1:25–1:35 | **Slide insert — data-flow diagram** (submission → clarify LLM question/answer/action → cached official-source poll → aggregate → triage → store → render) | Quick technical grounding for how data moves end-to-end — reinforces "working demo," not a black box |
| 1:35–1:50 | Back to live dashboard: full prioritised feed grouped by location, map, detail panel showing the official context that informed the triage judgement, plus the model's plain-language rationale | Point at the visible official context and rationale for "honesty about limits," **then**: "because these are our own small custom-trained models, not a third-party API, this keeps sensitive data secure and respects data sovereignty — **(point 2)** — and is financially and environmentally more sustainable to run at enterprise scale — **(point 3)**, right down to the frontend itself, built in Svelte instead of React for a lighter footprint on every device *(if time allows — see production notes)*" |
| 1:50–2:00 | Live dashboard or a plain title card | Next step is hardening this into a test → demo → production release cadence — **(point 4)** — plus, time permitting, that the same model-building process upskills Council staff rather than replacing them — **(point 5, ⚠️ rehearse to confirm it fits)** — then piloting with WCC directly; close on the ask |

**Production notes:**
- Slide inserts should be simple static diagrams, on screen for 5-10 seconds each — no more. If either diagram needs more than a sentence of narration to make sense, simplify the diagram rather than extending its screen time.
- Everything else stays on the live dashboard; resist the urge to cut back to slides to "explain" — if something needs a slide to make sense, that's a signal the live UI itself should surface it instead (e.g. the visible official context and plain-language rationale already do this for the "honesty about limits" point).
- The 1:35–1:50 beat is now carrying three ideas (limits, security/sovereignty, sustainability) in 15 seconds — needs a tightly scripted, rehearsed line.
- **The 0:55–1:25 beat now has four live moments (question, answer, action, triaged result) in 30 seconds, where it used to have two — prefill the answer ahead of recording (have it ready to paste/select instantly, don't type it live) to keep pace, rather than extending this beat's time at the cost of others.**
- **Point 5 is explicitly an "if it fits" addition** — rehearse the full 2:00 with it included first; if the closing beat runs long, cut point 5 before compressing points 1-4 or rushing the ask.
- **The Svelte-vs-React clause in the 1:35–1:50 beat is the same kind of "if it fits" addition** — that beat already carries three ideas in 15 seconds (see above); rehearse with it in first, and cut it before compressing the security/sovereignty or model-sustainability points if the beat runs long. The model-efficiency framing alone still fully lands point 3 without it.

**Slides needed for video:**
- Architecture
- Data flow
- Roadmap + Scalability
- Team members

---

## Live demo (4 minutes, 16:30)

**Confirmed from the hackathon organisers' README** (`impact.lab.wlg.team-10`): judging includes a
**separate, in-person, 4-minute live demo at 16:30** — distinct from the 2-minute pre-recorded
video, which is what actually gets submitted by the 16:00 cutoff. Both systems are now real and
deployed (backend on Cloud Run; both frontends on Vercel), so this is a concrete script against the
live URLs, not a placeholder.

**Live URLs (confirm both are warm — see pre-demo checklist — before walking on):**
- Public report form: the deployed frontend root, with `?clarify=1` appended to force the two-step Clarifier flow on
- Staff dashboard: the deployed frontend's `/dashboard/` route

**Ground rule for the whole 4 minutes:** unlike the video, judges can interrupt with questions at
any point — don't treat this as a script to recite start-to-finish regardless of what's asked.
Treat the beats below as the *default path if nobody interrupts*, and the "if asked" section as
prepared answers to drop in wherever a question actually lands.

| Time | What happens | Who | Talking point |
|---|---|---|---|
| 0:00–0:20 | Open on the dashboard, idle | Presenter | One-sentence problem statement — 10 activations in 2 years, fragmented information, no fast way to triage it |
| 0:20–1:00 | Submit a real report on the public form (phone or laptop, presenter's choice — phone reads better to a room) | Presenter or a volunteer from the audience | Name 2 of the 5 real official sources this gets checked against (MetService, GeoNet, NZTA, NEMA, GWRC) — this is a live submission against real infrastructure, not a canned demo |
| 1:00–1:40 | The clarifying question appears immediately; answer it (prefilled answer ready to paste, not typed live — see pre-demo checklist); the suggested action appears | Same person | Every submission gets this two-way exchange, not just ambiguous ones — this is both tracks (two-way channel + prioritised triage) in one moment |
| 1:40–2:20 | Switch to the dashboard: the new report appears on the map and feed within one poll cycle; open its detail panel | Presenter | Point at the visible official context and the plain-language rationale — the triage judgement isn't a black box, staff can see exactly what informed it |
| 2:20–2:40 | Use the severity filter toggles (with live counts) to isolate High only | Presenter | This is a staff-facing control, not just a display — during a real activation this is how a team lead narrows the feed fast |
| 2:40–3:10 | One sentence each on data sovereignty/security and efficiency (small self-hosted models, Svelte frontend) | Presenter | "These are our own small custom-trained models on infrastructure we control, not a third-party API — that's data sovereignty and it's financially and environmentally cheaper to run at council scale, right down to the frontend framework choice" |
| 3:10–3:40 | Roadmap beat: name the confidence + priority extension as the concrete "what's next" | Presenter | *"The classifier already outputs severity and rationale — next is having it also say how confident it is, so a high-severity call backed by strong evidence and a high-severity call that's just a vague, uncorroborated report don't get treated the same in the queue."* Ties directly to the Lean Canvas's "foundation to iteratively build more capability" claim — a concrete example, not a vague promise |
| 3:40–4:00 | Close on the ask | Presenter | What we'd want from WCC to take the next step; thank you |

**If asked (don't volunteer unless it comes up):**
- *"What breaks this?"* — venue wifi. The whole live path depends on real external API calls; if it degrades mid-demo, switch immediately to the pre-recorded video rather than fighting a live failure in front of judges (see pre-demo checklist).
- *"Why not a bigger model / GPT-4 API?"* — no per-token cost, no rate limits, no vendor uptime dependency during an actual emergency, and it can run fully within infrastructure WCC controls. See Slide 7.
- *"How does this scale past Wellington?"* — see Slide 10; national data sources are near drop-in, the two LLMs are retrain-not-rebuild.

**Pre-demo checklist (do this in the 4:00–4:30 prep slot, not on the way to the podium):**
- [ ] Send a real request to the deployed backend a few minutes beforehand — Cloud Run scale-to-zero means a cold instance adds real seconds to the first request, and that first request should not be the one judges watch (see `BUILD_PLAN.md`'s 4:00–4:30 note)
- [ ] Both frontend URLs already open in browser tabs, pre-loaded, not typed live
- [ ] The Phase 2 answer text ready to paste (clipboard or a visible note), not typed live — same discipline as the video's production notes
- [ ] The 2-minute video cued up and ready to play instantly as the wifi-failure fallback (see `BUILD_PLAN.md`'s open risk: "no fallback if venue wifi degrades or drops right before judging") — decide now, not mid-demo, who hits play if it's needed
- [ ] Dashboard already has at least one prior triaged report visible before 0:00, so the feed/map/detail panel aren't empty during the opening beat

**Slides for this slot:** none required — this is fully live-product, unlike the video which uses two slide inserts for architecture/data-flow. If a question needs a diagram to answer well, sketch it verbally or point back to the architecture beat's mental model rather than breaking the live flow to hunt for a slide.
