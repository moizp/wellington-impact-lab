# Paper plan — comparing fine-tuned and untrained candidates for HR-query triage

**Status:** plan only — nothing here has been implemented or run. Thresholds in "Pre-registered
decision rules" (§7) must be committed *before* any Stage 2 result exists, so the commit history
proves they weren't tuned to the outcome.

**What changed from the previous version.** The original plan targeted the Wellington hazard-report
Triage Classifier; it is preserved unchanged as `docs/paper_plan_triage.md`. This version:

- swaps the task for a **stand-in HR-query task** (§1) so the method can be developed and
  rehearsed on a clean, fully synthetic problem;
- moves the baseline from Phi-3.5-mini to **Phi-4-mini-instruct**, and **newly fine-tunes** it
  (there is no deployed model for this task);
- puts the **policy text in the model input for every model** (option 1, §1.3);
- adds an **untrained / zero- and few-shot arm** (§5, Stage Z; confirmed, D9);
- re-derives the grader, test set, safety rule and gates for a two-label task (§3, §7);
- **(review revision)** replaces `next_step` with a model-emitted **`resolution`** plus a
  code-derived route (D8), makes **QWK the urgency endpoint** with a margin taken from annotator
  agreement (D3′), requires **two annotators on every test row** (D10), and declares **one primary
  endpoint family** with urgency and `resolution` as pre-registered secondary endpoints (D11).

The method (single benchmark script, process-isolated memory/latency, strict mechanical grader,
paired non-inferiority test, 2× resource gate, structured setup-effort rating) carries over.

**Research question.** For a routing-and-reply task (HR query + relevant policy text in →
`classification`, `urgency`, `resolution`, `summary` out; destination queue derived in code), can a smaller model — fine-tuned
BERT/BART family, a smaller decoder, or an *untrained* instruct model with a prompt — match a
fine-tuned Phi-4-mini-instruct (Q4_K_M) on quality while using substantially less memory and
latency on a CPU-only production-class target?

```mermaid
flowchart TD
    A[Stage 1: harness, grader, frozen test set, policy corpus] --> B[Stage 0: benchmark untrained-weights candidates for resources]
    A --> Z[Stage Z: untrained instruct models, zero/few-shot, quality + resources]
    B --> G0{Gate 0: >=2x less memory AND p95 latency vs baseline on CPU?}
    G0 -- no --> X0[Drop; record negative result]
    G0 -- yes --> C[Stage 2: fine-tune, 3 seeds, equal budget]
    Z --> G1
    C --> G1{Gate 1: format >=99% AND non-inferior AND safety rules hold?}
    G1 -- no --> X1[Report as quality-inferior]
    G1 -- inconclusive --> N[Enlarge test set or CV, re-run]
    N --> G1
    G1 -- yes --> D[Stage 3: production-like validation]
    D --> G2{Prod ratios still >=2x and E2E smoke test passes?}
    G2 -- no --> X2[No migration; report dev-vs-prod gap]
    G2 -- yes --> M[Recommend]
```

---

## 1. The task and its output contract

### 1.1 Task (stand-in, fully synthetic)

A general HR-department query (free text from an employee) is categorised on two parameters and
answered with a recommended reply and routing:

- **`classification`** ∈ {`leave_policy`, `complaint`, `hazard_report`, `hiring_request`,
  `other_unclear`}
- **`urgency`** ∈ {`low`, `medium`, `high`}
- **`resolution`** ∈ {`answer_from_policy`, `escalate_to_human`, `ask_clarification`} (D8) —
  model output carrying information *independent* of the class: whether the supplied policy
  covers the question and whether a human must act.
- **`summary`**: a one-to-two-sentence recommended response / case summary.
- **Destination queue (`route`) is not a model output.** It is derived in code from
  `classification` via a committed table (`eval/routing_table.json`; queue names provisional:
  `leave_policy`→hr_services, `complaint`→employee_relations, `hazard_report`→health_safety,
  `hiring_request`→recruitment, `other_unclear`→hr_triage) — the same "deterministic vs
  model-inferred" split the Wellington system applies to `hazard_type`. The user-facing "next
  step" is the pair (`resolution`, `route`).

This is a *stand-in*: it exists to exercise the methodology on a task whose data can be authored
freely. It is not part of the Wellington emergency-triage system. All data is synthetic: no real
people, cases, names or organisations. This repo stays free of personal information (`CLAUDE.md`).

### 1.2 Rules that make the labels gradable

- **One label per query.** Queries with several intents get a written **precedence rule**
  (proposed: `hazard_report` > `complaint` > `hiring_request` > `leave_policy`). Without it the
  test labels measure annotator disagreement, not the models.
- **`other_unclear` exists** so out-of-scope or ambiguous queries have a correct answer
  (`resolution = ask_clarification`). Include these in train and test (≈ 10%).
- **Urgency calibration rule** (written, committed before labelling), e.g. `high` = risk of
  physical harm, allegations of harassment/discrimination, or a deadline within 48 h; `medium` =
  time-bound but no harm; `low` = informational. Urgency is ordinal and subjective → the
  **endpoint is quadratic-weighted κ (QWK)**, with exact match and within-one reported as
  secondary measures, and model QWK always shown next to the **human–human QWK ceiling** (D3′).
- **`resolution` gold rule** (written, committed before labelling): `answer_from_policy` = the
  supplied clause covers the question and no human decision is needed; `escalate_to_human` = a
  human must act (complaints, hazards, approvals) or the clause does not cover the question;
  `ask_clarification` = the query is ambiguous or missing information. `resolution` still
  correlates with class, which is why a class→resolution control exists (§3.5).
- **Urgency correlates with class** (hazards mostly high, leave mostly low). That is realistic,
  and it makes "class-only → urgency" a useful trivial control (§3).

### 1.3 Policy text is in the input for every model (decision D7)

Fine-tuning on policy Q&A alone would put facts in the weights: they are unreliable on
paraphrased or novel questions, go stale when policy changes, and cannot be checked by a
mechanical grader. Instead:

- A small **synthetic policy corpus** (≈ 30–60 short clauses: leave entitlements, complaint
  procedure, hazard-reporting procedure, hiring-request process) is committed with stable clause
  IDs.
- Each example's input = the query **plus the relevant clause(s)** (gold clause + 1–2 distractors,
  fixed per example). Retrieval is *given*, not tested: the benchmark measures grounding and
  routing, not search. State this limitation.
- **The same canonical render function** builds this input for training data, the benchmark, and
  any serving code (`build_user_message(query, clauses)`); a test asserts the stored test text
  equals the render output. Training data is built with policy present, so fine-tuned models
  learn to *use* the text, not memorise it.
- **Frontier/untrained models get the identical rendered input** — no extra hints — so quality
  gaps reflect the models, not different inputs.
- **Held-out clauses.** A slice of the test set uses clauses never seen in training (new
  entitlement numbers / procedures), to show the models read the snippet rather than recall
  training facts.
- **Abstention cases.** Some examples carry no clause that answers the question; the correct
  behaviour is `resolution` ∈ {`escalate_to_human`, `ask_clarification`} (never `answer_from_policy`) and a summary that states no figure. This makes abstention directly gradable.

### 1.4 Output format and mechanical checks

Raw model output is exactly four lines, in order:

```
Classification: <leave_policy|complaint|hazard_report|hiring_request|other_unclear>
Urgency: <low|medium|high>
Resolution: <answer_from_policy|escalate_to_human|ask_clarification>
Summary: <1-2 sentences>
```

