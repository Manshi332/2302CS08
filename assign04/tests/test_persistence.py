import json
import os
import random

import pytest

from conftest import make_wallet
from utxolab import Ledger, LedgerError
from utxolab.tx import Output


def test_save_load_preserves_logical_contents(alice, bob, funded, tmp_path):
    funded.apply(alice.build_payment(funded, bob.primary_address, 85, fee=2))
    p = tmp_path / "s.json"
    digest = funded.save(p)
    back = Ledger.load(p)
    assert back.state_hash() == digest == funded.state_hash()
    assert back.to_state() == funded.to_state()
    back.check_invariants()


def test_pretty_and_compact_files_load_to_same_state(funded, tmp_path):
    funded.save(tmp_path / "a.json")
    funded.save(tmp_path / "b.json", pretty=True)
    assert (tmp_path / "a.json").read_bytes() != (tmp_path / "b.json").read_bytes()
    assert Ledger.load(tmp_path / "a.json").state_hash() == Ledger.load(tmp_path / "b.json").state_hash()


def test_reloaded_ledger_keeps_spent_history_and_keeps_validating(alice, bob, funded, tmp_path):
    first = alice.build_payment(funded, bob.primary_address, 85, fee=2)
    funded.apply(first)
    funded.save(tmp_path / "s.json")
    back = Ledger.load(tmp_path / "s.json")
    with pytest.raises(LedgerError) as e:
        back.apply(first)
    assert e.value.code == "duplicate_transaction"
    back.apply(bob.build_payment(back, alice.primary_address, 10, fee=1))
    back.check_invariants()


def test_tampered_value_detected_by_checksum(funded, tmp_path):
    p = tmp_path / "s.json"
    funded.save(p, pretty=True)
    doc = json.loads(p.read_text())
    key = next(iter(doc["state"]["utxos"]))
    doc["state"]["utxos"][key]["value"] += 1000
    p.write_text(json.dumps(doc))
    with pytest.raises(LedgerError) as e:
        Ledger.load(p)
    assert e.value.code == "snapshot_corrupt"


def test_consistent_but_inflated_snapshot_fails_invariants(funded, tmp_path):
    p = tmp_path / "s.json"
    funded.save(p)
    state = funded.to_state()
    key = next(iter(state["utxos"]))
    state["utxos"][key]["value"] += 1000                      # attacker also fixes the checksum
    import hashlib
    from utxolab.canonical import canonicalize_value
    doc = {"format": "utxolab-snapshot-v1", "state": state,
           "state_sha256": hashlib.sha256(canonicalize_value(state)).hexdigest()}
    p.write_text(json.dumps(doc))
    with pytest.raises(LedgerError) as e:
        Ledger.load(p)
    assert e.value.code == "bad_snapshot" and "issued" in e.value.reason


@pytest.mark.parametrize("content", ["", "not json", "[]", '{"format":"x","state":{},"state_sha256":"0"}'])
def test_garbage_snapshots_rejected(tmp_path, content):
    p = tmp_path / "s.json"
    p.write_text(content)
    with pytest.raises(LedgerError):
        Ledger.load(p)


def test_missing_file(tmp_path):
    with pytest.raises(LedgerError) as e:
        Ledger.load(tmp_path / "nope.json")
    assert e.value.code == "snapshot_unreadable"


def test_save_is_atomic_and_leaves_no_temp_files(funded, tmp_path):
    p = tmp_path / "s.json"
    funded.save(p)
    old = p.read_bytes()
    funded.save(p)
    assert p.read_bytes() == old
    assert [f.name for f in tmp_path.iterdir()] == ["s.json"]


def test_random_activity_conserves_value_and_roundtrips(tmp_path):
    rng = random.Random(7)
    wallets = [make_wallet(f"w{i}") for i in range(4)]
    led = Ledger()
    for w in wallets:
        led.issue([Output(rng.randint(50, 500), w.pkhs[0])], f"seed-{w.primary_address}")
    ok = rejected = 0
    for n in range(150):
        src, dst = rng.sample(wallets, 2)
        try:
            led.apply(src.build_payment(led, dst.primary_address, rng.randint(1, 120), rng.randint(0, 3),
                                        memo=f"n{n}"))
            ok += 1
        except LedgerError as exc:
            assert exc.code == "insufficient_funds"
            rejected += 1
    led.check_invariants()
    assert ok > 50
    assert led.issued == sum(w.balance(led) for w in wallets) + led.fees
    led.save(tmp_path / "r.json")
    assert Ledger.load(tmp_path / "r.json").state_hash() == led.state_hash()
