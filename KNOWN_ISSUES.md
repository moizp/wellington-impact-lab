# Known issues and limitations

Started 8 August 2026. One list of everything we know is wrong, missing or
deliberately simplified — so it can be said out loud in the demo rather than
found by a judge.

Some entries are **deliberate scope decisions**, not defects. Those are marked
as such. A one-day build is allowed to be incomplete; it is not allowed to be
incomplete and quiet about it.

This consolidates issues already recorded in `docs/BUILD_PLAN.md` and
`docs/FINETUNE_PLAN.md` alongside newer findings, so there is one place to look.

**Status key** — `TO FIX` (agreed, not yet done) · `OPEN` (real, undecided) ·
`ACCEPTED` (known limitation, deliberately not fixed for the hackathon)

---

## Summary

| # | Area | Issue | Severity | Status |
|---|---|---|---|---|
| 1 | Location | Suburb→coordinate lookup missing most affected suburbs; fails silently | High | `TO FIX` |
| 2 | Time | System assumes "now"; no way to represent a past or replayed event | High | `ACCEPTED` |
| 3 | Triage | `hazard_type` inherited from nearest official item even when unrelated | High | `OPEN` |
| 4 | Model | Classifier under-rates reports describing concrete impact | High | `OPEN` |
| 5 | Safety | Clarifier suggests `call_111`/`evacuate` at the least-informed point | High | `ACCEPTED` |
| 6 | Scope | Only public reports enter the queue; official sources are context only | Medium | `ACCEPTED` |
| 7 | Scope | Output axis is severity, not the brief's awareness/verification/action | Medium | `OPEN` |
| 8 | Location | MetService relevance is keyword matching, not geography | Medium | `ACCEPTED` |
| 9 | Privacy | GPS coordinates stored at full precision | Medium | `OPEN` |
| 10 | UX | Unresolvable location looks identical to "nothing happening nearby" | Medium | `OPEN` |
| 11 | Data | Bulk-seeded reports can collide on ID and silently overwrite | Medium | `OPEN` |
| 12 | Triage | Related-report context conveys no distance or recency to the model | Low | `OPEN` |
| 13 | API | `?suburb=` filter is case- and whitespace-sensitive | Low | `OPEN` |
| 14 | Data | Event store is in-memory and resets on any cold start | Low | `ACCEPTED` |
| 15 | Docs | `FINETUNE_PLAN.md` shows a context render format the code doesn't produce | Low | `OPEN` |
| 16 | Data | Training data has power/water-outage scenarios with no live source behind them | Medium | `OPEN` |

---

## 1. Suburb→coordinate lookup is missing most of the affected suburbs

**Status:** `TO FIX` — agreed 8 August.

`WELLINGTON_SUBURB_COORDS` in `backend/app/gazetteer.py` has 26 hand-typed
entries. Missing: **Berhampore, Vogeltown, Mornington, Ōwhiro Bay, Kingston,
Mount Cook, Hataitai** — very nearly the exact list of suburbs worst affected by
the 20 April 2026 Wellington flood.

**Why it matters more than it sounds.** When a submitter gives a suburb name but
no GPS, `resolve_location()` returns `(None, None)` for an unlisted suburb.
`build_official_context()` then skips **every coordinate-based source** — GeoNet,
NZTA, NEMA and GWRC — leaving only MetService's keyword match. The report is
triaged against almost nothing and inherits `hazard_type: "other"`.

The failure is **silent**. The result renders as *"No relevant official data
found for this location/time"*, which is also the correct output for a genuinely
quiet moment. On screen, "we don't know where that is" and "nothing is happening
there" are indistinguishable.

Note this is our gap, not a Council data gap — every official source publishes
proper coordinates.

Partial mitigation already in place: `find_related_report()` degrades gracefully,
falling back to case-insensitive suburb-name comparison when coordinates are
unavailable. Only official context is lost, not duplicate detection.

**Fix:** generate the dictionary from `community-emergency-hubs` in the WCC GIS
catalogue — its `SUBURB` field plus `lat`/`lng` yields 107 distinct suburbs with
real coordinates, including Berhampore, Mount Cook and Hataitai. Hand-add the
four with no emergency hub (Vogeltown, Mornington, Ōwhiro Bay, Kingston). Seeded
demo reports should also carry `lat`/`lon` directly so they never depend on name
lookup.

## 2. The system assumes "now" — there is no way to represent a past event

