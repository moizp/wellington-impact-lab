---
name: add-data-source
description: Use when adding or modifying a poller for an official open-data source (GeoNet, MetService, NZTA, NEMA, GWRC, or a new one) in the Wellington Emergency Information Triage backend, so every source normalizes into the same OfficialEvent schema and gets picked up by the aggregator's distance/recency logic correctly.
---

# Add a data source

This project ingests multiple independent official feeds that all normalize into one shared
`OfficialEvent` schema (`app/schema.py`) before the aggregator (`app/context.py`) or the Triage
Classifier ever sees them. Five exist today: GeoNet, MetService, NZTA, NEMA, GWRC — one module
each in `app/sources/`. This skill exists because the normalization pattern must stay identical
for every source, and because every source added so far has hit at least one real bug that only
showed up against live data, never in the source's own documentation.

## The shared shape (`OfficialEvent`, see `app/schema.py`)

```python
OfficialEvent(
    source="nema",              # must be added to schema.py's Literal — see step 2
    hazard_type="earthquake" | "severe_weather" | "flooding" | "road_hazard" | "fire" | "other",
    severity_hint="low" | "medium" | "high",
    event_time="...",           # ISO 8601, UTC — see step 5 on timezones
    lat=..., lon=...,           # real coordinates, or both None if genuinely unavailable
    summary="...",
    raw_source_url="...",
)
```

`hazard_type` and `severity_hint` are **always deterministic, rule-derived** — never an LLM call.
Every source module has a `_severity_hint(...)` and (where hazard type isn't fixed for the whole
source) a `_hazard_type(...)` function doing plain threshold/lookup logic. If a new source's
hazard doesn't fit the existing taxonomy, that's a real decision (adding a taxonomy value touches
the Triage Classifier's training data too) — flag it, don't just pick the closest fit silently.

## Steps

1. **Inspect the real live endpoint before writing any code** — query it directly (`curl` is
   fine), look at actual field names and sample values, not just documentation or a catalogue
   description. Every source added to this project so far revealed something the description
   didn't: NEMA's feed includes literal `"TEST MESSAGE"` records with `severity: Severe` that
   have to be filtered out; GWRC's `LatestTime` field turned out to be NZ local time with no
   timezone marker, not UTC (would have silently mis-timestamped every event by 12-13 hours if
   not checked against actual current time); NZTA's `impact` field only had one confirmed value
   until more live samples were checked.

2. **Add the new source name to `OfficialEvent.source`'s `Literal` in `app/schema.py`.** Pydantic
   will reject the event otherwise — this is usually the first error you'll hit, and it's the
   correct signal to add the source name deliberately, not a bug to work around.

3. **Write `fetch() -> list[OfficialEvent]` as its own async function** in
   `app/sources/<name>.py`, wrapped in the same shape as the existing five: an `httpx.AsyncClient`
   call, a loop over the response's items, one `OfficialEvent(...)` per item. A malformed or empty
   response must never crash the poller or block other sources — `app/poller.py` already wraps
   each source's `fetch()` in try/except-and-skip, so a single bad response degrades gracefully
   (falls back to last-cached data) rather than taking down the whole `/events` pipeline. Don't
   add your own try/except inside `fetch()` unless a *specific* field needs graceful handling —
   the outer catch in `poller.py` is deliberately the safety net, not each source individually.

4. **Register it in `app/poller.py`'s `SOURCES` list** and import the module. That's the only
   wiring needed — the aggregator (`app/context.py`) picks up any source with real coordinates
   automatically via the same generic Haversine-distance branch GeoNet/NZTA/NEMA/GWRC already use
   (see `resolve_location()`). Only a source with **no coordinates at all** (MetService is the one
   example) needs a special-cased branch in `context.py` — check this genuinely empirically (query
   real live features, don't assume from the schema) before deciding a source needs one.

5. **Recency and timezone, checked, not assumed:**
   - Decide whether this source needs its own recency cutoff (like GeoNet's 24h window) or should
     rely entirely on the source's own "still active" signal (like NZTA's `status == "active"`
     filter, or NEMA's `historic=0` query param) — a blanket cutoff applied to every source was
     tried once and was wrong (a multi-week NZTA road closure got incorrectly excluded).
   - If the source returns timestamps without an explicit UTC marker, **check what timezone they
     actually are** against real current time before writing any parsing code — don't assume UTC.
     GWRC's `gwrc.py` has a worked example (`_parse_nz_time()`) of localizing via `zoneinfo`.
   - If a nationwide/non-region-scoped source has no location filtering of its own (most ArcGIS
     FeatureServer sources don't), confirm this **and** confirm what happens when a report has no
     location at all — a naive fallback for this exact case once surfaced GeoNet quakes 150km+
     from Wellington. The current answer (see `context.py`) is: exclude entirely rather than guess,
     for every coordinate-based source.

6. **Before calling it done: run `fetch()` against the live source directly** (not a mock), and
   run a full `context.build_official_context()` call against a real Wellington location to
   confirm the new source's items actually surface with sane distance/recency/severity values.
   A source that's only been tested against a hand-written mock response hasn't actually been
   verified — every real bug found in this project's five existing sources was found this way,
   never by reading documentation alone.

7. **If the new source adds real, useful examples to the Triage Classifier's training data
   (`backend/data/triage_examples.csv`)**, consider adding a couple — the dataset had zero
   examples referencing NEMA or GWRC for a while after those sources were added, meaning the model
   had no training exposure to what their rendered context actually looks like. See
   `.claude/skills/fine-tune-adapter` for the dataset-generation pipeline.
