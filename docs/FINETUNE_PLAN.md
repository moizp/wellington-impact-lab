# Fine-tuning plan — Clarifier + Triage Classifier

Final, simplified design. Two small fine-tuned models sit inside the public-submission-triggered
flow (see `BUILD_PLAN.md`'s "System summary" and "Public-submission-triggered flow" for the full
pipeline). This doc is about *what to train each model on*; the mechanical how-to (fine-tune →
fuse → GGUF → quantize → test → upload → Cloud Build → Cloud Run) is unchanged and already
validated end-to-end via the OIA project — see `BUILD_PLAN.md`'s "Validated model build/deploy
pipeline".

## Base model

**Phi-3.5-mini-instruct** — small enough to fine-tune on a MacBook Pro in minutes via MLX, small
enough to run cheaply on Cloud Run's CPU-only free tier, whole pipeline already proven for this
exact model.

## The pipeline these two models sit inside

**⚠️ Built in two phases (agreed explicitly):** Phase 1 (below, with the Clarifier step struck
through) is built, tested, and working — single-step submission straight to triage. Phase 2 adds
the Clarifier once it's actually fine-tuned, plus a feature-flagged frontend step to call it. Don't
build against "Clarifier always runs" as current fact — it's the end state, not phase 1.

1. Public submits a report (raw text, optional location)
2. ~~**Clarifier Call 1 ("ask")** runs immediately, on every submission, no exceptions — always
   produces 1-3 clarifying questions~~ **Phase 2 only — not called in phase 1's backend code**
3. ~~Submitter answers the question; **Clarifier Call 2 ("act")** runs on (report + question +
   answer), producing 1-2 action items shown on the frontend as the immediate, actionable
   response~~ **Phase 2 only, same as step 2** — see "Model 1 — Clarifier" below for the full
   two-call design and its known limitation
4. Submitter is thanked (in phase 2, this is the natural close of the Call 1/Call 2 exchange);
   nothing downstream blocks them
5. That submission triggers the poller (official sources, 5-min in-memory cache/throttle)
6. Aggregator builds two small **deterministic** context blocks (no LLM involved in building
   them): relevant official data, and at most one related pre-existing public report
7. **Triage Classifier** takes the report (raw in phase 1, clarified in phase 2) + both context
   blocks → outputs `severity` + `rationale` — nothing else
8. Aggregator **deterministically** sets `hazard_type` (inherited from a matched official source,
   else `"other"`)
9. Staff dashboard shows the result, grouped by location, rationale visible on hover

## Model 1 — Clarifier

**Status: Phase 2 — not yet built/wired in.** `app/clarifier.py` exists as a stub with the decided
interface, but is not called from the submission endpoint yet. The design below is the target for
when it's actually fine-tuned.

**One model, two distinct inference calls** — task-conditioned via a different system prompt per
call. This is standard prompt-conditioned multi-task fine-tuning, the same underlying mechanism as
the rest of this project's "instruction contract" work (see Model 2's section below) — two
instruction shapes trained into one set of weights, not two separate models. Decided explicitly
over building a third model for the hackathon, given time constraints (see the limitation note
under Call 2 for why this is a deliberate simplification, not the intended long-term design).

- **Call 1 — "ask":** input is the raw report alone (`raw_text`, + optional location). Output is
  1-3 targeted clarifying questions — **always produced**, not conditional on the message being
  ambiguous. This is today's design, unchanged.
- **Call 2 — "act":** runs *after* the submitter answers Call 1's question. Input is `raw_text` +
  the clarifying question + the submitter's answer. Output is **1-2 action items**, drawn from a
  single unified vocabulary spanning both non-critical and safety-critical suggestions (see below).
  `clarified_text` itself is **not** produced by this call — it's a deterministic concatenation of
  `raw_text` + the answer (no judgement involved in stitching two pieces of text together, so no
  reason to spend a model call on it — same discipline that keeps `hazard_type` deterministic
  rather than LLM-produced).

Call 1 must stay single-purpose (just the question) — it cannot know what action to suggest yet,
since the whole point of asking is to obtain information that doesn't exist until the answer comes
back.

### Call 2 — action vocabulary and output format

**Vocabulary:** `check_neighbours` | `monitor_situation` | `document_further` | `call_111` |
`evacuate` | `none`

