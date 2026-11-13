"""Merkle tree construction and proof generation.

Specification (identical to the tree of RFC 6962 / Certificate Transparency):

  * leaf i      : Hleaf(data_i)
  * parents     : adjacent nodes are paired left-to-right: Hnode(left, right)
  * odd count   : the last, unpaired node is PROMOTED to the next level
                  UNCHANGED. It is never duplicated and never re-hashed.
  * zero leaves : root = EMPTY_ROOT = SHA-256("")
  * one leaf    : root = Hleaf(data)
  * levels      : level k+1 has ceil(n_k / 2) nodes; stop when one node remains.

Why promote instead of duplicate (Bitcoin style)? With duplication the lists
[a, b, c] and [a, b, c, c] have the SAME root (CVE-2012-2459). Promotion keeps
every leaf list's root unique.
"""

from __future__ import annotations

from typing import Iterable

from .hashing import EMPTY_ROOT, MerkleError, hash_leaf, hash_node
from .proof import Proof, Sibling


def _next_level(level: list[bytes]) -> list[bytes]:
    nxt = [hash_node(level[i], level[i + 1]) for i in range(0, len(level) - 1, 2)]
    if len(level) & 1:
        nxt.append(level[-1])  # promote the unpaired node unchanged
    return nxt


def build_levels(leaves: Iterable[bytes]) -> list[list[bytes]]:
    """Return all levels, leaf hashes first, root level (1 node) last. Empty -> [[]]."""
    level = [hash_leaf(x) for x in leaves]
    levels = [level]
    while len(level) > 1:
        level = _next_level(level)
        levels.append(level)
    return levels


def merkle_root(leaves: Iterable[bytes]) -> bytes:
    """Root only; keeps just one level in memory."""
    level = [hash_leaf(x) for x in leaves]
    if not level:
        return EMPTY_ROOT
    while len(level) > 1:
        level = _next_level(level)
    return level[0]


class MerkleTree:
    """An immutable Merkle tree that keeps every level so proofs are O(log n) lookups."""

    def __init__(self, leaves: Iterable[bytes]) -> None:
        self._levels = build_levels(leaves)

    @property
    def size(self) -> int:
        return len(self._levels[0])

    @property
    def root(self) -> bytes:
        return self._levels[-1][0] if self.size else EMPTY_ROOT

    @property
    def height(self) -> int:
        """Number of hashing levels above the leaves (0 for sizes 0 and 1)."""
        return len(self._levels) - 1

    def leaf_hash(self, index: int) -> bytes:
        self._check(index)
        return self._levels[0][index]

    def _check(self, index: int) -> None:
        if isinstance(index, bool) or not isinstance(index, int):
            raise MerkleError("index must be an integer")
        if self.size == 0:
            raise MerkleError("the tree is empty: no leaf can be proven")
        if not 0 <= index < self.size:
            raise MerkleError(f"index {index} out of range: tree has {self.size} leaves (0..{self.size - 1})")

    def prove(self, index: int) -> Proof:
        """Inclusion proof: sibling hashes from the leaf level upward, with directions."""
        self._check(index)
        siblings: list[Sibling] = []
        idx = index
        for level in self._levels[:-1]:
            if idx & 1:
                siblings.append(Sibling("left", level[idx - 1]))
            elif idx + 1 < len(level):
                siblings.append(Sibling("right", level[idx + 1]))
            # else: unpaired last node, promoted, no sibling at this level
            idx >>= 1
        return Proof(index, self.size, tuple(siblings))
