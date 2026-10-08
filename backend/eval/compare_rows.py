"""Compare candidate prediction files against a baseline on the same items.

  python3 -m eval.compare_rows results/b0.preds.jsonl results/cand.preds.jsonl

Implements the primary / secondary endpoint structure of docs/paper_plan.md 7 (D11). Verdicts are
labelled EXPLORATORY unless eval/gates.json has frozen=true. The resource gate (2x memory and
p95 latency) needs isolated benchmark rows and is NOT evaluated here.
"""

import argparse
import json
import os

from .contract import URGENCIES
from .stats import mcnemar_exact, paired_bootstrap, paired_bootstrap_stat, quadratic_weighted_kappa

GATES_PATH = os.path.join(os.path.dirname(__file__), "gates.json")


def load_preds(path: str) -> dict[str, dict]:
    with open(path) as f:
        return {r["row_id"]: r for r in (json.loads(l) for l in f if l.strip())}


def non_inferiority_verdict(point: float, lo: float, hi: float, margin: float) -> str:
    if lo > -margin:
        return "non-inferior"
    if hi < 0 and point <= -margin:
        return "inferior"
    return "inconclusive"


def compare(base: dict, cand: dict, gates: dict) -> dict:
    ids = sorted(set(base) & set(cand))
    if not ids:
        raise ValueError("no overlapping row_ids between the two prediction files")
    n, seed, nb = len(ids), gates["seed"], gates["bootstrap_resamples"]
    B, C = [base[i] for i in ids], [cand[i] for i in ids]
    vec = lambda rows, key: [1.0 if r["grade"][key] else 0.0 for r in rows]
    out: dict = {"n_paired": n, "n_missing": len(set(base) ^ set(cand)), "frozen": gates["frozen"]}

    def endpoint(key: str, margin):
        d, lo, hi = paired_bootstrap(vec(C, key), vec(B, key), nb, seed)
        _, _, p = mcnemar_exact([bool(x) for x in vec(C, key)], [bool(x) for x in vec(B, key)])
        res = {"diff": d, "ci95": [lo, hi], "mcnemar_p": p,
               "base": sum(vec(B, key)) / n, "cand": sum(vec(C, key)) / n}
        res["verdict"] = non_inferiority_verdict(d, lo, hi, margin) if margin is not None else "reported only (no margin set)"
        return res

    prim = {
        "format_pass_cand": sum(vec(C, "format_ok")) / n,
        "format_min": gates["format_min"],
        "format_ok": sum(vec(C, "format_ok")) / n >= gates["format_min"],
        "classification": endpoint("classification_ok", gates["classification_margin"]),
    }
    full = all(r["grade"]["grounding_ok"] is not None or not r["grade"]["format_ok"] for r in B + C)
    if full:
        gc = lambda rows: sum(1 for r in rows if r["grade"]["format_ok"] and r["grade"]["grounding_ok"])
        prim["grounding_clean"] = {"base": gc(B) / n, "cand": gc(C) / n}
        prim["abstention_violations"] = {
            "base": sum(r["grade"]["abstention_violation"] for r in B),
            "cand": sum(r["grade"]["abstention_violation"] for r in C),
        }
    for key in ("critical_misroute", "under_urgency"):
        b, c = sum(r["grade"][key] for r in B), sum(r["grade"][key] for r in C)
        prim[key] = {"base": b, "cand": c, "ok": c <= b}
    out["primary"] = prim

    def qwk_of(rows, idxs):
        t = [rows[i]["gold"]["urgency"] for i in idxs if rows[i]["grade"]["pred"]]
        p = [rows[i]["grade"]["pred"]["urgency"] for i in idxs if rows[i]["grade"]["pred"]]
        return quadratic_weighted_kappa(t, p, URGENCIES)

    qb, qc = qwk_of(B, range(n)), qwk_of(C, range(n))
    diff_stat = lambda idx: (None if qwk_of(C, idx) is None or qwk_of(B, idx) is None
                             else qwk_of(C, idx) - qwk_of(B, idx))
    bs = paired_bootstrap_stat(diff_stat, n, min(nb, 2000), seed)
    sec_urg = {"qwk_base": qb, "qwk_cand": qc}
    if bs:
        d, lo, hi = bs
        m = gates["urgency_qwk_margin"]
        sec_urg |= {"diff": d, "ci95": [lo, hi],
                    "verdict": non_inferiority_verdict(d, lo, hi, m) if m is not None else "reported only (margin awaits the annotation pilot)"}
    out["secondary"] = {"urgency_qwk": sec_urg, "resolution": endpoint("resolution_ok", gates["resolution_margin"])}
    out["descriptive"] = {"pass_rate_base": sum(vec(B, "pass")) / n, "pass_rate_cand": sum(vec(C, "pass")) / n}
    return out


def render_markdown(name: str, res: dict) -> str:
    tag = "" if res["frozen"] else " — **EXPLORATORY: gates not frozen**"
    p, s = res["primary"], res["secondary"]
    L = [f"### {name}{tag}", f"paired n = {res['n_paired']}"]
    c = p["classification"]
    L.append(f"- format pass {p['format_pass_cand']:.2f} (min {p['format_min']}): {'ok' if p['format_ok'] else 'FAIL'}")
    L.append(f"- classification Δ {c['diff']:+.3f} (95% CI {c['ci95'][0]:+.3f}…{c['ci95'][1]:+.3f}): **{c['verdict']}**")
    if "grounding_clean" in p:
        g = p["grounding_clean"]
        L.append(f"- grounding clean: base {g['base']:.2f}, cand {g['cand']:.2f}; abstention violations base "
                 f"{p['abstention_violations']['base']} / cand {p['abstention_violations']['cand']}")
    for k, label in (("critical_misroute", "critical misroutes"), ("under_urgency", "under-urgency")):
        x = p[k]
        L.append(f"- {label}: base {x['base']}, cand {x['cand']} → {'ok' if x['ok'] else 'WORSE: review rows'}")
    u, r = s["urgency_qwk"], s["resolution"]
    qb = "n/a" if u["qwk_base"] is None else f"{u['qwk_base']:.2f}"
    qc = "n/a" if u["qwk_cand"] is None else f"{u['qwk_cand']:.2f}"
    L.append(f"- (secondary) urgency QWK base {qb}, cand {qc}" + (f", Δ {u['diff']:+.3f}: {u['verdict']}" if "diff" in u else ""))
    L.append(f"- (secondary) resolution Δ {r['diff']:+.3f} (CI {r['ci95'][0]:+.3f}…{r['ci95'][1]:+.3f}): {r['verdict']}")
    L.append(f"- (descriptive) joint pass rate base {res['descriptive']['pass_rate_base']:.2f}, cand {res['descriptive']['pass_rate_cand']:.2f}")
    L.append("- resource gate: not evaluated here (needs isolated benchmark rows)")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("baseline")
    ap.add_argument("candidates", nargs="+")
    ap.add_argument("--gates", default=GATES_PATH)
    a = ap.parse_args(argv)
    with open(a.gates) as f:
        gates = json.load(f)
    base = load_preds(a.baseline)
    for path in a.candidates:
        name = os.path.basename(path).removesuffix(".preds.jsonl")
        print(render_markdown(name, compare(base, load_preds(path), gates)) + "\n")


if __name__ == "__main__":
    main()
