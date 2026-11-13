"""Block header and block: byte layout, hashing, strict JSON.

Header (112 bytes, fixed layout, all integers big-endian):

    offset  size  field
         0     4  version       must be 1
         4    32  prev_hash     block hash of the parent (32 zero bytes for genesis)
        36    32  merkle_root   Merkle root of the txids (see merkle.py)
        68     8  timestamp     seconds since the Unix epoch
        76    32  target        PoW target, 256-bit unsigned integer
       108     4  nonce

    block_hash = SHA-256(SHA-256(header_bytes))

A block is {"header": {...}, "txs": [signed tx, ...]}. txs[0] is the coinbase.
"""

from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass
from functools import cached_property
from typing import Any, Iterable

from .canonical import parse_strict
from .errors import BlockError, WalletError
from .merkle import merkle_root
from .proofofwork import MAX_NONCE, hash_to_int, sha256d, work_from_target
from .tx import SignedTx

HEADER_SIZE = 112
BLOCK_VERSION = 1
MAX_TIMESTAMP = 2**53 - 1
ZERO_HASH = b"\x00" * 32
HEADER_FIELDS = (("version", 0, 4), ("prev_hash", 4, 36), ("merkle_root", 36, 68),
                 ("timestamp", 68, 76), ("target", 76, 108), ("nonce", 108, 112))
_HEX64 = re.compile(r"[0-9a-f]{64}")


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _exact(obj: Any, keys: Iterable[str], what: str) -> dict:
    if not isinstance(obj, dict):
        raise BlockError("malformed_block", f"{what} must be a JSON object")
    want, have = set(keys), set(obj)
    if want != have:
        raise BlockError("malformed_block", f"{what} must have exactly the fields {sorted(want)}"
                         + (f" (missing: {sorted(want - have)})" if want - have else "")
                         + (f" (unexpected: {sorted(have - want)})" if have - want else ""))
    return obj


def _hex32(v: Any, what: str) -> bytes:
    if not isinstance(v, str) or not _HEX64.fullmatch(v):
        raise BlockError("malformed_block", f"{what} must be 64 lowercase hex characters")
    return bytes.fromhex(v)


@dataclass(frozen=True)
class BlockHeader:
    version: int
    prev_hash: bytes
    merkle_root: bytes
    timestamp: int
    target: int
    nonce: int

    def __post_init__(self) -> None:
        if not _is_int(self.version) or self.version != BLOCK_VERSION:
            raise BlockError("malformed_header", f"unsupported block version {self.version!r}")
        for name in ("prev_hash", "merkle_root"):
            v = getattr(self, name)
            if not isinstance(v, bytes) or len(v) != 32:
                raise BlockError("malformed_header", f"{name} must be exactly 32 bytes")
        if not _is_int(self.timestamp) or not 0 <= self.timestamp <= MAX_TIMESTAMP:
            raise BlockError("malformed_header", f"timestamp must be an integer in 0..{MAX_TIMESTAMP}")
        if not _is_int(self.target) or not 0 < self.target < 2**256:
            raise BlockError("malformed_header", "target must be an integer in 1..2**256-1")
        if not _is_int(self.nonce) or not 0 <= self.nonce <= MAX_NONCE:
            raise BlockError("malformed_header", f"nonce must be an integer in 0..{MAX_NONCE}")

    def serialize(self) -> bytes:
        return (struct.pack(">I", self.version) + self.prev_hash + self.merkle_root
                + struct.pack(">Q", self.timestamp) + self.target.to_bytes(32, "big")
                + struct.pack(">I", self.nonce))

    @classmethod
    def parse(cls, raw: bytes) -> "BlockHeader":
        if len(raw) != HEADER_SIZE:
            raise BlockError("malformed_header", f"header must be {HEADER_SIZE} bytes, got {len(raw)}")
        return cls(struct.unpack(">I", raw[0:4])[0], raw[4:36], raw[36:68],
                   struct.unpack(">Q", raw[68:76])[0], int.from_bytes(raw[76:108], "big"),
                   struct.unpack(">I", raw[108:112])[0])

    @cached_property
    def hash(self) -> bytes:
        return sha256d(self.serialize())

    @property
    def hash_hex(self) -> str:
        return self.hash.hex()

    @property
    def work(self) -> int:
        return work_from_target(self.target)

    def with_nonce(self, nonce: int) -> "BlockHeader":
        return BlockHeader(self.version, self.prev_hash, self.merkle_root, self.timestamp,
                           self.target, nonce)

    def to_obj(self) -> dict:
        return {"version": self.version, "prev_hash": self.prev_hash.hex(),
                "merkle_root": self.merkle_root.hex(), "timestamp": self.timestamp,
                "target": f"{self.target:064x}", "nonce": self.nonce}

    @classmethod
    def from_obj(cls, obj: Any) -> "BlockHeader":
        obj = _exact(obj, ("version", "prev_hash", "merkle_root", "timestamp", "target", "nonce"), "header")
        return cls(obj["version"], _hex32(obj["prev_hash"], "prev_hash"),
                   _hex32(obj["merkle_root"], "merkle_root"), obj["timestamp"],
                   int.from_bytes(_hex32(obj["target"], "target"), "big"), obj["nonce"])


