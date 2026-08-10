# Wellington Impact Lab — Building Plan (pre hackathon and on the day)

**Event:** Saturday 8 August, Wellington Impact Lab civic AI hackathon
**Build window:** 9:30 AM start → 4:00 PM submissions close (~6.5 hours)
**Target tracks:** "Help emergency staff sort and prioritise incoming information" (primary, via classification feature) + "Create a two-way information channel between communities and Council" (secondary, via clarification feature)

## System summary

A triage system for WCC emergency staff, built around a public report as the trigger for everything else. Two small fine-tuned LLMs do the work:

- **Clarifier:** runs immediately on every public submission (not just ambiguous ones) and always generates a follow-up question — the seed of a real two-way channel
- **Triage Classifier:** takes the clarified report plus deterministically-built context (relevant official data + at most one related pre-existing public report) and outputs a **severity level and a one-line rationale** — nothing else. Everything countable or already-structured (which official source is relevant, what `hazard_type` a matched official event implies) is handled by plain code, not the model — the model is reserved for the one genuinely hard judgement call: how serious does this report look, in light of what else is known.

**Technical note:** Google Cloud Run (validated end-to-end, including a real Vercel-deployed frontend calling it successfully) — not Hugging Face Spaces as originally planned, since HF now requires a paid PRO plan for any Docker/Gradio Space. Full setup detail in "Validated model build/deploy pipeline" below.

**The flow, end to end** (full detail in "Public-submission-triggered flow" below):

1. A member of the public submits a report (form today; social media later) — optionally with location
2. **Clarifier runs immediately and always** — no "already clear enough" check
3. Submitter is thanked right away — nothing downstream blocks them
4. That submission **triggers the poller** (official sources, in-memory cache, 5-min throttle) — this is also what keeps the Cloud Run instance alive for the work, sidestepping a real problem: continuous background polling doesn't reliably survive Cloud Run's scale-to-zero behaviour
5. **Aggregator** builds two small deterministic context blocks: relevant official data (by location/recency), and at most one related pre-existing public report (by location/recency, from the same event store — no separate cache needed)
6. **Triage Classifier** takes clarified report + both context blocks → outputs `severity` + `rationale`
7. **Aggregator deterministically sets `hazard_type`** — inherited from the matched official source if one exists, else `"other"`. The model never produces this field.
8. Staff dashboard shows the result, grouped by location, rationale visible on hover

**Why classify the public report and not the official sources directly:** each official source already publishes its own severity signal (GeoNet magnitude, NZTA impact rating, MetService warning level) — re-deriving that with an LLM would be a slower, less reliable version of information already free. The genuinely valuable, non-redundant problem is judging an unverified public claim against what's officially known — that's the model's entire scope.

**PHASED ROLLOUT (agreed explicitly, changes the "clarifier always runs" framing above from "already true" to "the end state, built in two phases"):**
- **Phase 1 (built, tested, working now):** single-step public submission — `raw_text` → poller trigger → aggregation → Triage Classifier → deterministic `hazard_type` → store. **No clarifier call at all.** `clarified_text`/`clarification_question` stay null. This is the base flow to get solid before adding the clarifier.
- **Phase 2 (later, once the fine-tuned clarifier model exists):** frontend adds a feature-flagged (query-param controlled) second step — call a dedicated clarify endpoint, show the question, collect an answer, submit the clarified report. Only then does step 2 above ("Clarifier runs immediately and always") actually happen.
- Backend code already reflects this: `app/clarifier.py` exists as a stub but is **not called** from the submission endpoint yet — deliberately, matching this phasing, not an oversight.

**Deferred, noted for later, not built in this pass:** a manual/on-demand staff-side trigger (pull official data independent of a public submission).

## Team

- **Sara — hazard & emergency social scientist:** dataset design and labelling (grounded in real emergency-management practice), hazard/severity taxonomy, WCC domain-expert liaison, community-sensitivity review
- **Isla — user research, UX:** frontend dashboard, user journey design, demo video, pitch visuals
- **Moiz — architect / technical lead:** system architecture, backend (FastAPI, poller), LoRA fine-tuning, adapter-swap serving, deployment/integration, AI-assisted development workflow

The review checkpoints below should help the team catch problems before they compound. Each checkpoint is a short pause (~10 min), not a formal sign-off process. This is a team build — task tags below indicate only who drives a piece of work, not who owns it alone.

## Pre-hackathon prep (do before Aug 8)

Several parts of this build don't depend on hackathon-day data or the WCC briefing — starting these early reduces what has to happen inside the 6.5-hour window.

