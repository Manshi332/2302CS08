"""Task 7: hashes per second, and expected vs observed attempts at three toy targets.

Mining a target of `b` bits succeeds with probability p = 2**-b per attempt, so the number
of attempts is geometric with mean 1/p = 2**b and standard deviation ~ 2**b. Averaging
`trials` independent searches gives a mean whose standard error is 2**b / sqrt(trials), so a
healthy result has |z| = |observed - expected| / standard_error of about 1 and rarely above 3.

Each trial hashes a different fixed pseudo-header (derived from the bits and trial number),
so the numbers of attempts are reproducible; only the timings depend on the machine.
"""

from __future__ import annotations

import hashlib
import math
import platform
import statistics
import time
from dataclasses import dataclass

from .proofofwork import search_nonce, target_from_bits

DEFAULT_BITS = (8, 12, 16)


def _prefix(bits: int, trial: int) -> bytes:
    seed = hashlib.sha256(f"chainlab-bench:{bits}:{trial}".encode()).digest()
    return (seed * 4)[:108]


def hash_rate(count: int = 200_000, repeat: int = 3) -> float:
    """Raw SHA-256d header hashes per second (target 0 = never succeeds, so exactly `count` run)."""
    best = float("inf")
    prefix = _prefix(0, 0)
    for _ in range(repeat):
        t0 = time.perf_counter()
        nonce, n = search_nonce(prefix, 0, 0, count)
        assert nonce is None and n == count
        best = min(best, time.perf_counter() - t0)
    return count / best


@dataclass
class BenchRow:
    bits: int
    trials: int
    expected: int            # 2**bits
    mean: float              # observed mean attempts
    median: float
    stdev: float
    min: int
    max: int
    ratio: float             # mean / expected
    z: float                 # (mean - expected) / (expected / sqrt(trials))
    seconds: float
    hps: float               # attempts / seconds during this run


def bench_bits(bits: int, trials: int = 20) -> BenchRow:
    target = target_from_bits(bits)
    attempts = []
    t0 = time.perf_counter()
    for i in range(trials):
        nonce, n = search_nonce(_prefix(bits, i), target)
        assert nonce is not None
        attempts.append(n)
    secs = time.perf_counter() - t0
    expected = 2 ** bits
    mean = statistics.fmean(attempts)
    return BenchRow(bits, trials, expected, mean, statistics.median(attempts),
                    statistics.pstdev(attempts), min(attempts), max(attempts), mean / expected,
                    (mean - expected) / (expected / math.sqrt(trials)), secs, sum(attempts) / secs)


def run_bench(bits=DEFAULT_BITS, trials: int = 20, log=None) -> list[BenchRow]:
    rows = []
    for b in bits:
        if log:
            log(f"benchmarking {b} bits x {trials} trials ...")
        rows.append(bench_bits(b, trials))
    return rows


def machine_info() -> str:
    return f"Python {platform.python_version()} on {platform.system()} {platform.machine()}"


def format_table(rows: list[BenchRow], markdown: bool = False) -> str:
    head = ["bits", "trials", "expected", "observed mean", "median", "min", "max", "obs/exp", "z", "time (s)"]
    body = [[str(r.bits), str(r.trials), f"{r.expected:,}", f"{r.mean:,.1f}", f"{r.median:,.0f}",
             f"{r.min:,}", f"{r.max:,}", f"{r.ratio:.2f}", f"{r.z:+.2f}", f"{r.seconds:.2f}"] for r in rows]
    if markdown:
        lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---:" for _ in head) + "|"]
        return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in body])
    widths = [max(len(h), *(len(r[i]) for r in body)) for i, h in enumerate(head)]
    fmt = "  ".join(f"{{:>{w}}}" for w in widths)
    return "\n".join([fmt.format(*head), fmt.format(*("-" * w for w in widths))]
                     + [fmt.format(*r) for r in body])
