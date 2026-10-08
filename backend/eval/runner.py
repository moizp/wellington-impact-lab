"""Run one backend over one dataset, grade every output, write a result row + per-example
predictions. Quality only: the isolated memory/latency benchmark (benchmark_model.py in
docs/paper_plan.md 2) will wrap this, not replace it."""

import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone

from .backends import Backend
from .contract import (
    SYSTEM_PROMPT,
    build_user_message,
    clause_texts,
    format_output,
    gold_output,
    render_example,
)
from .grader import grade
from .metrics import aggregate


def load_jsonl(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def load_corpus(path: str) -> dict:
    with open(path) as f:
        return json.load(f)["clauses"]


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def select_shots(train_rows: list[dict], corpus: dict, k: int, contract: str = "full") -> list[tuple[str, str]]:
    """Deterministic few-shot examples: round-robin over classes in row_id order. Freeze the
    choice (and commit it) before any test run (docs/paper_plan.md 5, Stage Z)."""
    if k <= 0:
        return []
    by_class: dict[str, list[dict]] = {}
    for r in sorted(train_rows, key=lambda r: r["row_id"]):
        by_class.setdefault(r["classification"], []).append(r)
    order = sorted(by_class)
    picked, i = [], 0
    while len(picked) < min(k, len(train_rows)):
        for cls in order:
            if by_class[cls] and len(picked) < k:
                picked.append(by_class[cls].pop(0))
        i += 1
        if i > k + len(order):
            break
    out = []
    for r in picked:
        _, user = render_example(r, corpus)
        out.append((user, gold_output(r, contract)))
    return out


def suggest_max_new_tokens(rows: list[dict], contract: str) -> int:
    """Heuristic until tokenizers are in play: longest gold output in characters / 3, + margin."""
    longest = max(len(gold_output(r, contract)) for r in rows)
    return math.ceil(longest / 3) + 32


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return None


def env_fingerprint(data_path: str, policy_path: str) -> dict:
    return {
        "git_sha": _git_sha(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "dataset_sha256": sha256_file(data_path),
        "policy_sha256": sha256_file(policy_path),
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def percentile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]


def run(backend: Backend, rows: list[dict], corpus: dict, contract: str = "full",
        shots: list[tuple[str, str]] | None = None, max_new_tokens: int | None = None,
        allow_gold: bool = False, limit: int | None = None) -> tuple[dict, list[dict]]:
    if backend.uses_gold and not allow_gold:
        raise PermissionError(f"{backend.name} reads gold labels; pass allow_gold=True (pipeline sanity checks only)")
    rows = rows[:limit] if limit else rows
    max_new = max_new_tokens or suggest_max_new_tokens(rows, contract)
    preds, grades = [], []
    for ex in rows:
        system, user = render_example(ex, corpus)
        t0 = time.perf_counter()
        gen = backend.generate(system, user, shots=shots or [], example=ex if backend.needs_example else None,
                               max_new_tokens=max_new)
        wall = time.perf_counter() - t0
        g = grade(gen.text, ex, [t for _, t in clause_texts(ex, corpus)], contract, gen.truncated)
        grades.append(g)
        preds.append({
            "row_id": ex["row_id"],
            "gold": {k: ex[k] for k in ("classification", "urgency", "resolution")}
                    | {"abstention": bool(ex.get("abstention", False)), "slice": ex.get("slice", {})},
            "raw": gen.text, "truncated": gen.truncated,
            "prompt_tokens": gen.prompt_tokens, "completion_tokens": gen.completion_tokens,
            "seconds": gen.seconds if gen.seconds is not None else wall,
            "grade": g,
        })
    secs = [p["seconds"] for p in preds]
    row = {
        "backend": backend.name, "contract": contract, "k_shots": len(shots or []),
        "max_new_tokens": max_new,
        "quality": aggregate(rows, grades, contract),
        "in_process_latency_s": {
            "p50": percentile(secs, 0.5), "p95": percentile(secs, 0.95),
            "note": "wall time per request inside the eval loop; NOT the isolated benchmark, and includes network for API backends",
        },
    }
    return row, preds


def write_outputs(row: dict, preds: list[dict], out_dir: str, name: str, env: dict) -> tuple[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    row = {"run_id": name, "env": env} | row
    rp, pp = os.path.join(out_dir, f"{name}.json"), os.path.join(out_dir, f"{name}.preds.jsonl")
    with open(rp, "w") as f:
        json.dump(row, f, indent=2)
    with open(pp, "w") as f:
        for p in preds:
            f.write(json.dumps(p) + "\n")
    return rp, pp
