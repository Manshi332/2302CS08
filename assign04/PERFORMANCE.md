# Performance notes (Assignment 4)

Measured with `python scripts/bench.py` on Python 3.12.3, Linux x86_64 (single thread, one run; your numbers will differ).

| Operation | Result |
|---|---|
| `apply()` of a 1-input / 1-output transaction (dominated by one Ed25519 verify) | about 7,000 tx/s (about 140 us/tx) |

| UTXOs in snapshot | save (ms) | load + verify (ms) | file size (KB) |
|---:|---:|---:|---:|
| 1,000 | 30 | 25 | 216 |
| 10,000 | 380 | 396 | 2,158 |
| 50,000 | 1,996 | 1,525 | 10,791 |

## Complexity
* `validate/apply`: O(inputs + outputs) dictionary operations plus one signature verification per input.
* Wallet balance / coin listing: O(own outputs) thanks to a pubkey-hash index kept inside the ledger (no full scan).
* Coin selection: O(k log k) for k candidate outputs (sort), then a linear prefix scan.
* Snapshot save/load: O(total entries). Cost is dominated by canonical JSON, checksum and strict re-validation.
  The file also stores spent-output history and applied txids, so it grows with history, not only with UTXOs.
* Memory: one `Output` object per UTXO plus the spent/applied history.

## Trade-offs
Keeping `spent` and `applied` gives precise rejection reasons (`input_already_spent` names the spender) and
replay protection across restarts, at the cost of unbounded history. A real node would prune this and rely on
block-level undo data instead.