The strict grader (`eval/grader.py`; rejects, never defaults) checks:

1. **Format**: exactly four lines, label spelling, enum membership, lowercase, summary non-empty
   and ≤ N tokens / ≤ 2 sentences, no trailing text, EOS reached before `max_new_tokens`
   (truncation = fail).
2. **Semantic**: `classification`, `urgency` and `resolution` equal gold; urgency also scored ordinally (QWK, within-one).
3. **Route derivation**: the code-derived `route` for the predicted class is computed through
   the same `routing_table.json` used for gold labels; a test asserts a gold row's route equals
   the table's output. A critical misroute (§7) is a *class* error visible through this table.
4. **Grounding (mechanical)**: every number/duration/date token in `summary` also appears in the
   supplied clause text; on abstention examples the summary contains none. A wrong figure is a
   hard fail — this is the hallucination check the format grader alone cannot do.
5. **Safety-weighted**: confusion matrices; the specific costly errors in §7.

Summary *prose quality* is not mechanically gradable. It is **not** in the pass rate and never a
gate. Report mechanical properties only (length, sentence count, non-empty, grounding), plus an
optional, clearly secondary reference-based similarity (e.g. BERTScore).

**Pass rate (primary generative metric)** = format valid ∧ classification correct ∧ urgency correct
∧ resolution correct ∧ grounding clean. **Descriptive only** — not an endpoint (D11). **Per-field
metrics** are always reported, since the joint metric is harsh when urgency labels are noisy.

**Non-generative candidates (D1, generalised).** BERT/DistilBERT use classification heads and
cannot write a summary. They are scored on the **labels-only contract**
(`classification`, `urgency`, `resolution`; three heads) and `contract: labels_only` is
recorded in every row; only generative candidates are scored on the full contract. `summary` is
`null` for labels-only candidates (default; to settle in implementation).

---

## 2. The single benchmark script

`backend/eval/benchmark_model.py` — one entry point, identical for every candidate and the
baseline:

```bash
python -m eval.benchmark_model \
  --task hr_query --model <path-or-hf-id> \
  --backend {llamacpp,mlx,hf,onnx,ctranslate2,anthropic} \
  --mode {finetuned,zeroshot,fewshot} --k-shots 0 \
  --split {test,valid} --n-runs 100 --threads 4 --device cpu \
  --out results/<run_id>.json --preds-out results/<run_id>.preds.jsonl
```

- **Task registry**: `--task hr_query` binds prompt builder, gold labels, strict grader and
  contract. Prompt assembly imports the canonical render — never re-typed.
- **Backend adapters** (`load()`, `generate(prompt) -> text, n_out_tokens`). Backend is a recorded
  variable, not hidden.
- **Process isolation**: a fresh child process per model per phase; the parent samples child RSS
  with `psutil` (10 ms); in-process `ru_maxrss` is avoided. Phases: load → first request →
  5 discarded warm-ups → N timed requests. On Apple Silicon also record MLX/Metal peak memory
  (RSS under-counts unified memory; verify the API name for the installed `mlx`).
- **Determinism**: greedy decoding, fixed seed, fixed `--threads`, `max_new_tokens` set from the
  longest gold output plus margin (replaces triage's 80; this task's output is longer).
  `--serving-sampling` reruns at the intended serving temperature as a sensitivity check.
  Stage 1 verifies two runs on the same weights give identical predictions, or reports the
  observed tolerance.
- **Primary device is CPU** (`n_gpu_layers=0` / `device=cpu`), because the assumed production
  target is CPU-only (4 vCPU / 16 GiB). Metal/MPS runs are dev-only secondary rows.
- **Prompt length is a recorded variable.** Few-shot prompts are much longer than fine-tuned
  prompts; mean prompt tokens, mean generated tokens and an estimated FLOPs/request
  (≈ 2 × params × tokens processed, labelled an estimate) go in every row.
- **Environment fingerprint** in every row: git SHA, dataset and policy-corpus SHA-256s, model
  file SHA-256, library versions, CPU model, OS, threads, seed.

Row schema (sketch):

```json
{
  "run_id": "...", "task": "hr_query", "model": "phi4mini-q4km-baseline", "backend": "llamacpp",
  "mode": "finetuned", "device": "cpu", "threads": 4, "seed": 0, "decoding": "greedy",
  "env": {"git_sha": "...", "dataset_sha256": "...", "policy_sha256": "...", "model_sha256": "...", "libs": {}, "cpu": "..."},
  "static": {"params_m": 0, "disk_mb": 0, "quant": "Q4_K_M", "mean_prompt_tokens": 0},
  "memory": {"peak_rss_load_mb": 0, "peak_rss_infer_mb": 0, "metal_peak_mb": null},
  "train": {"total_s": 0, "to_best_ckpt_s": 0, "s_per_step": 0, "samples_per_s": 0,
            "tuning_budget_total_s": 0, "peak_train_mem_mb": 0, "trainable_params_m": 0, "seeds": 3},
  "time": {"load_s": 0, "cold_first_s": 0, "n": 100,
           "avg_s": 0, "p50_s": 0, "p95_s": 0, "p99_s": 0, "tok_per_s": 0},
  "quality": {"n": 0, "format_pass": 0, "class_acc": 0, "urgency_acc": 0, "urgency_within1": 0,
              "resolution_acc": 0, "grounding_clean": 0, "pass_rate": 0,
              "class_macro_f1": 0, "urgency_qwk": 0, "urgency_qwk_human_ceiling": 0,
              "critical_misroute": 0, "under_urgency": 0,
              "by_class": {}, "slice_heldout_clause": {}, "ci95": {"pass_rate": [0, 0]}},
  "setup": {"finetune": {"scores": {}, "median": 0, "raters": 2, "steps": 0, "manual_interventions": 0,
                         "errors_hit": 0, "time_to_first_run_h": 0},
            "serving": {"apple_silicon": {}, "gcp_x86": {}}},
  "contract": "full | labels_only"
}
```

**What exists today (harness v0, stdlib-only, 39 unit tests passing).** `backend/eval/`: `contract.py`
(enums, system prompt, canonical render, `format_output`), `grader.py` (strict parse, grounding,
safety flags), `metrics.py`, `stats.py` (Wilson, QWK, paired bootstrap, exact McNemar),
`runner.py` / `run_eval.py` (one backend → result row + per-example predictions),
`run_suite.py` (all enabled models, one at a time → `summary.md` + paired comparison),
`compare_rows.py`, `gates.json` (**`frozen: false`**, so every verdict prints as EXPLORATORY),
three controls (`oracle`, `keyword`, `majority`), and thin adapters for llama.cpp, MLX and the
Anthropic API that are **written but untested** (they need model files, weights or an API key).
`hf` / `onnx` / `ctranslate2` adapters for BART and DistilBERT are not implemented. The data under
`eval/fixtures/` is an invented 24-row fixture for testing the harness, **not** the benchmark.
This is the quality half only: the isolated memory / latency benchmark (`benchmark_model.py`) is
still to build and will wrap `runner.run`.

Run it: `cd backend && python3 -m unittest discover -s tests -t . -p "test_eval_*.py"` and
`python3 -m eval.run_suite`.

`backend/eval/compare_rows.py` consumes baseline + candidate rows and per-example predictions →
diff table, paired bootstrap CI, McNemar test, gate verdicts.

---

## 3. Candidates

### 3.1 Model set

