import hashlib
import json
import os

from utxolab import keys
from utxolab.demo import demo_wallet
from utxolab.tx import DOMAIN_SIG, DOMAIN_TXID, SignedTx

HERE = os.path.dirname(__file__)
VEC = json.load(open(os.path.join(HERE, "..", "vectors", "tx_vectors.json"), encoding="utf-8"))["tx_alice_pays_bob"]


def test_canonical_body_and_txid_known_answer():
    tx = SignedTx.from_obj(VEC["signed_tx"])
    assert tx.body.canonical_bytes.decode() == VEC["canonical_body"]
    assert tx.txid == VEC["txid"]
    # independent recomputation with only hashlib
    assert hashlib.sha256(DOMAIN_TXID + VEC["canonical_body"].encode()).hexdigest() == VEC["txid"]


def test_signatures_verify_and_are_deterministic():
    tx = SignedTx.from_obj(VEC["signed_tx"])
    msg = DOMAIN_SIG + VEC["canonical_body"].encode()
    assert hashlib.sha256(msg).hexdigest() == VEC["signing_bytes_sha256"]
    for w in tx.witnesses:
        assert keys.verify(w.public_key, msg, w.signature)
    alice = demo_wallet("alice")
    assert keys.sign(alice._keys[alice.pkhs[0]], msg) == tx.witnesses[0].signature
