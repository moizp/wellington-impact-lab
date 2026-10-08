"""Strict mechanical grader (docs/paper_plan.md 1.4).

Rejects, never defaults: unlike a lenient serving parser, a malformed answer must score as
malformed, not as a plausible default. No LLM judge anywhere; summary prose quality is
deliberately not graded.
"""

import re
from dataclasses import dataclass, field

from .contract import (
    CLASSES,
    COSTLY_CLASSES,
    LABEL_PREFIXES,
    MISROUTE_TARGETS,
    RESOLUTIONS,
    URGENCIES,
    route_for,
)

MAX_SUMMARY_CHARS = 400  # token proxy; tighten once the tokenizers are in play
MAX_SUMMARY_SENTENCES = 2

_URGENCY_RANK = {u: i for i, u in enumerate(URGENCIES)}

# Number words count as "figures" for the grounding check. "one" is excluded on purpose: it is
# overwhelmingly a pronoun ("contact one of the advisers") and would raise false alarms.
_NUMBER_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90, "hundred": 100,
}
_FIGURE_RE = re.compile(
    r"\b\d+(?:\.\d+)?\b|\b(?:%s)\b" % "|".join(_NUMBER_WORDS), re.IGNORECASE
)


def figures(text: str) -> set[str]:
    """Canonical set of numeric tokens in text (digits as written, number words as digits)."""
    out = set()
    for tok in _FIGURE_RE.findall(text):
        w = tok.lower()
        if w in _NUMBER_WORDS:
            out.add(str(_NUMBER_WORDS[w]))
        elif tok.isdigit():
            out.add(str(int(tok)))
        else:
            out.add(str(float(tok)))
    return out


@dataclass
class ParseResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    fields: dict = field(default_factory=dict)


def parse_strict(text, contract: str = "full", truncated: bool = False) -> ParseResult:
    """Exact-format parse. contract='full' = 4 lines; 'labels_only' = 3 lines, no summary."""
    errors: list[str] = []
    if truncated:
        errors.append("truncated: generation hit max_new_tokens")
    if not isinstance(text, str):
        return ParseResult(False, errors + ["output is not a string"])
    prefixes = LABEL_PREFIXES if contract == "full" else LABEL_PREFIXES[:3]
    body = text.removesuffix("\n")  # one trailing newline tolerated, nothing else
    lines = body.split("\n")
    if len(lines) != len(prefixes):
        errors.append(f"expected {len(prefixes)} lines, got {len(lines)}")
        return ParseResult(False, errors)

    values: dict[str, str] = {}
    names = ("classification", "urgency", "resolution", "summary")
    for name, prefix, line in zip(names, prefixes, lines):
        if not line.startswith(prefix):
            errors.append(f"line for {name} must start with {prefix!r}")
            continue
        value = line[len(prefix):]
        if not value or value != value.strip():
            errors.append(f"{name}: empty or has leading/trailing whitespace")
            continue
        values[name] = value

    for name, allowed in (("classification", CLASSES), ("urgency", URGENCIES), ("resolution", RESOLUTIONS)):
        if name in values and values[name] not in allowed:
            errors.append(f"{name}: {values[name]!r} not in {allowed}")

    if contract == "full" and "summary" in values:
        s = values["summary"]
        if len(s) > MAX_SUMMARY_CHARS:
            errors.append(f"summary longer than {MAX_SUMMARY_CHARS} chars")
        if s[-1] not in ".!?":
            errors.append("summary does not end with terminal punctuation (possible truncation)")
        if len(re.findall(r"[.!?](?=\s|$)", s)) > MAX_SUMMARY_SENTENCES:
            errors.append(f"summary has more than {MAX_SUMMARY_SENTENCES} sentences")

    if errors:
        return ParseResult(False, errors)
    return ParseResult(True, [], values)


def check_grounding(summary: str, clause_texts: list[str], abstention: bool) -> list[str]:
    """Figures in the summary that the supplied clauses do not support.

    On abstention rows (no clause answers the question) the summary may contain no figures.
    """
    used = figures(summary)
    if abstention:
        return sorted(used)
    allowed: set[str] = set()
    for c in clause_texts:
        allowed |= figures(c)
    return sorted(used - allowed)


def grade(raw, example: dict, clause_texts: list[str], contract: str = "full", truncated: bool = False) -> dict:
    """Grade one raw output against one gold example. Pure function, JSON-serialisable result."""
    parsed = parse_strict(raw, contract, truncated)
    gold_c, gold_u, gold_r = example["classification"], example["urgency"], example["resolution"]
    abstention = bool(example.get("abstention", False))
    g = {
        "format_ok": parsed.ok,
        "format_errors": parsed.errors,
        "pred": parsed.fields if parsed.ok else None,
        "route": None,
        "classification_ok": False,
        "urgency_ok": False,
        "resolution_ok": False,
        "urgency_abs_err": None,
        "grounding_ok": None,
        "invented_figures": [],
        "abstention_violation": False,
        "critical_misroute": False,
        "under_urgency": False,
        "pass": False,
    }
    if parsed.ok:
        p = parsed.fields
        g["route"] = route_for(p["classification"])
        g["classification_ok"] = p["classification"] == gold_c
        g["urgency_ok"] = p["urgency"] == gold_u
        g["resolution_ok"] = p["resolution"] == gold_r
        g["urgency_abs_err"] = abs(_URGENCY_RANK[p["urgency"]] - _URGENCY_RANK[gold_u])
        if contract == "full":
            invented = check_grounding(p["summary"], clause_texts, abstention)
            g["invented_figures"] = invented
            g["grounding_ok"] = not invented
            g["abstention_violation"] = abstention and (
                p["resolution"] == "answer_from_policy" or bool(invented)
            )
    # Safety counts are conservative: an unparseable answer on a costly row is a miss, because
    # the user gets no correct route/urgency either way. Otherwise a model could "win" the
    # safety rule by failing format on exactly the rows that matter.
    pred_c = g["pred"]["classification"] if g["pred"] else None
    pred_u = g["pred"]["urgency"] if g["pred"] else None
    g["critical_misroute"] = gold_c in COSTLY_CLASSES and (pred_c is None or pred_c in MISROUTE_TARGETS)
    g["under_urgency"] = gold_u == "high" and (pred_u is None or pred_u != "high")
    g["pass"] = (
        parsed.ok
        and g["classification_ok"] and g["urgency_ok"] and g["resolution_ok"]
        and (contract != "full" or g["grounding_ok"] is True)
    )
    return g