@dataclass(frozen=True)
class Block:
    header: BlockHeader
    txs: tuple[SignedTx, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "txs", tuple(self.txs))

    @property
    def hash(self) -> bytes:
        return self.header.hash

    @property
    def hash_hex(self) -> str:
        return self.header.hash_hex

    @property
    def txids(self) -> list[str]:
        return [t.txid for t in self.txs]

    def computed_merkle_root(self) -> bytes:
        return merkle_root([bytes.fromhex(t.txid) for t in self.txs])

    def to_obj(self) -> dict:
        return {"header": self.header.to_obj(), "txs": [t.to_obj() for t in self.txs]}

    def to_json(self, pretty: bool = True) -> str:
        return json.dumps(self.to_obj(), indent=2 if pretty else None, sort_keys=True,
                          separators=None if pretty else (",", ":"))

    @classmethod
    def from_obj(cls, obj: Any) -> "Block":
        try:
            obj = _exact(obj, ("header", "txs"), "block")
            if not isinstance(obj["txs"], list):
                raise BlockError("malformed_block", "txs must be a list")
            return cls(BlockHeader.from_obj(obj["header"]),
                       tuple(SignedTx.from_obj(t) for t in obj["txs"]))
        except BlockError:
            raise
        except WalletError as exc:
            raise BlockError("malformed_block", str(exc)) from None

    @classmethod
    def from_json(cls, raw: "bytes | str") -> "Block":
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        try:
            obj = parse_strict(raw)
        except WalletError as exc:
            raise BlockError("malformed_block", str(exc)) from None
        return cls.from_obj(obj)


def hexdump_header(header: BlockHeader) -> str:
    """Field-by-field and xxd-style dump of the 112 header bytes, plus hash and PoW check."""
    raw = header.serialize()
    lines = [f"{'field':<12}{'offset':>6}{'size':>6}  value (hex)", "-" * 78]
    for name, a, b in HEADER_FIELDS:
        shown = raw[a:b].hex()
        note = ""
        if name == "version":
            note = f"   (= {header.version})"
        elif name == "timestamp":
            note = f"   (= {header.timestamp})"
        elif name == "nonce":
            note = f"   (= {header.nonce})"
        lines.append(f"{name:<12}{a:>6}{b - a:>6}  {shown}{note}")
    lines += ["", f"raw header, {len(raw)} bytes:"]
    for off in range(0, len(raw), 16):
        chunk = raw[off:off + 16]
        lines.append(f"{off:04x}  {' '.join(f'{x:02x}' for x in chunk)}")
    digest = header.hash
    zeros = 256 - hash_to_int(digest).bit_length()
    lines += ["", f"block hash = SHA-256(SHA-256(header)) = {digest.hex()}",
              f"target                                  = {header.target:064x}",
              f"hash <= target: {hash_to_int(digest) <= header.target}   "
              f"(hash has {zeros} leading zero bits; work of this block = {header.work})"]
    return "\n".join(lines)