**Status:** `ACCEPTED` for the hackathon. Captured because it constrains what a
replay-based demo can honestly claim.

Two separate problems, one root cause.

**The visible half.** Both submission endpoints in `backend/app/main.py` set
`ingested_at` *and* `event_time` to `datetime.now(timezone.utc)`. A submitter
cannot say *when* the thing happened, only that they are reporting it now. The
schema draws the distinction; the code collapses it.

**The deeper half.** `_triage()` calls `poller.get_official_events()`, which
fetches **live** data at triage time. So even if a report carried a past
timestamp, it would be judged against today's earthquakes and today's weather.
The report and its context would be months apart and the rationale meaningless.

**Consequences for a replay.** Reports pushed through the public API all land
within the same second, so: the dashboard's `event_time` sort is meaningless; the
60-minute window in `find_related_report()` matches everything against everything;
and the shape of the storm — which is the whole point of replaying one — is lost.

**The chosen approach: shift the clock, not the data.** Re-stamp a recorded event
as happening today, compressed (roughly 19 real hours into ~10 minutes of demo
time), and pre-load the recorded official data into the poller's cache so the
aggregator sees a consistent world. "Now" stays genuinely now and nothing in the
core system has to understand time travel.

**What this means we must not claim.** The prototype cannot reconstruct a past
activation, and cannot answer "what did we know at 04:00?". It replays a recorded
event as though it were happening live. Say that plainly.

True time travel — a submittable `event_time` plus an "as at" mode on the poller
— is the correct long-term design and is deliberately out of scope today.

## 3. `hazard_type` is inherited from the nearest official item even when unrelated

**Status:** `OPEN`. Already recorded in `docs/FINETUNE_PLAN.md` "Next steps" #7.

`inherit_hazard_type()` returns `official_context[0].hazard_type`
unconditionally. Since the list is ranked by distance and recency rather than
relevance, the closest item wins even if it describes a different hazard
entirely. Caught in a live test: a road-slip report with no nearby NZTA source
matched a GWRC rain gauge and was labelled `flooding`.

Needs a plausibility check, or a fall back to `"other"` rather than adopting an
unrelated source's type.

## 4. The classifier under-rates reports describing concrete impact

**Status:** `OPEN`. Already recorded in `docs/FINETUNE_PLAN.md` "Next steps" #8.

A live test on a report describing a half-blocked road with traffic backing up
returned `severity: low`, against the team's own calibration rule (concrete
impact → at least `medium`, regardless of official corroboration). Suspected
coverage gap in the 226-row dataset for "concrete impact + irrelevant official
context present", rather than a problem with the rule.

## 5. Safety-critical suggestions are made at the least-informed point in the pipeline

**Status:** `ACCEPTED` — deliberate simplification, recorded in
`docs/FINETUNE_PLAN.md` "Model 1 — Clarifier".

Clarifier Call 2 can output `call_111` or `evacuate`, but runs *before* the
poller, aggregation and triage. It sees only the report and the clarifying
exchange — no official context, no corroboration, no severity judgement. The
highest-stakes outputs in the system rest on the thinnest evidence in the system.

Combined into one call with low-stakes suggestions purely to fit a one-day build.
The sounder design — a dedicated model running *after* triage — is on the roadmap.
Must be stated plainly in the demo, not left implicit.

Related open decision: whether a permanent "in an emergency call 111" banner
should show regardless of model output.

## 6. Only public reports enter the queue

**Status:** `ACCEPTED` scope decision, recorded in `docs/BUILD_PLAN.md`.

`source_type` is always `"community"`. Official-source events never appear as
standalone items — only as `official_context` attached to a public report. A
MetService red warning or a partner-agency report cannot enter the queue on its
own; something must be reported by a member of the public first.

The brief describes information arriving from "phone calls, emails, forms, social
media, news reports and partner agencies". We handle one of those six. Worth
being straight about in the demo rather than implying broader coverage.

## 7. The output axis is severity, not the brief's three buckets

**Status:** `OPEN` — worth a decision before the demo.

The classifier outputs `low`/`medium`/`high`. Problem statement 04 asks for
**awareness / requiring verification / requiring action**. These are different
axes: an unverified report of a collapsed building is high-severity *and* needs
verification; a confirmed official warning is high-severity and needs neither.

The second axis is close to free — it falls out of whether the report is
corroborated by `official_context`, which is already deterministic.

## 8. MetService relevance is keyword matching, not geography

