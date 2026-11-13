import copy

import pytest

from conftest import spend
from utxolab import Ledger, LedgerError
from utxolab.keys import GROUP_ORDER_L
from utxolab.tx import MAX_VALUE, Output, OutPoint, SignedTx, TxBody, Witness, sign_body


def coins(ledger, wallet):
    return {o.value: op for op, o in wallet.spendable(ledger)}


def rejected(ledger, tx, code):
    before = ledger.state_hash()
    with pytest.raises(LedgerError) as e:
        ledger.apply(tx)
    assert e.value.code == code, e.value
    assert ledger.state_hash() == before, "a rejected transaction changed the ledger"
    return e.value


def test_assignment_scenario_alice_pays_bob(alice, bob, funded):
    tx = alice.build_payment(funded, bob.primary_address, 85, fee=2)
    assert [o.value for o in tx.body.outputs] == [85, 23]
    r = funded.apply(tx)
    assert r.fee == 2
    assert bob.balance(funded) == 85 and alice.balance(funded) == 23
    assert funded.fees == 2
    funded.check_invariants()


def test_resubmitting_the_same_signed_tx_does_not_pay_twice(alice, bob, funded):
    tx = alice.build_payment(funded, bob.primary_address, 85, fee=2)
    funded.apply(tx)
    rejected(funded, tx, "duplicate_transaction")
    assert bob.balance(funded) == 85


def test_nonexistent_input_rejected(alice, funded):
    tx = spend(alice, funded, [OutPoint("ab" * 32, 0)], [Output(10, alice.pkhs[0])])
    e = rejected(funded, tx, "input_not_found")
    assert "does not exist" in e.reason


def test_nonexistent_index_of_existing_tx_rejected(alice, funded):
    op = next(iter(funded.utxos))
    tx = spend(alice, funded, [OutPoint(op.txid, 7)], [Output(10, alice.pkhs[0])])
    rejected(funded, tx, "input_not_found")


def test_repeated_outpoint_within_one_tx_rejected(alice, funded):
    op = coins(funded, alice)[70]
    tx = spend(alice, funded, [op, op], [Output(140, alice.pkhs[0])])
    rejected(funded, tx, "duplicate_input")


def test_second_spend_of_consumed_output_rejected_with_spender(alice, bob, funded):
    op70 = coins(funded, alice)[70]
    first = alice.build_payment(funded, bob.primary_address, 85, fee=2)
    funded.apply(first)
    again = spend(alice, funded, [op70], [Output(60, bob.pkhs[0])], "respend")
    e = rejected(funded, again, "input_already_spent")
    assert first.txid[:8] in e.reason


def test_bad_signature_after_tampering_rejected(alice, bob, funded):
    tx = alice.build_payment(funded, bob.primary_address, 85, fee=2)
    obj = copy.deepcopy(tx.to_obj())
    obj["body"]["outputs"][0]["value"] = 86
    rejected(funded, obj, "bad_signature")


def test_signature_from_other_message_rejected(alice, bob, funded):
    a = alice.build_payment(funded, bob.primary_address, 85, fee=2)
    b = alice.build_payment(funded, bob.primary_address, 80, fee=2)
    franken = SignedTx(a.body, b.witnesses)       # signatures made for a different body
    rejected(funded, franken, "bad_signature")


def test_wrong_key_rejected(alice, mallory, funded):
    op = coins(funded, alice)[70]
    tx = spend(mallory, funded, [op], [Output(69, mallory.pkhs[0])])
    rejected(funded, tx, "pubkey_hash_mismatch")


def test_noncanonical_signature_rejected(alice, bob, funded):
    tx = alice.build_payment(funded, bob.primary_address, 85, fee=2)
    w = tx.witnesses[0]
    s = int.from_bytes(w.signature[32:], "little") + GROUP_ORDER_L      # same math, malleable encoding
    forged = Witness(w.public_key, w.signature[:32] + s.to_bytes(32, "little"))
    rejected(funded, SignedTx(tx.body, (forged,) + tx.witnesses[1:]), "noncanonical_signature")


