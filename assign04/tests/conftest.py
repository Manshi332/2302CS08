import hashlib

import pytest

from utxolab import Ledger, Wallet
from utxolab.tx import Output, TxBody, sign_body


def make_wallet(name: str, **kw) -> Wallet:
    """TEST-ONLY deterministic wallet."""
    return Wallet.from_seeds([hashlib.sha256(b"test-" + name.encode()).digest()], **kw)


def spend(wallet, ledger, ops, outs, memo="t"):
    """Sign a hand-built body in which every input belongs to wallet's first key."""
    body = TxBody(ledger.network_id, tuple(ops), tuple(outs), memo)
    return sign_body(body, [wallet._keys[wallet.pkhs[0]]] * len(body.inputs))


@pytest.fixture
def alice():
    return make_wallet("alice")


@pytest.fixture
def bob():
    return make_wallet("bob")


@pytest.fixture
def carol():
    return make_wallet("carol")


@pytest.fixture
def mallory():
    return make_wallet("mallory")


@pytest.fixture
def funded(alice):
    """Ledger where Alice owns outputs worth 40 and 70 (the assignment's scenario)."""
    led = Ledger()
    led.issue([Output(40, alice.pkhs[0])], "g1")
    led.issue([Output(70, alice.pkhs[0])], "g2")
    return led
