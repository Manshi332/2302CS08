"""Versioned wire messages with safe length-prefixed framing.

Frame:  4-byte big-endian length N | N bytes of canonical JSON
Body:   {"v": 1, "type": "<name>", "payload": {...}}

N is checked against MAX_MESSAGE_SIZE *before* any body byte is read, so a peer
cannot make us allocate memory by lying about the length.
"""

from __future__ import annotations

import asyncio
import re
import struct
from typing import Any

from chainlab.canonical import canonicalize_value, parse_strict
from chainlab.errors import WalletError

PROTO_VERSION = 1
MAX_MESSAGE_SIZE = 1_000_000
MAX_INV_ITEMS = 500
MAX_ADDRS = 100
_LEN = struct.Struct(">I")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

TYPES = ("version", "verack", "getaddr", "addr", "inv", "getdata", "notfound",
         "tx", "block", "ping", "pong", "error")


class ProtocolError(Exception):
    def __init__(self, code: str, reason: str, fatal: bool = False):
        super().__init__(f"{code}: {reason}")
        self.code, self.reason, self.fatal = code, reason, fatal


# ----------------------------------------------------------------- framing
def encode(mtype: str, payload: dict) -> bytes:
    body = canonicalize_value({"v": PROTO_VERSION, "type": mtype, "payload": payload})
    if len(body) > MAX_MESSAGE_SIZE:
        raise ProtocolError("oversized", f"outgoing message is {len(body)} bytes", fatal=True)
    return _LEN.pack(len(body)) + body


async def read_frame(reader: asyncio.StreamReader) -> bytes:
    """Read one frame body. IncompleteReadError (EOF) propagates to the caller."""
    (n,) = _LEN.unpack(await reader.readexactly(_LEN.size))
    if n == 0 or n > MAX_MESSAGE_SIZE:
        raise ProtocolError("oversized", f"declared length {n} outside 1..{MAX_MESSAGE_SIZE}", fatal=True)
    return await reader.readexactly(n)


def decode(body: bytes) -> tuple[str, dict]:
    try:
        msg = parse_strict(body)
    except WalletError as exc:
        raise ProtocolError("malformed", str(exc)) from None
    if not isinstance(msg, dict) or set(msg) != {"v", "type", "payload"}:
        raise ProtocolError("malformed", "envelope must have exactly v, type, payload")
    if msg["v"] != PROTO_VERSION:
        raise ProtocolError("unsupported_version", f"version {msg['v']!r} (we speak {PROTO_VERSION})", fatal=True)
    mtype, payload = msg["type"], msg["payload"]
    if mtype not in TYPES:
        raise ProtocolError("unknown_type", f"unknown message type {mtype!r}")
    if not isinstance(payload, dict):
        raise ProtocolError("malformed", "payload must be an object")
    validate_payload(mtype, payload)
    return mtype, payload


# -------------------------------------------------------------- validation
def _int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _str(v: Any, lo: int = 1, hi: int = 64) -> bool:
    return isinstance(v, str) and lo <= len(v) <= hi


def _need(cond: bool, what: str) -> None:
    if not cond:
        raise ProtocolError("bad_payload", what)


def _keys(p: dict, keys: tuple[str, ...]) -> None:
    _need(set(p) == set(keys), f"payload keys must be exactly {list(keys)}")


def _items(p: dict) -> None:
    _keys(p, ("items",))
    items = p["items"]
    _need(isinstance(items, list) and 0 < len(items) <= MAX_INV_ITEMS, f"items must be a list of 1..{MAX_INV_ITEMS}")
    for it in items:
        _need(isinstance(it, dict) and set(it) == {"kind", "id"}, "item must be {kind,id}")
        _need(it["kind"] in ("tx", "block"), "item kind must be tx or block")
        _need(isinstance(it["id"], str) and bool(_HEX64.match(it["id"])), "item id must be 64 lowercase hex chars")


def validate_payload(mtype: str, p: dict) -> None:
    if mtype == "version":
        _keys(p, ("proto", "node_id", "port", "network", "genesis", "height", "tip"))
        _need(_int(p["proto"]) and _str(p["node_id"]) and _int(p["port"]) and p["port"] < 65536, "bad version fields")
        _need(_str(p["network"]) and _int(p["height"]), "bad version fields")
        _need(bool(_HEX64.match(str(p["genesis"]))) and bool(_HEX64.match(str(p["tip"]))), "genesis/tip must be hex32")
    elif mtype in ("verack", "getaddr"):
        _keys(p, ())
    elif mtype == "addr":
        _keys(p, ("peers",))
        _need(isinstance(p["peers"], list) and len(p["peers"]) <= MAX_ADDRS, f"at most {MAX_ADDRS} peers")
        for e in p["peers"]:
            _need(isinstance(e, dict) and set(e) == {"id", "host", "port"}, "peer must be {id,host,port}")
            _need(_str(e["id"]) and _str(e["host"], 1, 255) and _int(e["port"]) and 0 < e["port"] < 65536, "bad peer entry")
    elif mtype in ("inv", "getdata", "notfound"):
        _items(p)
    elif mtype == "tx":
        _keys(p, ("tx",))
        _need(isinstance(p["tx"], dict), "tx must be an object")
    elif mtype == "block":
        _keys(p, ("block",))
        _need(isinstance(p["block"], dict), "block must be an object")
    elif mtype in ("ping", "pong"):
        _keys(p, ("nonce",))
        _need(_int(p["nonce"]), "nonce must be a non-negative integer")
    elif mtype == "error":
        _keys(p, ("code", "reason"))
        _need(_str(p["code"], 1, 64) and _str(p["reason"], 0, 500), "bad error fields")