**Output format** (fixed template, mirrors the Triage Classifier's `Severity:`/`Rationale:`
pattern — same reasoning: simple, deterministic to parse, no JSON fragility with a small
fine-tuned model):
```
Actions: <action1>[, <action2>]
```
One or two comma-separated values from the vocabulary above, parsed by splitting on the comma —
same robustness philosophy as the Triage Classifier's `parse_triage_output()`.

**⚠️ Known limitation — deliberate, not accidental.** Call 2 only ever sees the raw report + the
clarifying Q&A. It has **no access to official context, no corroboration, and no Triage Classifier
severity/rationale**, because it runs *before* the poller/aggregation/triage step in the
public-submission-triggered flow (see `BUILD_PLAN.md`). This means the system's highest-stakes
recommendations (`call_111`, `evacuate`) are made on the least-informed, least-corroborated basis
in the entire pipeline — combined into the same call and vocabulary as low-stakes suggestions
purely to fit a one-day build, not because that's the right long-term architecture. This should be
stated plainly in the demo/pitch as a named limitation, not left implicit.

The architecturally sounder version, **deferred to the roadmap** (see `PITCH.md`), is a dedicated
**third model** running *after* the Triage Classifier — informed by official context and the
severity/rationale judgement, so high-stakes actions get decided at the most-informed point in the
pipeline, not the least. Whether a `call_111`/`evacuate`-style output should ever reach the public
submitter directly, versus only flagging staff, is also an open question for that later phase, not
resolved here.

**Relevant new context for the deferred static-banner decision** (see `FRONTEND_PLAN.md`'s open
questions): the hackathon organisers' own README states, as a ground rule for the whole event —
*"These are hazard-planning layers, not live emergency information. In an emergency, call 111."*
Written about the underlying GIS data, not our Clarifier specifically, but it's evidence of the
organisers' own house style for this exact kind of disclaimer, worth weighing when that decision
actually gets made.

### Dataset plan

Entirely synthetic, same approach as the OIA project's clarification model, now split across two
instruction shapes:
- **Call 1 examples:** NZ hazard reports spanning the full completeness spectrum, paired with the
  question a human triage operator would actually ask at that level of detail.
- **Call 2 examples:** report + question + a plausible answer, paired with 1-2 action items a human
  triage operator would suggest given *only* that combined information — no official data is
  available at this stage, and the dataset should reflect that constraint honestly rather than
  assuming corroboration Call 2 will never actually have at inference time.

**Sample size note:** since this is now two distinct instruction-following tasks sharing one model,
the ~150-row target (see "Sample size" under Model 2) applies to **each call roughly
independently** — around 150 for Call 1 and 150 for Call 2, not 150 total split between them, or
one sub-task ends up under-trained relative to the other.

Train/valid mechanics are otherwise the same for both models — see "Sample size" and "Training
mechanics" under Model 2 below, rather than duplicated here.

## Model 2 — Triage Classifier

**Input:** clarified public report text + `official_context` block + (optional) one related
pre-existing public report block
**Output:** `severity` (`low` | `medium` | `high`) + `rationale` (one-line free text) — **that's
the entire output.**

### What's deliberately excluded, and why (simplified for a one-day build)

- **No LLM-produced `hazard_type`.** Set deterministically by the aggregator instead: inherited
  from a matched official source in `official_context` if one exists, else `"other"`. Each
  official source already implies a fixed hazard type (GeoNet → earthquake, NZTA → road_hazard,
  MetService → severe_weather/road_hazard depending on warning type) via simple rules — no
  inference needed, and pushing this into the model would have meant building a
  confirmed/contradicted/inconclusive matching state machine that added real complexity for no
  clear hackathon-day benefit. Deferred; revisit only if there's evidence it's needed.
- **No structured `corroboration` field.** If a report agrees or disagrees with official/public
  context, that shows up naturally in the free-text `rationale` — not tracked as a separate,
  separately-tested field.