| ID | Model | Params | Type | Contract | How it is used |
|---|---|---|---|---|---|
| **B0** | `microsoft/Phi-4-mini-instruct`, LoRA fine-tuned here, Q4_K_M GGUF | ~3.8B | dense decoder | full | **Newly fine-tuned baseline** (nothing deployed for this task) |
| **A** | `facebook/bart-base` | ~139M | encoder-decoder | full | fine-tuned |
| **C** | `distilbert/distilbert-base-uncased` (multi-head classifier) | ~66M | encoder + heads | labels_only | fine-tuned |
| **D** | `LiquidAI/LFM2-1.2B` (fallback: `google/gemma-3-1b-it`) | 1.17B | hybrid conv + attention decoder | full | fine-tuned **and** untrained (Stage Z); decided D12 |
| **R-frontier** | Anthropic **Claude Opus 5.5** (`claude-opus-5-5`), via API | not disclosed | hosted | full | Quality reference, zero- and few-shot, policy in prompt (§5.1); cost and latency reported separately, not gated |

Stage-Z (untrained) rows are added for B0's family and D: Phi-4-mini-instruct zero- and few-shot,
and LFM2-1.2B zero- and few-shot. BERT/BART have no useful untrained mode (random heads) and
enter Stage 0 only.

**Dropped models (D13).** `google-bert/bert-base-uncased` (the capacity ablation) and
`microsoft/phi-4` (the 14B reference) are removed. Consequences to state in the paper: the encoder
family is represented by DistilBERT alone, so there is no encoder capacity-scaling result; and the
"too big for 4 vCPU" argument for choosing Phi-4-mini over Phi-4 is reasoning (a Q4_K_M 14B
needs roughly 8–9 GB for weights alone), not a measured row.

### 3.2 Which Phi-4 variant is the baseline

**Phi-4-mini-instruct**, not the 14B Phi-4. Verified from the model card and `config.json`
(WebFetch of huggingface.co, this session):

- exists as an instruct variant; MIT licence; ~3.8B parameters; 128K context; released
  February 2025;
- `architectures: Phi3ForCausalLM`, 32 layers, hidden 3072, **24 attention heads / 8 KV heads**
  (GQA), **vocab 200,064**, **tied embeddings**, LongRoPE, partial rotary factor 0.75.

Why not the 14B: at Q4_K_M it needs roughly 8–9 GB for weights alone and would be impractically
slow on 4 vCPU. A "≥ 2× cheaper" gate against it would be trivially met by almost anything and
therefore meaningless, and the production shape would have to change. It is **not run**
(D13); the argument is stated, not measured. (If the production target changes to GPU or a much
larger CPU instance, revisit; recorded as D6.)

Tooling, checked against the upstream source this session (GitHub, not an installed copy):
`mlx_lm` has `phi3.py` handling LongRoPE, `partial_rotary_factor` and tied embeddings, and its LoRA
layer selection is generic over any model exposing `model.layers`; llama.cpp's converter registers
`Phi3ForCausalLM`; community Q4_K_M GGUFs exist. **Still not confirmed** (needs your machine):

- `mlx_lm.lora` actually training Phi-4-mini-instruct in the installed `mlx_lm` version. Stage 0
  step 0 must run a 20-step `mlx_lm.lora` smoke test and a GGUF convert-and-load round trip
  before anything depends on it.
- Whether the existing fuse → GGUF → Cloud Run path used for Phi-3.5 works unchanged (200k vocab
  and tied embeddings change file size and conversion behaviour).

### 3.3 Candidate-D architecture rule, re-checked against the new baseline

D must differ from the baseline on at least one *structural* axis, and have both an `mlx_lm` LoRA
path and a llama.cpp/GGUF path, so the pipeline stays identical to the baseline's.

The new baseline is *closer* to the Llama-3.2 family than Phi-3.5 was: Phi-4-mini now has GQA, a
large (~200k) vocabulary and tied embeddings — exactly the axes on which the old plan said
Llama-3.2-1B differed. Consequently:

- **Llama-3.2-1B and Qwen-class ~1B models do not qualify.** They are the same dense decoder
  design; use only as a labelled **size-only control**, if at all.
- **LFM2-1.2B qualifies and is the chosen D (D12).** `Lfm2ForCausalLM`: 16 layers, of which 10 are
  gated short-convolution blocks and 6 are attention; 32 heads / 8 KV heads; vocab 65,536. Not a
  pure transformer, so the structural difference from Phi-4-mini is large.
- **Gemma-3-1B-it is the fallback** (interleaved local sliding-window / global attention, 26
  layers, 4 heads / 1 KV head, vocab 262,144). Its repo is gated and its config was read from an
  ungated mirror; re-check against the official repo if it is ever used. Phi-4-mini's
  `sliding_window` entry is effectively inactive at 262,144 vs 128K context, so Phi-4-mini is not
  a sliding-window model in practice.
- A Mamba/SSM ~1B model qualifies architecturally; GGUF/MLX support must be confirmed.

Verified from upstream source this session: LFM2 `config.json` and card (1,170,340,608
parameters; LFM Open License v1.0), `mlx_lm` has `lfm2.py`, and llama.cpp's converter registers
`Lfm2ForCausalLM`. Still to check in Stage 0: a LoRA smoke test and a GGUF round trip for
LFM2-1.2B, and the **licence terms** (the card names the licence but this session did not read its
terms; confirm before publishing any derived weights). Note the LFM2 card points to a newer
LFM2.5-1.2B-Instruct; LFM2-1.2B is kept because its config and tooling are the ones checked here.
If the smoke test fails, fall back to Gemma-3-1B-it; if that fails too, drop D rather than
substitute a same-architecture model under another name.

### 3.4 Tooling for BART / DistilBERT

Checked upstream this session:

- `mlx_lm` has **no** BART, BERT or DistilBERT model files, so `mlx_lm.lora` cannot train A or C.
  Train them with HF Transformers (+ PEFT, or full fine-tuning; at 66M–139M parameters full FT is
  feasible — run LoRA as primary if LoRA is required, full FT as an ablation).
- **Fine-tuning BERT-family models on macOS works.** PyTorch's MPS backend (Apple GPU) or plain
  CPU both run HF Transformers training; models this small fit comfortably in unified memory.
  Practical notes (general knowledge, to be confirmed by a smoke test, not checked here): set
  `PYTORCH_ENABLE_MPS_FALLBACK=1` in case an op lacks an MPS kernel; avoid `bitsandbytes`
  (not available on macOS); prefer fp32 or bf16 over fp16 on MPS if loss goes NaN. Training time
  from MPS/CPU is **not** comparable with MLX decoder training — already a stated caveat in §6.
- **llama.cpp**: the converter has no BART module (only the T5 family for encoder-decoder), so A
  cannot use GGUF. It registers `BertModel` / `DistilBertModel` and their `…ForSequenceClassification`
  variants with a single set of output labels — aimed at single-head classification/reranking, so
  our three-head design does not map onto it.
- Serving therefore: **A** on CTranslate2 (BART is on its supported list) or ONNX Runtime; **C**
  on ONNX Runtime int8 via Optimum (documented for DistilBERT). ONNX export of BART is untested
  here. Runtime becomes a confound: report each model on its best supported runtime *and* any pair
  sharing a runtime; don't claim an architecture effect that is really a runtime effect.

### 3.4a Tooling matrix — final model list, fine-tuning on macOS (D14)

"Checked" = read in upstream source or the model card this session (GitHub / Hugging Face), not
tried on the target machine. Footprints are **arithmetic from parameter counts, not measurements**;
Stage 0 step 0 measures them.

