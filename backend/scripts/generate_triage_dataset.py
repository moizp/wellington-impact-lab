"""Generate the Triage Classifier's fine-tuning dataset from
data/triage_examples.csv.

See docs/FINETUNE_PLAN.md "Instruction contract" and "Dataset plan" for the
full rationale. Run from backend/:

    python3 scripts/generate_triage_dataset.py

Fully synthetic, deliberately decoupled from live official data (see
FINETUNE_PLAN.md — this replaced an earlier "reuse real live data" design
after live data proved unreliable to depend on at dataset-generation time:
Wellington doesn't reliably have a live GeoNet/NZTA/MetService event at any
given moment, and even when it does, using its own coordinates as a synthetic
report's location surfaced real bugs — a nationwide fetch anchoring examples
150-500km from Wellington, and a candidate that failed to survive its own
recency filtering, rendering a context that contradicted the row's own target
rationale). The dataset is now authored directly, then reviewed/corrected by
the team for domain accuracy — see FINETUNE_PLAN.md "Dataset plan".

Still reuses the exact same functions live serving will use
(context.render_context_text, classifier.SYSTEM_PROMPT,
classifier.build_user_message, classifier.parse_triage_output) rather than
hand-typing an approximation of them — only the *source* of the official
context data changed (structured CSV fields instead of a live fetch), not how
it gets turned into the actual text the model reads. That's the fix for this
project's composite-input training/serving drift risk (see FINETUNE_PLAN.md
"Instruction contract"): the official context fields are synthetic, but the
render step that turns them into text is the identical function serving uses.

HOW TO ADD MORE EXAMPLES (no engineering knowledge required):
    Open data/triage_examples.csv in Excel/Sheets/a text editor and add a new
    row. Columns:
        meta_category             one of: no_context, official_supports,
                                official_unrelated, related_report,
                                no_location — bookkeeping only (coverage
                                tracking, validation), never seen by the
                                model — see the "category" note in
                                FINETUNE_PLAN.md
        report_text              the new public report's text (always
                                required)
        severity_output           low | medium | high — the Triage
                                Classifier's target output (always required)
        rationale_output          the one-line target rationale — the Triage
                                Classifier's other output (always required)
        official_source          geonet | nzta | metservice — leave blank
                                for rows with no official context at all
        official_hazard_type     earthquake | severe_weather | road_hazard |
                                flooding | fire | other
        official_severity_hint   low | medium | high
        official_distance_km     numeric, or blank for MetService (no
                                coordinates — see FINETUNE_PLAN.md)
        official_minutes_ago     integer minutes since the official event
        official_summary         one-line description, in the style of a
                                real GeoNet/NZTA/MetService summary (e.g.
                                "M4.2 earthquake, 12km deep, near Ngaio")
        prior_suburb             only for related_report rows — the earlier
                                report's location (a Wellington suburb name)
        prior_text               only for related_report rows — the earlier
                                report's text
        prior_minutes_ago        only for related_report rows — how many
                                minutes before the new report the earlier
                                one happened
    Then re-run this script — it regenerates train.jsonl/valid.jsonl from
    scratch, validating every row's target output round-trips through
    classifier.parse_triage_output() before accepting it. A malformed row
    (bad severity value, wrong output formatting) fails loudly with which
    row broke, rather than silently writing bad data into the dataset.

Five categories, per FINETUNE_PLAN.md's dataset plan:
  no_context           No relevant context at all
  official_supports    Official context (one item) clearly supports the
                        report
  official_unrelated   Official context (one item) present but doesn't
                        clearly relate to the report's own hazard
  related_report       A related pre-existing public report present
                        (synthetic prior report)
  no_location          No location given at all — realistically means no
                        GeoNet/NZTA context (both require a location to judge
                        relevance), but MetService can still legitimately
                        apply, since its relevance never depends on the
                        report's own location
"""