- **No counting logic anywhere.** LLMs are unreliable at exact counting, so the aggregator caps
  related-report context at **one** — the model is asked to make a *qualitative* corroboration
  judgement ("does this related report describe the same thing, and does that change how serious
  this looks"), the same kind of task it already does for official context, not a quantitative one
  ("how many reports, apply a threshold"). No deterministic severity-boost-by-count rule either —
  deliberately dropped in favour of the model learning the qualitative pattern directly from
  training examples.

### Why classify the public report and not official sources directly

Each official source already publishes its own severity signal before it's reduced to `raw_text`
(GeoNet magnitude/depth, NZTA `impact` field, MetService warning-title vocabulary) — re-deriving
that with an LLM would be a slower, less reliable version of information already free. The
genuinely valuable, non-redundant problem is judging an unverified public claim against what's
officially and publicly known — that's this model's entire scope.

### Official context format (finalized)

**Structured item, per relevant official event:**
```json
{
  "source": "geonet" | "metservice" | "nzta" | "nema" | "gwrc",
  "hazard_type": "earthquake" | "severe_weather" | "flooding" | "road_hazard" | "fire" | "other",
  "severity_hint": "low" | "medium" | "high",
  "distance_km": 8.2,
  "minutes_ago": 14,
  "summary": "M4.2 earthquake, 12km deep, near Ngaio"
}
```

`severity_hint` and `hazard_type` here are deterministic, rule-derived (not an LLM call) — this is
what the aggregator later inherits `hazard_type` from when `severity_hint`/corroboration reads as
relevant:
- **GeoNet**: magnitude thresholds (draft: <3.5 low, 3.5-5 medium, >5 high — refine with
  Sara/WCC input)
- **NZTA**: lookup on the `impact` field (`"Caution"` confirmed as one observed value; other
  values still need enumerating from more live samples)
- **MetService**: keyword match on warning title (`"Red"` → high, `"Orange"`/`"Severe"` → medium,
  else low)
- **NEMA** (Emergency Mobile Alert CAP polygons, added after the hackathon organisers' data
  catalogue was released): `severity_hint` from the CAP standard `severity` field directly
  (Extreme/Severe → high, Moderate → medium, Minor/Unknown → medium as a safe default, same
  precedent as NZTA's unknown-impact fallback). `hazard_type` from the CAP `category` field
  (Fire → fire, Met → severe_weather, Geo → earthquake, Transport → road_hazard, everything else
  → other) — every category observed maps onto the existing taxonomy, no new hazard_type needed.
- **GWRC** (river levels + rainfall telemetry, same catalogue): two sub-feeds, both `hazard_type:
  flooding`. River sites: `severity_hint` from `Stage_pct` (current level as % of that site's own
  historical range — ≥100% high, ≥75% medium, else low). Rainfall sites: `severity_hint` from
  `RainTot6Hrs` (mm in the past 6h — ≥50mm high, ≥20mm medium, else low). Both threshold sets are
  drafts, same "refine with Sara/WCC input" caveat as GeoNet's magnitude bands — not derived from
  an official warning-tier definition.

**Canonical render** (identical function used for training data and live serving — this is the
actual text handed to the classifier):
```
Official context (2 items found near this location):
- GeoNet: M4.2 earthquake, 12km deep, near Ngaio (8.2km away, 14 min ago) [severity: medium]
- MetService: Severe Thunderstorm Watch, Wellington region (55 min ago) [severity: medium]

Related public report:
- "Water pooling on the road, getting worse" (0.4km away, 22 min ago)
```
(Dropped the "past few hours" qualifier that used to sit in the header line — it's redundant with
each item's own `minutes_ago`, and became actively misleading once GeoNet's window was widened to
24h and NZTA/MetService have no fixed window at all — see below.)
When nothing relevant is found, this must say so explicitly, not return an empty string:
```
Official context: No relevant official data found for this location/time.
```

### Distance and region-matching — confirmed empirically, not assumed

- **GeoNet**: always real point coordinates (confirmed — every quake feature has lat/lon).
  Distance via the Haversine formula, plain code, no external library or API. Recency window is
  **24h, not a tighter cutoff** — a felt earthquake can trigger an emergency situation (aftershocks,
  delayed damage reports, ongoing structural assessment) well past the initial shake, so a quake
  from earlier the same day stays relevant context, not stale.
- **NZTA**: confirmed empirically — all 104 live features checked had `Point` geometry, zero
  nulls. Same Haversine calculation applies directly.
- **MetService**: confirmed empirically — **no coordinates anywhere in the CAP feed**, only place
  names embedded in free text. It's also a **nationwide** feed, not Wellington-specific, so it
  cannot simply be "always included." Handled instead via a **static Wellington-region gazetteer**
  — a maintained list of Wellington suburb names plus the word "Wellington" itself — keyword
  matched against each warning's title/description text. This is inherently approximate (an
  unlisted place name gets missed) — a named, honest limitation, not a hidden gap.
- **NEMA**: real point coordinates, but derived, not native — the feed carries polygon geometry
  (the alert's broadcast area), not a point. Resolved via a simple vertex-average centroid of the
  outer ring (not area-weighted — an approximation, same MVP-scale tradeoff as the gazetteer's
  suburb centroids), then the same Haversine calculation as GeoNet/NZTA. Also nationwide — a
  Northland civil defence alert and a generic national test message both showed up in early
  sampling — so the same distance filter is what keeps it Wellington-relevant, not a gazetteer.
- **GWRC**: real point coordinates, requested directly as lat/lon (`outSR=4326`) rather than the
  service's native projection — same Haversine calculation as GeoNet/NZTA. Confirmed empirically:
  its `LatestTime` field is **NZ local time, not UTC, with no timezone marker** — naively parsing
  it as UTC would silently mis-timestamp every event by 12-13 hours. Also confirmed empirically:
  some listed sites return years-stale readings (one rainfall site's sample was from 2018) —
  filtered out client-side by recency (readings older than 6h treated as not currently reporting),
  same principle as NZTA's `status == "active"` check.
- **Related public reports**: matched the same way as GeoNet/NZTA (Haversine against the
  submitter's location, if given), sourced from the same in-memory event store — no separate
  cache needed, since community reports are already stored there.
- **If the public submitter gives no location**, GeoNet/NZTA/NEMA/GWRC are excluded entirely, not
  shown via a distance-blind "recency-only" fallback — confirmed empirically that a naive fallback
  surfaced quakes 150km+ from Wellington (Kaikoura, Dannevirke) with no location to filter against.
  Same principle already used in `find_related_report()`: can't judge relevance without a location,
  so don't guess. MetService is unaffected — its own relevance check is always a gazetteer match on
  the *warning's* text, independent of whether the report gave a location. A real, expected case
  (most likely outcome: no context from the four coordinate-based sources, possibly a MetService
  item if one's live), not an error path.

### Instruction contract (the exact request format — decide this before writing any dataset rows)

This is the single biggest risk carried over from thinking about the OIA project's lessons: OIA's
classifier took raw text alone, so there was only one thing to get right. The Triage Classifier's
input is a **composite** (report + official context + related report) assembled from multiple
pieces — if the training data's assembly doesn't exactly match what live serving actually sends,
the model learns one format and gets served a different one, silently. Everything below exists to
prevent that.

**The chat template — confirmed, not assumed.** When the OIA models were converted to GGUF earlier
this build, the conversion tool printed the literal chat template baked into the model's own
metadata:

```
{% for message in messages %}
  {% if message['role'] == 'system' and message['content'] %}{{'<|system|>\n' + message['content'] + '<|end|>\n'}}
  {% elif message['role'] == 'user' %}{{'<|user|>\n' + message['content'] + '<|end|>\n'}}
  {% elif message['role'] == 'assistant' %}{{'<|assistant|>\n' + message['content'] + '<|end|>\n'}}
  {% endif %}
{% endfor %}
{% if add_generation_prompt %}{{ '<|assistant|>\n' }}{% else %}{{ eos_token }}{% endif %}
```

This is Phi-3.5-mini-instruct's actual chat template — confirmed straight from the model's
metadata, and matches what was manually reconstructed and successfully tested via
`llama-completion` earlier in this build. `mlx_lm.lora` applies this automatically from a
`"messages"` JSONL record at training time; the real serving code must reproduce the identical
token sequence manually (llama-cpp-python doesn't know about chat roles on its own) — this is
exactly the kind of thing that's easy to get subtly wrong on one side and not the other.

**Training JSONL record shape** (one line per example, matching the OIA project's proven format):
```json
{"messages": [
  {"role": "system", "content": "<SYSTEM_PROMPT — see app/classifier.py>"},
  {"role": "user", "content": "<assembled via app.classifier.build_user_message()>"},
  {"role": "assistant", "content": "Severity: medium\nRationale: ..."}
]}
```

**`SYSTEM_PROMPT` and `build_user_message()` now live in `app/classifier.py`** — not duplicated
here — specifically so the dataset-generation script and any future real model call both import
from the same place, rather than each hand-typing an approximation that can drift apart. Current
system prompt:

```
You are an emergency information triage assistant for Wellington City Council. You are given a
public report about a possible hazard, along with any relevant official warning data and any
related recent public report for the same location. Judge how serious this report is and explain
your reasoning in one sentence. Respond only in this exact format:
Severity: <low|medium|high>
Rationale: <one sentence>
```

`build_user_message(report_text, context_text)` returns `f"{report_text}\n\n{context_text}"` —
report text, blank line, then the exact output of `context.render_context_text()`. **The
dataset-generation script must call these two functions directly, not re-type their output by
hand** — this is the concrete fix for the "don't repeat the OIA mistake" concern: there is no OIA
mistake to point to in the dataset-format sense (its raw-text-only input never had this composite
risk), but this project's composite input creates the exact failure mode OIA never had to worry
about, so the discipline has to be new, not copied.

**Output validation, not just visual consistency.** Every training example's `assistant` content
must round-trip cleanly through `app.classifier.parse_triage_output()` — run this as a build-time
check on the generated dataset before committing it, so a stray casing/spacing inconsistency is
caught by a script, not by eyeballing a few hundred lines of JSONL.

### Dataset plan

**⚠️ Superseded design decision — dataset preparation is now fully synthetic, decoupled from live
data entirely** (originally planned as "reuse real live official data, don't invent it" — that
approach was tried first and abandoned after hitting real problems: Wellington doesn't reliably
have a live GeoNet/NZTA/MetService event at any given moment, so `official_supports` examples could
generate zero rows depending purely on when the script happened to run; and even when live data
existed, anchoring a synthetic report to a live event's own coordinates surfaced two real bugs —
a nationwide, non-region-scoped fetch occasionally anchored examples 150-500km from Wellington, and
a candidate could fail to survive its own recency filtering, rendering a context that silently
contradicted the row's own target rationale — see `backend/scripts/generate_triage_dataset.py`'s
module docstring for the full history). The replacement:

1. **The full dataset is authored directly in `backend/data/triage_examples.csv`, entirely
   synthetic** — report text, target `severity_output`/`rationale_output` (named to make clear
   these are the Triage Classifier's target output columns, not input), and (for rows that need
   it) the official-context fields as **structured columns** (`official_source`, `official_hazard_type`,
   `official_severity_hint`, `official_distance_km`, `official_minutes_ago`, `official_summary`),
   written in the style of a real GeoNet/NZTA/MetService record, not free text. Structured fields,
   not pre-rendered text — the script still builds the actual context string by calling
   `context.render_context_text()` on those fields, the same canonical function live serving uses,
   so there's no risk of a human hand-typing a slightly-wrong approximation of the render format
   (exactly the failure mode the "Instruction contract" section above exists to prevent).
2. **The team reviews and corrects every row for domain accuracy** before it's used — is the
   severity/rationale judgement realistic, does the official summary read like something a real
   feed would actually say, is the taxonomy right. This is the same review role Sara already has
   for the OIA-style dataset work, just applied here.
3. Write reports across the hazard taxonomy, each paired with:
   - No relevant context at all (the common `"no_official_data"`-equivalent case — must be
     handled gracefully as a normal case, not an edge case)
   - Official context that clearly supports the report
   - Official context that's present but doesn't clearly relate
   - A related pre-existing public report present (teaches the qualitative "independently
     corroborated → more serious" pattern) — include at least one case where the *prior* report
     describes something unrelated, so the model doesn't learn to blindly escalate severity just
     because *any* related report exists
   - No location given at all — realistically means no GeoNet/NZTA context (both require a
     location to judge relevance — see "Distance and region-matching" above), but MetService can
     still legitimately apply, since its relevance never depends on the report's own location
   - Each example paired with a `severity` label **and** a natural one-line `rationale` — write
     these rationales thoughtfully, since their tone/style is exactly what gets fine-tuned. Vary
     severity within each category too (e.g. official-supports shouldn't always be `medium`) —
     otherwise the model risks learning "context present → medium" as a shortcut rather than
     actually reading the report.
4. Combine, split train/valid (80/20).

### Sample size

No hard rule, but for a narrow, fixed-output-template task like this (not open-ended generation),
LoRA fine-tunes on a ~3.8B model tend to converge well on the order of **100-300 examples** —
nowhere near the scale needed for training a model from scratch or for open-ended tasks. Target
**at least ~100-150 examples per model** for the hackathon build, aiming for roughly even coverage
across categories (for the Triage Classifier: ~20-30 per category × 5 categories; for the
Clarifier: spread across the completeness spectrum, not skewed toward "very vague") and a
reasonable severity spread within each category, not just across the dataset as a whole. The
current CSV (25 rows) is enough to prove the pipeline end-to-end — round-trip validation passes,
JSONL is well-formed — but is *pipeline-proving scale*, not yet training-target scale.

At 100-150 examples with an 80/20 split, the validation set lands around 20-30 examples — small,
but enough to give a directionally meaningful loss signal, unlike the current 5-example valid set
which is really just a smoke test.

### Training mechanics — how train vs. valid actually get used

Once there's a real dataset to fine-tune on, `mlx_lm.lora --data <dir>` (pointing at the folder
containing `train.jsonl`/`valid.jsonl`) treats the two files completely differently, not just as
an arbitrary split:
- **`train.jsonl`** — every example is used to compute gradients and update the model's weights
  via backpropagation. This is what the model actually learns from.
- **`valid.jsonl`** — never used to update weights. Periodically during training, the trainer runs
  a forward pass only (loss computation, no backprop) on these examples and reports the loss — a
  check on generalization, not a training input. If train loss keeps dropping while valid loss
  plateaus or rises, that's the standard overfitting signal.

The separation only has to be right once, at dataset-generation time (the script's seeded shuffle
already guarantees no example appears in both files) — there's no further "separating" step during
training itself, since the trainer just reads whichever file for whichever purpose.

**Implemented as:** `backend/data/triage_examples.csv` (the editable source — one row per example,
fully synthetic, no engineering knowledge needed to add rows; see the header comment in
`backend/scripts/generate_triage_dataset.py` for the exact column meanings) + that script, which
reads the CSV, builds each example through the instruction contract above (rendering the row's
structured official-context fields via the same canonical `context.render_context_text()` live
serving uses), validates every target output round-trips through
`classifier.parse_triage_output()`, and writes `backend/data/triage/{train,valid}.jsonl`. Re-run
the script after editing the CSV — it regenerates both files from scratch every time, so there's
no separate "transform" step and no risk of the CSV and the JSONL drifting apart.

### Taxonomy

- `severity`: `low` | `medium` | `high` (LLM output)
- `hazard_type`: `earthquake` | `severe_weather` | `flooding` | `road_hazard` | `fire` | `other`
  (deterministic assignment only — `"other"` is the fallback when no official match exists)

## Next steps

1. ✅ **Done** — Wellington gazetteer list (suburbs + "Wellington")
2. ✅ **Done** — deterministic official-context construction (Haversine for GeoNet/NZTA, gazetteer
   keyword match for MetService, per-source `severity_hint`/`hazard_type` rules)
3. ✅ **Done** — related-public-report lookup (query the existing event store, proximity + recency,
   cap at one)
4. ✅ **Done** — Triage Classifier dataset, **231 rows** across all 5 `meta_category` cases (target
   was minimum 150), in `backend/data/triage_examples.csv`, generated via
   `backend/scripts/generate_triage_dataset.py`. Severity distribution: 94 low / 99 medium / 38
   high. Includes 4 rows exercising the two data sources added after the hackathon organisers'
   catalogue was released (NEMA, GWRC — see "Official context format" below) — before that, the
   dataset had zero training exposure to what those sources' rendered context actually looks like.
   Calibrated against Sara's domain corrections (see the severity-calibration rule recorded
   below this list) — **still needs a full team review pass before being used to actually
   fine-tune**, per the "verified and corrected by the team" process agreed for this dataset.
5. ✅ **Done** — clarifier dataset, **210 rows per call, 420 total** (target was minimum 150 per
   call), in `backend/data/clarifier_examples.csv`, generated via
   `backend/scripts/generate_clarifier_dataset.py`. `1_ask` rows span the full completeness
   spectrum (minimal/moderate/detailed) across 12 hazard families; `2_act` rows span 3 severity
   tiers per family (mild/moderate/severe) with the action vocabulary deliberately weighted toward
   mild/moderate outcomes (`call_111`/`evacuate` kept a minority, not ~1/3 by construction) — same
   "don't prematurely raise severity" discipline as the Triage Classifier dataset. All rows
   round-trip validated; `meta_call` checked for consistency against which fields are populated.
   **Still needs the team's review/correction pass before actual fine-tuning**, same process as the
   Triage dataset.
6. ✅ **Done** — both models fine-tuned, following the validated pipeline in `BUILD_PLAN.md`.
   Clarifier: iter 200 (killed at iter 500 after val loss plateaued from iter 200 onward). Triage
   Classifier: retrained on the team-corrected dataset (`triage_examples_corrected.csv`, 226 rows
   after fixing 15 rows with stray trailing whitespace in `rationale_output` that failed the
   round-trip validator), iter 100 selected — val loss climbed monotonically at every checkpoint
   from iter 100 through the final iter 500 (0.565 → 0.727 → 0.763 → 0.791 → 0.865), a clear and
   consistent overfitting signal on this dataset size, not noise.
7. **Follow-up — pre-existing bug, not caused by retraining:** `context.inherit_hazard_type()`
   unconditionally takes `official_context[0].hazard_type` (the closest/most-recent matched
   official item), even when that item isn't actually relevant to the report's own hazard. Caught
   via a live end-to-end test: a road-slip report with no nearby NZTA source matched a GWRC rain
   gauge instead, and inherited `hazard_type: "flooding"` — wrong category for the report. Needs a
   relevance check (e.g. only inherit when the closest item's hazard_type is plausible for the
   report, or fall back to `"other"` rather than an unrelated source's type) before this is
   trustworthy on real reports.
8. **Follow-up — model-quality gap in the current Triage Classifier fine-tune:** the same live test
   above showed the model output `severity: low` for a report describing concrete impact (a road
   half-blocked, cars backing up) alongside irrelevant low-severity official context — inconsistent
   with the severity-calibration rule (concrete impact → at least `medium`, regardless of official
   corroboration) and inconsistent with a separate spot-check that got a similar unrelated-context
   case right. Likely a coverage gap in the 226-row dataset for "concrete impact + irrelevant
   official context present" specifically, not a fundamental failure — worth adding more rows in
   that exact shape before the next retrain, rather than assuming the calibration rule itself needs
   changing.

**Severity calibration rule** (established with Sara, applied throughout the 177-row dataset):
1. Report describes concrete, real impact (damage, injury, spreading, blocked access) → at least
   `medium`, `high` if genuinely dangerous — regardless of official corroboration.
2. Report is vague/uncertain with **no** concrete impact, and directly addresses the *same* hazard
   as a matching official item (`official_supports`) → the direct "nothing happened/fell/broke"
   account overrides the official `severity_hint`, i.e. `low`, even if the hint itself is `medium`
   or `high`.
3. Report is vague/uncertain with no concrete impact and does **not** directly address the nearby
   official item's hazard (`official_unrelated`, or the MetService case of `no_location`) →
   severity follows the official `severity_hint` directly, even though the hazard types don't
   match — elevated official activity nearby still warrants proportional caution.
4. Related-report corroboration follows #1 applied to the pair: two trivial reports stay `low`, two
   reports of concrete-but-contained damage → `medium`, genuinely severe/dangerous corroborated
   pairs → `high`. An unrelated prior report doesn't corroborate anything — judge the new report
   alone via #1.
5. `high` stays reserved for real danger: structural collapse, injury, fire/explosion, life-safety
   risk, or high-confidence severe official confirmation (red warnings, full/unavoidable closures).

**Deferred (noted, not built in this pass):** manual/on-demand staff trigger (see
`BUILD_PLAN.md`); structured `corroboration` field; LLM-produced `hazard_type`; any
counting-based severity logic. Worth reconsidering only with clear evidence they're needed —
not before.