| Model | Fine-tune on the MacBook | Precision / rough footprint on 16 GB | Export → serving format | CPU serving runtime (x86, Stage 3) | Mac-specific risks |
|---|---|---|---|---|---|
| **B0** `microsoft/Phi-4-mini-instruct` (3.8B) | `mlx_lm lora` on the Metal GPU. `phi3.py` checked (LongRoPE, partial rotary, tied embeddings). Smoke test needed | bf16 weights ≈ 7.6 GB, so LoRA is tight and needs `--grad-checkpoint` and a small batch; or QLoRA on a 4-bit base (≈ 2.0–2.5 GB). One choice for all decoders (§3.4b) | adapter → `mlx_lm fuse` (dequantise if QLoRA) → HF → `convert_hf_to_gguf.py` (`Phi3ForCausalLM` registered, checked) → `llama-quantize` Q4_K_M | llama.cpp / `llama-cpp-python`, GGUF | **200k-vocab logits memory** (§3.4b); Metal OOM mid-training after a clean validation pass; fused bf16 export is ≈ 7.6 GB + scratch disk |
| **D** `LiquidAI/LFM2-1.2B` (1.17B) | `mlx_lm lora`. `lfm2.py` checked. Smoke test needed — confirm which conv/attention linears LoRA touches and what `--num-layers` selects | bf16 ≈ 2.3 GB: comfortable | same pipeline (`Lfm2ForCausalLM` registered, checked) | llama.cpp, GGUF | Newer architecture: check the installed `mlx_lm` / llama.cpp versions include LFM2 |
| **A** `facebook/bart-base` (≈ 139M) | HF Transformers (+ PEFT or full FT) on PyTorch **MPS**, or CPU. Not supported by `mlx_lm` (no BART file) | fp32 full FT with AdamW ≈ 2–3 GB: comfortable | PyTorch → ONNX (Optimum, export untested here) or CTranslate2 (`ct2-transformers-converter`; BART listed as supported). **No GGUF path** (no BART converter) | ONNX Runtime or CTranslate2 | MPS op gaps (`PYTORCH_ENABLE_MPS_FALLBACK=1`); seq2seq `generate` may be slower on MPS than CPU, so evaluate generation on CPU and record the device |
| **C** `distilbert/distilbert-base-uncased` (≈ 66M) | HF Transformers (+ PEFT or full FT) on MPS or CPU. Not supported by `mlx_lm` | fp32 full FT ≈ 1 GB: trivial | PyTorch → ONNX (Optimum) → int8 dynamic quantisation. GGUF registers DistilBERT but only a single classification head, not our three | ONNX Runtime int8 | int8 kernels differ by CPU, so a model quantised and benchmarked on the Mac must be re-benchmarked on x86 |
| *Fallback* `google/gemma-3-1b-it` (≈ 1B) | `mlx_lm lora`; `gemma3_text.py` checked | bf16 ≈ 2 GB weights; 262k-vocab logits are large like B0's | `Gemma3ForCausalLM` registered, checked; `ggml-org` GGUF exists | llama.cpp, GGUF | Gated repo; custom licence |
| **Stage Z** (no training) Phi-4-mini-instruct, LFM2-1.2B | none | Q4_K_M GGUF ≈ 2.5 GB for Phi-4-mini (community builds) | existing GGUFs or the same pipeline | llama.cpp, GGUF | Few-shot prompts raise memory and latency; record prompt tokens |

### 3.4b Hardware constraint: MacBook Pro, 16 GB (decision D14)

**Constraint.** All fine-tuning, and all development-side testing and benchmarking (Stage 0, Stage Z,
Stage 2), runs on **one MacBook Pro with 16 GB of unified memory**. GCP x86-64 CPU is used only for
the Stage 3 serving validation; nothing is trained there (D5). The chip is recorded as a fact
about the machine: **MacBook Pro, Apple M2 Pro, 16 GB unified memory** (confirmed by the
owner; matches `system_profiler` on this laptop). The paper names the exact chip because core
counts and memory bandwidth differ from the base M2; record core counts and macOS version in the
environment fingerprint.

**Consequences, and what the plan does about each**

1. **16 GB is shared by macOS, other apps, CPU and GPU.** Metal caps the GPU working set at a
   fraction of RAM (roughly two-thirds to three-quarters; read the real figure from MLX device
   info at Stage 0 step 0 rather than assuming it). Training runs with the machine otherwise
   idle: no browsers, no dev servers, no second model held in memory. The repo's own earlier
   gotcha applies: a stray process memory-mapping a GGUF causes Metal OOM; check with `lsof`
   before blaming the dataset.
2. **Large-vocabulary decoders cost more than their parameter count suggests.** Fp32 logits
   for a batch cost batch × sequence × vocab × 4 bytes: at batch 4 × 512 tokens that is ≈ 1.6 GB
   for Phi-4-mini's 200,064-token vocabulary versus ≈ 0.26 GB for Phi-3.5's ~32k. The previous
   Phi-3.5 recipe (`--batch-size 4 --num-layers 16`, in `docs/BUILD_PLAN.md`) is therefore **not**
   safe to reuse unchanged; start from `--grad-checkpoint` with a physical batch of 1–2 and
   gradient accumulation to the same effective batch. Arithmetic only — measure it.
3. **Precision choice is a confound, so choose it once.** LoRA on a bf16 base vs QLoRA on a 4-bit
   base changes both memory and the model. Pick one for B0 and D from the smoke test (preferring
   bf16 LoRA if it fits, because it matches the previous pipeline), apply it to both decoders, and
   state it. If B0 only fits with QLoRA, use QLoRA for D too even though D would fit in bf16.
4. **Measure memory correctly on unified memory.** RSS under-counts GPU allocations. Record the
   framework's own peak (MLX peak-memory API; PyTorch `torch.mps` allocated-memory counters — the
   exact function names differ by version, verify at Stage 0), plus system swap before and after
   each run (`sysctl vm.swapusage`). **A run that swaps is invalid for timing and is repeated.**
5. **One training job at a time.** The older docs allow two LoRA runs side by side; this plan does
   not, because concurrency distorts both timing and peak memory.
6. **Thermals and power.** A MacBook throttles under sustained load. Always plugged in, same power
   mode, lid open, cooldown between runs, thermal state noted. Interleave candidates across the
   session (do not run all of B0's seeds first and then all of C's) so drift does not align with
   one model. Re-run one reference job at the start and end of each session to detect drift.
7. **Budget is set from a measurement.** B0 and D dominate cost: 3 seeds × up to 6 configurations
   each. After the Stage 0 smoke test measures seconds per step for B0 at the chosen precision,
   fix the equal tuning budget (§6) so B0's whole budget fits the available time. If it does not,
   the number of configurations is reduced for **every** candidate, not just B0.
8. **Mac CPU numbers are arm64 CPU numbers.** CPU-only benchmark rows on the Mac (llama.cpp with
   `n_gpu_layers=0`, ONNX Runtime CPU) measure Apple performance cores, and macOS cannot pin
   threads, so latency noise is higher than on Linux. They are a relative signal; absolute
   latency and the 2× gate are confirmed on x86 in Stage 3. Export formats must therefore be ones
   x86 can run (GGUF, ONNX, CTranslate2 — all are).
9. **Disk.** The fuse → HF → GGUF → quantise path for a 3.8B model holds several full-precision
   copies at once (≈ 7.6 GB each); keep tens of GB free and delete intermediates after each run.
