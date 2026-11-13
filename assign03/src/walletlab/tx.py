"""Canonical transaction, signing message, signed envelope and verification.

Transaction (all seven fields required, no others allowed):
    version       int, must be 1
    network_id    string, a known network
    sender        string, address on that network
    recipient     string, address on that network
    amount_units  int, 1 .. 2**53-1, smallest unit (no decimals)
    nonce         int, 0 .. 2**53-1, per-sender counter
    memo_hash     string, 64 lowercase hex (SHA-256 of the off-chain memo)

Signed bytes = DOMAIN_TAG || canonical_json(transaction)
Envelope     = {"transaction": {...}, "public_key": hex32, "signature": hex64}
See docs/TX_FORMAT.md for the byte-level description.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from typing import Any

from . import keys
from .address import address_from_pubkey, check_address, version_byte
from .canonical import canonicalize_value, parse_strict
from .errors import WalletError

TX_VERSION = 1
MAX_INT = 2**53 - 1
DOMAIN_TAG = b"walletlab/tx/v1\x00"
TX_FIELDS = ("version", "network_id", "sender", "recipient", "amount_units", "nonce", "memo_hash")
ENVELOPE_FIELDS = ("transaction", "public_key", "signature")


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _lower_hex(v: Any, nbytes: int) -> bool:
    return isinstance(v, str) and len(v) == 2 * nbytes and keys._is_lower_hex(v)


def memo_hash(memo: str) -> str:
    """Helper: SHA-256 of the UTF-8 memo, as lowercase hex."""
    return hashlib.sha256(memo.encode("utf-8")).hexdigest()


def validate_tx(tx: Any, expected_network: str | None = None) -> dict:
    """Strict schema check. Raises WalletError with a specific reason."""
    if not isinstance(tx, dict):
        raise WalletError("transaction must be a JSON object")
    missing = [f for f in TX_FIELDS if f not in tx]
    extra = [f for f in tx if f not in TX_FIELDS]
    if missing:
        raise WalletError(f"transaction missing field(s): {', '.join(missing)}")
    if extra:
        raise WalletError(f"transaction has unknown field(s): {', '.join(sorted(extra))}")
    if not _is_int(tx["version"]) or tx["version"] != TX_VERSION:
        raise WalletError(f"unsupported transaction version {tx['version']!r}")
    net = tx["network_id"]
    if not isinstance(net, str):
        raise WalletError("network_id must be a string")
    version_byte(net)  # unknown network -> error
    if expected_network is not None and net != expected_network:
        raise WalletError(f"wrong network: transaction is for {net!r}, expected {expected_network!r}")
    for role in ("sender", "recipient"):
        check_address(tx[role], expected_network=net)  # checksum + same network
    if not _is_int(tx["amount_units"]) or not 1 <= tx["amount_units"] <= MAX_INT:
        raise WalletError(f"amount_units must be an integer in 1..{MAX_INT}")
    if not _is_int(tx["nonce"]) or not 0 <= tx["nonce"] <= MAX_INT:
        raise WalletError(f"nonce must be an integer in 0..{MAX_INT}")
    if not _lower_hex(tx["memo_hash"], 32):
        raise WalletError("memo_hash must be 64 lowercase hex characters")
    return tx


def signing_bytes(tx: dict) -> bytes:
    """The exact bytes that are signed (domain tag + canonical JSON)."""
    return DOMAIN_TAG + canonicalize_value(tx)


def make_envelope(tx: dict, public_key: bytes, signature: bytes) -> dict:
    return {"transaction": tx, "public_key": public_key.hex(), "signature": signature.hex()}


def sign_transaction(raw_tx: bytes, private_key, expected_network: str | None = None) -> dict:
    tx = validate_tx(parse_strict(raw_tx), expected_network)
    pub = keys.public_bytes(private_key)
    if address_from_pubkey(pub, tx["network_id"]) != tx["sender"]:
        raise WalletError("this key does not own the transaction's sender address")
    sig = keys.sign(private_key, signing_bytes(tx))
    return make_envelope(tx, pub, sig)


# ---- replay state -----------------------------------------------------------
def load_state(path: str) -> dict[str, int]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "rb") as fh:
            data = json.loads(fh.read().decode("utf-8"))
        last = data["last_nonce"]
        if not all(isinstance(k, str) and _is_int(v) for k, v in last.items()):
            raise ValueError
        return dict(last)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise WalletError(f"state file {path} is unreadable or malformed") from None


def save_state(path: str, last: dict[str, int]) -> None:
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".state-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"last_nonce": last}, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


# ---- verification ---------------------------------------------------------
def verify_envelope(
    raw: bytes,
    expected_network: str,
    last_nonce: dict[str, int] | None = None,
) -> dict:
    """Verify a signed envelope independently of the signer's software.

    Needs only the envelope bytes, the network name and (optionally) the replay
    state. Returns the validated transaction, or raises WalletError naming the
    first failed check. Whitespace and key order in `raw` are irrelevant.
    """
    env = parse_strict(raw)
    if not isinstance(env, dict):
        raise WalletError("envelope must be a JSON object")
    if sorted(env) != sorted(ENVELOPE_FIELDS):
        raise WalletError(f"envelope must have exactly the fields {', '.join(ENVELOPE_FIELDS)}")

    tx = validate_tx(env["transaction"], expected_network)

    pub_hex, sig_hex = env["public_key"], env["signature"]
    if not _lower_hex(pub_hex, 32):
        raise WalletError("public_key must be 64 lowercase hex characters")
    if not _lower_hex(sig_hex, 64):
        raise WalletError("malformed signature: must be 128 lowercase hex characters")
    pub, sig = bytes.fromhex(pub_hex), bytes.fromhex(sig_hex)
    if not keys.signature_is_canonical(sig):
        raise WalletError("non-canonical signature encoding (scalar S is not reduced mod L)")

    if address_from_pubkey(pub, tx["network_id"]) != tx["sender"]:
        raise WalletError("wrong signer: public key does not match the sender address")

    if not keys.verify(pub, signing_bytes(tx), sig):
        raise WalletError("signature does not verify (a signed field was changed, or wrong key)")

    if last_nonce is not None:
        prev = last_nonce.get(tx["sender"])
        if prev is not None and tx["nonce"] <= prev:
            raise WalletError(
                f"replayed or stale nonce: {tx['nonce']} <= last accepted {prev} for this sender"
            )
    return tx
