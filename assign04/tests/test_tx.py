import copy
import hashlib
import json

import pytest

from conftest import spend
from utxolab import LedgerError
from utxolab.tx import (DOMAIN_TXID, MAX_VALUE, Output, OutPoint, SignedTx, TxBody, coerce_signed)


def _pay(alice, bob, funded):
    return alice.build_payment(funded, bob.primary_address, 85, fee=2)


def test_outpoint_and_output_model(alice):
    op = OutPoint("ab" * 32, 3)
    assert str(op) == "ab" * 32 + ":3" and OutPoint.parse(str(op)) == op
    out = Output(5, alice.pkhs[0])
    assert Output.from_obj(out.to_obj()) == out
    assert out.to_obj()["lock"] == {"type": "p2pkh", "pkh": alice.pkhs[0].hex()}


def test_txid_is_deterministic_and_matches_independent_computation(alice, bob, funded):
    tx = _pay(alice, bob, funded)
    canon = json.dumps(tx.body.to_obj(), sort_keys=True, separators=(",", ":")).encode()
    assert tx.txid == hashlib.sha256(DOMAIN_TXID + canon).hexdigest()
    assert tx.txid == _pay(alice, bob, funded).txid


def test_txid_excludes_witnesses_but_changes_with_any_body_field(alice, bob, funded):
    tx = _pay(alice, bob, funded)
    stripped = SignedTx(tx.body, ())
    assert stripped.txid == tx.txid                       # witnesses are not part of the id
    obj = copy.deepcopy(tx.body.to_obj())
    obj["memo"] = "x"
    assert TxBody.from_obj(obj).txid != tx.txid
    obj = copy.deepcopy(tx.body.to_obj())
    obj["outputs"][0]["value"] += 1
    assert TxBody.from_obj(obj).txid != tx.txid


def test_json_roundtrip_ignores_whitespace_and_key_order(alice, bob, funded):
    tx = _pay(alice, bob, funded)
    pretty = json.dumps(tx.to_obj(), indent=4, sort_keys=False)
    again = SignedTx.from_json(pretty)
    assert again.txid == tx.txid and again == tx
    reordered = json.dumps(dict(reversed(list(tx.to_obj().items()))))
    assert SignedTx.from_json(reordered) == tx


@pytest.mark.parametrize("mutate,code", [
    (lambda o: o["body"].pop("memo"), "malformed_tx"),
    (lambda o: o["body"].update(extra=1), "malformed_tx"),
    (lambda o: o["body"].update(version=2), "unsupported_version"),
    (lambda o: o["body"].update(network_id="nope"), "unknown_network"),
    (lambda o: o["body"]["outputs"][0].update(value=-1), "bad_output_value"),
    (lambda o: o["body"]["outputs"][0].update(value=0), "bad_output_value"),
    (lambda o: o["body"]["outputs"][0].update(value="5"), "bad_output_value"),
    (lambda o: o["body"]["outputs"][0].update(value=True), "bad_output_value"),
    (lambda o: o["body"]["outputs"][0].update(value=MAX_VALUE + 1), "bad_output_value"),
    (lambda o: o["body"]["outputs"][0]["lock"].update(pkh="zz"), "bad_lock"),
    (lambda o: o["body"]["outputs"][0]["lock"].update(type="p2sh"), "bad_lock"),
    (lambda o: o["body"].update(outputs=[]), "no_outputs"),
    (lambda o: o["body"]["inputs"][0].update(txid="AB" * 32), "malformed_tx"),
    (lambda o: o["witnesses"][0].update(signature="00"), "bad_witness"),
])
def test_schema_rejections(alice, bob, funded, mutate, code):
    obj = copy.deepcopy(_pay(alice, bob, funded).to_obj())
    mutate(obj)
    with pytest.raises(LedgerError) as e:
        coerce_signed(obj)
    assert e.value.code == code


def test_json_floats_and_oversized_ints_are_rejected(alice, bob, funded):
    text = json.dumps(_pay(alice, bob, funded).to_obj())
    with pytest.raises(LedgerError) as e:
        SignedTx.from_json(text.replace('"value": 85', '"value": 85.0'))
    assert e.value.code == "malformed_json"
    with pytest.raises(LedgerError):
        SignedTx.from_json("not json")
