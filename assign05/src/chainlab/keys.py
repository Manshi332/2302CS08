"""Ed25519 keys and signatures (from Assignment 3). All curve math is in `cryptography`.

Only the cryptographic core is kept here; the key-file helpers of Assignment 3
are not needed because wallets in this assignment are in-memory.
"""

from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .address import PUBKEY_LEN
from .errors import WalletError

# Order of the Ed25519 base-point group (RFC 8032). Used ONLY to reject
# non-canonical signatures whose scalar half S is >= L (malleable encodings).
GROUP_ORDER_L = 2**252 + 27742317777372353535851937790883648493
SIGNATURE_LEN = 64
SEED_LEN = 32


def generate() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def private_from_seed(seed: bytes) -> Ed25519PrivateKey:
    if len(seed) != SEED_LEN:
        raise WalletError(f"private key seed must be {SEED_LEN} bytes")
    return Ed25519PrivateKey.from_private_bytes(seed)


def public_bytes(key: Ed25519PrivateKey | Ed25519PublicKey) -> bytes:
    pub = key.public_key() if isinstance(key, Ed25519PrivateKey) else key
    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


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
