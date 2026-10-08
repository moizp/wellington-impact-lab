# Paper skeleton — small models for routing-and-reply tasks

> **Skeleton only.** Headings and prompt bullets to refine later. Nothing here is a result: no
> experiment has been run. Section references (§) point to `docs/paper_plan.md`. Working title is
> a placeholder.

**Working title:** *When is a small model enough? Fine-tuned and untrained candidates for
policy-grounded query routing on CPU*

---

## Abstract

- Problem: routing + reply drafting for policy-grounded queries; CPU-only deployment constraint
- Compared: fine-tuned Phi-4-mini-instruct baseline vs smaller fine-tuned models vs untrained instruct models
- Method: one repeatable benchmark (memory, latency, quality, fine-tune time, setup effort), pre-registered gates
- Headline result: *(fill after Stage 2/3)*
- Caveat: synthetic stand-in task; in-distribution only

## 1. Introduction

- Motivation: organisations route free-text queries to the right team and draft a first reply
- The cost question: does a 3.8B model justify its footprint when a smaller or untrained model might do?
- Why CPU-only matters (cost, scale-to-zero, data residency)
- Gap: model comparisons often skip memory/latency, fine-tune cost, and setup effort together
- Research question (§ research question)
- Contributions
  - policy-in-prompt, mechanically gradable task design
  - single benchmark covering resources, quality, training time and structured setup effort
  - pre-registered non-inferiority + safety rules
  - untrained-vs-fine-tuned comparison under identical inputs
  - released dataset, policy corpus, harness

## 2. Related work

- Small / distilled models vs LLMs for text classification
- Parameter-efficient fine-tuning (LoRA/QLoRA) and quantisation (GGUF)
- Zero/few-shot instruct models vs fine-tuning for classification
- Grounded generation and hallucination in policy / enterprise QA
- LLM serving benchmarks and efficiency reporting; non-inferiority testing in ML evaluation
- Inter-annotator agreement for subjective ordinal labels

## 3. Task and output contract

- Input: HR-style query + supplied policy clause(s) (retrieval given, not tested)
- Outputs: `classification` (5 classes), `urgency` (3 ordinal), `resolution` (3), `summary`
- Route derived deterministically from `classification` (not model output)
- Label rules: one label per query, precedence, `other_unclear`, urgency calibration, `resolution` gold rule
- Strict mechanical grader: format, semantic, grounding (numbers must appear in the clause)
- Why prose quality is not graded; labels-only contract for encoder models

## 4. Data

- Synthetic policy corpus (clause IDs, hashes)
- Training/validation CSV, stable stratified split
- Test set: newly authored, machine-drafted then human-verified; held-out-clause and abstention slices
- Annotation: two annotators on every row, adjudication log, blind subset for unanchored ceiling
- Agreement statistics (κ / QWK with CIs); size and power reasoning
- Leakage tests; frozen by hash

## 5. Candidates and controls

- Baseline: Phi-4-mini-instruct, newly fine-tuned, Q4_K_M
- Smaller fine-tuned: bart-base (full contract); distilbert (+ bert-base ablation), labels-only
- Optional ~1B decoder, architecturally different from the baseline (Gemma-3-1B / LFM2)
- Untrained arm: instruct models, zero- and few-shot; frontier reference (quality ceiling only)
- Reference: Phi-4 14B (resource/scale argument, not a candidate)
- Controls: majority, keyword, TF-IDF + LR, class-only rules, summary-copy, quantisation ablation

## 6. Methodology

### 6.1 Benchmark harness

- One script, one row schema; process-isolated memory sampling; greedy decoding, fixed seeds
- Phases: load, cold start, warm, timed; CPU primary, Metal secondary
- Recorded confounds: backend/runtime, quantisation, prompt length

### 6.2 Fine-tuning protocol

- Same split, same rendered inputs, equal tuning budget, 3 seeds
- Per-family best recipe and best serving architecture, chosen on validation only
- Fine-tune time measured identically across frameworks

### 6.3 Setup-effort evaluation

- Rubric (8 dimensions), contemporaneous logs, objective counters, two raters, bias controls
- Explicitly subjective and never a gate

### 6.4 Pre-registered decisions and statistics

- Staged gates (resource screen → quality → production-like)
- Primary family: format, classification non-inferiority, safety counts, grounding, resources
- Secondary: urgency QWK (margin from human–human CI), `resolution` accuracy
- Paired bootstrap, McNemar / exact paired tests, Holm correction, seed variance
- Three-way verdict: non-inferior / inferior / inconclusive

## 7. Results *(placeholders)*

- 7.1 Resource table (memory, latency, cold start) with ratios to baseline
- 7.2 Quality table with CIs; comparison to the human–human ceiling
- 7.3 Safety analysis: critical misroutes, under-urgency
- 7.4 Grounding and abstention behaviour
- 7.5 Untrained vs fine-tuned: what fine-tuning buys; few-shot cost in latency
- 7.6 Pareto plot: pass rate vs p95 latency vs peak memory
- 7.7 Fine-tune cost and setup-effort ratings
- 7.8 Dev (Apple Silicon) vs production-like (x86 CPU) validation and drift
- 7.9 Ablations: quantisation, runtime, encoder capacity, robustness perturbations

## 8. Discussion

- Which candidate (if any) meets the gates, and under which constraints
- Where fine-tuning is and isn't worth its cost
- What the runtime/quantisation confounds do and don't allow us to claim
- Practical guidance: choosing a model size for CPU-only routing tasks

## 9. Threats to validity and limitations

- Synthetic, small, single-team data; stand-in task; in-distribution only
- Retrieval given, not tested
- Subjective urgency labels; ceiling set by annotator agreement
- Machine-drafted labels and anchoring; drafter-vs-evaluated-model separation
- Subjective, familiarity-dependent setup ratings
- Runtime and prompt-length confounds; test-set size limits
- Not HR or legal advice; invented policy

## 10. Ethics and responsible release

- No real personal data; synthetic by design
- Licence checks for base models and any released weights
- Intended use and misuse notes (workflow aid with human review, not an automated decision-maker)

## 11. Conclusion

- Restate the question, the answer, and the conditions under which it holds
- Future work: real data, retrieval in the loop, larger label sets, other tasks

## Appendices

- A. Full prompts, output contract and routing table
- B. Label rules and annotation guidelines
- C. Policy-corpus and dataset statistics
- D. Gate definitions (`gates.yaml`) and their pre-registration commit
- E. Per-seed and per-class results; confusion matrices
- F. Setup-effort rubric, logs and rater disagreement
- G. Reproducibility package: lockfiles, container digest, hashes, hardware fingerprint

## Open items before drafting

- Fix numeric gate values after the pilot annotation (δ_u, test-set size)
- Choose target venue (affects length and required checklists)
- Decide what is released (data, harness, weights) subject to licences
