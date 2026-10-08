"""Output contract and canonical render for the HR-query task.

Single source of truth, shared by dataset generation, every model adapter and the grader: the
same functions that build training text must build evaluation prompts (docs/paper_plan.md 1.3),
or train/serve drift hides in hand-typed copies.
"""

import json
import os

CLASSES = ("leave_policy", "complaint", "hazard_report", "hiring_request", "other_unclear")
URGENCIES = ("low", "medium", "high")
RESOLUTIONS = ("answer_from_policy", "escalate_to_human", "ask_clarification")

# The two classes whose misrouting is the costly error (paper_plan.md 7, Safety 1).
COSTLY_CLASSES = ("hazard_report", "complaint")
MISROUTE_TARGETS = ("leave_policy", "hiring_request")

_ROUTING_PATH = os.path.join(os.path.dirname(__file__), "routing_table.json")


def load_routing_table() -> dict:
    with open(_ROUTING_PATH) as f:
        table = json.load(f)
    return {k: v for k, v in table.items() if not k.startswith("_")}


ROUTING_TABLE = load_routing_table()


def route_for(classification: str) -> str | None:
    return ROUTING_TABLE.get(classification)


SYSTEM_PROMPT = (
    "You are an HR helpdesk triage assistant. You are given a short list of policy clauses "
    "and an employee's query. Classify the query, judge its urgency, choose a resolution, and "
    "write a one-to-two-sentence recommended response.\n"
    "Use only the policy clauses provided. Never state a number, duration or date that does not "
    "appear in them. If the clauses do not answer the question, do not guess: choose "
    "escalate_to_human or ask_clarification and state no figures.\n"
    "Respond only in this exact format, four lines, nothing else:\n"
    "Classification: <leave_policy|complaint|hazard_report|hiring_request|other_unclear>\n"
    "Urgency: <low|medium|high>\n"
    "Resolution: <answer_from_policy|escalate_to_human|ask_clarification>\n"
    "Summary: <one or two sentences>"
)

LABEL_PREFIXES = ("Classification: ", "Urgency: ", "Resolution: ", "Summary: ")


def build_user_message(query: str, clauses: list[tuple[str, str]]) -> str:
    """Canonical user message: policy clauses (id, text) then the query."""
    lines = ["Policy clauses:"]
    lines += [f"[{cid}] {text}" for cid, text in clauses]
    lines += ["", "Employee query:", query]
    return "\n".join(lines)


def format_output(classification: str, urgency: str, resolution: str, summary: str | None = None) -> str:
    """Canonical model output (training target / few-shot answer). Omit summary for labels-only."""
    out = [
        f"Classification: {classification}",
        f"Urgency: {urgency}",
        f"Resolution: {resolution}",
    ]
    if summary is not None:
        out.append(f"Summary: {summary}")
    return "\n".join(out)


def clause_texts(example: dict, corpus: dict) -> list[tuple[str, str]]:
    return [(cid, corpus[cid]) for cid in example["clause_ids"]]


def render_example(example: dict, corpus: dict) -> tuple[str, str]:
    """(system, user) for one example."""
    return SYSTEM_PROMPT, build_user_message(example["query"], clause_texts(example, corpus))


def gold_output(example: dict, contract: str = "full") -> str:
    summary = example["reference_summary"] if contract == "full" else None
    return format_output(example["classification"], example["urgency"], example["resolution"], summary)
