"""Key generation, storage and Ed25519 signing. All curve math is in `cryptography`.

Randomness: Ed25519PrivateKey.generate() draws from the operating system's
CSPRNG (via OpenSSL). Nothing in this project implements its own RNG or curve.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .address import PUBKEY_LEN, address_from_pubkey
from .errors import WalletError

# Order of the Ed25519 base-point group (RFC 8032). Used ONLY to reject
# non-canonical signatures whose scalar half S is >= L (malleable encodings).
GROUP_ORDER_L = 2**252 + 27742317777372353535851937790883648493
SIGNATURE_LEN = 64
SEED_LEN = 32

PRIVATE_WARNING = (
    "TEST-ONLY DEVELOPMENT KEY. Never use for real funds, never commit, never share."
)
_RAW = dict(encoding=serialization.Encoding.Raw)


def generate() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def private_from_seed(seed: bytes) -> Ed25519PrivateKey:
    if len(seed) != SEED_LEN:
        raise WalletError(f"private key seed must be {SEED_LEN} bytes")
    return Ed25519PrivateKey.from_private_bytes(seed)


def seed_bytes(key: Ed25519PrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )


def public_bytes(key: Ed25519PrivateKey | Ed25519PublicKey) -> bytes:
    pub = key.public_key() if isinstance(key, Ed25519PrivateKey) else key
    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


# ---- signing / verifying ---------------------------------------------------
def sign(key: Ed25519PrivateKey, message: bytes) -> bytes:
    return key.sign(message)  # deterministic (RFC 8032)


def signature_is_canonical(sig: bytes) -> bool:
    return len(sig) == SIGNATURE_LEN and int.from_bytes(sig[32:], "little") < GROUP_ORDER_L


def verify(public_key: bytes, message: bytes, sig: bytes) -> bool:
    """True only for a canonical, valid signature. Never raises on bad input."""
    if len(public_key) != PUBKEY_LEN or not signature_is_canonical(sig):
        return False
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(sig, message)
    except (InvalidSignature, ValueError):
        return False
    return True


# ---- files -----------------------------------------------------------------
def public_record(pub: bytes, network_id: str) -> dict:
    return {
        "algorithm": "ed25519",
        "network_id": network_id,
        "public_key": pub.hex(),
        "address": address_from_pubkey(pub, network_id),
    }


def write_new_file(path: str | Path, text: str, mode: int) -> None:
    """Create `path` exclusively (never overwrite) with the given permission bits."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, mode)
    except FileExistsError:
        raise WalletError(f"{path} already exists; refusing to overwrite") from None
    except OSError as exc:
        raise WalletError(f"cannot create {path}: {exc.strerror or exc}") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    if os.name == "posix":
        os.chmod(path, mode)  # defeat a permissive umask


def write_public(path: str | Path, key: Ed25519PrivateKey, network_id: str) -> None:
    rec = public_record(public_bytes(key), network_id)
    write_new_file(path, json.dumps(rec, indent=2) + "\n", 0o644)


def write_private_dev(path: str | Path, key: Ed25519PrivateKey, network_id: str) -> None:
    rec = {
        "WARNING": PRIVATE_WARNING,
        "algorithm": "ed25519",
        "network_id": network_id,
        "private_key_seed": seed_bytes(key).hex(),
    }
    write_new_file(path, json.dumps(rec, indent=2) + "\n", 0o600)
    print(f"WARNING: wrote UNENCRYPTED private key to {path} (mode 0600).", file=sys.stderr)
    print(f"WARNING: {PRIVATE_WARNING}", file=sys.stderr)


def _read_json(path: str | Path) -> dict:
    try:
        with open(path, "rb") as fh:
            data = json.loads(fh.read().decode("utf-8"))
    except OSError as exc:
        raise WalletError(f"cannot read {path}: {exc.strerror or exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WalletError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise WalletError(f"{path}: expected a JSON object")
    return data


def read_public(path: str | Path) -> tuple[bytes, str]:
    rec = _read_json(path)
    return parse_pubkey_hex(rec.get("public_key")), rec.get("network_id", "")


def parse_pubkey_hex(text) -> bytes:
    if not isinstance(text, str) or len(text) != 2 * PUBKEY_LEN or not _is_lower_hex(text):
        raise WalletError("public key must be 64 lowercase hex characters")
    return bytes.fromhex(text)


def _is_lower_hex(text: str) -> bool:
    return all(c in "0123456789abcdef" for c in text)


def read_private(path: str | Path) -> tuple[Ed25519PrivateKey, str]:
    """Load a development private key; refuse files readable by group/others."""
    if os.name == "posix":
        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
        except OSError as exc:
            raise WalletError(f"cannot read {path}: {exc.strerror or exc}") from exc
        if mode & 0o077:
            raise WalletError(
                f"{path} has permissions {mode:04o}; private key files must be 0600 "
                f"(fix with: chmod 600 {path})"
            )
    rec = _read_json(path)
    seed = rec.get("private_key_seed")
    if not isinstance(seed, str) or len(seed) != 2 * SEED_LEN or not _is_lower_hex(seed):
        raise WalletError(f"{path}: private_key_seed must be 64 lowercase hex characters")
    return private_from_seed(bytes.fromhex(seed)), rec.get("network_id", "")
