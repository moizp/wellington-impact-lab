"""Run every enabled model in a suite file, one at a time (one job at a time on the 16 GB laptop,
docs/paper_plan.md 3.4b), then write a combined results table and a comparison against the
baseline entry.

  cd backend
  python3 -m eval.run_suite --suite eval/suite.example.json
"""

import argparse
import json
import os

from .backends import make_backend
from .compare_rows import compare, load_preds, render_markdown
from .runner import env_fingerprint, load_corpus, load_jsonl, run, select_shots, write_outputs

HERE = os.path.dirname(__file__)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", default=os.path.join(HERE, "suite.example.json"))
    ap.add_argument("--out-dir", default="results")
    ap.add_argument("--gates", default=os.path.join(HERE, "gates.json"))
    a = ap.parse_args(argv)
    with open(a.suite) as f:
        suite = json.load(f)
    with open(a.gates) as f:
        gates = json.load(f)
    base_dir = os.path.dirname(os.path.abspath(a.suite))
    path = lambda p: p if os.path.isabs(p) else os.path.normpath(os.path.join(base_dir, p))
    rows, corpus = load_jsonl(path(suite["data"])), load_corpus(path(suite["policy"]))
    train = load_jsonl(path(suite["train"]))
    env = env_fingerprint(path(suite["data"]), path(suite["policy"]))

    table, skipped = [], []
    for e in suite["runs"]:
        if not e.get("enabled", True):
            skipped.append(e["name"])
            continue
        try:
            backend = make_backend(e["backend"], train_rows=train, threads=e.get("threads", 4),
                                   adapter_path=e.get("adapter_path"))
            try:
                contract = e.get("contract", "full")
                shots = select_shots(train, corpus, e.get("k_shots", 0), contract)
                row, preds = run(backend, rows, corpus, contract, shots, e.get("max_new_tokens"),
                                 allow_gold=e.get("allow_gold", False))
            finally:
                backend.close()
        except Exception as ex:  # a missing model / key must not stop the other runs
            table.append((e["name"], None, f"ERROR: {type(ex).__name__}: {ex}"))
            continue
        write_outputs(row, preds, a.out_dir, e["name"], env)
        table.append((e["name"], row["quality"], None))

    f = lambda m: "n/a" if m is None else f"{m:.2f}"
    lines = ["| run | n | format | class | urgency | urg. QWK | resolution | grounding | pass | misroute | under-urg. |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, q, err in table:
        if err:
            lines.append(f"| {name} | {err} |||||||||")
            continue
        g = q.get("grounding_clean", {}).get("rate")
        lines.append(f"| {name} | {q['n']} | {f(q['format_pass']['rate'])} | {f(q['class_acc']['rate'])} | "
                     f"{f(q['urgency_acc']['rate'])} | {f(q['urgency_qwk'])} | {f(q['resolution_acc']['rate'])} | "
                     f"{f(g)} | {f(q['pass_rate']['rate'])} | {q['critical_misroute']} | {q['under_urgency']} |")
    md = ["# Eval suite results", "", f"data: `{suite['data']}` (sha256 {env['dataset_sha256'][:12]}…) · "
          f"git {str(env['git_sha'])[:10]} · gates frozen: {gates['frozen']}", ""] + lines
    if skipped:
        md += ["", "Skipped (disabled): " + ", ".join(skipped)]
    base = suite.get("baseline")
    if base and os.path.exists(os.path.join(a.out_dir, f"{base}.preds.jsonl")):
        bp = load_preds(os.path.join(a.out_dir, f"{base}.preds.jsonl"))
        md += ["", f"## Paired comparison against baseline `{base}`", ""]
        for name, q, err in table:
            if err or name == base:
                continue
            md += [render_markdown(name, compare(bp, load_preds(os.path.join(a.out_dir, f"{name}.preds.jsonl")), gates)), ""]
    os.makedirs(a.out_dir, exist_ok=True)
    out = os.path.join(a.out_dir, "summary.md")
    with open(out, "w") as fh:
        fh.write("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