def test_witness_count_mismatch_rejected(alice, bob, funded):
    tx = alice.build_payment(funded, bob.primary_address, 85, fee=2)
    rejected(funded, SignedTx(tx.body, tx.witnesses[:1]), "bad_witness")
    rejected(funded, SignedTx(tx.body, tx.witnesses + tx.witnesses[:1]), "bad_witness")


def test_negative_and_zero_values_rejected(alice, bob, funded):
    obj = copy.deepcopy(alice.build_payment(funded, bob.primary_address, 85, fee=2).to_obj())
    for bad in (-5, 0):
        o = copy.deepcopy(obj)
        o["body"]["outputs"][0]["value"] = bad
        rejected(funded, o, "bad_output_value")


def test_sum_overflow_rejected(alice, funded):
    op = coins(funded, alice)[70]
    tx = spend(alice, funded, [op], [Output(MAX_VALUE, alice.pkhs[0]), Output(MAX_VALUE, alice.pkhs[0])])
    rejected(funded, tx, "value_overflow")


def test_excessive_value_and_incorrect_change_rejected(alice, bob, funded):
    op = coins(funded, alice)[70]
    tx = spend(alice, funded, [op], [Output(60, bob.pkhs[0]), Output(11, alice.pkhs[0])])   # 71 > 70
    e = rejected(funded, tx, "outputs_exceed_inputs")
    assert "1 unit" in e.reason


def test_overpaying_the_fee_is_valid_and_burned(alice, bob, funded):
    op = coins(funded, alice)[70]
    tx = spend(alice, funded, [op], [Output(60, bob.pkhs[0]), Output(5, alice.pkhs[0])])    # fee 5
    assert funded.apply(tx).fee == 5


def test_zero_fee_is_allowed_and_exact_payment_has_no_change(alice, bob, funded):
    tx = alice.build_payment(funded, bob.primary_address, 110, fee=0)
    assert len(tx.body.outputs) == 1
    assert funded.apply(tx).fee == 0 and alice.balance(funded) == 0


def test_wrong_network_rejected(alice, funded):
    other = TxBody("course-mainnet", (coins(funded, alice)[70],), (Output(10, alice.pkhs[0]),), "x")
    rejected(funded, sign_body(other, [alice._keys[alice.pkhs[0]]]), "wrong_network")


def test_transaction_with_no_inputs_cannot_create_value(alice, funded):
    body = TxBody(funded.network_id, (), (Output(1000, alice.pkhs[0]),), "free money")
    rejected(funded, SignedTx(body, ()), "no_inputs")


def test_chained_spend_of_new_output_works(alice, bob, carol, funded):
    funded.apply(alice.build_payment(funded, bob.primary_address, 85, fee=2))
    funded.apply(bob.build_payment(funded, carol.primary_address, 30, fee=1))
    assert (alice.balance(funded), bob.balance(funded), carol.balance(funded)) == (23, 54, 30)
    assert funded.fees == 3
    funded.check_invariants()


def test_validate_does_not_mutate(alice, bob, funded):
    tx = alice.build_payment(funded, bob.primary_address, 85, fee=2)
    h = funded.state_hash()
    plan = funded.validate(tx)
    assert plan.fee == 2 and funded.state_hash() == h


def test_issue_rejects_overflow_and_duplicates(alice):
    led = Ledger()
    led.issue([Output(5, alice.pkhs[0])], "a")
    with pytest.raises(LedgerError) as e:
        led.issue([Output(5, alice.pkhs[0])], "a")
    assert e.value.code == "duplicate_transaction"
    with pytest.raises(LedgerError) as e:
        led.issue([Output(MAX_VALUE, alice.pkhs[0])], "big")
    assert e.value.code == "value_overflow"
