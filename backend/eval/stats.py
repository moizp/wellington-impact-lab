"""Small, dependency-free statistics: Wilson interval, quadratic-weighted kappa, paired
bootstrap and exact McNemar (docs/paper_plan.md 6). Seeded, so reruns are identical."""

import math
import random


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def quadratic_weighted_kappa(y_true: list[str], y_pred: list[str], labels: tuple[str, ...]) -> float | None:
    """QWK over ordinal labels. None when undefined (no rows, or no variation in expectation)."""
    k = len(labels)
    idx = {l: i for i, l in enumerate(labels)}
    n = len(y_true)
    if n == 0 or k < 2:
        return None
    obs = [[0] * k for _ in range(k)]
    for t, p in zip(y_true, y_pred):
        obs[idx[t]][idx[p]] += 1
    row = [sum(r) for r in obs]
    col = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = (i - j) ** 2 / (k - 1) ** 2
            num += w * obs[i][j]
            den += w * row[i] * col[j] / n
    if den == 0:
        return None
    return 1.0 - num / den


def paired_bootstrap(a: list[float], b: list[float], n_resamples: int = 10000, seed: int = 0):
    """Mean of (a - b) over paired items with a percentile 95% CI. a, b are per-item scores."""
    assert len(a) == len(b) and a, "paired vectors must be equal-length and non-empty"
    diffs = [x - y for x, y in zip(a, b)]
    n = len(diffs)
    rng = random.Random(seed)
    means = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_resamples))
    lo = means[int(0.025 * n_resamples)]
    hi = means[min(n_resamples - 1, int(0.975 * n_resamples))]
    return sum(diffs) / n, lo, hi


def paired_bootstrap_stat(stat, idx_n: int, n_resamples: int = 10000, seed: int = 0):
    """Bootstrap of stat(indices) -> float|None over resampled item indices.

    Used for non-decomposable statistics (QWK). Resamples where stat is None are skipped.
    Returns (point, lo, hi), or None when no resample is defined.
    """
    point = stat(list(range(idx_n)))
    rng = random.Random(seed)
    vals = []
    for _ in range(n_resamples):
        v = stat([rng.randrange(idx_n) for _ in range(idx_n)])
        if v is not None:
            vals.append(v)
    if point is None or not vals:
        return None
    vals.sort()
    lo = vals[int(0.025 * len(vals))]
    hi = vals[min(len(vals) - 1, int(0.975 * len(vals)))]
    return point, lo, hi


def mcnemar_exact(a_correct: list[bool], b_correct: list[bool]) -> tuple[int, int, float]:
    """Exact two-sided McNemar on paired correctness. Returns (b_only, a_only, p)."""
    a_only = sum(1 for x, y in zip(a_correct, b_correct) if x and not y)
    b_only = sum(1 for x, y in zip(a_correct, b_correct) if y and not x)
    n = a_only + b_only
    if n == 0:
        return b_only, a_only, 1.0
    k = min(a_only, b_only)
    p = 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return b_only, a_only, min(1.0, p)
