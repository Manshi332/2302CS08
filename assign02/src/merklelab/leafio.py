"""Reading leaves from files: one leaf per line.

Rules (so the same file gives the same leaves everywhere):
  * Split on b"\n". A line ending in b"\r" loses that one CR (CRLF == LF).
  * A final line terminator does NOT start another (empty) leaf.
  * Blank lines in the middle ARE leaves (empty byte strings).
  * An empty file has zero leaves; a file containing only "\n" has one empty leaf.
  * --encoding text: the leaf is the raw bytes of the line (no decoding or normalization).
  * --encoding hex : each line is a strict hex string (even length, 0-9a-fA-F only).
"""

from __future__ import annotations

import re
import sys

from .hashing import MerkleError

_HEX_RE = re.compile(rb"[0-9a-fA-F]*")


def split_lines(data: bytes) -> list[bytes]:
    parts = data.split(b"\n")
    if parts and parts[-1] == b"":
        parts.pop()
    return [p[:-1] if p.endswith(b"\r") else p for p in parts]


def parse_leaves(data: bytes, encoding: str = "text") -> list[bytes]:
    lines = split_lines(data)
    if encoding == "text":
        return lines
    if encoding != "hex":
        raise MerkleError(f"unknown encoding {encoding!r}")
    out = []
    for n, line in enumerate(lines, 1):
        if len(line) % 2 or not _HEX_RE.fullmatch(line):
            raise MerkleError(f"line {n}: malformed hex leaf (need an even number of 0-9a-fA-F digits)")
        out.append(bytes.fromhex(line.decode("ascii")))
    return out


def read_bytes(path: str) -> bytes:
    try:
        if path == "-":
            return sys.stdin.buffer.read()
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        raise MerkleError(f"cannot read {path!r}: {exc.strerror or exc}") from exc


def read_leaves(path: str, encoding: str = "text") -> list[bytes]:
    return parse_leaves(read_bytes(path), encoding)
