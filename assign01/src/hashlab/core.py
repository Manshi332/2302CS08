"""Byte-level helpers: input parsing, streaming SHA-256, bit flipping.

SHA-256 itself is NOT implemented here; we call hashlib (OpenSSL-backed).
"""

from __future__ import annotations

import base64
import hashlib
import re
import sys
import unicodedata
from dataclasses import dataclass
from typing import BinaryIO

CHUNK_SIZE = 1024 * 1024  # 1 MiB read buffer: memory use is O(chunk), not O(file)
NORMAL_FORMS = ("NFC", "NFD", "NFKC", "NFKD")

_HEX_RE = re.compile(r"[0-9a-fA-F]*")
_ESCAPE_RE = re.compile(r"\\([nrt\\])")
_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\"}


class HashlabError(Exception):
    """A user-facing input error (bad hex, missing file, bad bit index...)."""


@dataclass(frozen=True)
class HashResult:
    length: int      # number of input bytes
    digest: bytes    # raw 32-byte SHA-256 digest

    @property
    def hex(self) -> str:
        return self.digest.hex()

    @property
    def base64(self) -> str:
        return base64.b64encode(self.digest).decode("ascii")


# --------------------------------------------------------------------------
# Input parsing
# --------------------------------------------------------------------------
def parse_hex(value: str) -> bytes:
    """Strictly parse a hex string. Optional 0x prefix; no spaces; even length."""
    text = value[2:] if value[:2] in ("0x", "0X") else value
    if len(text) % 2 != 0:
        raise HashlabError(
            f"malformed hex: odd number of digits ({len(text)}); "
            "each byte needs exactly two hex digits"
        )
    if not _HEX_RE.fullmatch(text):
        bad = next(c for c in text if c not in "0123456789abcdefABCDEF")
        raise HashlabError(f"malformed hex: invalid character {bad!r}")
    return bytes.fromhex(text)


def text_to_bytes(value: str, normalize: str | None = None, escapes: bool = False) -> bytes:
    """Encode text as UTF-8, optionally interpreting \\n \\r \\t \\\\ and normalizing."""
    if escapes:
        value = _ESCAPE_RE.sub(lambda m: _ESCAPES[m.group(1)], value)
    if normalize:
        value = unicodedata.normalize(normalize, value)
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise HashlabError(f"text is not valid Unicode (cannot encode as UTF-8): {exc}") from exc


# --------------------------------------------------------------------------
# Hashing
# --------------------------------------------------------------------------
def hash_bytes(data: bytes) -> HashResult:
    return HashResult(len(data), hashlib.sha256(data).digest())


def check_bit_in_range(bit: int, length: int) -> None:
    if bit < 0:
        raise HashlabError(f"bit index must be >= 0, got {bit}")
    if bit >= length * 8:
        raise HashlabError(
            f"bit index {bit} out of range: input has {length} bytes = {length * 8} bits "
            f"(valid indices 0..{length * 8 - 1})" if length else
            "cannot flip a bit of empty input"
        )


def bit_mask(bit: int) -> int:
    """Mask inside the byte. Bit 0 is the MOST significant bit of byte 0."""
    return 0x80 >> (bit & 7)


def flip_bit(data: bytes, bit: int) -> bytes:
    check_bit_in_range(bit, len(data))
    out = bytearray(data)
    out[bit >> 3] ^= bit_mask(bit)
    return bytes(out)


def hash_stream(stream: BinaryIO, chunk_size: int = CHUNK_SIZE,
                flip: int | None = None) -> HashResult:
    """Hash a binary stream chunk by chunk using one reusable buffer.

    If `flip` is given, that input bit is inverted on the fly (used by the
    avalanche command on files without ever holding the file in memory).
    """
    h = hashlib.sha256()
    buf = bytearray(chunk_size)
    view = memoryview(buf)
    total = 0
    while True:
        n = stream.readinto(view)
        if not n:
            break
        if flip is not None:
            idx = flip >> 3
            if total <= idx < total + n:
                buf[idx - total] ^= bit_mask(flip)
        h.update(view[:n])
        total += n
    if flip is not None:
        check_bit_in_range(flip, total)
    return HashResult(total, h.digest())


def hash_file(path: str, chunk_size: int = CHUNK_SIZE, flip: int | None = None) -> HashResult:
    """Hash a file by path ('-' means standard input)."""
    try:
        if path == "-":
            return hash_stream(sys.stdin.buffer, chunk_size, flip)
        with open(path, "rb", buffering=0) as fh:
            return hash_stream(fh, chunk_size, flip)
    except OSError as exc:
        raise HashlabError(f"cannot read {path!r}: {exc.strerror or exc}") from exc


# --------------------------------------------------------------------------
# Avalanche
# --------------------------------------------------------------------------
def hamming_distance(a: bytes, b: bytes) -> int:
    """Number of differing bits between two equal-length byte strings."""
    if len(a) != len(b):
        raise ValueError("hamming_distance needs equal-length inputs")
    return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).bit_count()
