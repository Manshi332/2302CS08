"""The assignment's example scenario plus every acceptance check, as a printed trace.

Deterministic: wallets come from fixed TEST-ONLY seeds, Ed25519 signatures are
deterministic, so the trace, txids and snapshots are identical on every run.
"""

from __future__ import annotations

import copy
import hashlib
import os
from typing import Callable, List, Optional

from . import keys
from .address import address_from_pkh
from .errors import LedgerError
from .ledger import Ledger
from .tx import MAX_VALUE, Output, OutPoint, SignedTx, TxBody, sign_body
from .wallet import Wallet


def demo_wallet(name: str) -> Wallet:
    """TEST-ONLY deterministic wallet (never use such seeds for anything real)."""
    return Wallet.from_seeds([hashlib.sha256(b"utxolab-demo-" + name.encode()).digest()])


def run_scenario(snapshot_dir: Optional[str] = None, emit: Callable[[str], None] = print) -> dict:
    alice, bob, carol, mallory = (demo_wallet(n) for n in ("alice", "bob", "carol", "mallory"))
    names = {}
    for n, w in (("Alice", alice), ("Bob", bob), ("Carol", carol), ("Mallory", mallory)):
        names[w.pkhs[0]] = n
    ledger = Ledger()
    records: List[dict] = []
    snaps: List[str] = []

    def snap(label: str) -> None:
        if snapshot_dir:
            os.makedirs(snapshot_dir, exist_ok=True)
            path = os.path.join(snapshot_dir, f"{len(snaps):02d}_{label}.json")
            ledger.save(path, pretty=True)
            snaps.append(path)

    def who(pkh: bytes) -> str:
        return names.get(pkh, pkh.hex()[:8])

    def describe(tx: SignedTx) -> str:
        ins = ", ".join(f"{op.short()}" for op in tx.body.inputs)
        outs = ", ".join(f"{o.value}->{who(o.pkh)}" for o in tx.body.outputs)
        return f"inputs [{ins}] outputs [{outs}]"

    def attempt(step: str, title: str, tx, expect: str) -> Optional[dict]:
        before = ledger.state_hash()
        rec = {"step": step, "title": title, "expect": expect}
        emit(f"\n[{step}] {title}")
        if isinstance(tx, SignedTx):
            emit(f"    tx {tx.txid[:12]}  {describe(tx)}")
        try:
            r = ledger.apply(tx)
            rec.update(result="ACCEPTED", fee=r.fee, txid=r.txid)
            emit(f"    ACCEPTED  fee={r.fee}  created={[o.short() for o in r.created]}")
        except LedgerError as exc:
            unchanged = ledger.state_hash() == before
            rec.update(result="REJECTED", code=exc.code, reason=exc.reason, state_unchanged=unchanged)
            emit(f"    REJECTED  code={exc.code}")
            emit(f"    reason:   {exc.reason}")
            emit(f"    ledger state unchanged: {'yes' if unchanged else 'NO (BUG)'}")
        rec["code"] = rec.get("code", "")
        records.append(rec)
        return rec

    emit("utxolab trace: Alice, Bob, Carol, Mallory on course-testnet")
    emit("=" * 72)
    emit("\n[0] genesis issuance (the only way value enters the system)")
    for label, w, amt in (("genesis-alice-1", alice, 40), ("genesis-alice-2", alice, 70)):
        r = ledger.issue([Output(amt, w.pkhs[0])], memo=label)
        emit(f"    issued {amt} to Alice  outpoint {r.created[0].short()}")
    snap("genesis")
    emit(f"    Alice balance = {alice.balance(ledger)}   state {ledger.state_hash()[:16]}")
    coin40, coin70 = [op for op, _ in sorted(ledger.outputs_for(alice.pkhs[0]), key=lambda p: p[1].value)]

    # ---- 1. the assignment's example payment
    pay = alice.build_payment(ledger, bob.primary_address, 85, fee=2)
    attempt("1", "Alice pays Bob 85 with fee 2 (spends 40 and 70, change 23)", pay, "accepted")
    snap("alice_paid_bob")
    emit(f"    balances: Alice={alice.balance(ledger)} Bob={bob.balance(ledger)} fees burned={ledger.fees}")

    # ---- 2. replay of the same signed transaction
    attempt("2", "Same signed transaction submitted again", pay, "rejected")
    emit(f"    Bob balance is still {bob.balance(ledger)} (he was not paid twice)")

    # ---- 3. nonexistent input
    ghost = TxBody(ledger.network_id, (OutPoint("ab" * 32, 0),), (Output(10, bob.pkhs[0]),), "ghost")
    attempt("3", "Spend an output that never existed",
            sign_body(ghost, [alice._keys[alice.pkhs[0]]]), "rejected")

    # ---- 4. repeated outpoint inside one transaction
    bob_coin = bob.spendable(ledger)[0][0]
    dup = TxBody(ledger.network_id, (bob_coin, bob_coin), (Output(170, carol.pkhs[0]),), "dup")
    attempt("4", "Same outpoint listed twice in one transaction (would double the 85)",
            sign_body(dup, [bob._keys[bob.pkhs[0]]] * 2), "rejected")

    # ---- 5. second spend of an already consumed output
    again = TxBody(ledger.network_id, (coin70,), (Output(60, carol.pkhs[0]),), "respend")
    attempt("5", "Alice tries to spend the 70-unit output that step 1 consumed",
            sign_body(again, [alice._keys[alice.pkhs[0]]]), "rejected")

    # ---- 6. bad signature: output amount edited after signing
    good = bob.build_payment(ledger, carol.primary_address, 30, fee=1)
    obj = copy.deepcopy(good.to_obj())
    obj["body"]["outputs"][0]["value"] = 31          # attacker raises Carol's amount, keeps old signature
    attempt("6", "Transaction edited after signing (Carol's amount 30 -> 31)", obj, "rejected")

    # ---- 7. wrong key
    steal = TxBody(ledger.network_id, (bob_coin,), (Output(84, mallory.pkhs[0]),), "steal")
    attempt("7", "Mallory signs a spend of Bob's output with her own key",
            sign_body(steal, [mallory._keys[mallory.pkhs[0]]]), "rejected")

    # ---- 8. negative value
    neg = copy.deepcopy(good.to_obj())
    neg["body"]["outputs"][0]["value"] = -5
    attempt("8", "Negative output value (-5)", neg, "rejected")

    # ---- 9. arithmetic overflow
    big = TxBody(ledger.network_id, (bob_coin,),
                 (Output(MAX_VALUE, carol.pkhs[0]), Output(MAX_VALUE, carol.pkhs[0])), "overflow")
    attempt("9", f"Two outputs of {MAX_VALUE} each: their sum overflows the safe maximum",
            sign_body(big, [bob._keys[bob.pkhs[0]]]), "rejected")

    # ---- 10. incorrect change: 1 unit created from nothing
    wrong = TxBody(ledger.network_id, (bob_coin,),
                   (Output(60, carol.pkhs[0]), Output(26, bob.pkhs[0])), "bad-change")
    attempt("10", "Bob pays 60 but claims 26 change from an 85 coin (60+26=86 > 85)",
            sign_body(wrong, [bob._keys[bob.pkhs[0]]]), "rejected")

    # ---- 11. malformed witness count
    short = SignedTx(good.body, ())
    attempt("11", "Transaction without any witness (no signature at all)", short, "rejected")

    # ---- 12. a valid payment after all the failed attempts
    attempt("12", "Bob pays Carol 30 with fee 1 (spends 85, change 54)", good, "accepted")
    snap("final")

    emit("\n" + "=" * 72)
    emit("final balances: " + "  ".join(
        f"{n}={w.balance(ledger)}" for n, w in (("Alice", alice), ("Bob", bob), ("Carol", carol))))
    emit(f"issued={ledger.issued}  unspent={ledger.total_unspent()}  fees={ledger.fees}  "
         f"(issued == unspent + fees: {ledger.issued == ledger.total_unspent() + ledger.fees})")
    ledger.check_invariants()
    if snapshot_dir:
        reloaded = Ledger.load(snaps[-1])
        emit(f"reload check: saved snapshot reloads to the same state hash: "
             f"{reloaded.state_hash() == ledger.state_hash()}")
    emit(f"final state hash {ledger.state_hash()}")
    return {"records": records, "ledger": ledger, "snapshots": snaps, "pay_tx": pay, "good_tx": good}
