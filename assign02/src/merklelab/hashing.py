"""Domain-separated hashing primitives (the whole tree specification starts here).

    Hleaf(data)        = SHA-256( 0x00 || data )
    Hnode(left, right) = SHA-256( 0x01 || left || right )      left, right: 32 bytes each
    EMPTY_ROOT         = SHA-256( "" )                          root of a tree with zero leaves

The 0x00 / 0x01 prefixes make leaf hashes and internal-node hashes live in
different "domains", so an internal node can never be passed off as a leaf
(the second-preimage attack on un-prefixed Merkle trees).

SHA-256 comes from hashlib; no Merkle-tree package is used anywhere.
"""

from __future__ import annotations

import hashlib

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"
HASH_SIZE = 32
EMPTY_ROOT = hashlib.sha256(b"").digest()

_sha256 = hashlib.sha256


class MerkleError(Exception):
    """Base class for all user-facing errors of this library."""


def hash_leaf(data: bytes) -> bytes:
    """Hash raw leaf bytes. Text must be encoded by the caller (e.g. UTF-8)."""
    if isinstance(data, str):
        raise TypeError("leaf data must be bytes, not str; encode it first (e.g. .encode('utf-8'))")
    return _sha256(LEAF_PREFIX + bytes(data)).digest()


def hash_node(left: bytes, right: bytes) -> bytes:
    """Hash two child digests. Both must be exactly 32 bytes (no ambiguous splits)."""
    if len(left) != HASH_SIZE or len(right) != HASH_SIZE:
        raise MerkleError(
            f"child hashes must be {HASH_SIZE} bytes each, got {len(left)} and {len(right)}"
        )
    return _sha256(NODE_PREFIX + left + right).digest()
