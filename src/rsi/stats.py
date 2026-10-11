"""Small statistics helpers for accuracy and paired comparisons."""

from __future__ import annotations

import math
import random


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def paired_bootstrap(a: list[int], b: list[int], iters: int = 5000, seed: int = 0) -> float:
    """P(mean(b) > mean(a)) over resamples of paired 0/1 outcomes; ties count half."""
    assert len(a) == len(b)
    n = len(a)
    if n == 0:
        return 0.5
    diffs = [y - x for x, y in zip(a, b, strict=True)]
    rng = random.Random(seed)
    wins = 0.0
    for _ in range(iters):
        s = sum(diffs[rng.randrange(n)] for _ in range(n))
        wins += 1.0 if s > 0 else 0.5 if s == 0 else 0.0
    return wins / iters
