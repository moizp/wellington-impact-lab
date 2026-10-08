"""CLI: evaluate one backend.

  cd backend
  python3 -m eval.run_eval --backend controls:keyword
  python3 -m eval.run_eval --backend llamacpp:models/phi4mini-q4km.gguf --name b0 --k-shots 0
  python3 -m eval.run_eval --backend anthropic:claude-opus-5-5 --k-shots 3 --name opus-3shot
"""

import argparse
import os

from .backends import make_backend
from .runner import env_fingerprint, load_corpus, load_jsonl, run, select_shots, write_outputs

HERE = os.path.dirname(__file__)
FIX = os.path.join(HERE, "fixtures")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", required=True)
    ap.add_argument("--name", help="result name (default: derived from backend)")
    ap.add_argument("--data", default=os.path.join(FIX, "test_fixture.jsonl"))
    ap.add_argument("--policy", default=os.path.join(FIX, "policy_fixture.json"))
    ap.add_argument("--train", default=os.path.join(FIX, "train_fixture.jsonl"), help="for few-shot examples and the majority control")
    ap.add_argument("--contract", choices=("full", "labels_only"), default="full")
    ap.add_argument("--k-shots", type=int, default=0)
    ap.add_argument("--max-new-tokens", type=int)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--adapter-path", help="MLX LoRA adapter directory")
    ap.add_argument("--allow-gold", action="store_true", help="permit controls:oracle (pipeline sanity only)")
    ap.add_argument("--out-dir", default="results")
    a = ap.parse_args(argv)

    rows, corpus, train = load_jsonl(a.data), load_corpus(a.policy), load_jsonl(a.train)
    backend = make_backend(a.backend, train_rows=train, threads=a.threads, adapter_path=a.adapter_path)
    try:
        shots = select_shots(train, corpus, a.k_shots, a.contract)
        row, preds = run(backend, rows, corpus, a.contract, shots, a.max_new_tokens, a.allow_gold, a.limit)
    finally:
        backend.close()
    name = a.name or a.backend.replace(":", "_").replace("/", "_")
    rp, pp = write_outputs(row, preds, a.out_dir, name, env_fingerprint(a.data, a.policy))
    q = row["quality"]
    print(f"{backend.name}  n={q['n']}  format={q['format_pass']['rate']:.2f}  class={q['class_acc']['rate']:.2f}  "
          f"urgency={q['urgency_acc']['rate']:.2f} (qwk={q['urgency_qwk']})  resolution={q['resolution_acc']['rate']:.2f}  "
          f"pass={q['pass_rate']['rate']:.2f}  misroute={q['critical_misroute']}  under_urgency={q['under_urgency']}")
    print(f"wrote {rp} and {pp}")


if __name__ == "__main__":
    main()