10. **Environment fingerprint** gains: exact chip and core count, macOS version, RAM, power mode,
    `mlx` / `mlx_lm` / PyTorch / `transformers` / `peft` / `llama.cpp` versions and commit.

### 3.5 Controls (cheap, strengthen the paper)

- Majority class; keyword rules per class; **TF-IDF + logistic regression** (three heads) on the
  rendered input; **class-only → urgency** and **class-only → resolution** rules (quantify how much of these fields is just the class). If a trivial classifier is within tolerance of
  B0 on the labels, that is a central finding.
- Quantisation ablation: B0 fused FP16/MLX vs Q4_K_M.
- A **"summary-copy" control**: output the first sentence of the gold clause as the summary — shows
  how much of the grounding check a trivial strategy passes.

---

## 4. Stage 1 — harness, grader, policy corpus and test set *(needed regardless)*

Everything in the previous plan's Stage 1 is re-derived for this task:

1. **Author the policy corpus** (§1.3) with clause IDs; commit its SHA-256.
2. **Author the training/validation data** as a CSV (`hr_query_examples.csv`): query, gold
   clause IDs, classification, urgency, resolution, reference summary, `row_id` (hash of
   normalised query text). CSV-driven, generated to JSONL by a script that uses the canonical
   render and round-trip validates each row. Pin the CSV by SHA-256.
3. **Stable, stratified split** (`hr_query_splits.json`): by `row_id`, stratified by
   `classification × urgency`; persisted, never reshuffled. Lesson carried from the triage audit:
   a regenerating split and a validation set reused for headline numbers are both invalid.
4. **Frozen test set** (`backend/data/hr_query_test/test.jsonl`):
   - Newly authored rows, not carved from the training CSV; stratified over 5 classes × 3
     urgencies; `high` urgency and `hazard_report` / `complaint` deliberately over-represented
     (the costly classes) — target ≥ 40 rows in each of those cells combined with ≥ 40 gold-`high`.
   - Includes the **held-out-clause slice** and the **abstention slice** (§1.3).
   - **Size**: target 300–400, **floor 150**. The earlier power estimate (≈ 360 rows for ±4
     points when ≈ 15% of items disagree between two models) was derived for triage; **re-estimate
     from the pilot disagreement rate on this task** before fixing the target. Size the set for the
     **primary endpoint family** (§7: classification accuracy and the two safety counts); the
     secondary endpoints are reported with whatever precision the set gives. Safety counts are
     small numbers → compared with exact paired tests, so the ≥ 40 rows per costly cell matter more
     than the total.
   - **Authoring (D2 carried over)**: machine-drafted, then human-verified/corrected. Drafts come
     from **Claude Sonnet 5.5 (`claude-sonnet-5-5`)** (D2), which is **not** an evaluated model in any arm. It is the same vendor family as R-frontier (Claude Opus 5.5), so this is an accepted, documented risk handled by the mitigations in §5.1
     (see §5 circularity warning); committed prompt; per-row `generator`, `prompt_version`,
     date. **Every test row is independently labelled by two annotators (A1, A2; IDs only; D10)**
     on `classification`, `urgency` and `resolution`, each recording `human_action` ∈ {accepted,
     edited, rejected} against the draft. Disagreements are adjudicated in a logged step (who,
     what changed, why); the adjudicated label is gold. Rejected rows kept in an audit file.
     **Anchoring audit and ceiling**: a random, stratified ≥ ⅓ of rows is labelled **blind**
     (before seeing the draft) by *both* annotators. Human–human agreement on this blind subset —
     Cohen's κ for `classification` and `resolution`, QWK for `urgency`, each with bootstrap CI —
     is the **unanchored ceiling** models are compared against. Agreement on the non-blind rows
     is reported but flagged as inflated by anchoring. Also report blind-vs-draft agreement.
   - **Manual correction of the drafted set (explicit risk control, D2).** Human review covers the
     whole row, not just the labels: (i) the query text — realistic, unambiguous under the written
     rules, no drafter stylistic tells; (ii) the gold clause IDs and distractors — the clause really
     does or does not answer the question; (iii) all three gold labels; (iv) the reference summary
     — consistent with the clause, no invented figures. Every correction is logged (row, field,
     before, after, reason, annotator). Rows that cannot be fixed are rejected into the audit file.
   - **Human-written slice.** At least 20% of test rows are written from scratch by the
     annotators with no model draft, covering the same class × urgency cells. All metrics are
     also reported on this drafter-free slice, so any drafter effect (including Sonnet–Opus
     family agreement, §5.1) can be seen directly.
   - **Rubber-stamp guard.** Report each annotator's accept/edit/reject rate by field. An
     accept-everything rate above a pre-declared threshold (set after the pilot) triggers a
     re-review of that annotator's accepted rows by the other annotator.
   - Frozen by SHA-256; never used for tuning or checkpoint selection; evaluated once per final
     configuration.
5. **Leakage tests (pytest, CI)**: no test query/full message in train/valid; max token-Jaccard
   test→train below threshold (start 0.6); split stable when unrelated rows are appended;
   held-out-clause slice really has no clause ID present in any train example.
6. **Strict grader + contract tests** (§1.4) with a table of good/bad outputs: extra lines, wrong
   case, unknown enum, missing summary, truncated, invented number, number present in the clause,
   abstention with a figure, `answer_from_policy` on an abstention row, route derivation for each class.
7. **Benchmark script + `compare_rows.py`** (§2) with the determinism test.
8. **Reproduce the baseline**: fine-tune B0 once (Phi-4-mini-instruct, smoke-tested per §3.2),
   run it on the test set → first row. If it fails format > 1% at greedy decoding, that changes the
   interpretation of every comparison.

*Exit criterion:* baseline row exists, reruns identically, tests green.

---

## 5. Stage 0 and Stage Z — resource screen and untrained models

### Stage 0 — resources only (untrained weights are a valid probe)

Memory and latency depend on architecture, size, quantisation and sequence length, not on trained
weights. Run the benchmark on B0, A, C, D with identical settings (CPU, 4 threads,
N=100, real validation-split prompts, same `max_new_tokens`), 3 repeats of the whole process.
Generative candidates get ~20–50 LoRA steps first so they emit the four-line format and
realistic token counts.

**Gate 0 (pre-registered):** a candidate proceeds only if, on CPU, both `peak_rss_infer_mb` and
p95 latency are **≤ 50% of B0's**, with repeat spread smaller than the margin by which it clears.
Fail → drop, keep the row as a negative result. Expected: encoders clear it trivially, so Gate 0
mainly screens D and A and confirms magnitudes. Passing earns a fine-tune, nothing more.

### Stage Z — untrained open instruct models (decision D9: confirmed)

**Why it is worth doing.** It answers a question fine-tuning rows cannot: *is fine-tuning needed
at all?* If an untrained instruct model with a good prompt is non-inferior to the fine-tuned
baseline, the cost (data authoring, training, conversion, setup effort) vanishes. It also shows
what fine-tuning buys, and gives the paper an honest "no training" row.

**Design.**

- Models: Phi-4-mini-instruct and D's instruct model . "Untrained" here means *no task fine-tuning*; it
  must be the **instruct** variant, since pretrained-only base models do not follow the four-line
  format and would fail on format, which says nothing about capability. A pretrained-only row may
  be added as an appendix to show that.
