"""Merkle root over transaction ids (same specification as Assignment 2).

    Hleaf(data)        = SHA-256( 0x00 || data )
    Hnode(left, right) = SHA-256( 0x01 || left || right )
    odd level          : the last unpaired node is PROMOTED unchanged (never duplicated,
                         so [a,b,c] and [a,b,c,c] have different roots: no CVE-2012-2459)
    zero leaves        : SHA-256("")

Leaves are the 32 raw bytes of each transaction id, in block order.
"""

from __future__ import annotations

import hashlib
from typing import Sequence

EMPTY_ROOT = hashlib.sha256(b"").digest()


def leaf_hash(data: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + data).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def merkle_root(leaves: Sequence[bytes]) -> bytes:
    level = [leaf_hash(x) for x in leaves]
    if not level:
        return EMPTY_ROOT
    while len(level) > 1:
        nxt = [node_hash(level[i], level[i + 1]) for i in range(0, len(level) - 1, 2)]
        if len(level) & 1:
            nxt.append(level[-1])
        level = nxt
    return level[0]