import csv
import json
import os
import random
from datetime import datetime, timedelta, timezone

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import classifier, context  # noqa: E402
from app.schema import Event, Location, OfficialContextItem  # noqa: E402

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "triage_examples.csv")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "triage")
VALID_SPLIT = 0.2
SEED = 42


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _minutes_ago_iso(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def make_prior_report(suburb: str, text: str, minutes_ago: int) -> Event:
    """A synthetic *prior* public report, used only to build the
    related-report-context category. Constructed directly rather than via
    the live store — there's no real community-report history yet to draw
    from, and this is an offline dataset-generation script, not live serving."""
    return Event(
        id=f"synthetic-{suburb.lower()}-{minutes_ago}",
        ingested_at=_now_iso(),
        event_time=_minutes_ago_iso(minutes_ago),
        location=Location(suburb=suburb),
        raw_text=text,
        clarified_text=text,
    )


def make_official_context_item(row) -> "OfficialContextItem | None":
    """Builds the one structured official-context item a row describes, if
    any. Returns None for rows with no official_source set."""
    source = row["official_source"].strip().lower()
    if not source:
        return None
    distance_km = row["official_distance_km"].strip()
    return OfficialContextItem(
        source=source,
        hazard_type=row["official_hazard_type"].strip(),
        severity_hint=row["official_severity_hint"].strip(),
        distance_km=float(distance_km) if distance_km else None,
        minutes_ago=int(row["official_minutes_ago"]),
        summary=row["official_summary"].strip(),
    )


def build_example(report_text, official_context_items, related_report, severity_output, rationale_output):
    context_text = context.render_context_text(official_context_items, related_report)
    user_message = classifier.build_user_message(report_text, context_text)
    assistant = f"Severity: {severity_output}\nRationale: {rationale_output}"

    # Round-trip validation — catches formatting drift automatically instead
    # of relying on eyeballing the dataset (see FINETUNE_PLAN.md).
    parsed_severity, parsed_rationale = classifier.parse_triage_output(assistant)
    assert parsed_severity == severity_output, f"Severity round-trip failed: {assistant!r}"
    assert parsed_rationale == rationale_output, f"Rationale round-trip failed: {assistant!r}"

    return {
        "messages": [
            {"role": "system", "content": classifier.SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant},
        ]
    }


def load_rows(csv_path):
    with open(csv_path, newline="") as f:
        return list(csv.DictReader(f))


def build_row_example(row):
    """One builder for every row, regardless of meta_category — the only
    thing that varies row to row is which structured fields are populated,
    not the code path. meta_category itself is never read here — it plays no
    role in what gets built, only in validation/coverage-counting in main()."""
    official_item = make_official_context_item(row)
    official_context_items = [official_item] if official_item else []

    related_report = None
    if row["prior_suburb"].strip():
        related_report = make_prior_report(
            row["prior_suburb"], row["prior_text"], int(row["prior_minutes_ago"])
        )

    return build_example(
        row["report_text"], official_context_items, related_report, row["severity_output"], row["rationale_output"]
    )


VALID_CATEGORIES = {"no_context", "official_supports", "official_unrelated", "related_report", "no_location"}


def write_jsonl(path, records):
    with open(path, "w") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"  Wrote {len(records)} records to {path}")


def main():
    print(f"Reading source examples from {CSV_PATH}...")
    rows = load_rows(CSV_PATH)
    print(f"  {len(rows)} rows found\n")

    examples = []
    counts: dict[str, int] = {}
    for row in rows:
        meta_category = row["meta_category"].strip()
        if meta_category not in VALID_CATEGORIES:
            print(f"  (skipping row — unknown meta_category {meta_category!r}: {row})")
            continue
        examples.append(build_row_example(row))
        counts[meta_category] = counts.get(meta_category, 0) + 1

    print("Examples generated per meta_category (bookkeeping only — never seen by the model):")
    for meta_category in sorted(VALID_CATEGORIES):
        print(f"  {meta_category}: {counts.get(meta_category, 0)}")
    print(f"\nTotal examples generated: {len(examples)}")

    random.seed(SEED)
    random.shuffle(examples)
    split_idx = max(1, int(len(examples) * (1 - VALID_SPLIT)))
    train, valid = examples[:split_idx], examples[split_idx:]

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    write_jsonl(os.path.join(OUTPUT_DIR, "train.jsonl"), train)
    write_jsonl(os.path.join(OUTPUT_DIR, "valid.jsonl"), valid)


if __name__ == "__main__":
    main()