**Status:** `ACCEPTED`, recorded in `docs/FINETUNE_PLAN.md`.

The raw CAP feed carries no coordinates, so relevance is a substring match
against a hand-maintained Wellington place-name list. An unlisted place name is
missed entirely, and there is no distance signal at all.

Known better option, deferred: the Eagle/ArcGIS MetService endpoint in the WCC
catalogue has real polygon geometry. Swapping to it would allow genuine
point-in-polygon matching, but means rewriting the relevance logic rather than
plugging in a new module.

## 9. GPS coordinates are stored at full precision

**Status:** `OPEN` decision, recorded in `docs/BUILD_PLAN.md`.

Browser Geolocation can be accurate to a few metres — enough to identify a
submitter's home address if they report from there. Currently stored as given,
with no rounding or fuzzing. Needs a decision, and a community-sensitivity
review, before this touches real submitters.

## 10. An unresolvable location looks identical to a quiet neighbourhood

**Status:** `OPEN`.

The downstream half of issue 1, and it survives fixing the dictionary — any
unrecognised place name produces the same output. "We couldn't place this report"
and "nothing relevant is happening near this report" should not render
identically to staff.

Directly relevant to the event's own ground rule about making limitations
visible, and it is close to a one-line distinction in the UI.

## 11. Bulk-seeded reports can collide on ID

**Status:** `OPEN`.

`_new_event_id()` is `f"community-{millisecond_timestamp}"`, and
`store.upsert_event()` overwrites on key collision without complaint. Fine for
hand-submitted demo reports; a seeding loop injecting a few hundred will silently
lose some. Needs a counter or UUID suffix before any replay work.

## 12. Related-report context conveys no distance or recency

**Status:** `OPEN`, low priority.

`find_related_report()` selects a report within 2 km and 60 minutes, but
`render_context_text()` renders only its text. To the classifier, "a report 1.9 km
away, 59 minutes ago" and "a report 50 m away, 2 minutes ago" are identical, even
though they are very different corroboration.

The dataset CSV already carries `prior_suburb` and `prior_minutes_ago` columns
that are collected but never rendered.

## 13. The `?suburb=` filter is case- and whitespace-sensitive

**Status:** `OPEN`, trivial.

`store.get_events()` compares with `e.location.suburb == suburb`, so `Berhampore`
and `berhampore` are different suburbs to the dashboard filter, and a trailing
space breaks the match. `resolve_location()` and `find_related_report()` both
normalise; this path doesn't.

## 14. The event store is in-memory and resets on cold start

**Status:** `ACCEPTED` — deliberate, recorded in `docs/BUILD_PLAN.md`.

Cloud Run scales to zero, so all triaged reports are lost after any idle period.
Reseed demo data immediately before recording or presenting; do not assume
anything submitted earlier is still there.

## 15. Documentation drift in the context render example

**Status:** `OPEN`, trivial.

`docs/FINETUNE_PLAN.md` shows the related-report line rendering as
`- "Water pooling on the road, getting worse" (0.4km away, 22 min ago)`. The code
emits only the quoted text.

Not a training/serving mismatch — the dataset generator calls the same
`render_context_text()` the live path uses, so both sides genuinely agree. Only
the documented example is stale. Worth correcting so nobody "fixes" the code to
match the doc.

## 16. Training data has power/water-outage scenarios with no live source behind them

**Status:** `OPEN`, recorded in `docs/BUILD_PLAN.md` "Official data sources — current and
deferred".

Both training CSVs (`triage_examples.csv`, `clarifier_examples.csv`) include hazard scenarios
describing power outages and burst water mains — but only 5 official sources are actually polled
(GeoNet, MetService, NZTA, NEMA, GWRC), none of which cover electricity or water-network faults. A
report matching one of these trained-for scenarios can never get real official corroboration; it
always falls through to "no relevant official data found."

Two live, confirmed-working sources in the organisers' catalogue would close this: NEMA's national
electricity-outage points, and Wellington Water's live network-fault jobs. Evaluated but not built
this pass — same integration effort as `nema.py`/`gwrc.py` (inspect the real live schema, confirm
recency/timezone handling empirically, decide whether a new hazard taxonomy value is needed).

Two smaller, lower-priority items in the same "deferred sources" list: a MetService endpoint with
real polygon geometry (would replace the current keyword-match workaround — see issue 8, more
rework than new coverage) and GNS ShakingLayers (would refine GeoNet's earthquake severity, not a
new hazard type).
