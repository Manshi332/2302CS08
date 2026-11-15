"""TEST-ONLY deterministic wallets (same derivation as the Assignment 4 demo).

The seed is SHA-256("utxolab-demo-" + name), so `alice` is the same wallet on every
machine and in every run. NEVER use such seeds for anything real.
"""

from __future__ import annotations

import hashlib

from .wallet import Wallet


def demo_wallet(name: str, network_id: str = "course-testnet") -> Wallet:
    return Wallet.from_seeds([hashlib.sha256(b"utxolab-demo-" + name.encode()).digest()], network_id)


def demo_address(name: str, network_id: str = "course-testnet") -> str:
    return demo_wallet(name, network_id).primary_address
