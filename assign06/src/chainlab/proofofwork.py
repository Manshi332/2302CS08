"""Toy Proof of Work primitives.

    block hash  = SHA-256( SHA-256( header_bytes ) )          (double SHA-256, like Bitcoin)
    valid PoW   : int.from_bytes(block_hash, "big") <= target (digest read as a big-endian
                  unsigned integer; NO Bitcoin-style byte reversal, so what you see in hex
                  is exactly the number that is compared)
    difficulty  : target_from_bits(b) = 2**(256-b) - 1, i.e. the first b bits of the hash
                  must be zero; each attempt succeeds with probability 2**-b, so the
                  expected number of attempts is 2**b.
    work        : work(target) = floor(2**256 / (target + 1))  = expected attempts
                  (the same definition Bitcoin uses for chain work)

SHA-256 itself comes from hashlib; nothing here implements a hash function.
"""

from __future__ import annotations

import hashlib
import math
import struct

from .errors import BlockError

HASH_SIZE = 32
MAX_NONCE = 2**32 - 1
_pack_nonce = struct.Struct(">I").pack


def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def hash_to_int(digest: bytes) -> int:
    return int.from_bytes(digest, "big")


def target_from_bits(bits: int) -> int:
    if isinstance(bits, bool) or not isinstance(bits, int) or not 0 <= bits <= 255:
        raise BlockError("bad_target", "bits must be an integer in 0..255")
    return (1 << (256 - bits)) - 1


def work_from_target(target: int) -> int:
    if isinstance(target, bool) or not isinstance(target, int) or not 0 < target < 2**256:
        raise BlockError("bad_target", "target must be an integer in 1..2**256-1")
    return (1 << 256) // (target + 1)


def bits_from_target(target: int) -> float:
    """log2(work): the 'difficulty in bits' of an arbitrary target."""
    return math.log2(work_from_target(target))


def meets_target(digest: bytes, target: int) -> bool:
    return digest <= target.to_bytes(HASH_SIZE, "big")  # big-endian bytes compare == integer compare


def search_nonce(prefix: bytes, target: int, start: int = 0, max_attempts: int | None = None):
    """Try nonces start.. on `prefix || nonce(4 bytes BE)`.

    Returns (nonce, attempts) on success, (None, attempts) if the range or the
    attempt budget ran out. `prefix` is the 108 header bytes before the nonce.
    """
    tb = target.to_bytes(HASH_SIZE, "big")
    sha = hashlib.sha256
    stop = MAX_NONCE + 1 if max_attempts is None else min(MAX_NONCE + 1, start + max_attempts)
    for nonce in range(start, stop):
        if sha(sha(prefix + _pack_nonce(nonce)).digest()).digest() <= tb:
            return nonce, nonce - start + 1
    return None, max(0, stop - start)
