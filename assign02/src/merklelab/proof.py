"""Inclusion proofs: data model, strict JSON (de)serialization, verification.

Proof JSON format (field names/shape as in the assignment sheet):

    {
      "leaf_index": 2,
      "tree_size": 5,
      "siblings": [
        {"side": "right", "hash": "<64 hex>"},     # first = sibling of the leaf
        {"side": "left",  "hash": "<64 hex>"}
      ]
    }

`side` is where the SIBLING sits relative to the running hash:
    "left"  -> h = Hnode(sibling, h)
    "right" -> h = Hnode(h, sibling)

The verifier never trusts `side` or the proof length. It recomputes the exact
shape of the path from (leaf_index, tree_size) and rejects any difference.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .hashing import HASH_SIZE, MerkleError, hash_leaf, hash_node

SIDES = ("left", "right")
MAX_TREE_SIZE = 2**64 - 1
_HASH_RE = re.compile(r"[0-9a-fA-F]{64}")
_TOP_KEYS = {"leaf_index", "tree_size", "siblings"}
_SIB_KEYS = {"side", "hash"}


class ProofFormatError(MerkleError):
    """The proof (JSON or object) is structurally malformed."""


class ProofError(MerkleError):
    """The proof is well-formed but inconsistent (wrong shape/direction/length/index)."""


@dataclass(frozen=True)
class Sibling:
    side: str
    hash: bytes

    def __post_init__(self) -> None:
        if self.side not in SIDES:
            raise ProofFormatError(f"invalid direction {self.side!r}; must be 'left' or 'right'")
        if not isinstance(self.hash, bytes) or len(self.hash) != HASH_SIZE:
            raise ProofFormatError(f"sibling hash must be exactly {HASH_SIZE} bytes")


@dataclass(frozen=True)
class Proof:
    leaf_index: int
    tree_size: int
    siblings: tuple[Sibling, ...]

    def __post_init__(self) -> None:
        for name in ("leaf_index", "tree_size"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int):
                raise ProofFormatError(f"{name} must be an integer")
        if not 1 <= self.tree_size <= MAX_TREE_SIZE:
            raise ProofFormatError(f"tree_size must be between 1 and {MAX_TREE_SIZE}")
        if not 0 <= self.leaf_index < self.tree_size:
            raise ProofFormatError(
                f"leaf_index {self.leaf_index} out of range for tree_size {self.tree_size}"
            )
        object.__setattr__(self, "siblings", tuple(self.siblings))
        if not all(isinstance(s, Sibling) for s in self.siblings):
            raise ProofFormatError("siblings must be Sibling objects")

    # ---- serialization -------------------------------------------------
    def to_obj(self) -> dict[str, Any]:
        return {
            "leaf_index": self.leaf_index,
            "tree_size": self.tree_size,
            "siblings": [{"side": s.side, "hash": s.hash.hex()} for s in self.siblings],
        }

    def to_json(self, compact: bool = False) -> str:
        if compact:
            return json.dumps(self.to_obj(), separators=(",", ":"))
        return json.dumps(self.to_obj(), indent=2)

    @classmethod
    def from_obj(cls, obj: Any) -> "Proof":
        if not isinstance(obj, dict):
            raise ProofFormatError("proof must be a JSON object")
        keys = set(obj)
        if keys != _TOP_KEYS:
            missing, extra = sorted(_TOP_KEYS - keys), sorted(keys - _TOP_KEYS)
            raise ProofFormatError(
                "proof must have exactly the keys leaf_index, tree_size, siblings"
                + (f" (missing: {missing})" if missing else "")
                + (f" (unexpected: {extra})" if extra else "")
            )
        raw = obj["siblings"]
        if not isinstance(raw, list):
            raise ProofFormatError("siblings must be a list")
        sibs = []
        for i, item in enumerate(raw):
            if not isinstance(item, dict) or set(item) != _SIB_KEYS:
                raise ProofFormatError(f"siblings[{i}] must be an object with exactly 'side' and 'hash'")
            side, h = item["side"], item["hash"]
            if not isinstance(side, str) or side not in SIDES:
                raise ProofFormatError(f"siblings[{i}]: invalid direction {side!r}; must be 'left' or 'right'")
            if not isinstance(h, str) or not _HASH_RE.fullmatch(h):
                raise ProofFormatError(f"siblings[{i}]: malformed hash; need exactly 64 hex characters")
            sibs.append(Sibling(side, bytes.fromhex(h)))
        return cls(obj["leaf_index"], obj["tree_size"], tuple(sibs))

    @classmethod
    def from_json(cls, text: str | bytes) -> "Proof":
        if isinstance(text, (bytes, bytearray)):
            try:
                text = bytes(text).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ProofFormatError(f"proof is not valid UTF-8: {exc}") from exc
        try:
            obj = json.loads(text, object_pairs_hook=_no_dup_keys, parse_constant=_bad_const)
        except json.JSONDecodeError as exc:
            raise ProofFormatError(f"proof is not valid JSON: {exc}") from exc
        except ValueError as exc:  # e.g. absurdly long integer literal
            raise ProofFormatError(f"proof is not valid JSON: {exc}") from exc
        return cls.from_obj(obj)


def _no_dup_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise ProofFormatError(f"duplicate JSON key {k!r}")
        out[k] = v
    return out


def _bad_const(name: str) -> Any:
    raise ProofFormatError(f"{name} is not allowed in a proof")


# --------------------------------------------------------------------------
# Path shape and verification
# --------------------------------------------------------------------------
def expected_sides(leaf_index: int, tree_size: int) -> list[str]:
    """The exact list of sibling directions (leaf -> root) for a leaf in a tree.

    Level by level: at a level with `n` nodes, node `idx` has
      * a LEFT sibling  if idx is odd,
      * a RIGHT sibling if idx is even and idx + 1 < n,
      * NO sibling      if it is the last, unpaired node (it is promoted unchanged).
    The next level has ceil(n / 2) nodes and the node's index becomes idx // 2.
    """
    if tree_size < 1:
        raise ProofError("an empty tree has no inclusion proofs")
    if not 0 <= leaf_index < tree_size:
        raise ProofError(f"leaf_index {leaf_index} out of range for tree_size {tree_size}")
    sides: list[str] = []
    idx, n = leaf_index, tree_size
    while n > 1:
        if idx & 1:
            sides.append("left")
        elif idx + 1 < n:
            sides.append("right")
        idx >>= 1
        n = (n + 1) >> 1
    return sides


def compute_root(leaf: bytes, proof: Proof) -> bytes:
    """Fold a leaf up the proof (after the shape has been checked)."""
    h = hash_leaf(leaf)
    for s in proof.siblings:
        h = hash_node(s.hash, h) if s.side == "left" else hash_node(h, s.hash)
    return h


def verify(leaf: bytes, proof: Proof, expected_root: bytes, *, tree_size: int | None = None) -> bool:
    """Verify using ONLY the leaf bytes, the proof, and the expected root.

    Returns True if the proof is valid, False if it is well-formed and
    consistent but folds to a different root. Raises ProofError /
    ProofFormatError if the proof is malformed, has a wrong index, a wrong
    direction, or the wrong number of siblings (including unnecessarily long).

    `tree_size`, if given, is the size you trust from the same source as the
    root; the proof must claim exactly that size (the root alone does not
    commit to the number of leaves).
    """
    if not isinstance(expected_root, (bytes, bytearray)) or len(expected_root) != HASH_SIZE:
        raise ProofFormatError(f"expected root must be exactly {HASH_SIZE} bytes")
    if tree_size is not None and proof.tree_size != tree_size:
        raise ProofError(f"proof claims tree_size {proof.tree_size}, but {tree_size} was expected")

    sides = expected_sides(proof.leaf_index, proof.tree_size)
    got = len(proof.siblings)
    if got > len(sides):
        raise ProofError(
            f"proof is unnecessarily long: {got} siblings, but leaf_index {proof.leaf_index} "
            f"in a tree of {proof.tree_size} leaves needs exactly {len(sides)}"
        )
    if got < len(sides):
        raise ProofError(
            f"proof is too short: {got} siblings, but leaf_index {proof.leaf_index} "
            f"in a tree of {proof.tree_size} leaves needs exactly {len(sides)}"
        )
    for i, (sib, want) in enumerate(zip(proof.siblings, sides)):
        if sib.side != want:
            raise ProofError(
                f"siblings[{i}]: direction '{sib.side}' is wrong for leaf_index {proof.leaf_index} "
                f"in a tree of {proof.tree_size} leaves (expected '{want}')"
            )
    return compute_root(leaf, proof) == bytes(expected_root)
