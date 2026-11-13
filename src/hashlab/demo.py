"""`hashlab demo`: inputs that LOOK the same but are different bytes."""

from __future__ import annotations

import json
import unicodedata
from typing import TextIO

from .canonical import canonicalize
from .core import hash_bytes


def _show(out: TextIO, label: str, data: bytes) -> None:
    res = hash_bytes(data)
    shown = data.hex() if len(data) <= 24 else data[:24].hex() + "..."
    out.write(f"  {label:<10} bytes={res.length:<3} hex={shown}\n")
    out.write(f"  {'':<10} sha256={res.hex}\n")


def _compare(out: TextIO, title: str, why: str, a: tuple[str, bytes], b: tuple[str, bytes]) -> None:
    out.write(f"\n[{title}]\n  {why}\n")
    _show(out, *a)
    _show(out, *b)
    same_bytes = a[1] == b[1]
    out.write(f"  identical bytes: {'yes' if same_bytes else 'NO'}   "
              f"identical digests: {'yes' if hash_bytes(a[1]).digest == hash_bytes(b[1]).digest else 'NO'}\n")


def run_demo(out: TextIO) -> None:
    out.write("hashlab demo: same-looking input, different bytes, different hashes\n")

    base = "Alice pays Bob 10"
    _compare(out, "1. trailing newline",
             "A file saved by an editor often ends with an invisible \\n.",
             ("no newline", base.encode()), ("with \\n", (base + "\n").encode()))

    _compare(out, "2. line endings",
             "Unix uses LF (0a); Windows uses CRLF (0d0a). Same text on screen.",
             ("LF", b"line1\nline2"), ("CRLF", b"line1\r\nline2"))

    nfc = unicodedata.normalize("NFC", "caf\u00e9")
    nfd = unicodedata.normalize("NFD", "caf\u00e9")
    _compare(out, "3. Unicode normalization",
             f"Both render as 'caf\u00e9' but NFC uses one code point, NFD uses e + combining accent.",
             ("NFC", nfc.encode()), ("NFD", nfd.encode()))

    _compare(out, "4. look-alike letters",
             "Latin 'a' (U+0061) vs Cyrillic 'a' (U+0430): visually identical.",
             ("Latin", "pay".encode()), ("Cyrillic", "p\u0430y".encode()))

    _compare(out, "5. integer vs string (canonical JSON)",
             '{"amount": 10} vs {"amount": "10"}: different JSON types.',
             ("int", canonicalize(b'{"amount": 10}')), ("string", canonicalize(b'{"amount": "10"}')))

    d1 = {"from": "Alice", "to": "Bob", "amount": 10}
    d2 = {"amount": 10, "to": "Bob", "from": "Alice"}
    naive1 = json.dumps(d1).encode()
    naive2 = json.dumps(d2).encode()
    _compare(out, "6a. key order, NAIVE json.dumps",
             "Same object, keys inserted in a different order -> different bytes.",
             ("order A", naive1), ("order B", naive2))
    _compare(out, "6b. key order, CANONICAL",
             "hashlab canonical-json sorts keys and removes whitespace -> same bytes.",
             ("order A", canonicalize(naive1)), ("order B", canonicalize(naive2)))

    out.write("\nConclusion: a hash is a hash of BYTES. Blockchains therefore define one exact\n"
              "byte encoding for every transaction and block before hashing.\n")
