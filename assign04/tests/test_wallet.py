import pytest

from conftest import make_wallet
from utxolab import Ledger, LedgerError
from utxolab.selection import select_coins
from utxolab.tx import MAX_VALUE, Output, OutPoint


def ledger_with(wallet, values):
    led = Ledger()
    for i, v in enumerate(values):
        led.issue([Output(v, wallet.pkhs[0])], f"g{i}")
    return led


def test_largest_first_picks_biggest_coins(alice):
    led = ledger_with(alice, [10, 50, 20, 5])
    chosen, total = select_coins(alice.spendable(led), 55)
    assert [o.value for _, o in chosen] == [50, 20] and total == 70


def test_smallest_first_strategy_consolidates():
    w = make_wallet("s", strategy="smallest_first")
    led = ledger_with(w, [10, 50, 20, 5])
    tx = w.build_payment(led, w.new_address(), 30, fee=0)
    assert sorted(led.get(op).value for op in tx.body.inputs) == [5, 10, 20]


def test_selection_is_deterministic_with_ties(alice):
    led = ledger_with(alice, [10, 10, 10, 10])
    a, _ = select_coins(alice.spendable(led), 25)
    b, _ = select_coins(list(reversed(alice.spendable(led))), 25)
    assert [op for op, _ in a] == [op for op, _ in b]


def test_unknown_strategy_rejected(alice):
    with pytest.raises(LedgerError) as e:
        select_coins([], 1, "random")
    assert e.value.code == "bad_strategy"


def test_change_is_exact(alice, bob):
    led = ledger_with(alice, [40, 70])
    tx = alice.build_payment(led, bob.primary_address, 85, fee=2)
    total_in = sum(led.get(op).value for op in tx.body.inputs)
    assert total_in == 110
    assert sum(o.value for o in tx.body.outputs) == total_in - 2
    assert tx.body.outputs[-1].pkh == alice.pkhs[0] and tx.body.outputs[-1].value == 23


def test_change_can_go_to_a_chosen_address(alice, bob):
    led = ledger_with(alice, [40, 70])
    fresh = alice.new_address()
    tx = alice.build_payment(led, bob.primary_address, 85, fee=2, change_address=fresh)
    led.apply(tx)
    assert led.balance_of(alice.pkhs[1]) == 23 and led.balance_of(alice.pkhs[0]) == 0


def test_insufficient_funds(alice, bob):
    led = ledger_with(alice, [40, 70])
    with pytest.raises(LedgerError) as e:
        alice.build_payment(led, bob.primary_address, 109, fee=2)
    assert e.value.code == "insufficient_funds"


def test_wallet_never_spends_other_peoples_coins(alice, bob):
    led = ledger_with(alice, [40])
    led.issue([Output(500, bob.pkhs[0])], "bob")
    with pytest.raises(LedgerError):
        alice.build_payment(led, bob.primary_address, 100, fee=0)


def test_multi_recipient_payment(alice, bob, carol):
    led = ledger_with(alice, [40, 70])
    tx = alice.build_payments(led, [(bob.primary_address, 50), (carol.primary_address, 40)], fee=1)
    led.apply(tx)
    assert (bob.balance(led), carol.balance(led), alice.balance(led)) == (50, 40, 19)


@pytest.mark.parametrize("amount,fee,code", [(0, 0, "bad_amount"), (-3, 0, "bad_amount"),
                                             (1.5, 0, "bad_amount"), (True, 0, "bad_amount"),
                                             (5, -1, "bad_fee"), (MAX_VALUE, 1, "value_overflow")])
def test_bad_amounts_and_fees(alice, bob, amount, fee, code):
    led = ledger_with(alice, [40, 70])
    with pytest.raises(LedgerError) as e:
        alice.build_payment(led, bob.primary_address, amount, fee)
    assert e.value.code == code


def test_bad_or_foreign_network_address_rejected(alice):
    led = ledger_with(alice, [40])
    other = make_wallet("x")
    mainnet = type(other)(network_id="course-mainnet")
    mainnet.new_address()
    for addr in (mainnet.primary_address, "not-an-address"):
        with pytest.raises(LedgerError) as e:
            alice.build_payment(led, addr, 5, fee=0)
        assert e.value.code == "bad_address"


def test_wallet_does_not_change_ledger_while_building(alice, bob):
    led = ledger_with(alice, [40, 70])
    h = led.state_hash()
    alice.build_payment(led, bob.primary_address, 85, fee=2)
    assert led.state_hash() == h
