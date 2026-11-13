"""Address derivation (documented, version "walletlab-addr-v1").

    pubkey   = 32-byte raw Ed25519 public key
    pkh      = SHA-256(pubkey)[:20]                    public-key hash
    payload  = version_byte || pkh                     21 bytes
    address  = Base58Check(payload)                    checksum = SHA256(SHA256(payload))[:4]

The version byte encodes the network, so a testnet address cannot be
mistaken for a mainnet one (different first character and different byte).
"""

from __future__ import annotations

import hashlib

from .base58 import b58check_decode, b58check_encode
from .errors import WalletError

PKH_LEN = 20
PUBKEY_LEN = 32

NETWORK_VERSION = {
    "course-testnet": 0x6F,
    "course-mainnet": 0x3F,
}
DEFAULT_NETWORK = "course-testnet"


def version_byte(network_id: str) -> int:
    try:
        return NETWORK_VERSION[network_id]
    except KeyError:
        raise WalletError(
            f"unknown network {network_id!r}; known: {', '.join(sorted(NETWORK_VERSION))}"
        ) from None


def network_for_version(version: int) -> str | None:
    for name, v in NETWORK_VERSION.items():
        if v == version:
            return name
    return None


def pubkey_hash(public_key: bytes) -> bytes:
    if len(public_key) != PUBKEY_LEN:
        raise WalletError(f"public key must be {PUBKEY_LEN} bytes, got {len(public_key)}")
    return hashlib.sha256(public_key).digest()[:PKH_LEN]


def address_from_pubkey(public_key: bytes, network_id: str = DEFAULT_NETWORK) -> str:
    return b58check_encode(bytes([version_byte(network_id)]) + pubkey_hash(public_key))


def decode_address(address: str) -> tuple[str, bytes]:
    """Validate checksum/length/version; return (network_id, pubkey_hash)."""
    if not isinstance(address, str):
        raise WalletError("address must be a string")
    payload = b58check_decode(address)
    if len(payload) != 1 + PKH_LEN:
        raise WalletError(f"address payload must be {1 + PKH_LEN} bytes, got {len(payload)}")
    network = network_for_version(payload[0])
    if network is None:
        raise WalletError(f"unknown address version byte 0x{payload[0]:02x}")
    return network, payload[1:]


def check_address(address: str, expected_network: str | None = None) -> str:
    """Validate an address; optionally require a particular network. Returns its network."""
    network, _ = decode_address(address)
    if expected_network is not None and network != expected_network:
        raise WalletError(
            f"address is for {network}, but this operation is on {expected_network}"
        )
    return network
