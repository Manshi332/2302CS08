"""Minimal end-to-end example: the assignment's Alice/Bob scenario in ~20 lines.

    python examples/alice_pays_bob.py
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from utxolab import Ledger, LedgerError, Wallet          # noqa: E402
from utxolab.tx import Output                             # noqa: E402

alice = Wallet.from_seeds([hashlib.sha256(b"example-alice").digest()])   # TEST-ONLY seed
bob = Wallet.from_seeds([hashlib.sha256(b"example-bob").digest()])

ledger = Ledger()
ledger.issue([Output(40, alice.pkhs[0])], memo="genesis-1")              # Alice controls 40 ...
ledger.issue([Output(70, alice.pkhs[0])], memo="genesis-2")              # ... and 70

tx = alice.build_payment(ledger, bob.primary_address, 85, fee=2)         # largest-first, change = 23
print("outputs:", [o.value for o in tx.body.outputs])
print("accepted, fee =", ledger.apply(tx).fee)
print("Alice:", alice.balance(ledger), " Bob:", bob.balance(ledger))

try:
    ledger.apply(tx)                                                     # same signed tx again
except LedgerError as exc:
    print("second submission rejected ->", exc.code)
print("Bob still has:", bob.balance(ledger))
