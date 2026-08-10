"""Clarifier — one model, two distinct inference calls, task-conditioned via
a different system prompt per call (see FINETUNE_PLAN.md "Model 1 —
Clarifier" for the full design and its known limitation).

Fine-tuned model wired in: a Phi-3.5-mini-instruct LoRA (iter 200 checkpoint,
picked from validation-loss trend, not the final iter 500) fused and
quantized (Q4_K_M) via the pipeline in BUILD_PLAN.md "Validated model
build/deploy pipeline", loaded in-process via llama-cpp-python — the same
GGUF artifact and runtime path used in the Cloud Run deployment, so local
dev and production never diverge. See _get_llm() below for the model path.

Call 1 ("ask"): raw report only -> a clarifying question. Always produced,
not conditional on the message being ambiguous — runs on every submission.

Call 2 ("act"): raw report + Call 1's question + the submitter's answer ->
1-2 action items, drawn from ACTION_VOCABULARY. This combines non-critical
suggestions (e.g. check_neighbours) with safety-critical ones (call_111,
evacuate) into one vocabulary for the hackathon build — a deliberate
simplification, not the intended long-term design. Call 2 never sees official
context or the Triage Classifier's severity/rationale, since it runs before
the poller/aggregation/triage step — see FINETUNE_PLAN.md's limitation note.
A dedicated third model informed by official corroboration is the roadmap
item for moving high-stakes actions off this call (see PITCH.md's roadmap).

clarified_text is NOT produced by either call — build_clarified_text() below
is a deterministic concatenation, since stitching raw_text + answer together
involves no judgement call (same discipline that keeps hazard_type
deterministic rather than LLM-produced — see context.py).
"""

import os

from llama_cpp import Llama

_MODEL_PATH = os.environ.get(
    "CLARIFIER_MODEL_PATH",
    os.path.join(os.path.dirname(__file__), "..", "models", "clarifier-q4km.gguf"),
)
_llm: Llama | None = None


def _get_llm() -> Llama:
    # Lazy singleton — loaded once on first call, not at import time, so
    # importing this module (e.g. for tests) never requires the model file.
    global _llm
    if _llm is None:
        _llm = Llama(model_path=_MODEL_PATH, n_ctx=2048, verbose=False)
    return _llm


ACTION_VOCABULARY = {
    "check_neighbours",
    "monitor_situation",
    "document_further",
    "call_111",
    "evacuate",
    "none",
}

SYSTEM_PROMPT_ASK = (
    "You are helping a member of the public report a possible hazard to Wellington City "
    "Council. Given their report, ask one targeted follow-up question that would help a "
    "human triage operator understand the situation better. Always ask a question, even if "
    "the report already sounds fairly complete — in that case, ask a light, brief "
    "confirmatory question rather than inventing a gap. Respond only in this exact format:\n"
    "Question: <your question>"
)

SYSTEM_PROMPT_ACT = (
    "You are helping a member of the public who has just reported a possible hazard to "
    "Wellington City Council and answered a follow-up question about it. Based on the report "
    "and their answer, suggest 1-2 concrete next steps for them, chosen only from this list: "
    "check_neighbours, monitor_situation, document_further, call_111, evacuate, none. You do "
    "not have access to official warning data — base your suggestion only on what the report "
    "and answer describe. Respond only in this exact format:\n"
    "Actions: <action1>[, <action2>]"
)


def ask(raw_text: str) -> str:
    """Call 1. Returns the clarifying question."""
    raw_output = _stub_generate_ask(raw_text)
    return parse_ask_output(raw_output)


def act(raw_text: str, question: str, answer: str) -> list[str]:
    """Call 2. Returns 1-2 action items from ACTION_VOCABULARY."""
    raw_output = _stub_generate_act(raw_text, question, answer)
    return parse_actions_output(raw_output)


def build_act_user_message(raw_text: str, question: str, answer: str) -> str:
    """The exact Call 2 user-message assembly. Must be used identically for
    training data and live serving (same discipline as
    classifier.build_user_message())."""
    return f"{raw_text}\n\nQuestion: {question}\nAnswer: {answer}"


def build_clarified_text(raw_text: str, answer: str) -> str:
    """Deterministic — not a model call. See module docstring."""
    return f"{raw_text}\n\n{answer}"


def parse_ask_output(text: str) -> str:
    for line in text.strip().splitlines():
        if line.lower().startswith("question:"):
            return line.split(":", 1)[1].strip()
    return "Can you tell us more about what you're seeing?"


def parse_actions_output(text: str) -> list[str]:
    for line in text.strip().splitlines():
        if line.lower().startswith("actions:"):
            values = line.split(":", 1)[1].strip()
            actions = [v.strip().lower() for v in values.split(",") if v.strip()]
            valid = [a for a in actions if a in ACTION_VOCABULARY]
            if valid:
                return valid[:2]
    return ["none"]


def _stub_generate_ask(raw_text: str) -> str:
    # Same messages shape used to build the training data (see
    # scripts/generate_clarifier_dataset.py's build_ask_example()) — the
    # GGUF's baked-in chat template applies the identical formatting
    # mlx_lm used during fine-tuning, so this must stay in sync with that.
    completion = _get_llm().create_chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_ASK},
            {"role": "user", "content": raw_text},
        ],
        max_tokens=60,
        temperature=0.2,
    )
    return completion["choices"][0]["message"]["content"]


def _stub_generate_act(raw_text: str, question: str, answer: str) -> str:
    # Mirrors build_act_example() in scripts/generate_clarifier_dataset.py.
    completion = _get_llm().create_chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_ACT},
            {"role": "user", "content": build_act_user_message(raw_text, question, answer)},
        ],
        max_tokens=60,
        temperature=0.2,
    )
    return completion["choices"][0]["message"]["content"]
