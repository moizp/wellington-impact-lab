"""Aggregate per-example grades into the `quality` block of a result row
(schema sketch in docs/paper_plan.md 2). Descriptive vs primary vs secondary endpoints are
declared in the plan (D11); this module only computes, it does not decide."""

from .contract import CLASSES, URGENCIES
from .stats import quadratic_weighted_kappa, wilson


def _rate(k: int, n: int) -> dict:
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": (k / n) if n else None, "ci95": [lo, hi]}


def macro_f1(y_true: list[str], y_pred: list[str | None], labels: tuple[str, ...]) -> float | None:
    """Macro-F1; an unparseable prediction (None) is a miss for the true class, a hit for none."""
    f1s = []
    for lab in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p == lab)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != lab and p == lab)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p != lab)
        if tp + fp + fn == 0:
            continue  # class absent from both gold and predictions
        f1s.append(2 * tp / (2 * tp + fp + fn))
    return sum(f1s) / len(f1s) if f1s else None


def urgency_qwk(examples: list[dict], grades: list[dict]) -> tuple[float | None, int]:
    """QWK over parseable rows only; returns (qwk, n_scored). Unparseable rows are reported via
    format_pass, not silently folded into agreement."""
    t, p = [], []
    for e, g in zip(examples, grades):
        if g["pred"]:
            t.append(e["urgency"])
            p.append(g["pred"]["urgency"])
    return quadratic_weighted_kappa(t, p, URGENCIES), len(t)


def aggregate(examples: list[dict], grades: list[dict], contract: str = "full") -> dict:
    n = len(examples)
    assert n == len(grades)
    c = lambda key: sum(1 for g in grades if g[key])
    q: dict = {
        "n": n,
        "contract": contract,
        "format_pass": _rate(c("format_ok"), n),
        "class_acc": _rate(c("classification_ok"), n),
        "urgency_acc": _rate(c("urgency_ok"), n),
        "urgency_within1": _rate(
            sum(1 for g in grades if g["urgency_abs_err"] is not None and g["urgency_abs_err"] <= 1), n
        ),
        "resolution_acc": _rate(c("resolution_ok"), n),
        "pass_rate": _rate(c("pass"), n),
        "critical_misroute": c("critical_misroute"),
        "under_urgency": c("under_urgency"),
    }
    qwk, n_scored = urgency_qwk(examples, grades)
    q["urgency_qwk"] = qwk
    q["urgency_qwk_n"] = n_scored
    q["class_macro_f1"] = macro_f1(
        [e["classification"] for e in examples],
        [g["pred"]["classification"] if g["pred"] else None for g in grades],
        CLASSES,
    )
    if contract == "full":
        q["grounding_clean"] = _rate(sum(1 for g in grades if g["format_ok"] and g["grounding_ok"]), n)
        q["abstention_violations"] = c("abstention_violation")
        q["invented_figures_total"] = sum(len(g["invented_figures"]) for g in grades)

    q["by_class"] = {}
    for cls in CLASSES:
        idx = [i for i, e in enumerate(examples) if e["classification"] == cls]
        if idx:
            q["by_class"][cls] = _rate(sum(1 for i in idx if grades[i]["classification_ok"]), len(idx))

    q["slices"] = {}
    for name, pick in (
        ("heldout_clause", lambda e: e.get("slice", {}).get("heldout_clause", False)),
        ("human_written", lambda e: e.get("slice", {}).get("human_written", False)),
        ("abstention", lambda e: bool(e.get("abstention", False))),
    ):
        idx = [i for i, e in enumerate(examples) if pick(e)]
        if idx:
            q["slices"][name] = {
                "n": len(idx),
                "class_acc": _rate(sum(1 for i in idx if grades[i]["classification_ok"]), len(idx)),
                "resolution_acc": _rate(sum(1 for i in idx if grades[i]["resolution_ok"]), len(idx)),
                "pass_rate": _rate(sum(1 for i in idx if grades[i]["pass"]), len(idx)),
            }
    return q