- [ ] **(All)** Team introduction (either video call or in person)
- [x] **(Moiz)** Draft pitch/solution and building plan/todos
- [ ] **(Sara + Isla)** Review draft pitch/solution and provide feedback
- [ ] **(Sara + Isla)** Review draft building plan/todos and provide feedback
- [ ] **(All)** Questions/suggestions on the hackathon and solution
- [ ] **(Sara)** Confirm which of the required datasets are available, and research WCC's past activations from public sources (news coverage, WCC/WREMO public reports) to draft a realistic hazard/severity taxonomy ahead of the 9:00am briefing
- [ ] **(Sara + Moiz)** Draft the classifier dataset (hazard type, suburb, severity labels) using that research, plus the clarifier dataset (ambiguous report → good follow-up question pairs) and a set of deliberately "bad"/incomplete example reports to seed both training and demo data
- [ ] **(Moiz)** Test MetService CAP feed, GeoNet API, NZTA TREIS, GWRC ArcGIS layer access — confirm no auth walls
- [x] **(Moiz)** Have Phi-3.5-mini (or chosen base model) downloaded locally; confirm `llama.cpp` / `mlx` conversion toolchain works end to end
- [x] **(Moiz)** Run the *entire* local pipeline once, end to end, with placeholder/synthetic data before the day: fine-tune a LoRA adapter with MLX (or PEFT+transformers) → export/fuse it into a standard HF/PEFT adapter format → convert to GGUF with `convert_lora_to_gguf.py` → load it in the actual serving stack.
  - *Technical note: MLX saves adapters in its own layout, not the HF/PEFT format `convert_lora_to_gguf.py` expects — confirm the export/fuse step between the two (e.g. via `mlx_lm`'s HF export tooling) actually works before assuming the two tools interoperate directly. This is the one link in the fine-tune-locally-serve-on-HF chain that hasn't been verified anywhere else in this plan.*
  - **Update — verified with real data (OIA project models), not just placeholder data.** The bridge works via `mlx_lm.fuse` (without its `--export-gguf` flag, which does **not** support Phi-3 — throws `ValueError: Model type phi3 not supported for GGUF conversion`) producing a standard HF-format directory, then `llama.cpp`'s `convert_hf_to_gguf.py` on that directory. Two gotchas found: (1) `mlx_lm.fuse` doesn't write `tokenizer.model` — copy it manually from the base model or any prior fuse output, it's unaffected by fine-tuning; (2) `convert_hf_to_gguf.py` needs the `gguf` pip package specifically (small, pure-Python) — everything else it needs (torch, transformers, numpy, sentencepiece) was likely already present from the MLX training environment. Full details in "Validated model build/deploy pipeline" below.
- [x] **(Moiz)** Build and test the adapter-swap serving skeleton ahead of time, reusing the pattern from the OIA project — proven code, no need to rebuild it live on the day
  - Technical note: verify the actual hot-swap mechanics on the real serving stack (e.g. llama.cpp/GGUF) ahead of time some setups require a reload rather than a true in-place swap, which changes expected latency.
  - Technical note: guard against concurrent requests hitting the shared model mid-swap (poller classifying while a community report triggers the clarifier at the same time) — a simple lock/queue around swaps avoids a race condition.
  - Update: Tried but we won’t do this for the hackathon and treat it as a future optimisation — see "Validated model build/deploy pipeline" below.
- [x] **(Moiz)** Write the poller framework as a generic, source-agnostic interface, so hackathon day is mostly plugging in 3/4 endpoint configs rather than writing async logic from scratch
- [ ] **(Moiz)** Get a free API/account set up for each open data source if required (e.g. NZTA opendata@nzta.govt.nz contact if a key is needed)
  - *Technical note: store any keys as HF Space secrets / Vercel env vars, instead of commiting them to the repo.*
- [ ] **(Isla)** Design dashboard wireframes/mockups (Figma or sketches) so layout decisions are made before build time, not during it
- [ ] **(Isla + Sara)** Sketch the staff user journey — from an alert/report arriving to a decision being made — this also strengthens the pitch's own UX narrative
- [ ] **(Moiz)** Draft the frontend scaffold against a mock event schema, so frontend work isn't blocked waiting on a live pipeline on the day
- [ ] **(Moiz)** Create Hugging Face account/org, Vercel account, test a "hello world" Space + Vercel deploy end-to-end so the deployment path is proven before hackathon day
  - *Technical note: also do at least one dry-run deploying the actual quantized model + both adapters (not just a placeholder) — real Docker builds with model weights can hit build timeouts or memory limits a hello-world Space won't reveal.*
  - **HF Space part UNSUCCESSFUL as planned:** Hugging Face now requires a paid PRO plan ($9/month) for Docker or Gradio Spaces — confirmed current policy, not an assumption. Only Static (client-side) Spaces are free, which can't run our backend at all.
  - **DONE with Google Cloud Run instead** — dry-run completed successfully with real models (not placeholders), full pipeline verified working end-to-end including a live Vercel frontend talking to it. Google Cloud Run's Always Free tier (180,000 vCPU-seconds, 360,000 GiB-seconds memory, 2M requests — per month) is genuinely ongoing, not a trial, but **pooled per Google billing account, not per service or project** — worth remembering once the hackathon system adds its own Cloud Run service under the same account. See "Validated model build/deploy pipeline" and updated "Hosting" section below for full setup steps (Artifact Registry, custom service account + IAM roles, Cloud Build trigger with a custom `cloudbuild.yaml`).
  - **Also evaluated and rejected:** Google's "Agent Platform" (rebrand of Vertex AI, now "Gemini Enterprise Agent Platform") — it can import custom fine-tuned weights from Hugging Face, but its custom-weights path explicitly does not support GGUF/quantized models, only full HF-format weights via GPU-backed managed endpoints. Wrong tool for cheaply self-hosting a small quantized model; noted here so this isn't re-investigated later.
- [ ] **(All)** Agree the event schema (fields, naming) together in advance — this is the contract between backend and frontend, and it's the most expensive thing to get wrong mid-build
- [ ] **(All)** Rehearse the pitch narrative and demo video storyboard against the draft pitch, so only the screen-recording itself remains to be done on the day
- [ ] **(All)** Set up the shared GitHub repo skeleton and README structure
  - *Technical note: agree a simple branching approach (e.g. short-lived feature branches, frequent small merges) before the day, but try to avoid multiple devs on the same repo, due to time constraints*
- [ ] **(Isla, build; Moiz + Sara, content-review)** Prepare the 4 static slides needed for the demo video (see storyboard section of Pitch doc) — none of these depend on hackathon-day data, so can build them in advance:
  - **Architecture diagram** (sources → poller → classifier → store → dashboard)
  - **Data-flow diagram** (poll cadence per source → normalize → classify → store → render)
  - **Roadmap + Scalability** (condensed from Slides 9-10 — one visual, not the full detail)
  - **Team members** (names, roles, photo if wanted)

## Demo video production checklist

The video is almost entirely live screen-recording of the dashboard, not slides — see Pitch's storyboard for exact timing. This checklist is what needs to exist before recording can happen.

**Slides (prepared in advance, not on the day — see pre-hackathon prep above):**
- [ ] Architecture diagram
- [ ] Data-flow diagram
- [ ] Roadmap + Scalability
- [ ] Team members

**Live screens to capture on the day (in storyboard order):**
- [ ] Dashboard sitting idle/live at rest, before anything dramatic happens (0:00–0:15)
- [ ] A public report submitted live through the form, the clarifying question appearing immediately, then the submitter's answer and a suggested action appearing (0:20–0:50)
- [ ] The triaged result appearing once checked against real official data (MetService/GeoNet/NZTA/NEMA/GWRC) for that location — the official context that informed it visible in the detail panel (0:50–1:20)
- [ ] The full prioritised feed grouped by location + map + detail panel, with severity, the deterministic hazard type, and the rationale visible on hover clearly shown (1:30–1:45)
- [ ] A closing screen — either the live dashboard or a plain title card with the roadmap one-liner and the ask (1:45–2:00)

Since the community-report clarifier trigger (0:50–1:20) depends on a seeded example firing correctly on demand, test this specific moment during the 2:30–3:15 integration test, not for the first time during recording.

## Hour-by-hour plan

### 9:00–9:30 — Problem briefing + datasets
- **(Sara)** Confirm final problem framing with WCC domain expert
- **(All)** Confirm exact datasets/formats provided on the day (may replace pre-hackathon assumptions)
- **(All)** Lock scope: which hazard types, which suburbs, what "done" looks like for the demo

### 9:30–10:30 — Data ingestion skeleton + dataset finalization
- **(Moiz)** Stand up FastAPI service with a background poller (async loop or APScheduler)
  - One polling function per source (MetService CAP, GeoNet, NZTA TREIS, GWRC gauges), each on its own interval
  - Normalise each source's response into a common **event schema** — a single, shared shape that every incoming item gets converted into regardless of which source it came from, so the classifier, store, and frontend only ever have to deal with one format instead of four different source-specific ones: `{source, timestamp, location, raw_text, hazard_type: null, severity: null}` (see the "Proposed event schema" section below for the full version)
  - Dedup via last-seen ID/timestamp per source
  - Store in SQLite (or in-memory list if time-pressed)
- **Review checkpoint (Isla checks the event schema):** before going further, confirm the schema covers what the dashboard will need to render (fields, naming) — cheap to fix now, expensive to fix after the UI is built against it
- **(Sara)** Finalize fine-tuning datasets (in final JSONL format), incorporating anything new from the 9:00 briefing (real WCC taxonomy/examples)

### 10:30–12:30 — Fine-tuning + adapter integration (actually, we should be able to do most of steps till here before the 8th, and make our lives easier on the day)
- **(Moiz)** Run LoRA fine-tune for **Adapter 1 (classifier/extractor)** (MLX or PEFT+transformers) — do not merge into the base model; see "Fine-tuning approach" below for the base-model-once + per-adapter GGUF conversion steps and time estimates (better to try doing this earlier to reduce dependency)
- **(Moiz)** Run LoRA fine-tune for **Adapter 2 (clarifier)** — sequentially after Adapter 1, or in parallel if compute headroom allows (better to try doing this earlier to reduce dependency)
- **(Moiz)** Build the adapter-swap serving logic — one base model loaded, swap LoRA weights per request type (classify vs. clarify)
  - Update: Loads both fine-tuned models fully (as separate fused GGUF files, not a shared base + swapped adapters) into one process at startup. Therefore no swap-mechanics or race-condition risk to guard against. Simpler and proven; costs more memory (two full models instead of one base + two small adapters) but well within Cloud Run's configurable memory range. The adapter-swap approach above remains a valid future optimization.
- **(Moiz)** Wire poller output → classifier adapter → store classified fields back onto each event
- **(Isla)** In parallel: continue frontend build against the agreed schema (static/mock data first, since the live pipeline isn't ready yet) — keeps frontend progress independent of backend timing
- **(Sara)** In parallel: prepare the simulated community-report seed data (realistic scenarios, including deliberately ambiguous ones to trigger the clarifier) and draft the wording/tone guidance for how clarifier questions should read to a real community member
- **Review checkpoint (Sara checks the adapter outputs):** once both adapters produce output, check classification results and clarifier questions against real emergency-management judgment and community-appropriate tone — before this gets wired into the live UI. This is the most important checkpoint of the day: it's the one place domain accuracy gets verified by the person qualified to verify it

### 12:30–1:00 — Lunch + lightning talks

**Team check-in #1**
- **(All)** Sync: is ingestion working end-to-end? Any source down/rate-limited? Did the adapter-output review surface anything that needs a re-train pass? Adjust scope, if needed.
- **(All)** Motivate each other: quick round where each person says one thing that's going well so far — the first stretch is the hardest to judge progress on, and a deliberate word of encouragement here sets the tone for the afternoon
- **(All)** Take an actual break, eat, enjoy the lightning talks, and have some fun together — a good hackathon result comes from a team that enjoys the day

### 1:00–2:30 — Frontend build
- **(Isla)** Build out the full triage dashboard (see FRONTEND section below) against real data now that the pipeline is live
- **(Isla)** Point it at the backend's `/events` endpoint (poll every 10-15s)
- **(Moiz)** Stand up the simulated community-report input (simple form or pre-loaded seed file prepared earlier) and route it through both adapters (classify, then clarify if fields are missing)
- **Review checkpoint (Sara checks the UI copy/labels):** badge wording ("verified/unverified"), severity labels, and any clarifier-facing text get a quick pass for accuracy and community tone before deploy

### 2:30–3:15 — Deploy + integration test
- **(Moiz)** Deploy backend + model to Hugging Face Space (Docker SDK)
  - Update: Didn’t work. Instead, deploy to Google Cloud Run instead (validated end-to-end pre-hackathon).
- **(Moiz)** Deploy frontend to Vercel, pointed at the live Space URL
  - **✅ Confirmed working**, pointed at the Cloud Run service URL instead of a Space URL — same Vercel deploy step either way, Update: Point at the Cloud Run service URL instead of a HF Space URL — only change the backend URL in vercel.json's rewrite.
- **(Moiz)** Full end-to-end test: real data flowing in, classified, displayed, clarification triggered on an ambiguous seeded report
- **(Moiz)** Fix CORS/networking issues as early as possible — always the first thing that breaks
- **(Isla)** End-to-end UX test on the deployed dashboard: walk through the full staff user journey exactly as the demo video will show it — does the feed load, sort, and update as expected; any confusing labels, slow renders, or layout breaks on the actual deployed version (not just localhost)
- **(Sara)** End-to-end domain test: submit a spread of realistic and edge-case reports (different hazard types, a genuinely ambiguous one, a clearly low-severity one) through the live deployed pipeline and confirm the classifications and clarifier questions still hold up as sensible and defensible — deployed behaviour can differ from what was checked earlier in the adapter-output review checkpoint
- **(Isla + Sara)** Together, run through the exact sequence that will be recorded for the demo video at least twice, back to back, to confirm it's reliably repeatable

### 3:15–3:45 — Polish + demo prep
- **(Moiz + Isla)** Add the poll-health indicator, and the detail panel's rationale-on-hover plus visible `official_context` (which doubles as the "was this officially corroborated or not" signal, replacing the earlier separate badge concept)
- **(Sara)** Sanity-check the "honesty about limits" story: what's real data, what's simulated, and say so plainly in the demo

**Team check-in #2**
- **(All)** Walk through the live demo together once, end to end, before recording — a shared final check catches what any one person alone would miss
- **(All)** Motivate each other: this is the last stretch before submission — take a moment to acknowledge what's been built before diving into the final push

### 3:45–4:00 — Record demo video + submit
- **(Sara, narrates)** 2-minute demo video following the storyboard in Pitch and the "Demo video production checklist" above — 4 prepared slides + 5 live screen captures, cut together
- **(Isla + Moiz, filming/editing)**
- **(Moiz)** Push final commit, write README with architecture summary and known limitations
- **(Moiz)** ⚠️ **Remove all references to the OIA project from every doc before the final commit** (`BUILD_PLAN.md`, `FINETUNE_PLAN.md` — currently 2 and 8 mentions respectively, `grep -rn "OIA" docs/` to find them all). OIA was this project's internal validation reference (proving the fine-tune → GGUF → Cloud Run pipeline before applying it here) — genuinely useful context for the team during the build, but not something that should appear in the public hackathon submission. Rewrite each mention to describe the underlying fact directly (e.g. "validated end-to-end via the OIA project" → "validated end-to-end pre-hackathon") rather than just deleting the sentence, so the reasoning/evidence isn't lost.
- **(All)** Submit GitHub repo + video before 4:00 cutoff

### 4:00–4:30 — Rest, prep for live demo/judging
- Technical note: Cloud Run scale-to-zero means cold starts happen after any idle period, same underlying risk as an HF Space sleeping — confirm the service is warm (send a test request) right before the live demo.

### 4:30–5:45 — Live demo + judging
- **⚠️ Confirmed from the organisers' README**: each team gets a **4-minute live demo**, separate from the submitted 2-minute video — see `PITCH.md`'s "Live demo (4 minutes, 16:30)" section, currently a placeholder, not yet planned
- **(All)** Whoever's presenting should have rehearsed this specific slot, not just the video's script — 4 minutes is roughly double the video's runtime, likely with room for judge Q&A

### 5:45–6:15 — Awards + celebrate
- **⚠️ Confirmed from the organisers' README**: awards start at **17:45**, not 5:30 — adjusted from the original estimate
- **(All)** Whatever the judging outcome, take the moment to celebrate.

## Fine-tuning approach (both adapters)

**Driven by: Moiz (execution), Sara (content/validation)**

Two different environments are involved here, not one: fine-tuning happens locally on the MacBook Pro (MLX, Apple Silicon-only), but serving happens on the Hugging Face Space, a Linux container where MLX cannot run. The bridge between the two is the GGUF export/conversion in step 5 below — that step exists because the fine-tuning tool and the serving tool cannot run in the same place.


**⚠️ UPDATE:** "serving happens on the Hugging Face Space" is no longer accurate — HF Docker Spaces require a paid plan. The reasoning about why a bridge step is needed still holds exactly as written (MLX is Apple-Silicon-only, the serving container is Linux) — only the specific serving target changed to Google Cloud Run. See "Validated model build/deploy pipeline" below for the confirmed-working version of this whole section.

1. Prepare JSONL datasets: `{"input": "...", "output": "..."}` pairs — **current, final design** (see `docs/FINETUNE_PLAN.md` for full detail):
   - **Triage Classify:** (clarified public report + relevant official context + at most one related pre-existing public report) → `{severity, rationale}`. Deliberately does **not** produce `hazard_type` (deterministic, inherited from a matched official source or `"other"`) or any structured corroboration field — kept out of the model to keep the dataset small and the behaviour testable.
   - **Clarify:** two distinct calls sharing one model, task-conditioned via system prompt — Call 1: report → clarifying question (1-3, always produced). Call 2: report + question + answer → 1-2 action items from a fixed vocabulary. Always runs, on every submission, once built (Phase 2 — see the phased-rollout note in "System summary"; not called in Phase 1's backend code yet). Full design, vocabulary, and the known limitation (Call 2 has no official corroboration): see FINETUNE_PLAN.md "Model 1 — Clarifier".
2. Fine-tune with LoRA on Phi-3.5-mini (low-rank adapters, small footprint, fast to train on a laptop)
3. Keep adapters separate (don't merge into base) — this is what enables single-server adapter-swapping later
4. Validate each adapter against a small held-out set before wiring into the pipeline — even 10 examples catches obvious failures. The content review here matters as much as the technical check — a technically-correct-looking classification can still be wrong from an emergency-management perspective
5. Export for HF Space deployment — two full models (see technical note on “validated model build/deploy pipeline” below):
   - **Base model → GGUF + quantize, once**, using `convert_hf_to_gguf.py` then `quantize` (e.g. Q4_K_M). ~10-20 min for a ~3.8B model, mostly I/O-bound.
   - **Each adapter → its own GGUF, separately**, using `convert_lora_to_gguf.py` — this converts only the small adapter weights (tens of MB), not the full model. ~1-5 min per adapter, so ~10 min for both.
   - Fuse each adapter with base model to create its own full model

## Fine-tuning commands (run these yourself, one per terminal)

**Driven by: Moiz, run manually — not something to automate away, since watching the loss curves as they go matters (see FINETUNE_PLAN.md's "Training mechanics" for what train vs. valid loss actually mean here).**

Both datasets are done and validated (see FINETUNE_PLAN.md's "Next steps" — Triage Classifier: 231 rows; Clarifier: 420 rows across both calls). Run from the repo root, one command per terminal window — nothing about these two runs depends on each other, so they're safe to run either sequentially or side by side if the laptop has the headroom (two Phi-3.5-mini LoRA runs at once is not huge, but keep an eye on memory pressure if running both together).

**Environment — confirmed working, not guessed:** `mlx_lm` (0.31.3) is installed in the `myenv` venv used for the OIA fine-tuning, at `/Users/moiz/Documents/Courses+Trainings/Understanding-Open-AI-Workspaces/jupyter/myenv`. Activate it in each terminal before running either command below:
```bash
source "/Users/moiz/Documents/Courses+Trainings/Understanding-Open-AI-Workspaces/jupyter/myenv/bin/activate"
```
Then `cd` to this repo (`wellington-impact-lab`) and run the commands from its root — activating a venv doesn't depend on which directory you're in.

The commands below are the **actual validated invocation from `fine_tune_oia_mlx.ipynb`** (its code cells, not its markdown — the markdown table and the executed code disagreed on two flag names/values: docs said `--lora-layers`/`--iters 400`, the code that actually ran used `--num-layers`/`--iters 500` — using what actually ran), and every flag has been directly checked against `myenv`'s installed `mlx_lm lora --help` output (not assumed from the notebook alone) — all present, all correctly named. Adapted for our dataset sizes: `--val-batches` capped below each dataset's actual valid-set size at `batch-size 4`, so the run doesn't request more validation batches than exist.

**Triage Classifier** (231 rows, single task — closest to the OIA notebook's classification model, which used `--iters 500`):
```bash
python -m mlx_lm lora \
  --model microsoft/Phi-3.5-mini-instruct \
  --train \
  --data backend/data/triage \
  --iters 500 \
  --batch-size 4 \
  --num-layers 16 \
  --val-batches 10 \
  --learning-rate 1e-4 \
  --steps-per-report 10 \
  --steps-per-eval 100 \
  --save-every 100 \
  --adapter-path adapters/triage
```

**Clarifier** (420 rows across two instruction shapes — closest to the OIA notebook's clarification model, which used `--iters 600` on ~350 rows; bumped up given ~20% more data and two distinct sub-tasks to learn, not one):
```bash
python -m mlx_lm lora \
  --model microsoft/Phi-3.5-mini-instruct \
  --train \
  --data backend/data/clarifier \
  --iters 700 \
  --batch-size 4 \
  --num-layers 16 \
  --val-batches 20 \
  --learning-rate 1e-4 \
  --steps-per-report 10 \
  --steps-per-eval 100 \
  --save-every 100 \
  --adapter-path adapters/clarifier
```

`--iters` above are estimates anchored to the OIA notebook's validated values, not independently tuned for these exact datasets — watch the printed train/val loss as it runs (every `--steps-per-eval` steps, reported every `--steps-per-report` steps): if val loss stops improving or starts climbing while train loss keeps dropping, that's overfitting — stop early and use an earlier `--save-every` checkpoint rather than the final one. Next step after a run completes (not covered here yet): validate the resulting adapter against a small held-out set per item 4 above, before moving on to "Validated model build/deploy pipeline" below.

## Validated model build/deploy pipeline (after testing)

**Driven by: Moiz. Confirmed working end-to-end**, including a live Vercel-deployed frontend calling the deployed models successfully.

This replaces the untested assumptions in "Fine-tuning approach" and "Hosting" above with what was actually built, step by step, plus every real gotcha hit along the way.

### The pipeline

1. Fine-tune locally (MLX, MacBook Pro) — unchanged from the original plan
2. **Fuse** the adapter into a full model with `mlx_lm.fuse` (no special flags) — produces a standard HF-format directory
3. **Convert to GGUF** with `llama.cpp`'s `convert_hf_to_gguf.py`, then **quantize** with `llama-quantize` (Q4_K_M)
4. **Test locally** before uploading anything, using `llama-completion` (a real llama.cpp binary) — confirms the fine-tuned behaviour actually made it through the conversion, not just that a file got produced
5. **Upload to a private Hugging Face model repo** — this is now HF's only role: artifact storage, not serving
6. **Cloud Build** (triggered by a push to a dedicated branch) builds a Docker image that fetches the model from that private HF repo **at build time** (baked into the image), then deploys automatically to **Cloud Run**
7. Repeat steps 1-6 independently per model — this system runs **two fully-fused models loaded simultaneously in one Cloud Run service**, not one base model with hot-swapped adapters (see architecture update earlier in this doc)

### Gotchas/issues found (noting as each one cost time to diagnose and shouldn’t be repeated)

- **MLX's own native `mlx_lm.fuse --export-gguf` flag does not support Phi-3** (`ValueError: Model type phi3 not supported for GGUF conversion`) — must use the external `llama.cpp` conversion path (`convert_hf_to_gguf.py`) instead. Don't assume a framework's own "export to GGUF" feature covers every architecture.
- **`mlx_lm.fuse` doesn't write `tokenizer.model`** — `convert_hf_to_gguf.py` needs it and will fail with `Error: Missing tokenizer.model` without it. It's the base tokenizer, unaffected by fine-tuning, so it's safe to copy from the base model cache or any prior fuse output.
- **`convert_hf_to_gguf.py` needs the `gguf` pip package** specifically (small, pure-Python, no heavy deps of its own) — check what's already installed in the MLX training environment before assuming a fresh install is needed; torch/transformers/numpy/sentencepiece were already present in ours.
- **Always check for and kill lingering background processes before retrying a failed command.** Hit this twice: once a runaway `llama-cli` process silently kept holding GPU memory in the background, causing an out-of-memory error on the very next attempt; once an `hf upload` genuinely hung for 2 hours 40 minutes (only 27 seconds of real CPU time used in that whole span — check elapsed-vs-CPU-time, not just "is it still running," to tell a hang from real progress) before being killed and retried successfully.
- **`llama-cli`'s `--no-conversation` flag is no longer supported** in current `llama.cpp` builds (it silently starts an interactive chat loop instead, which hangs with no stdin attached) — use `llama-completion` for non-interactive single-shot testing instead.
- **Cloud Run's simple "auto-detect Dockerfile" build path does not support custom Docker build-args at all** — passing the private HF repo's access token into the build (to fetch the model at build time) requires a custom `cloudbuild.yaml` with an explicit `--build-arg`, plus a Cloud Build **substitution variable** holding the token value.
- **`ARG`-based build-time secrets can persist in the image's layer history** (`docker history` would show it) — acceptable tradeoff for a private image in our own project, but switch to a BuildKit `--mount=type=secret` instead if this image is ever made public or shared.
- **Cloud Build service accounts changed behaviour for projects created after mid-2024** — new projects don't get the old default "Cloud Build legacy service account" automatically. Needed to create a dedicated custom service account with four specific roles: **Cloud Build Service Account**, **Artifact Registry Writer**, **Cloud Run Admin**, **Service Account User** — and explicitly select it in the trigger's "Service account" field (the Compute Engine default SA that appears as the other dropdown option does *not* have these roles and would fail partway through the build).
- **Cloud Run Admin API must be explicitly enabled per project** before the first deploy — a one-time console click, easy to miss and easy to fix (the error message names the exact URL to enable it at).
- **Pin exact versions for CLI tools baked into a Docker image, don't rely on "latest."** Hit a real failure from this: `requirements.txt` pinned an old `huggingface_hub` version (no `hf` CLI command included), and a later `pip install "huggingface_hub[cli]"` with no version constraint saw the old version as "already satisfied" and installed nothing new — resulting in `hf: command not found` (exit code 127) inside the Docker build. Fixed by removing the unnecessary runtime pin (the app doesn't actually import `huggingface_hub`) and pinning an exact known-good version (`huggingface_hub[cli]==1.10.1`) for the build-time model-fetch step specifically.
- **Vercel's rewrite/proxy config lives in `vercel.json`**, mirroring whatever local dev-server proxy config already exists (e.g. Vite's `server.proxy`) — the production build ignores dev-server proxy settings entirely, so this needs its own explicit config, not an assumption that "it already works because dev mode does."
- **Vercel's branch-to-environment mapping moved** — it's no longer under Settings → Git → "Production Branch" (an older UI location); it's now under **Settings → Environments → (click the Production environment) → Branch Tracking**. Worth knowing before assuming a documented setting has vanished.
- **Response latency is noticeably slower on Cloud Run than the MacBook Pro** for the same quantized model — expected, not a bug: no GPU/Metal acceleration on Cloud Run's CPU-only instances, virtualized vCPUs vs. real Apple Silicon cores, plus normal network round-trip. Not something to "fix," just something to expect and mention honestly in the pitch if asked.

## Polling logic

**Driven by: Moiz**

- One async task per source, each on its own interval (GeoNet 1-2 min, MetService 2-5 min, NZTA 5 min, GWRC 5-10 min)
   - Update: not doing this any more
- Normalise into common schema before hitting the classifier — the classifier should never see source-specific formats
- Dedup by source-native ID/timestamp, not by content hash (cheaper, avoids near-duplicate false negatives)
- Log every poll (success/fail/count) — this feeds the "poll-health" indicator in the UI, which is also useful for debugging on the day
- *Technical note: wrap each source's parsing in try/except-and-skip, not assume well-formed responses — real external APIs occasionally return malformed or unexpected shapes, and one bad response shouldn't crash the poller mid-demo.*
- SUPERSEDED — see "Public-submission-triggered flow" below. The design above (independent always-on background timers per source) doesn't reliably survive Cloud Run's scale-to-zero behaviour. The normalize-into-common-schema, dedup-by-native-ID, and try/except-and-skip logic all carry over unchanged — only when polling happens has changed (triggered by a request, not a standalone timer), plus an added in-memory cache with a 5-minute throttle.

## Proposed event schema

**Driven by: Moiz (proposes), all agree before frontend build starts**

The event schema is the single shared JSON shape a triaged public report is stored and displayed
as. This is the contract between backend and frontend: the Triage Classifier only ever writes to
`severity` and `rationale`; `hazard_type` is set deterministically by the aggregator; the dashboard
only ever reads from these fields.

```json
{
  "id": "community-1785806523715",
  "source": "community",
  "source_type": "community",
  "ingested_at": "2026-08-08T10:32:11Z",
  "event_time": "2026-08-08T10:31:45Z",
  "location": {
    "suburb": "Ngaio",
    "lat": -41.2408,
    "lon": 174.7645
  },
  "raw_text": "Water coming up on the street near my house",
  "clarified_text": "Water coming up on the street near my house. Started about 20 minutes ago, roughly ankle-deep, near the Ngaio shops.",
  "clarification_question": "Roughly when did you notice this, and how deep is the water?",
  "clarification_answer": "Started about 20 minutes ago, roughly ankle-deep, near the Ngaio shops.",
  "actions": ["monitor_situation"],
  "contact": "027xxxxxxx",

  "official_context": [
    { "source": "metservice", "hazard_type": "severe_weather", "severity_hint": "medium", "minutes_ago": 55, "summary": "Severe Thunderstorm Watch, Wellington region" }
  ],
  "related_report_id": null,

  "hazard_type": "severe_weather",
  "severity": "medium",
  "rationale": "Matches an active MetService severe weather watch for the region; no other corroborating reports yet.",

  "status": "triaged"
}
```

Field notes:
- **`id`** — unique per event; used for dedup, not a random UUID
- **`source`** / **`source_type`** — always `"community"` for a triaged public report — official-source events no longer exist as standalone displayed items (see "System summary"), only as `official_context` entries attached to a report
- **`ingested_at`** vs **`event_time`** — when the report was received vs. when the submitter says it happened; both matter for the poll-health indicator and staff trust in recency. *Technical note: store both in UTC, convert to NZ local time only at display time.*
- **`location`** — `suburb` is what the dashboard filters/displays by; `lat`/`lon` optional, either from the browser's Geolocation API (preferred — real coordinates, requires the submitter to grant permission) or resolved from `suburb` via the gazetteer's centroid if not given. `context.resolve_location()` already prefers real coordinates over the centroid fallback whenever both are present — no aggregator changes needed when the frontend started supplying them
- **`raw_text`** — the original, unedited submission
- **`clarified_text`** — `raw_text` + the submitter's answer, deterministically concatenated (not model-produced — see FINETUNE_PLAN.md "Model 1 — Clarifier"); kept alongside `raw_text` so staff can see both
- **`clarification_question`** — Clarifier Call 1's output; Phase 2 only, null in Phase 1
- **`clarification_answer`** — the submitter's raw answer to `clarification_question`, kept separately from `clarified_text` for transparency; Phase 2 only, null in Phase 1
- **`actions`** — Clarifier Call 2's output, 1-2 items from a fixed vocabulary (`check_neighbours` / `monitor_situation` / `document_further` / `call_111` / `evacuate` / `none`) shown to the submitter as an immediate actionable response once they answer. **⚠️ Combines non-critical and safety-critical suggestions into one call for the hackathon build** — deliberate simplification, not the intended long-term design; see FINETUNE_PLAN.md's limitation note and PITCH.md's roadmap for the deferred dedicated third model. Phase 2 only, empty in Phase 1
- **`contact`** — optional, free text (email or phone, unvalidated), collected on the same final step as `actions` — how the council can follow up with this specific submitter later, if they chose to give it. Never required, never blocks submission. Phase 2 only, null in Phase 1 (no equivalent later step to collect it on there)
- **`official_context`** — the deterministically-built array of relevant official events (see `docs/FINETUNE_PLAN.md` for the exact format/render contract); this is Triage Classifier *input*, and shown to staff so the "why" behind a judgement is inspectable
- **`related_report_id`** — set if the aggregator found one related pre-existing public report to include as extra context (also Triage Classifier input); null if none found
- **`hazard_type`** — set deterministically by the aggregator: inherited from a matched official source in `official_context`, else `"other"`. **Never produced by the LLM.**
- **`severity`** / **`rationale`** — the Triage Classifier's entire output. `rationale` is a one-line free-text explanation, shown on hover/in the detail panel
- **`status`** — Phase 1: `"new"` → `"triaged"` (final). Phase 2 adds `"awaiting_clarification"` (Call 1 done, waiting on the submitter's answer) as the initial state, before transitioning to `"new"` once Call 2 finishes and triage begins, then `"triaged"` (final) — same end state either phase

This is a starting proposal, not final — the team should agree the exact field names together before Isla's frontend build starts against it.

## Public-submission-triggered flow

**Driven by: Moiz.** This is the concrete version of the "Architecture Update" summarized near the top of this doc — read that first for the why, this section is the how.

1. **Public submits a report** via the form (`raw_text`, optional location). Social media as a second input channel is a later phase, not this pass.
2. **Clarifier Call 1 ("ask") runs immediately and always** — no branch for "already clear enough," it always produces at least one follow-up question. Deliberate simplification: removes a judgement call from the model, keeps the interaction predictable, and the two-way-channel story (secondary track) is stronger when every submission visibly gets a human-feeling follow-up. **⚠️ Phase 2, not built yet — see the phased-rollout note in "System summary".** Phase 1 (built, tested, working) skips this step entirely: `raw_text` goes straight to step 5, and `clarified_text`/`clarification_question`/`actions` stay null/empty.
3. **Submitter answers the question; Clarifier Call 2 ("act") runs**, producing 1-2 action items shown on the form as the immediate, actionable response (see FINETUNE_PLAN.md "Model 1 — Clarifier" for the vocabulary and the limitation this call has — no official context yet). `clarified_text` is built deterministically here too (raw text + the answer, no model call needed). Backend implementation (Phase 2, not called from the frontend yet): `POST /events/community-report/clarify` (step 2 above) returns the event with `clarification_question` set and `status: "awaiting_clarification"`; `POST /events/{id}/clarification-answer` (this step) returns the event with `actions` set and triggers step 5.
4. **Submitter is thanked immediately** once this exchange completes — this response does not wait on anything downstream (poller, aggregation, classifier). Whatever happens next is invisible to the public user. (Phase 1: this is immediately after step 1, since there's no Call 1/Call 2 exchange to wait on.)
5. **The clarified submission triggers the poller.** Async, not blocking the thank-you response above. This request is also what keeps the Cloud Run instance alive long enough to do the fetch — solves the scale-to-zero problem directly, rather than fighting it with `min-instances`.
6. **Poller checks its in-memory cache first.** If official-source data was fetched within the last 5 minutes, reuse it; otherwise fetch fresh from GeoNet/MetService/NZTA/NEMA/GWRC and refresh the cache. This throttle exists to avoid hammering external APIs on every single submission, not to limit staff-visible freshness (a burst of several reports in the same 5 minutes all share one fetch).
7. **Aggregation** builds two small deterministic context blocks:
   - `official_context` — the (possibly cached) official data filtered to what's relevant by location proximity and recency (see `docs/FINETUNE_PLAN.md` for the exact per-source distance/relevance rules — GeoNet/NZTA/NEMA/GWRC via Haversine on real coordinates, MetService via a Wellington place-name keyword match since it has no coordinates at all)
   - `related_report_id` — at most **one** related pre-existing public report found in the same event store by location/recency, if any exists — deliberately capped at one so the model reads it as qualitative corroborating evidence, not something to count
8. **Triage Classifier** takes the clarified report + both context blocks → outputs **only** `severity` and `rationale`. Immediately after, the **aggregator deterministically sets `hazard_type`** — inherited from a matched official source in `official_context` if one exists, else `"other"`. The model never produces `hazard_type`, and there is no structured corroboration field or counting logic anywhere in the system (see FINETUNE_PLAN.md for why these were deliberately dropped from the hackathon-day scope).
9. **Aggregator stores the triaged event.** The staff dashboard's existing poll of `GET /events` picks this up on its next cycle — no separate push mechanism needed, same polling-based frontend design as originally planned.

**Deferred, noted for later (not built in this pass):** a manual/on-demand trigger staff can pull themselves (independent of waiting for a public submission) to force an official-source refresh — same trigger point as step 5, just staff-initiated instead of public-submission-initiated. Could later run on a schedule instead of being manual. Worth revisiting once there's a reason to prioritise it (e.g. WCC feedback that staff want to check official status without waiting for a public report).

**What this means for the dashboard's grouping:** events are grouped by **location**, not by source — a public report and the official context attached to it render together as one location-grouped item, not as separate entries competing for attention in a flat feed.

## API

**Driven by: Moiz.** The concrete contract behind "Public-submission-triggered flow" above — what the frontend actually calls, in Phase 1 and Phase 2. All implemented and tested (`backend/app/main.py`).

| Method + path | Phase | Request body | Response | Notes |
|---|---|---|---|---|
| `GET /health` | both | — | `{"status": "ok", "poll_health": {...}}` | |
| `GET /events` | both | query params: `suburb`, `hazard_type`, `source_type` (all optional) | `list[Event]` | Staff dashboard polls this every 10-15s |
| `POST /events/community-report` | Phase 1 | `{"raw_text": str, "suburb": str \| null, "lat": float \| null, "lon": float \| null}` | `Event` (`status: "new"`) | No clarifier call — submits straight to triage. Untouched by the Phase 2 endpoints below; stays the fallback when the frontend's clarifier flag is off |
| `POST /events/community-report/clarify` | Phase 2, step 1 | `{"raw_text": str, "suburb": str \| null, "lat": float \| null, "lon": float \| null}` | `Event` (`status: "awaiting_clarification"`, `clarification_question` set) | Clarifier Call 1 ("ask"). Does **not** trigger triage yet |
| `POST /events/{event_id}/clarification-answer` | Phase 2, step 2 | `{"answer": str, "contact": str \| null}` | `Event` (`status: "new"`, `actions`, `clarified_text`, and `contact` set) | Clarifier Call 2 ("act"). **This** is what triggers triage — `404` if `event_id` unknown, `400` if the event isn't currently `awaiting_clarification` (e.g. already answered) |

**⚠️ Open, not yet decided:** the query-param name for the frontend's Phase 2 clarifier flag is referenced conceptually in "PHASED ROLLOUT" above but has never actually been picked — needs a name before Isla's frontend work reaches this point.

**Geolocation (`lat`/`lon` on `CommunityReport`) and `contact` (on `ClarificationAnswer`), added
together:**
- **Geolocation needed no aggregator changes at all.** `context.resolve_location()` already
  preferred real coordinates over the suburb-centroid fallback the moment they're present — it was
  built that way from the start, just never had a caller that actually supplied them. Purely a
  request-model + `Location(...)` construction change in `main.py`; `build_official_context()` and
  `find_related_report()` needed nothing.
- **`contact` is collected only on the final step** (`ClarificationAnswer`, Call 2), not the
  initial form — deliberately, to keep first-step friction low. Free text, no shape validation
  (email vs. phone) — staff read it directly, nothing parses or uses it programmatically yet.
  Phase 1 (single-step) has no equivalent field — there's no "later step" to defer it to there,
  and Phase 1 stays intentionally minimal as the low-friction fallback.
- **⚠️ Open, not yet decided — privacy:** real GPS coordinates from the Geolocation API can be
  precise to a few metres, potentially precise enough to identify a submitter's home address if
  they report from there. Currently stored and used at full precision — no rounding/fuzzing
  applied. Worth a decision (and probably Sara's community-sensitivity review, same checkpoint
  already planned for UI copy) before this reaches real submitters: store as given, or round to a
  coarser precision (e.g. ~100m) before persisting, trading some triage accuracy for reduced
  identifiability.

**"Common operating picture" requirement, confirmed from the organisers' README:** "Each team's
module is meant to slot into a shared common operating picture — a live map of emergency signals
that the ten prototypes feed together. Aim for something that can be pointed at a map, a feed or
an API, rather than a closed-off demo." `GET /events` above already satisfies the *shape* of this
— a plain, unauthenticated JSON endpoint returning our full triaged-event list.

**✅ Fixed while checking this** — `backend/app/main.py` had **no CORS middleware configured at
all** until this was checked directly. Not just a hypothetical gap for another team's tool: it
would have silently blocked our *own* frontend once deployed, since Vercel and Cloud Run are
different origins and browsers enforce CORS by default — the generic Risk list entry below ("CORS
between Vercel frontend and HF Space backend") turned out to be a concrete, already-present gap,
not just a risk to watch for. `CORSMiddleware` added with open origins (`allow_origins=["*"]`) —
matches the API's existing no-auth design (see "Hosting" below), not a new exposure, and also
satisfies the "point an API at it" half of the common-operating-picture requirement for other
teams' tools. Confirmed working (tested with a cross-origin request, real `Access-Control-Allow-Origin` header returned).

## Official data sources — current and deferred

**Current (5, all live, all polled):** GeoNet, MetService, NZTA, NEMA (Emergency Mobile Alert CAP
polygons), GWRC (river levels + rainfall telemetry). The last two were added after the hackathon
organisers released their own data catalogue
(`claudecommunity-nz/wcc-emergency-gis-data`) — see `app/sources/nema.py` and `app/sources/gwrc.py`
for the full rationale and gotchas found building each.

**Deferred, not this pass** — evaluated against the same catalogue, confirmed live and working,
but not built:
- **NEMA electricity outages** — live national outage points (NEMA), would fill the `power_utility`
  gap our Clarifier training data already has scenarios for but no official source behind
- **Wellington Water network faults (live)** — live burst-pipe/fault jobs, same gap from the water
  side
- **MetService polygon-geometry upgrade** — the hackathon catalogue's MetService endpoint
  (Eagle Technologies' ArcGIS-hosted version) has **real polygon geometry**, confirmed live —
  unlike our current raw CAP feed, which has none (the reason the Wellington gazetteer
  keyword-match workaround exists at all). Swapping to it would let real distance/point-in-polygon
  matching replace the keyword-match approximation — a fix to a named limitation, not new coverage.
  More work than adding a new source: means rewriting `metservice.py`'s relevance logic, not just
  plugging in a new module.
- **NZTA via the same catalogue** — a different endpoint (Eagle/ArcGIS) than our current one; worth
  a comparison later, not urgent since the current NZTA source already works
- **GNS ShakingLayers** (ground motion) — would refine GeoNet's earthquake severity assessment;
  enrichment of existing coverage, not a new hazard type

Adding any of these needs the same treatment `nema.py`/`gwrc.py` got: inspect the real live schema
first (don't assume from the catalogue description alone), confirm recency/timezone handling
empirically, and check whether the hazard needs a new taxonomy value or fits the existing one.

## Frontend (Svelte 5 + Tailwind, deployed on GitHub Pages + Vercel)

**Driven by: Moiz + Isla (build + UX/user journey), Sara (reviews copy/labels — see checkpoint above)**

Three-panel dashboard:
- **Map** — Wellington suburbs, pins colored by severity
- **Feed panel** — cards grouped by **location** (not a flat per-source list — official-source events never appear standalone, only as `official_context` attached to the public report that triggered their retrieval), each card showing the deterministic `hazard_type`, `severity`, and time
- **Detail panel** — the report's `raw_text`/`clarified_text`, the `clarification_question`/`clarification_answer` exchange, the suggested `actions` shown to the submitter (Phase 2), the Triage Classifier's `rationale` (shown on hover), and the `official_context` list so staff can see exactly what informed the triage judgement

Data flow: `setInterval` fetch against backend `/events` every 10-15s, render with Svelte 5 runes (`$state`, `$derived`). No auth needed for demo. Not a requirement but good to have offline/PWA.

## Hosting

**Driven by: Moiz**

- **Model + backend + poller:** single Hugging Face Space (Docker SDK, free CPU tier — 2 vCPU/16GB RAM)
- **Frontend:** Vercel (free Hobby tier — static SPA, no cron needed)
- Keep the HF Space awake during judging by having the frontend actively polling it beforehand

**⚠️ UPDATE — frontend hosting also changed, separately from the backend pivot below:** GitHub
Pages (primary, per the hackathon organisers' preference) + Vercel (live backup, not just Vercel
alone) — see the "Deployment map v2" table and `FRONTEND_PLAN.md`'s "Hosting: dual-platform
design" for the full setup.

**⚠️ UPDATE — HF Space part unsuccessful, replaced with Google Cloud Run (validated end-to-end pre-hackathon):**
- Hugging Face now requires a paid PRO plan ($9/month) for any Docker or Gradio Space — confirmed policy, only Static/client-side Spaces are free, which can't run our backend
- **Model + backend + poller now target: Google Cloud Run** (Docker-capable, Always Free tier: 180,000 vCPU-seconds + 360,000 GiB-seconds memory + 2M requests, per month, ongoing not a trial)
- **Important:** that free quota is pooled **per Google billing account**, not per service or per project — the hackathon system's own Cloud Run service will share the same monthly pool as anything else running under the same account
- **Hugging Face's role changed, not removed:** a private HF model repo still stores the model artifacts (GGUF files) as the source of truth — Cloud Build fetches from there at **build time** (baked into the image, not fetched at runtime) specifically because Cloud Run scales to zero and cold starts happen regularly; baking in avoids repeating a multi-GB download on every cold start
- Frontend deploy (Vercel) is unchanged — same target, just pointed at the Cloud Run URL instead of a Space URL
- Full setup steps, gotchas, and real timings: see "Validated model build/deploy pipeline" below

## Deployment map (what runs where)

| Component | Runs where | Notes |
|---|---|---|
| Poller (async ingestion loop) | Hugging Face Space | Background task inside the same FastAPI process — no separate service |
| Classifier LLM (Adapter 1) | Hugging Face Space | Loaded in-process; LoRA-swapped on the shared base model |
| Clarifier LLM (Adapter 2) | Hugging Face Space | Same base model instance, swapped via LoRA weights per request — not a second model |
| Backend/API (FastAPI, `/events`) | Hugging Face Space | Serves ingestion, both adapters, and the community-report intake from one process |
| Event store (SQLite/in-memory) | Hugging Face Space | Ephemeral — resets on Space restart/sleep; reseed community-report examples before recording/demoing, don't assume they persist |
| Staff dashboard (frontend) | Vercel | Static SPA, calls the HF Space's public API |
| Public community-report form | Vercel — same deployment, separate route | Not a separate app; just another view in the same frontend project |
| Simulated backup-device UI (stretch goal) | Vercel — same deployment, separate route | Same frontend project, third view |

The model, backend, poller, and both adapters intentionally live in **one** Hugging Face Space (one container, one process) rather than being split across services — this keeps the poller-to-classifier path an in-process call with no network hop, and means there's only one thing to deploy/debug on the backend side. The frontend is the only separate deployment (Vercel), talking to the Space over its public API — this split is also why CORS shows up on the risk list.

### Deployment map v2 (validated pre-hackathon — replaces "Hugging Face Space" above with Google Cloud Run)

The single-process principle above still holds — only the specific host changed, plus the model-storage role Hugging Face now plays.

| Component | Runs where | Notes |
|---|---|---|
| Poller (async ingestion loop) | Google Cloud Run service | Background task inside the same FastAPI process — no separate service |
| Triage Classifier | Google Cloud Run service | Loaded fully in-process as its own fused GGUF model — not LoRA-swapped, see architecture note above. Outputs only `severity` + `rationale`; `hazard_type` is set deterministically by the aggregator, not this model |
| Clarifier | Google Cloud Run service | Same process, second fully-loaded fused GGUF model, both resident simultaneously — called **twice** per submission (Call 1 "ask", Call 2 "act"), task-conditioned via a different system prompt per call, not two separate models — see FINETUNE_PLAN.md "Model 1 — Clarifier" |
| Backend/API (FastAPI, `/events`) | Google Cloud Run service | Same one-process design as originally planned |
| Event store (SQLite/in-memory) | Google Cloud Run service | Same ephemeral caveat as before — resets when the instance scales to zero |
| Model artifacts (GGUF files) | **Hugging Face Hub (private model repo)** | New: storage/versioning only, not serving — fetched at Cloud Build **build time**, baked into the container image |
| Staff dashboard (frontend) | **GitHub Pages (primary) + Vercel (live backup)** | Both deploy on every push, not just Pages — see `FRONTEND_PLAN.md`'s "Hosting: dual-platform design" for the build setup (`adapter-static`, direct-fetch, no rewrite proxy) |
| Public community-report form | Same two hosts as above, separate route | Not a separate app; just another view in the same frontend project, same as before |
| Simulated backup-device UI (stretch goal) | Same two hosts as above, separate route | Unchanged |

## Stretch goal (only if core demo is solid by ~3:00 PM): simulated backup-device UI

**Driven by: Isla (build), Sara (reviews framing/labels)**

Purpose: show judges the team has thought past the software layer to real-world resilience — the "large-scale, real-users, real-emergency" story — without claiming to have built actual hardware.

- Add a third, visually distinct panel/view to the frontend styled as a **low-bandwidth backup device**: e.g. an e-ink-style monochrome card showing only the top 3-5 critical/high-severity items in plain text, or an "SMS terminal" view showing the same items as short message-style lines
- Feed it from the same `/events` API, filtered to high-severity only — no new backend logic needed, just a second UI render mode
- Clearly label it in the UI (e.g. a banner: "Simulated concept — backup device for degraded-connectivity scenarios, see roadmap") so it reads as a deliberate concept demo, not an unfinished feature
- Mention it explicitly in the demo video as "here's what a Council backup dashboard or community-node device could look like" — ties directly to the roadmap's resilience-layer slide
- **Do not** attempt real SMS/radio integration on the day — this is a UI concept only; time spent on actual hardware/telephony integration is better spent hardening the two core adapters

## Risk list (check these early - add more, as they arise)

- [ ] **(Moiz)** Any open data source requiring an API key/approval not yet obtained
- [ ] **(Moiz)** LoRA fine-tune taking longer than expected — have a fallback (few-shot prompting instead of fine-tuning) ready as Plan B for one of the two adapters if time runs short
- [ ] **(Moiz)** HF Space cold-start/sleep timing during actual judging slot
- [x] **(Moiz + Isla)** CORS between Vercel frontend and HF Space backend — **fixed**: `CORSMiddleware` added to `main.py` after checking and finding it genuinely missing, not just a theoretical risk (see the "Common operating picture requirement" note in the API section above)
- [ ] **(Sara)** Clearly labeling simulated vs. real data in the demo
- [ ] **(All)** No fallback if venue wifi degrades or drops right before judging — the whole demo depends on live external API calls; have a cached/seeded "replay" mode or the recorded video ready as backup if live polling fails during the live demo slot
- [ ] **(Moiz)** Venue network may block some outbound domains/ports (rarer, but happens on conference wifi) — worth testing connectivity to HF Spaces/Vercel/the 5 data sources from the actual venue network if anyone can arrive early
- [ ] **(Moiz)** Cloud Run's shared free-tier pool (per billing account, not per service) means the hackathon system's Cloud Run usage isn't independent of anything else running under the same Google account — check actual usage against the 180,000 vCPU-second/month pool if other services are active
- [ ] **(Moiz)** When repeating the Cloud Run deploy for the hackathon's two models: budget time for the same one-time setup snags hit here (enabling the Cloud Run Admin API, creating a custom Cloud Build service account with the right four roles, writing a `cloudbuild.yaml` for build-arg support) — none of these are hard, but none are instant either the first time
- [ ] **(Moiz)** In-memory official-source cache resets whenever the Cloud Run instance scales to zero — treat the 5-minute throttle as "don't re-fetch too often while warm," not as a durability guarantee; a cold start after idle time re-fetches regardless of the 5-minute window
- [ ] **(All)** Official-source events no longer appear on the dashboard independently of a public report (scope narrowed from the original "official + community in one view" framing) — make sure the demo narrative and pitch honestly reflect this scope, not the earlier framing (see PITCH.md update)
