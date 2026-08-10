"""Generate the Clarifier's fine-tuning dataset from data/clarifier_examples.csv.

See docs/FINETUNE_PLAN.md "Model 1 — Clarifier" for the full rationale. Run
from backend/:

    python3 scripts/generate_clarifier_dataset.py

One model, two distinct inference calls (Call 1 "ask", Call 2 "act"),
task-conditioned via a different system prompt per call — see
app/clarifier.py. Simpler than the Triage Classifier's dataset: no official
data involved in either call, so no live/synthetic context to assemble, no
async fetch — just report text (+ Q&A for Call 2) -> a fixed-template target.

`meta_call` is bookkeeping only (validation + coverage counting), same
principle as the Triage dataset's `meta_category` — the actual dispatch below
is driven by whether `answer` is populated, not by reading `meta_call`
directly, so a mislabelled row gets caught as an inconsistency rather than
silently trusted.

HOW TO ADD MORE EXAMPLES (no engineering knowledge required):
    Open data/clarifier_examples.csv and add a new row. Columns:
        meta_call         1_ask | 2_act — bookkeeping only, never seen by
                          the model (must match whether answer is filled in)
        report_text        the public report's text (always required)
        question_output    1_ask rows: the target clarifying question.
                          2_act rows: the question being answered (input) —
                          same column either way, see FINETUNE_PLAN.md's
                          note on why these were merged
        answer             2_act rows only: a plausible answer to
                          question_output for this row — must actually
                          respond to that specific question, not filler text
        actions_output     2_act rows only: 1-2 comma-separated values from
                          app.clarifier.ACTION_VOCABULARY — the target
    Then re-run this script — it regenerates train.jsonl/valid.jsonl from
    scratch, validating every row's target output round-trips through
    clarifier.parse_ask_output()/parse_actions_output() before accepting it.
"""

import csv
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import clarifier  # noqa: E402

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "clarifier_examples.csv")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "clarifier")
VALID_SPLIT = 0.2
SEED = 42

VALID_META_CALLS = {"1_ask", "2_act"}


def load_rows(csv_path):
    with open(csv_path, newline="") as f:
        return list(csv.DictReader(f))


def build_ask_example(row):
    question = row["question_output"].strip()
    assistant = f"Question: {question}"

    parsed = clarifier.parse_ask_output(assistant)
    assert parsed == question, f"Ask round-trip failed: {assistant!r}"

    return {
        "messages": [
            {"role": "system", "content": clarifier.SYSTEM_PROMPT_ASK},
            {"role": "user", "content": row["report_text"]},
            {"role": "assistant", "content": assistant},
        ]
    }


def build_act_example(row):
    question = row["question_output"].strip()
    answer = row["answer"].strip()
    expected_actions = [a.strip().lower() for a in row["actions_output"].split(",") if a.strip()]
    assistant = f"Actions: {row['actions_output'].strip()}"

    parsed = clarifier.parse_actions_output(assistant)
    assert parsed == expected_actions, f"Act round-trip failed: {assistant!r} -> {parsed} != {expected_actions}"
    assert all(a in clarifier.ACTION_VOCABULARY for a in expected_actions), f"Unknown action in {row['actions_output']!r}"

    user_message = clarifier.build_act_user_message(row["report_text"], question, answer)

    return {
        "messages": [
            {"role": "system", "content": clarifier.SYSTEM_PROMPT_ACT},
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant},
        ]
    }


def build_row_example(row):
    """Dispatch on whether `answer` is populated, not on meta_call — see
    module docstring. meta_call is checked separately, only for consistency
    validation."""
    is_act_row = bool(row["answer"].strip())
    expected_meta_call = "2_act" if is_act_row else "1_ask"
    assert row["meta_call"].strip() == expected_meta_call, (
        f"meta_call {row['meta_call']!r} inconsistent with populated fields "
        f"(expected {expected_meta_call!r}) for row: {row['report_text'][:50]!r}"
    )
    return build_act_example(row) if is_act_row else build_ask_example(row)


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
        meta_call = row["meta_call"].strip()
        if meta_call not in VALID_META_CALLS:
            print(f"  (skipping row — unknown meta_call {meta_call!r}: {row})")
            continue
        examples.append(build_row_example(row))
        counts[meta_call] = counts.get(meta_call, 0) + 1

    print("Examples generated per meta_call (bookkeeping only — never seen by the model):")
    for meta_call in sorted(VALID_META_CALLS):
        print(f"  {meta_call}: {counts.get(meta_call, 0)}")
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
