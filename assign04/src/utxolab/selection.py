"""Deterministic coin selection.

STRATEGY (stated as the assignment requires): **largest-first greedy**.

    1. sort candidate outputs by value descending; ties broken by (txid, index) ascending
    2. take outputs in that order until the running total >= target (amount + fee)
    3. if all candidates together are still short, fail with `insufficient_funds`

Properties
  * deterministic: the same wallet state always selects the same coins
  * uses the fewest inputs possible for a given target (a prefix of the descending order),
    which keeps transactions small and the fee low
  * trade-off: it spends big coins first, so small "dust" outputs tend to accumulate;
    it is not minimal-change (that would need branch-and-bound / knapsack search)

``smallest_first`` (ascending, same tie-break) is provided for comparison; it
consolidates dust but produces larger transactions.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from .errors import LedgerError
from .tx import Output, OutPoint

Candidate = Tuple[OutPoint, Output]
STRATEGIES = ("largest_first", "smallest_first")


def order_candidates(candidates: Sequence[Candidate], strategy: str) -> List[Candidate]:
    if strategy == "largest_first":
        return sorted(candidates, key=lambda c: (-c[1].value, c[0].txid, c[0].index))
    if strategy == "smallest_first":
        return sorted(candidates, key=lambda c: (c[1].value, c[0].txid, c[0].index))
    raise LedgerError("bad_strategy", f"unknown coin selection strategy {strategy!r}; use one of {STRATEGIES}")


def select_coins(candidates: Sequence[Candidate], target: int,
                 strategy: str = "largest_first") -> Tuple[List[Candidate], int]:
    """Return (selected outputs, their total value). Raises insufficient_funds."""
    chosen: List[Candidate] = []
    total = 0
    for cand in order_candidates(candidates, strategy):
        if total >= target:
            break
        chosen.append(cand)
        total += cand[1].value
    if total < target:
        raise LedgerError("insufficient_funds", f"need {target} units but the wallet only has {total}")
    return chosen, total