- Modes: **zero-shot** (system prompt with the contract and policy clause) and **few-shot**
  (k = 3 and k = 8 examples drawn from *train*, fixed, same for all models, selected before looking
  at test). Prompt wording is frozen before any test run; allow a bounded, equal number of prompt
  variants per model, selected on valid, never test.
- The strict grader is unchanged. Format failures are first-class results: untrained models are
  expected to fail format more often, and Gate 1's ≥ 99% format rule applies to them too.
- **Resource rows are not comparable to fine-tuned rows** without care: few-shot prompts are much
  longer, which raises latency and memory. Record mean prompt tokens, and report resources for
  untrained models separately and at their actual prompt length.
- **R-frontier** (Claude Opus 5.5) is a separate reference arm: see §5.1.
- Encoders (BERT/DistilBERT) have no untrained quality mode — skip.

Untrained rows enter Gate 1 against B0 like any fine-tuned candidate.

### 5.1 Frontier reference — Claude Opus 5.5 (decision D15)

**Purpose.** A quality reference that answers "what does a frontier model do on this task with
nothing but the prompt?", and a cost/latency/privacy comparison that frames the case for running a
small model locally at all. It is **a reference, not a candidate**: never gated, never recommended,
no memory metric.

**Protocol (identical inputs, bounded freedom)**

- Model: `claude-opus-5-5`, exact ID string, access date and API/SDK version recorded in every row
  (a hosted model can change under the same alias; if a dated snapshot ID is offered, use it).
- Input: the **identical rendered input** (§1.3) and the **same frozen prompts and few-shot
  examples** as the Stage Z open models: zero-shot, k = 3, k = 8. Same bounded number of prompt
  variants, selected on valid, never test.
- Decoding: temperature 0 where the API allows it, otherwise the documented default, recorded.
  Hosted models are not guaranteed deterministic, so run the test set **3 times** per mode and
  report run-to-run disagreement (that is the reference's own noise); the headline row uses the
  majority-voted or first-run prediction as pre-declared before running.
- Output: the same four-line contract and the same strict grader. Format failures count.
- Reported with the same paired statistics versus B0 (bootstrap CI, exact paired tests, safety
  counts) but **labelled descriptive**: the point is the size of the gap, not a verdict.
- **Cost and latency**: record input/output tokens per request and the list-price cost per 1,000
  requests at the access date; end-to-end latency p50/p95 *including network*, reported on its own
  axis and never merged with the local CPU latencies. Compare against the cost of running the
  small model (instance-hours at the measured throughput) as a break-even volume, with the
  assumptions stated.
- **Privacy and data**: the data is fully synthetic, so sending it to an external API is
  acceptable here. This is **not** transferable to real HR data, which is a reason to keep a local
  model in the first place — state that in the discussion. API keys come from the environment and
  are never committed.
- **Independence (accepted risk, D2).** Test rows are drafted by Claude Sonnet 5.5, a sibling of
  Opus 5.5, so Opus may agree with draft labels more than an unrelated model would. Opus itself
  must not draft or label any row, and Sonnet is never evaluated. Mitigations, all pre-declared:
  (a) every row is fully reviewed and corrected by humans, ≥ ⅓ are labelled blind, and ≥ 20% of rows are human-written with no draft (§4 item 4); results are also reported on that drafter-free slice; (b) report Opus's
  accuracy **separately on rows the humans accepted unchanged, rows they edited, and the blind
  subset** — a large gap in Opus's favour on accepted rows is the signature of shared drafter
  bias and is reported as such; (c) interpret the Opus-vs-open-model gap with that diagnostic in
  hand, and describe it as an upper-bound-with-caveat, never a clean ceiling. Record the Sonnet
  exact model ID, access date, prompt version and temperature per row. If any train text was
  drafted by a Claude model, disclose it.
- **Not used as a judge.** The plan keeps summary prose out of every gate. If an LLM-judged
  summary comparison is added later it needs a judge from a different vendor than every model
  being judged, and is secondary.
- Optional: a cheaper Claude tier could be added as a second reference point on the cost axis;
  not planned.

---

## 6. Stage 2 — fine-tune and compare

**Training protocol (identical across candidates)**

- Same canonical train/valid split; inputs from the same rendered user message (including policy
  clauses). A per-family conversion function (decoder: chat messages; BART: source = system+user
  text, target = the four-line output; encoder: message → heads) unit-tested against the
  canonical render. Encoders have a 512-token limit — measure the rendered length distribution
  first; truncation policy is decided once and stated (do not silently cut the policy clause).
- **Equal tuning budget**: same number of configurations (≤ 6) per candidate, same early-stopping
  rule, selected on **valid** (loss *and* strict metrics), never test.
- **3 training seeds** per candidate including B0; report mean ± sd.
- **Time to fine-tune is a measured outcome for every model**, via `eval/train_timer.py`:
  total wall-clock per run, time to the best validation checkpoint, per step/epoch and samples/s,
  whole-tuning-budget wall-clock, peak training memory, trainable parameters, steps used. All
  fine-tuning timed on the same idle, plugged-in Apple Silicon machine; thermal state noted.
  Caveat: training time depends on framework (MLX vs PyTorch-MPS/CPU), so it is a pipeline-level
  cost, not a pure architecture property.
- Class imbalance (e.g. `hazard_report`, `high`) handled once, applied to all, stated.
- **Reduce confounding (per family)**: find each family's *best* fine-tuning recipe (LoRA rank /
  target layers / lr / steps vs full FT; imbalance handling) and *best* serving architecture
  (GGUF quant levels, ONNX fp32 vs int8, CTranslate2, PyTorch reference), chosen on valid. Give
  the baseline the same tuning protocol so it is not the only untuned model. Report two
  comparisons: each family at its tuned best, and all families under one controlled setting.

**Evaluation protocol**

- Test set evaluated **once per final (seed × candidate)** after selection is frozen. If the
  protocol changes, old results stay in the appendix.
- **Endpoints are declared in advance (D11).** *Primary family*: strict format pass,
  classification accuracy (non-inferiority), the two safety counts, grounding, and the resource
  gate. *Secondary (pre-registered)*: urgency QWK (plus exact / within-one / MAE) and
  `resolution` accuracy. *Descriptive*: joint pass rate, macro-F1, per-class breakdown,
  held-out-clause and abstention slices, summary mechanical properties.
- Statistics: Wilson intervals; **paired** bootstrap CI (10k resamples) and exact McNemar vs B0;
  seed variance alongside; Holm correction across candidates **and across the secondary endpoints**. The primary family is an all-must-pass (intersection) rule, so it needs no alpha split between its members, but each member needs enough power — the sizing driver in §4 item 4.
- Optional 5-fold CV on train+valid only, to tighten variance if the test set ends near the floor.
- Robustness slice (small, mechanical): typo/paraphrase/long-query perturbations — degradation
  reported, not gated.

**Setup-effort evaluation (subjective, structured; never a gate)** — unchanged in method:

- Two ratings per model: *fine-tuning setup* and *serving setup* (per environment). For untrained
  models the fine-tuning rating is "n/a" and the effort is *prompt engineering* (rate that
  instead).
- Rubric `backend/eval/setup_rubric.md`, committed before the first candidate: 1–5 on
  documentation; tooling maturity; manual steps; debugging burden; dependency fragility;
  reproducibility; portability (Apple Silicon → GCP x86); serving operational complexity.
- Dated contemporaneous setup logs per model per phase; scores assigned from the log. Objective
  counters beside the scores (steps, manual interventions, distinct errors, time to first
  end-to-end run, extra dependencies, glue-code lines, deployable artifact count).
