"""Deterministic JSON bytes: the Assignment 1 "hashlab canonical form, v1".

Copied (not imported) so this folder is self-contained. Rules, a strict subset
of RFC 8785 (JCS):
  * UTF-8, no BOM, top-level object; no floats, NaN/Infinity, or duplicate keys
  * integers within +/-(2**53 - 1)
  * keys sorted by UTF-16 code units; no whitespace; minimal string escapes;
    non-ASCII written literally; no Unicode normalization; no trailing newline
Two JSON texts that differ only in whitespace or key order therefore give
identical bytes, which is what makes a signature over them reproducible.
"""

from __future__ import annotations

import json
from typing import Any

from .errors import WalletError

MAX_SAFE_INT = 2**53 - 1


def _parse_int(text: str) -> int:
    value = int(text)
    if abs(value) > MAX_SAFE_INT:
        raise WalletError(f"integer {text[:20]}... outside safe range +/-{MAX_SAFE_INT}")
    return value


def _reject_float(text: str) -> Any:
    raise WalletError(f"floating-point number {text!r} is not allowed; use an integer or a string")


def _reject_constant(name: str) -> Any:
    raise WalletError(f"{name} is not allowed in canonical JSON")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise WalletError(f"duplicate object key {key!r}")
        obj[key] = value
    return obj


def _utf16_key(key: str) -> bytes:
    return key.encode("utf-16-be", errors="surrogatepass")


def _serialize(value: Any) -> str:
    if isinstance(value, dict):
        items = (
            f"{json.dumps(k, ensure_ascii=False)}:{_serialize(value[k])}"
            for k in sorted(value, key=_utf16_key)
        )
        return "{" + ",".join(items) + "}"
    if isinstance(value, list):
        return "[" + ",".join(_serialize(v) for v in value) + "]"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INT:
            raise WalletError(f"integer {value} outside safe range")
        return str(value)
    raise WalletError(f"unsupported value type {type(value).__name__}")


def parse_strict(raw: bytes) -> Any:
    """Parse JSON bytes with the strict rules above; returns the Python value."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WalletError(f"input is not valid UTF-8: {exc}") from exc
    if text.startswith("﻿"):
        raise WalletError("input starts with a byte-order mark")
    try:
        return json.loads(
            text,
            object_pairs_hook=_no_duplicates,
            parse_float=_reject_float,
            parse_int=_parse_int,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise WalletError(f"invalid JSON: {exc}") from exc
    except WalletError:
        raise
    except ValueError as exc:
        raise WalletError(f"invalid JSON number: {exc}") from exc


def canonicalize_value(value: Any) -> bytes:
    if not isinstance(value, dict):
        raise WalletError("top-level JSON value must be an object")
    try:
        return _serialize(value).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise WalletError("string contains a lone surrogate; not valid UTF-8") from exc


def canonicalize(raw: bytes) -> bytes:
    return canonicalize_value(parse_strict(raw))
