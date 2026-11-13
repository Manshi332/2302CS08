"""Base58Check (Bitcoin alphabet). Plain integer arithmetic; no crypto here.

Base58Check(payload) = Base58( payload || SHA256(SHA256(payload))[:4] )
Each leading 0x00 byte of the input is written as one leading '1'.
"""

from __future__ import annotations

import hashlib
import hmac

from .errors import WalletError

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_INDEX = {c: i for i, c in enumerate(ALPHABET)}
CHECKSUM_LEN = 4


def b58encode(data: bytes) -> str:
    zeros = len(data) - len(data.lstrip(b"\x00"))
    n = int.from_bytes(data, "big")
    out = []
    while n:
        n, rem = divmod(n, 58)
        out.append(ALPHABET[rem])
    return "1" * zeros + "".join(reversed(out))


def b58decode(text: str) -> bytes:
    if not text:
        raise WalletError("empty Base58 string")
    n = 0
    for ch in text:
        if ch not in _INDEX:
            raise WalletError(f"invalid Base58 character {ch!r}")
        n = n * 58 + _INDEX[ch]
    zeros = len(text) - len(text.lstrip("1"))
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\x00" * zeros + body


def checksum(payload: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:CHECKSUM_LEN]


def b58check_encode(payload: bytes) -> str:
    return b58encode(payload + checksum(payload))


def b58check_decode(text: str) -> bytes:
    """Return the payload; raise WalletError on bad characters or checksum."""
    raw = b58decode(text)
    if len(raw) <= CHECKSUM_LEN:
        raise WalletError("address too short")
    payload, got = raw[:-CHECKSUM_LEN], raw[-CHECKSUM_LEN:]
    if not hmac.compare_digest(got, checksum(payload)):
        raise WalletError("invalid checksum (address mistyped or corrupted)")
    # Reject non-canonical spellings (e.g. extra leading '1's that decode alike).
    if b58check_encode(payload) != text:
        raise WalletError("non-canonical Base58 encoding")
    return payload
