"""Performance measurement: construction time and proof size."""

from __future__ import annotations

import math
import platform
import time
from dataclasses import dataclass

from .proof import verify
from .tree import MerkleTree, merkle_root

DEFAULT_SIZES = (8, 1024, 100_000)


@dataclass
class BenchRow:
    leaves: int
    build_s: float          # best-of-N: hash leaves + build all levels (MerkleTree)
    root_only_s: float      # best-of-N: merkle_root() (no levels kept)
    hashes: int             # SHA-256 calls: n leaf hashes + (n - 1) node hashes
    prove_us: float         # mean time to make one proof (sampled indexes)
    verify_us: float        # mean time to verify one proof (sampled indexes)
    siblings_max: int       # longest proof in the sample
    ideal_siblings: int     # ceil(log2 n)
    proof_raw_bytes: int    # 32 * siblings (hashes only)
    proof_json_bytes: int   # compact JSON of the longest sampled proof


def _sample_indexes(n: int, k: int = 200) -> list[int]:
    if n <= k:
        return list(range(n))
    step = n / k
    idx = {int(i * step) for i in range(k)}
    idx.update({0, n - 1, n // 2})
    return sorted(idx)


def _best(fn, repeat: int) -> float:
    best = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


def bench_size(n: int, repeat: int = 3) -> BenchRow:
    leaves = [f"transaction-{i}".encode() for i in range(n)]
    build_s = _best(lambda: MerkleTree(leaves), repeat)
    root_only_s = _best(lambda: merkle_root(leaves), repeat)
    tree = MerkleTree(leaves)
    idxs = _sample_indexes(n)

    t0 = time.perf_counter()
    proofs = [tree.prove(i) for i in idxs]
    prove_us = (time.perf_counter() - t0) / len(idxs) * 1e6

    t0 = time.perf_counter()
    for i, p in zip(idxs, proofs):
        if not verify(leaves[i], p, tree.root):
            raise AssertionError(f"self-check failed for index {i}")
    verify_us = (time.perf_counter() - t0) / len(idxs) * 1e6

    longest = max(proofs, key=lambda p: len(p.siblings))
    return BenchRow(
        leaves=n, build_s=build_s, root_only_s=root_only_s, hashes=2 * n - 1,
        prove_us=prove_us, verify_us=verify_us,
        siblings_max=len(longest.siblings),
        ideal_siblings=math.ceil(math.log2(n)) if n > 1 else 0,
        proof_raw_bytes=32 * len(longest.siblings),
        proof_json_bytes=len(longest.to_json(compact=True)),
    )


def machine_info() -> str:
    return (f"Python {platform.python_version()} on {platform.system()} "
            f"{platform.machine()} ({platform.processor() or 'CPU n/a'})")


def run_bench(sizes=DEFAULT_SIZES, repeat: int = 3, log=None) -> list[BenchRow]:
    rows = []
    for n in sizes:
        if log:
            log(f"benchmarking {n} leaves ...")
        rows.append(bench_size(n, repeat))
    return rows


def format_table(rows: list[BenchRow], markdown: bool = False) -> str:
    head = ["leaves", "build (ms)", "root-only (ms)", "SHA-256 calls", "prove (us)", "verify (us)",
            "siblings", "ceil(log2 n)", "proof raw (B)", "proof JSON (B)"]
    body = [[
        f"{r.leaves:,}", f"{r.build_s * 1e3:,.2f}", f"{r.root_only_s * 1e3:,.2f}", f"{r.hashes:,}",
        f"{r.prove_us:,.1f}", f"{r.verify_us:,.1f}", str(r.siblings_max), str(r.ideal_siblings),
        f"{r.proof_raw_bytes:,}", f"{r.proof_json_bytes:,}",
    ] for r in rows]
    if markdown:
        lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---:" for _ in head) + "|"]
        lines += ["| " + " | ".join(row) + " |" for row in body]
        return "\n".join(lines)
    widths = [max(len(h), *(len(row[i]) for row in body)) for i, h in enumerate(head)]
    fmt = "  ".join(f"{{:>{w}}}" for w in widths)
    return "\n".join([fmt.format(*head), fmt.format(*("-" * w for w in widths))]
                     + [fmt.format(*r) for r in body])
