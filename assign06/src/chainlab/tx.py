"""Transaction data model: outpoints, outputs, canonical bytes, txid, signatures.

Body (what is identified and signed) -- all five fields required, no others:
    version      int, must be 1
    network_id   string, a known network
    inputs       list of {"txid": 64 lowercase hex, "index": int}      (outpoints)
    outputs      list of {"value": int, "lock": {"type": "p2pkh", "pkh": 40 lowercase hex}}
    memo         string, <= 64 chars (makes otherwise identical issuance txs distinct)

Signed transaction = {"body": <body>, "witnesses": [ {"public_key": hex64, "signature": hex128}, ... ]}
exactly one witness per input, in input order.

Bytes and identifiers:
    canonical(body) = Assignment-1 canonical JSON of the body (sorted keys, no whitespace, ints only)
    txid            = SHA-256( "utxolab/txid/v1\\0" || canonical(body) )      -> 64 hex
    signing bytes   = "utxolab/sig/v1\\0"  || canonical(body)

Signatures and public keys are NOT part of the txid (like SegWit's txid), so
re-encoding a witness can never change a transaction's identity.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import cached_property
from typing import Any, Iterable, Sequence

from . import keys
from .address import PKH_LEN, PUBKEY_LEN, version_byte
from .canonical import canonicalize_value, parse_strict
from .errors import LedgerError, WalletError

TX_VERSION = 1
MAX_VALUE = 2**53 - 1          # largest value of one output AND of any sum (no overflow)
MAX_IO = 1000                  # max inputs / outputs per transaction
MAX_INDEX = 2**32 - 1
MAX_MEMO = 64
DOMAIN_TXID = b"utxolab/txid/v1\x00"
DOMAIN_SIG = b"utxolab/sig/v1\x00"
BODY_FIELDS = ("version", "network_id", "inputs", "outputs", "memo")


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _lower_hex(v: Any, nbytes: int) -> bool:
    return (isinstance(v, str) and len(v) == 2 * nbytes
            and all(c in "0123456789abcdef" for c in v))


def _exact_keys(obj: Any, keys_: Iterable[str], what: str, code: str = "malformed_tx") -> dict:
    if not isinstance(obj, dict):
        raise LedgerError(code, f"{what} must be a JSON object")
    want = set(keys_)
    have = set(obj)
    if have != want:
        missing, extra = sorted(want - have), sorted(have - want)
        raise LedgerError(code, f"{what} must have exactly the fields {sorted(want)}"
                          + (f" (missing: {missing})" if missing else "")
                          + (f" (unexpected: {extra})" if extra else ""))
    return obj


# ------------------------------------------------------------------ outpoints
@dataclass(frozen=True, order=True)
class OutPoint:
    """Reference to one output of one transaction: transaction_id + output_index."""
    txid: str
    index: int

    def __post_init__(self) -> None:
        if not _lower_hex(self.txid, 32):
            raise LedgerError("malformed_tx", "outpoint txid must be 64 lowercase hex characters")
        if not _is_int(self.index) or not 0 <= self.index <= MAX_INDEX:
            raise LedgerError("malformed_tx", f"outpoint index must be an integer in 0..{MAX_INDEX}")

    def __str__(self) -> str:
        return f"{self.txid}:{self.index}"

    def short(self) -> str:
        return f"{self.txid[:8]}:{self.index}"

    def to_obj(self) -> dict:
        return {"txid": self.txid, "index": self.index}

    @classmethod
    def from_obj(cls, obj: Any) -> "OutPoint":
        obj = _exact_keys(obj, ("txid", "index"), "input")
        return cls(obj["txid"], obj["index"])

    @classmethod
    def parse(cls, text: str) -> "OutPoint":
        txid, sep, idx = text.partition(":")
        if not sep or not idx.isdigit():
            raise LedgerError("malformed_tx", f"bad outpoint {text!r}; expected <txid>:<index>")
        return cls(txid, int(idx))


# -------------------------------------------------------------------- outputs
@dataclass(frozen=True)
class Output:
    """An amount (integer units) plus its locking condition: pay-to-public-key-hash."""
    value: int
    pkh: bytes

    def __post_init__(self) -> None:
        if not _is_int(self.value):
            raise LedgerError("bad_output_value", f"output value must be an integer, got {self.value!r}")
        if self.value < 0:
            raise LedgerError("bad_output_value", f"output value is negative ({self.value})")
        if self.value == 0:
            raise LedgerError("bad_output_value", "output value is zero; outputs must carry at least 1 unit")
        if self.value > MAX_VALUE:
            raise LedgerError("bad_output_value", f"output value {self.value} exceeds the maximum {MAX_VALUE}")
        if not isinstance(self.pkh, bytes) or len(self.pkh) != PKH_LEN:
            raise LedgerError("bad_lock", f"locking pubkey hash must be exactly {PKH_LEN} bytes")

    def to_obj(self) -> dict:
        return {"value": self.value, "lock": {"type": "p2pkh", "pkh": self.pkh.hex()}}

    @classmethod
    def from_obj(cls, obj: Any) -> "Output":
        obj = _exact_keys(obj, ("value", "lock"), "output")
        lock = _exact_keys(obj["lock"], ("type", "pkh"), "output lock", "bad_lock")
        if lock["type"] != "p2pkh":
            raise LedgerError("bad_lock", f"unsupported lock type {lock['type']!r}; only 'p2pkh'")
        if not _lower_hex(lock["pkh"], PKH_LEN):
            raise LedgerError("bad_lock", f"lock pkh must be {2 * PKH_LEN} lowercase hex characters")
        return cls(obj["value"], bytes.fromhex(lock["pkh"]))


# ----------------------------------------------------------------------- body
@dataclass(frozen=True)
class TxBody:
    network_id: str
    inputs: tuple[OutPoint, ...]
    outputs: tuple[Output, ...]
    memo: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", tuple(self.inputs))
        object.__setattr__(self, "outputs", tuple(self.outputs))
        try:
            version_byte(self.network_id)
        except WalletError as exc:
            raise LedgerError("unknown_network", str(exc)) from None
        if not isinstance(self.memo, str) or len(self.memo) > MAX_MEMO:
            raise LedgerError("malformed_tx", f"memo must be a string of at most {MAX_MEMO} characters")
        if len(self.inputs) > MAX_IO or len(self.outputs) > MAX_IO:
            raise LedgerError("malformed_tx", f"at most {MAX_IO} inputs and {MAX_IO} outputs")
        if not self.outputs:
            raise LedgerError("no_outputs", "a transaction must create at least one output")

    def to_obj(self) -> dict:
        return {"version": TX_VERSION, "network_id": self.network_id,
                "inputs": [i.to_obj() for i in self.inputs],
                "outputs": [o.to_obj() for o in self.outputs], "memo": self.memo}

    @cached_property
    def canonical_bytes(self) -> bytes:
        return canonicalize_value(self.to_obj())

    @cached_property
    def txid(self) -> str:
        return hashlib.sha256(DOMAIN_TXID + self.canonical_bytes).hexdigest()

    @property
    def signing_bytes(self) -> bytes:
        return DOMAIN_SIG + self.canonical_bytes

    @classmethod
    def from_obj(cls, obj: Any) -> "TxBody":
        obj = _exact_keys(obj, BODY_FIELDS, "transaction body")
        if not _is_int(obj["version"]) or obj["version"] != TX_VERSION:
            raise LedgerError("unsupported_version", f"unsupported transaction version {obj['version']!r}")
        if not isinstance(obj["network_id"], str):
            raise LedgerError("malformed_tx", "network_id must be a string")
        if not isinstance(obj["inputs"], list) or not isinstance(obj["outputs"], list):
            raise LedgerError("malformed_tx", "inputs and outputs must be lists")
        return cls(obj["network_id"], tuple(OutPoint.from_obj(i) for i in obj["inputs"]),
                   tuple(Output.from_obj(o) for o in obj["outputs"]), obj["memo"])


# -------------------------------------------------------------------- witness
@dataclass(frozen=True)
class Witness:
    public_key: bytes
    signature: bytes

    def to_obj(self) -> dict:
        return {"public_key": self.public_key.hex(), "signature": self.signature.hex()}

    @classmethod
    def from_obj(cls, obj: Any) -> "Witness":
        obj = _exact_keys(obj, ("public_key", "signature"), "witness", "bad_witness")
        if not _lower_hex(obj["public_key"], PUBKEY_LEN):
            raise LedgerError("bad_witness", "public_key must be 64 lowercase hex characters")
        if not _lower_hex(obj["signature"], keys.SIGNATURE_LEN):
            raise LedgerError("bad_witness", "signature must be 128 lowercase hex characters")
        return cls(bytes.fromhex(obj["public_key"]), bytes.fromhex(obj["signature"]))


@dataclass(frozen=True)
class SignedTx:
    body: TxBody
    witnesses: tuple[Witness, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "witnesses", tuple(self.witnesses))

    @property
    def txid(self) -> str:
        return self.body.txid

    def to_obj(self) -> dict:
        return {"body": self.body.to_obj(), "witnesses": [w.to_obj() for w in self.witnesses]}

    @classmethod
    def from_obj(cls, obj: Any) -> "SignedTx":
        obj = _exact_keys(obj, ("body", "witnesses"), "signed transaction")
        if not isinstance(obj["witnesses"], list):
            raise LedgerError("bad_witness", "witnesses must be a list")
        return cls(TxBody.from_obj(obj["body"]), tuple(Witness.from_obj(w) for w in obj["witnesses"]))

    @classmethod
    def from_json(cls, raw: bytes | str) -> "SignedTx":
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        try:
            obj = parse_strict(raw)
        except LedgerError:
            raise
        except WalletError as exc:
            raise LedgerError("malformed_json", str(exc)) from None
        return cls.from_obj(obj)


def coerce_signed(tx: "SignedTx | dict | bytes | str") -> SignedTx:
    """Accept a SignedTx, a parsed dict, or JSON text/bytes."""
    if isinstance(tx, SignedTx):
        return tx
    if isinstance(tx, dict):
        return SignedTx.from_obj(tx)
    if isinstance(tx, (bytes, str)):
        return SignedTx.from_json(tx)
    raise LedgerError("malformed_tx", f"cannot interpret {type(tx).__name__} as a transaction")


def sign_body(body: TxBody, private_keys: Sequence) -> SignedTx:
    """Sign ``body`` once per input; ``private_keys[i]`` must own input i."""
    if len(private_keys) != len(body.inputs):
        raise LedgerError("bad_witness", "need exactly one private key per input")
    msg = body.signing_bytes
    wits = tuple(Witness(keys.public_bytes(k), keys.sign(k, msg)) for k in private_keys)
    return SignedTx(body, wits)