- ≥ 2 independent raters (IDs only), median/range/disagreement reported. Bias controls:
  one rater who didn't build the baseline follows its written recipe on a clean machine; fixed
  setup order; same time-box per candidate, with "not achieved" recorded as a result. Used only to
  rank candidates that are otherwise comparable.

---

## 7. Pre-registered decision rules (Gate 1)

All must hold for a candidate to be recommended. **Numbers are carried over from the triage plan
as a proposal (D3); the justification must be re-argued for this task and the values frozen in
`gates.yaml` before any Stage 2 run.**

**Primary family — all must hold to recommend (frozen in `gates.yaml`):**

| Criterion | Rule |
|---|---|
| Format validity (full-contract candidates) | strict format pass ≥ 99% on test at greedy decoding |
| Classification, non-inferiority | paired-bootstrap 95% CI lower bound of (candidate − B0) `classification` accuracy **> −5 points** |
| Grounding (full-contract only) | grounding-clean rate not lower than B0's by more than the margin, **and** invented figures on the abstention slice not above B0's count |
| Safety 1 — critical misroute | count of gold `hazard_report` or `complaint` predicted as `leave_policy` or `hiring_request` **not higher than B0's** (exact paired test; any increase → manual row review) |
| Safety 2 — under-urgency | count of gold `high` urgency predicted not-`high` **not higher than B0's** (same procedure) |
| Resource | still ≥ 2× on memory and p95 latency after fine-tuning (untrained models: at their real prompt length) |

**Secondary endpoints — pre-registered, reported with Holm-corrected CIs, do not gate on their own:**

| Endpoint | Non-inferiority reference |
|---|---|
| Urgency QWK | CI lower bound of (candidate − B0) QWK **> −δ_u**, where **δ_u = half-width of the 95% bootstrap CI of the human–human QWK on the blind pilot subset**, rounded down to 0.01, floored at 0.02 (D3′). Model QWK is always shown against the human–human ceiling; a model at or above the ceiling is *saturated*, and further differences are not interpretable |
| `resolution` accuracy | same −5-point rule as classification |

A candidate found **inferior** on a secondary endpoint is still recommendable on the primary
family, but the verdict must state the inferiority as a caveat — the recommendation text cannot
omit it. Within-one urgency and MAE are descriptive.

Any increase on a safety count triggers manual review of those rows regardless of aggregate score.
Three-way outcome: **non-inferior** (CI lower bound > −5), **inferior** (CI upper bound < 0 *and*
point estimate ≤ −5), otherwise **inconclusive** → enlarge test set / add CV and re-run; never call
inconclusive a win or loss.

Rationale to re-argue for this task (carry reasoning into the methods section):

- **5-point margin (classification, `resolution`)**: the largest loss accepted in exchange for the
  saving. For a routing aid whose output a human reviews it is tolerable; classification is the
  least subjective, most checkable label, which is why it carries the primary endpoint. Must stay
  no tighter than the test set's resolvable noise (re-derive from pilot data, §4 item 4).
- **Urgency margin from the data, not by fiat**: a margin smaller than the labels' own noise
  cannot be verified, and a larger one is arbitrary. Anchoring δ_u to the human–human CI
  half-width states exactly "we cannot distinguish differences smaller than what two humans
  disagree by". It is computed from the pilot blind subset and frozen before Stage 2.
- **Why urgency and `resolution` are secondary**: the primary family already contains an
  all-must-pass rule; adding noisy, correlated fields as gates would shrink power and encourage
  selecting margins after the fact. Declaring the hierarchy in advance, with caveats mandatory,
  keeps the paper honest without making the recommendation hostage to label noise.
- **2× resource gate**: unchanged reasoning — below ~2× is inside run-to-run and dev-vs-prod drift
  and would not change which instance size is viable; both memory and latency must pass.
- The safety rules replace the triage "under-triage" rule; they are stated as counts relative to
  B0 because average accuracy can hide a worse miss rate on the costly cells.

---

## 8. Stage 3 — production-representative validation

1. Run the benchmark inside a container on **x86-64 Linux CPU** (Cloud Build / small GCE VM /
   Cloud Run job — not an arm64 Mac under emulation) at 4 vCPU / 16 GiB, and at the smaller shape
   the candidate would permit (e.g. 2 vCPU / 4 GiB; the old Phi-3.5 pipeline hit OOM-kills at
   4 GiB, and Phi-4-mini's 200k vocabulary makes the embedding/output matrix larger — measure, don't
   assume).
2. Check ratios, not absolutes: do dev-machine candidate/B0 ratios hold (≥ 2×)? Report drift.
3. Real cold start (`min-instances=0`): container start → first handled request through an HTTP
   endpoint, baseline vs candidate; record memory utilisation and billable time.
4. End-to-end contract smoke test: a thin HTTP endpoint wrapping the model, driven by a seeded
   query set; assert the four fields parse, enums are valid, and the labels-only variant behaves
   (summary `null`). (No dashboard exists for this stand-in task, so this replaces the triage
   dashboard smoke test.)
5. Only then write the recommendation, or the "do not migrate" conclusion.

---

## 9. Paper structure and validity

Outline: (1) motivation — small models for routing-and-reply tasks; (2) task and output contract
(policy-in-prompt design); (3) dataset construction and held-out protocol; (4) candidates, controls
and the untrained arm; (5) benchmark methodology; (6) results — resource table, quality table,
Pareto plot (pass rate vs p95 vs peak RSS), safety analysis, untrained-vs-fine-tuned, dev-vs-prod;
(7) threats to validity; (8) reproducibility package.

Threats to validity:

- Fully synthetic, small, single-team-authored data, and a stand-in task: results show the method
  and in-distribution behaviour, not fitness for real HR use or any real policy.
- Policy retrieval is given, not tested; real systems also err in retrieval.
- Label subjectivity (urgency especially) — κ reported separately per field.
- Machine-drafted test labels; the drafter (Sonnet 5.5) is the same family as the frontier reference (Opus 5.5), so the Opus row may be flattered — diagnosed by the accepted/edited/blind split (§4 item 4, §5.1); the frontier row depends on a hosted model that may change under the same name and is not deterministic.
- Setup-effort score is subjective and familiarity-dependent; supporting evidence only.
- Runtime/quantisation confounds across families (§3.4); few-shot prompt-length confound (§5).
- Test-set size limits resolvable effect sizes.
- Fine-tune times and dev memory come from one 16 GB laptop (thermals, other load, framework differences); they describe that pipeline, not the architectures in general (§3.4b).
- One encoder (DistilBERT), one encoder-decoder (BART) and one hybrid (LFM2) each stand for a whole family; no within-family scaling result (D13).
- Not legal or HR advice; the synthetic policy is invented and says nothing about real entitlements.

Reproducibility package: lockfiles, container digest, dataset and policy-corpus hashes, split file,
benchmark script, raw rows and per-example predictions, seeds, hardware fingerprint, model-card and
licence notes (Phi-4-mini: MIT, confirmed; LFM2: LFM Open License v1.0, terms still to read; Gemma, if used: custom terms; BART / DistilBERT: Apache-2.0 from memory, confirm). Repo hygiene per
`CLAUDE.md`: no participant names or contact details; no references to the internal validation
project; confirm base-model licences before releasing weights.

---

## 10. Decisions

