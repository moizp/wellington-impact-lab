---
name: fine-tune-adapter
description: Use when preparing training data for, running, or exporting the fine-tune for either model (the Triage Classifier or the two-call Clarifier) in the Wellington Emergency Information Triage system, so both stay built and validated the same way.
---

# Fine-tune a model

This project trains **two small models, fully fused, not LoRA adapters swapped on a shared base**.
Adapter-swapping was the original plan and was explicitly tried and dropped — see
`docs/BUILD_PLAN.md`'s "Fine-tuning approach" for why (mainly: the validated serving pattern loads
both fully-fused models simultaneously in one process, which turned out simpler and had no
swap-mechanics/race-condition risk to guard against). This skill exists because both models' data
preparation goes through the same CSV → generation-script → JSONL pipeline, and it matters that
stays consistent, not built ad hoc per model.

## The two models — read this before touching either dataset

- **Triage Classifier** — input: clarified report + official context + (optional) one related
  public report. Output: **only** `severity` + `rationale` (fixed template,
  `Severity: <level>\nRationale: <text>`). `hazard_type` is never model output — deterministic,
  set by `app/context.py`. See `docs/FINETUNE_PLAN.md` "Model 2".
- **Clarifier** — **one model, two inference calls**, task-conditioned via a different system
  prompt per call (`app/clarifier.py`'s `SYSTEM_PROMPT_ASK`/`SYSTEM_PROMPT_ACT`), not two models:
  - Call 1 ("ask"): report → a clarifying question, always produced.
  - Call 2 ("act"): report + question + answer → 1-2 action items from a fixed vocabulary
    (`check_neighbours` / `monitor_situation` / `document_further` / `call_111` / `evacuate` /
    `none`). Combines non-critical and safety-critical suggestions into one call for the hackathon
    build — a named, deliberate limitation, not an oversight. See `docs/FINETUNE_PLAN.md`
    "Model 1" for the full reasoning and what a more correct future version looks like.

## Steps

1. **Add or edit rows in the CSV, not the JSONL directly** —
   `backend/data/triage_examples.csv` or `backend/data/clarifier_examples.csv`. Both are meant to
   be editable by non-engineers (e.g. Sara for domain content). Column meanings are documented in
   the header comment of the matching generation script; the `meta_`-prefixed columns
   (`meta_category`, `meta_call`) are bookkeeping only — never seen by the model, checked only for
   internal consistency against which other fields are populated.
2. **Apply the severity calibration rule already established** (see `docs/FINETUNE_PLAN.md`'s
   "Severity calibration rule" under the Triage Classifier's Next steps) rather than inventing a
   new one per row: concrete described impact → at least medium; a vague report directly
   confirming *no* impact overrides even a high official hint down to low; a vague report with no
   information either way follows the official hint's severity, even across unrelated hazard
   types; `high`/`call_111`/`evacuate`-tier outcomes stay a minority, not evenly distributed by
   construction — most real reports are mundane.
3. **Run the matching generation script**:
   ```bash
   .venv/bin/python3 scripts/generate_triage_dataset.py     # or generate_clarifier_dataset.py
   ```
   This regenerates `train.jsonl`/`valid.jsonl` from scratch every time — there's no separate
   "transform" step, and no risk of the CSV and the JSONL drifting apart. Every row's target
   output is round-trip validated through the real parser (`classifier.parse_triage_output()` /
   `clarifier.parse_ask_output()` / `clarifier.parse_actions_output()`) before being accepted — a
   malformed row (bad severity value, wrong formatting) fails loudly with which row broke, not
   silently written into the dataset.
4. **Never hand-type an approximation of the rendered context/user-message text.** The scripts
   call the exact same functions live serving uses
   (`context.render_context_text()`, `classifier.build_user_message()`,
   `clarifier.build_act_user_message()`) — this is the concrete fix for a training/serving drift
   risk this project's composite inputs create that a raw-text-only model wouldn't have. If a new
   field needs adding to what a model sees, add it to the shared function, not just the dataset
   script.
5. **Target minimum ~150 rows per distinct instruction shape**, not 150 total split across shapes
   — the Triage Classifier is one shape (~150+), the Clarifier is two (~150 each for Call 1 and
   Call 2). See `docs/FINETUNE_PLAN.md` "Sample size" for the reasoning.
6. **The dataset still needs a full team review/correction pass before actual fine-tuning** —
   round-trip validation catches formatting bugs, not domain-accuracy bugs. This is a standing,
   not-yet-completed step for both current datasets (231 Triage rows, 420 Clarifier rows as of the
   last count) — check `docs/FINETUNE_PLAN.md`'s "Next steps" for current status before assuming
   either is ready to train on.
7. **Run the actual fine-tune** with the validated `mlx_lm.lora` commands in `docs/BUILD_PLAN.md`
   "Fine-tuning commands" — copy them exactly rather than re-deriving flags, since they were
   checked directly against the installed `mlx_lm` version's real `--help` output, not assumed
   from a different version or from memory. Requires a venv with `mlx_lm` installed (Apple
   Silicon only) — this repo's own `.venv` doesn't have it. **The exact venv path in
   `BUILD_PLAN.md` is specific to the machine that path came from** — if you're on a different
   machine, create your own `mlx_lm` venv and substitute its path; the commands themselves stay
   the same.
8. **Watch train/valid loss as it runs**, not just at the end — `docs/FINETUNE_PLAN.md` "Training
   mechanics" explains what each actually measures. If valid loss stops improving or starts
   climbing while train loss keeps dropping, that's overfitting — stop early and use an earlier
   `--save-every` checkpoint, not the final one.
9. **Export via the validated pipeline** in `docs/BUILD_PLAN.md` "Validated model build/deploy
   pipeline" (`mlx_lm.fuse` → `convert_hf_to_gguf.py` → `llama-quantize` → test locally with
   `llama-completion` → upload to a private HF model repo → Cloud Build → Cloud Run) — this is
   proven end-to-end on the OIA project already; don't re-derive the adapter-swap/GGUF-conversion
   approach from the original (superseded) plan.
