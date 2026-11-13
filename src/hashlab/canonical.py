"""Deterministic JSON serialization ("hashlab canonical form", v1).

Rules (a strict subset of RFC 8785 / JCS, chosen so two programs can never
disagree about the bytes):

 1. Input must be UTF-8 (no BOM) and the top-level value must be an object.
 2. Allowed values: object, array, string, integer, true, false, null.
 3. Floats are REJECTED (1.0, 1e3, ...). Money/amounts must be integers or
    strings; float text formatting differs between languages.
 4. Integers must be within +/-(2**53 - 1) so every language can represent them.
 5. NaN / Infinity are rejected. Duplicate object keys are rejected.
 6. Object keys are sorted by their UTF-16 code units (same as JCS).
 7. No whitespace at all: separators are "," and ":".
 8. Strings are written as UTF-8 with the minimal JSON escapes:
    \\" \\\\ \\b \\f \\n \\r \\t and \\u00xx (lowercase hex) for other control
    characters < 0x20. Non-ASCII characters are emitted literally, not as \\uXXXX.
 9. Unicode is NOT normalized: "\u00e9" (NFC) and "e\u0301" (NFD) stay different.
10. No trailing newline. The hashed bytes are exactly the UTF-8 of the text.
"""

from __future__ import annotations

import json
from typing import Any

from .core import HashlabError

MAX_SAFE_INT = 2**53 - 1


def _parse_int(text: str) -> int:
    value = int(text)
    if abs(value) > MAX_SAFE_INT:
        raise HashlabError(f"integer {text[:20]}... outside safe range +/-{MAX_SAFE_INT}")
    return value


def _reject_float(text: str) -> Any:
    raise HashlabError(
        f"floating-point number {text!r} is not allowed; use an integer or a string"
    )


def _reject_constant(name: str) -> Any:
    raise HashlabError(f"{name} is not allowed in canonical JSON")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise HashlabError(f"duplicate object key {key!r}")
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
            raise HashlabError(f"integer {value} outside safe range")
        return str(value)
    raise HashlabError(f"unsupported value type {type(value).__name__}")


def canonicalize_value(value: Any) -> bytes:
    """Canonical UTF-8 bytes for an already-parsed Python object."""
    if not isinstance(value, dict):
        raise HashlabError("top-level JSON value must be an object")
    try:
        return _serialize(value).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise HashlabError("string contains a lone surrogate; not valid UTF-8") from exc


def canonicalize(raw: bytes) -> bytes:
    """Parse raw JSON bytes and return the canonical UTF-8 bytes."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HashlabError(f"input is not valid UTF-8: {exc}") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_no_duplicates,
            parse_float=_reject_float,
            parse_int=_parse_int,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise HashlabError(f"invalid JSON: {exc}") from exc
    except ValueError as exc:
        if isinstance(exc, HashlabError):
            raise
        raise HashlabError(f"invalid JSON number: {exc}") from exc
    return canonicalize_value(value)
