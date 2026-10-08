"""Trivial controls (docs/paper_plan.md 3.5). They cost nothing, need no model, and bound what
a real model has to beat. `oracle` reads gold labels and exists only to prove the pipeline
scores a perfect answer as perfect."""

import re

from ..contract import CLASSES, format_output
from . import Backend, Generation

# NOTE: these keyword lists were written while looking at the harness fixtures, so the control
# scores suspiciously well on them. For the real benchmark, rebuild the lists from the TRAIN
# split only, never from the test set (docs/paper_plan.md 3.5).
_KEYWORDS = {
    "hazard_report": ("wire", "flood", "slip", "spill", "fire", "hazard", "unsafe", "trip", "broken", "injur", "cable", "light", "exit"),
    "complaint": ("complain", "harass", "bully", "bullies", "shout", "inappropriate", "unfair", "touched", "discriminat"),
    "hiring_request": ("hire", "hiring", "recruit", "vacancy", "advertise", "fixed-term", "role", "resign"),
    "leave_policy": ("leave", "sick", "parental", "holiday", "off ", "flexible", "paperwork"),
}
_HIGH = ("immediately", "already", "unsafe", "live wire", "touched", "do not feel safe", "shouting", "bully", "flooded", "resigned", "fire exit")
_MEDIUM = ("monday", "this week", "next week", "pending", "tomorrow", "yesterday", "unfair", "week")


def _first_sentence(text: str) -> str:
    m = re.match(r"(.+?[.!?])(\s|$)", text.strip())
    return m.group(1) if m else text.strip()


class Oracle(Backend):
    name = "controls:oracle"
    needs_example = True
    uses_gold = True

    def generate(self, system, user, shots=None, example=None, max_new_tokens=160):
        e = example
        return Generation(format_output(e["classification"], e["urgency"], e["resolution"], e["reference_summary"]))


class Majority(Backend):
    """Always the most common label seen in a training file (or fixed defaults)."""

    name = "controls:majority"

    def __init__(self, train_rows=None, **_):
        from collections import Counter
        rows = train_rows or []
        pick = lambda key, default: Counter(r[key] for r in rows).most_common(1)[0][0] if rows else default
        self.c, self.u, self.r = pick("classification", CLASSES[0]), pick("urgency", "low"), pick("resolution", "escalate_to_human")

    def generate(self, system, user, shots=None, example=None, max_new_tokens=160):
        return Generation(format_output(self.c, self.u, self.r, "Please contact the HR service desk."))


class Keyword(Backend):
    """Keyword rules over the query only; summary = first sentence of the first clause
    (the 'summary-copy' control: shows what a trivial strategy scores on grounding)."""

    name = "controls:keyword"
    needs_example = True  # reads the public query and clause text, never gold

    def generate(self, system, user, shots=None, example=None, max_new_tokens=160):
        q = example["query"].lower()
        cls = "other_unclear"
        for c in ("hazard_report", "complaint", "hiring_request", "leave_policy"):  # precedence rule
            if any(k in q for k in _KEYWORDS[c]):
                cls = c
                break
        urg = "high" if any(k in q for k in _HIGH) else "medium" if any(k in q for k in _MEDIUM) else "low"
        res = "ask_clarification" if cls == "other_unclear" else "escalate_to_human" if cls in ("hazard_report", "complaint") or urg == "high" else "answer_from_policy"
        clause_block = user.split("\n\nEmployee query:")[0]
        first = next((l for l in clause_block.splitlines()[1:] if l.startswith("[")), "")
        summary = _first_sentence(re.sub(r"^\[[^\]]+\]\s*", "", first)) or "Please contact the HR service desk."
        return Generation(format_output(cls, urg, res, summary))


def make_control(name: str, train_rows=None, **_):
    if name == "oracle":
        return Oracle()
    if name == "majority":
        return Majority(train_rows)
    if name == "keyword":
        return Keyword()
    raise ValueError(f"unknown control {name!r}; choose oracle, majority or keyword")
