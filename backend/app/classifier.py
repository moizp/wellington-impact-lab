"""Triage Classifier — severity + rationale only, nothing else (see
BUILD_PLAN.md "System summary" and FINETUNE_PLAN.md "Model 2").

Fine-tuned model wired in: a Phi-3.5-mini-instruct LoRA (iter 100 checkpoint —
picked from validation-loss trend on the team-corrected dataset; val loss
climbed monotonically from iter 100 onward, iter 100 was the clear best),
fused and quantized (Q4_K_M), loaded in-process via llama-cpp-python — same
GGUF artifact and runtime path as the Clarifier, so local dev and Cloud Run
never diverge. See _get_llm() below for the model path.

This module is the single source of truth for the Triage Classifier's
instruction contract (see FINETUNE_PLAN.md "Instruction contract" for the
full writeup) — SYSTEM_PROMPT and build_user_message() must be used
identically by the dataset-generation script and by the real model call once
it exists, or training and serving will silently drift apart.

DECIDED output format (this was an explicitly open question — now settled):
mirrors the OIA project's proven fixed-template pattern (e.g. "Agency: [name]")
— simple, deterministic to parse, no JSON-parsing fragility with a small
fine-tuned model:

    Severity: <low|medium|high>
    Rationale: <one sentence>

parse_triage_output() is what the real model's raw text response gets passed
through. The stub below produces output in the same shape, so main.py's
calling code doesn't change when the real model is wired in — only
_stub_generate() gets replaced with an actual model call.
"""

import os

from llama_cpp import Llama

_MODEL_PATH = os.environ.get(
    "CLASSIFIER_MODEL_PATH",
    os.path.join(os.path.dirname(__file__), "..", "models", "triage-q4km.gguf"),
)
_llm: Llama | None = None


def _get_llm() -> Llama:
    # Lazy singleton — loaded once on first call, not at import time, so
    # importing this module (e.g. for tests) never requires the model file.
    global _llm
    if _llm is None:
        _llm = Llama(model_path=_MODEL_PATH, n_ctx=2048, verbose=False)
    return _llm


VALID_SEVERITIES = {"low", "medium", "high"}

SYSTEM_PROMPT = (
    "You are an emergency information triage assistant for Wellington City Council. "
    "You are given a public report about a possible hazard, along with any relevant "
    "official warning data and any related recent public report for the same location. "
    "Judge how serious this report is and explain your reasoning in one sentence. "
    "Respond only in this exact format:\n"
    "Severity: <low|medium|high>\n"
    "Rationale: <one sentence>"
)


def build_user_message(report_text: str, context_text: str) -> str:
    """The exact user-message assembly — report text, then a blank line, then
    the context render (see context.render_context_text()). Must be used
    identically for training data and live serving."""
    return f"{report_text}\n\n{context_text}"


def triage(clarified_text: str, context_text: str) -> tuple[str, str]:
    """Returns (severity, rationale)."""
    raw_output = _stub_generate(clarified_text, context_text)
    return parse_triage_output(raw_output)


def parse_triage_output(text: str) -> tuple[str, str]:
    severity = "medium"
    rationale = ""
    for line in text.strip().splitlines():
        lowered = line.lower()
        if lowered.startswith("severity:"):
            value = line.split(":", 1)[1].strip().lower()
            if value in VALID_SEVERITIES:
                severity = value
        elif lowered.startswith("rationale:"):
            rationale = line.split(":", 1)[1].strip()
    if not rationale:
        rationale = "No rationale produced."
    return severity, rationale


def _stub_generate(clarified_text: str, context_text: str) -> str:
    # Same messages shape used to build the training data — see
    # scripts/generate_triage_dataset.py's build_example(). The GGUF's baked-
    # in chat template applies the identical formatting mlx_lm used during
    # fine-tuning, so this must stay in sync with that.
    completion = _get_llm().create_chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(clarified_text, context_text)},
        ],
        max_tokens=80,
        temperature=0.2,
    )
    return completion["choices"][0]["message"]["content"]