| # | Decision | Status |
|---|---|---|
| D1 | Candidates that cannot generate text | **Decided (generalised):** labels-only contract for encoders; `summary = null` |
| D2 | Test-set authoring | **Decided:** machine-drafted, human-verified, blind-label anchoring audit; drafter = Claude Sonnet 5.5, never an evaluated model; same-family-as-R-frontier bias documented and diagnosed (§5.1) |
| D3 | 5-point margin and 2× gate | **Carried over as proposal; re-argue for this task and freeze in `gates.yaml`** (see D3′) |
| D3′ | Urgency margin | **Decided (this revision):** QWK endpoint; δ_u from the human–human QWK CI on the blind pilot subset (§7); ceiling always shown. Numeric value frozen in `gates.yaml` after the pilot |
| D4 | ~1B decoder must differ structurally from baseline | **Decided; re-checked** against Phi-4-mini (§3.3): Llama-3.2/Qwen ~1B no longer qualify |
| D5 | Environments | **Decided:** Apple Silicon (dev + fine-tuning timing), then GCP x86-64 CPU (Stage 3) |
| D6 | Baseline | **Decided:** Phi-4-mini-instruct, newly fine-tuned; Phi-4 14B not run (D13). Revisit if the target moves off 4 vCPU CPU |
| D7 | Policy handling | **Decided:** policy text in the input for all models (option 1); retrieval given |
| D8 | `next_step` design | **Decided (this revision):** model emits `resolution` ∈ {answer_from_policy, escalate_to_human, ask_clarification}; destination queue derived in code from `classification` (§1.1). Avoids a redundant label that would double-count class errors |
| D9 | Untrained models | **Decided:** include Stage Z with instruct variants, zero/few-shot, plus a frontier reference |
| D15 | Frontier reference | **Decided (this revision):** Claude Opus 5.5 (`claude-opus-5-5`), zero- and few-shot with the same frozen prompts and rendered input as Stage Z, 3 repeats, reference-only (not gated), cost and latency on a separate axis (§5.1) |
| D14 | Hardware constraint | **Decided:** all fine-tuning and dev-side benchmarking on one MacBook Pro, 16 GB unified memory (Apple M2 Pro, confirmed); GCP x86 CPU for Stage 3 serving validation only. Consequences in §3.4b |
| D12 | Candidate D | **Decided:** `LiquidAI/LFM2-1.2B` (hybrid conv + attention); `google/gemma-3-1b-it` is the fallback. Subject to the Stage 0 LoRA/GGUF smoke test and a read of the licence terms |
| D13 | Dropped models | **Decided:** `google-bert/bert-base-uncased` (C′) and `microsoft/phi-4` (R-big) are removed; encoder family = DistilBERT only |
| D10 | Test annotation | **Decided (this revision):** two independent annotators on every test row, logged adjudication; ≥ ⅓ blind subset labelled by both gives the unanchored human–human ceiling (§4 item 4) |
| D11 | Endpoints | **Decided (this revision):** primary family = format, classification accuracy, two safety counts, grounding, resource gate; secondary = urgency QWK, `resolution` accuracy; joint pass rate descriptive only (§6, §7) |

---

## 11. Todos

**Verify first (Stage 0, step 0)** — none of this has been checked in this repo yet
- [ ] `mlx_lm.lora` 20-step smoke test on Phi-4-mini-instruct; GGUF convert → Q4_K_M → load round trip; confirm existing Cloud Build/Docker path still works with the 200k vocab
- [ ] Record core counts (CPU/GPU), RAM and macOS version for the M2 Pro; read the Metal working-set limit from MLX device info; verify the peak-memory API names for the installed `mlx` and PyTorch
- [ ] B0 smoke test: bf16 LoRA with `--grad-checkpoint`, batch 1–2 — does it fit? Measure s/step, peak memory, swap; fall back to QLoRA if not; fix one precision for B0 and D
- [ ] LFM2-1.2B: 20-step `mlx_lm.lora` smoke test, GGUF round trip, read the LFM Open License v1.0 terms (fallback Gemma-3-1B-it: same checks)
- [ ] Smoke-test DistilBERT and BART fine-tuning on macOS (MPS and CPU); test ONNX export of BART and CTranslate2 conversion; choose serving runtimes (ONNX int8 / CTranslate2)

**Stage 1**
- [ ] Write the label rules: precedence, `other_unclear`, urgency calibration, class→route table (`routing_table.json`), `resolution` gold rule
- [ ] Author the policy corpus (clause IDs, SHA-256) and `hr_query_examples.csv`
- [ ] Canonical render function; generator script with round-trip validation
- [ ] Persist stable stratified split
- [ ] Draft test rows with Claude Sonnet 5.5 (committed prompt; record ID/date/version per row); keep it out of every evaluated arm; hand-write ≥ 20% of rows with no draft; log every correction; compute per-annotator accept/edit/reject rates; human verify; two annotators on every row; adjudication log; blind ≥ ⅓ subset labelled by both; κ / QWK with CIs per field
- [ ] Held-out-clause and abstention slices; freeze test (SHA-256); ≥ 150 rows, target set from pilot disagreement rate
- [ ] Leakage tests in CI (incl. clause-ID holdout)
- [ ] Strict grader incl. grounding check + contract tests
- [ ] `benchmark_model.py`, `compare_rows.py`, determinism test
- [ ] Fine-tune and reproduce the B0 row; add controls (trivial, summary-copy, quantisation)
- [ ] Pilot annotation → compute human–human QWK CI → fix δ_u; commit `gates.yaml` **before** any Stage 2 run

**Stage 0 / Stage Z**
- [ ] Benchmark B0, A, C, D (resource only), 3 repeats; apply Gate 0
- [ ] Freeze prompts; choose few-shot examples from train; run Phi-4-mini-instruct and D zero/few-shot (k = 3, 8) on test
- [ ] R-frontier (Claude Opus 5.5): confirm API access and budget; run zero-shot, k = 3, k = 8 on test × 3 repeats with the frozen prompts; record tokens, cost per 1,000 requests and network latency; compute break-even volume vs the local model

**Reduce confounding**
- [ ] Per-family best recipe and best serving architecture, chosen on valid; equal tuning budget; baseline gets the same protocol
- [ ] Report both tuned-best and controlled-setting comparisons

**Setup-effort**
- [ ] `setup_rubric.md` before first setup; dated logs; fixed order and time-box; two raters; clean-machine rater for baseline; `setup` block in rows

**Stage 2 / 3 / paper**
- [ ] Fine-tune A, C, D and re-train B0, 3 seeds each with `train_timer.py`; single test pass per final config
- [ ] Gate 1 verdicts (non-inferior / inferior / inconclusive), Holm-corrected
- [ ] Provision GCP x86-64 CPU (4 vCPU / 16 GiB and the smaller shape); rerun everything; Stage 3 checks
- [ ] Confirm model and data licences before releasing weights
- [ ] Draft the paper (§9) and reproducibility package

## 12. Files this plan will add (none exist yet)

```
backend/eval/benchmark_model.py   backend/eval/grader.py     backend/eval/compare_rows.py
backend/eval/train_timer.py       backend/eval/setup_rubric.md   backend/eval/gates.yaml
backend/eval/routing_table.json  backend/eval/backends/   backend/tests/test_eval_*.py   results/ (rows, predictions, setup_logs/)
backend/data/hr_policy_corpus.json   backend/data/hr_query_examples.csv   backend/data/hr_query_splits.json
backend/data/hr_query_test/test.jsonl   backend/data/hr_query_test.csv
backend/scripts/generate_hr_query_dataset.py   backend/scripts/train_hf_candidate.py
```
