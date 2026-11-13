# Design: UTXO ledger and transaction validator

## What is reused from Assignments 1-3
| Module | Origin | Used for |
|---|---|---|
| `canonical.py` | Assignment 1 (hashlab canonical JSON), via Assignment 3 | the exact bytes that are hashed and signed |
| `base58.py`, `address.py` | Assignment 3 | addresses; `pkh = SHA-256(pubkey)[:20]` **is** the locking condition |
| `keys.py` | Assignment 3 (crypto core only) | Ed25519 keys, deterministic signing, canonical-`S` check |

New in Assignment 4: `tx.py` (outpoints, outputs, txid, signing), `ledger.py` (state + validator + persistence),
`selection.py` + `wallet.py` (coin selection, change, builder), `demo.py`, `cli.py`.

## Task-by-task map
1. **Outpoints / outputs** - `OutPoint(txid, index)`, `Output(value:int, pkh:bytes)` in `tx.py`.
2. **P2PKH lock** - an output stores `{"type":"p2pkh","pkh":<40 hex>}`. To spend it an input's witness must give a
   public key whose `SHA-256(pubkey)[:20]` equals that pkh **and** a valid Ed25519 signature by that key.
3. **Transaction ID** - `txid = SHA-256("utxolab/txid/v1\0" || canonical_json(body))`. Witnesses (public keys,
   signatures) are *not* part of the body, so re-encoding a signature can never change an identity.
4. **Validation** - see the ordered list below.
5. **Fee + atomic update** - `fee = sum(inputs) - sum(outputs)`. `Ledger.validate()` is pure and returns a `Plan`;
   `Ledger.apply()` commits the plan. The commit only touches keys that validation proved present/absent and has no
   fallible step, so a rejected transaction leaves the state bit-for-bit unchanged (every rejection in the tests and
   in `examples/trace.txt` checks the state hash before/after). Fees are burned and tracked.
6. **Coin selection** - **largest-first greedy** (details below).
7. **Persistence** - `Ledger.save/load`: canonical JSON, atomic (temp file, fsync, rename), SHA-256 checksum,
   strict reload that re-checks all invariants. `state_hash()` proves identical logical contents.

## Transaction format
```
SignedTx = {"body": Body, "witnesses": [ {"public_key": hex64, "signature": hex128}, ... ]}   # one per input
Body     = {"version": 1, "network_id": "...", "inputs": [{"txid": hex64, "index": n}, ...],
            "outputs": [{"value": n, "lock": {"type": "p2pkh", "pkh": hex40}}, ...], "memo": "..."}
signing bytes = "utxolab/sig/v1\0" || canonical_json(body)       (every input signs the whole body)
```
Different domain tags for txid and signatures mean a signature can never be confused with an identifier hash.
`memo` (<= 64 chars) makes otherwise identical issuance transactions distinct.
Whitespace and key order in the JSON file do not matter: the canonical form is recomputed.

## Validation order (first failure wins; each has a stable `code`)
| # | Check | code |
|---|---|---|
| 0 | schema: exact fields, types, hex lengths, version, known network | `malformed_tx`, `malformed_json`, `unsupported_version`, `unknown_network`, `bad_lock`, `bad_witness`, `no_outputs` |
| 0 | each output value is an integer, not bool, `1 <= v <= 2^53-1` | `bad_output_value` (negative / zero / too large / not int) |
| 1 | transaction is for this ledger's network | `wrong_network` |
| 2 | at least one input (value can only enter through `Ledger.issue`) | `no_inputs` |
| 3 | txid not already applied (same signed tx submitted twice) | `duplicate_transaction` |
| 4 | no outpoint repeated inside the transaction | `duplicate_input` |
| 5 | every input exists in the UTXO set; otherwise already spent (names the spender) or never existed | `input_already_spent`, `input_not_found` |
| 6 | exactly one witness per input | `bad_witness` |
| 7 | sums of inputs and of outputs stay <= `2^53-1` (no overflow) | `value_overflow` |
| 8 | `sum(inputs) >= sum(outputs)` (no value from nothing; catches wrong change) | `outputs_exceed_inputs` |
| 9 | per input: pubkey hashes to the lock; signature is canonical (`S < L`); signature verifies | `pubkey_hash_mismatch`, `noncanonical_signature`, `bad_signature` |

Python integers do not overflow, so "overflow" is defined against the same `2^53-1` bound the canonical JSON
format uses; the check is explicit rather than relying on the language.

## Coin selection
Strategy: **largest-first**. Sort candidates by value descending (ties: `txid`, then `index`, ascending) and take
outputs until `total >= amount + fee`. Deterministic; uses the fewest inputs for a given target (so smallest
transaction); spends large coins first and so can leave small outputs behind; not minimal-change (that needs
branch-and-bound). `smallest_first` is available (`Wallet(strategy="smallest_first")`) for comparison.
Change = `sum(selected) - amount - fee`, added as the **last** output to the wallet's primary address (or
`change_address`), only if > 0. Example: 40 + 70 selected for 85 + fee 2 -> outputs `[85 -> Bob, 23 -> Alice]`.
The ledger also enforces the other side of "correct change": if outputs exceed inputs the transaction is rejected;
if the change is *too small* the difference is simply a larger fee, exactly like Bitcoin (the wallet never does this).

## Replay and double spending
A UTXO is consumed at most once, so there is no nonce. Re-sending the same signed transaction is caught by
`duplicate_transaction` (txid already applied); a *different* transaction spending a consumed output is caught
by `input_already_spent`. Both persist across save/load because `spent` and `applied` are part of the snapshot.

## Snapshot format (`utxolab-snapshot-v1`)
`{"format", "state": {network_id, issued, fees, utxos{"txid:i": Output}, spent{"txid:i": spender}, applied[txid]},
"state_sha256"}`. The checksum is over the canonical form of `state`, so pretty-printed and compact files load to
the same state. Load rejects: bad JSON, unknown format, checksum mismatch (`snapshot_corrupt`), or a state that
breaks `issued == unspent + fees` / disjointness / index consistency (`bad_snapshot`).

## Limits and non-goals
No mining, networking, mempool or block structure (that is later assignments). Ed25519 and the OS RNG come from the
`cryptography` package; nothing implements its own curve. Wallet keys are in memory only; the demo uses fixed
**test-only** seeds. No coinbase maturity, no timelocks, no dust limit (outputs just need value >= 1).
