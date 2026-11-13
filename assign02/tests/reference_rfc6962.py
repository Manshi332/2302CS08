"""Independent reference implementation, straight from RFC 6962 section 2.1.

Deliberately written differently from merklelab (recursive split at the largest
power of two, plain hashlib, no shared code) so tests compare two separate
implementations of the same specification.
"""

import hashlib


def H(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def largest_pow2_below(n: int) -> int:
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def MTH(d: list) -> bytes:
    n = len(d)
    if n == 0:
        return H(b"")
    if n == 1:
        return H(b"\x00" + d[0])
    k = largest_pow2_below(n)
    return H(b"\x01" + MTH(d[:k]) + MTH(d[k:]))


def PATH(m: int, d: list) -> list:
    """Sibling hashes from the leaf up, as in RFC 6962 (returns hashes only)."""
    n = len(d)
    if n == 1:
        return []
    k = largest_pow2_below(n)
    if m < k:
        return PATH(m, d[:k]) + [MTH(d[k:])]
    return PATH(m - k, d[k:]) + [MTH(d[:k])]
