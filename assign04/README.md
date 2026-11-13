# Assignment 4: A UTXO Ledger and Transaction Validator (`utxolab`)

An in-memory UTXO ledger that validates and applies transactions: value is preserved, ownership is proven by a pay-to-public-key-hash lock plus an Ed25519 signature, and double spending is prevented. No mining or networking is implemented.

It reuses earlier work, copied into this folder so the project is self-contained: canonical JSON (Assignment 1), Base58Check addresses and Ed25519 keys (Assignment 3).

Design details: [`docs/DESIGN.md`](docs/DESIGN.md).

## Folder Layout

```text
assign04/
├── docs/
│   └── DESIGN.md
├── examples/
│   ├── snapshots/
│   │   ├── 00_genesis.json
│   │   ├── 01_alice_paid_bob.json
│   │   └── 02_final.json
│   ├── alice_pays_bob.py
│   ├── trace.json
│   ├── trace.txt
│   ├── tx_alice_pays_bob.json
│   └── tx_bob_pays_carol.json
├── scripts/
│   ├── generate_samples.py
│   └── bench.py
├── src/
│   └── utxolab/
│       ├── __init__.py
│       ├── __main__.py
│       ├── address.py
│       ├── base58.py
│       ├── canonical.py
│       ├── cli.py
│       ├── demo.py
│       ├── errors.py
│       ├── keys.py
│       ├── ledger.py
│       ├── selection.py
│       ├── tx.py
│       └── wallet.py
├── tests/
├── vectors/
│   └── tx_vectors.json
├── .gitignore
├── PERFORMANCE.md
├── README.md
├── pyproject.toml
└── requirements.txt
```

## Setup

Python 3.10 or later is required.

Create a virtual environment:

```bash
python -m venv .venv
```

Activate the virtual environment.

**Windows (PowerShell):**

```powershell
.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

**Linux/macOS:**

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Install the project in editable mode:

```bash
pip install -e .
```

The editable installation provides the `utxolab` command. Alternatively, the package can be run using `python -m utxolab` from this folder.

## Run

Run the assignment's example:

```bash
python examples/alice_pays_bob.py
```

Run the complete accepted/rejected transaction demo:

```bash
python -m utxolab demo
```

The demo displays the transaction trace, including accepted and rejected transactions with their rejection reasons.

Generate pretty ledger snapshots:

```bash
python -m utxolab demo --snapshot-dir out_snaps
```

Run all automated tests:

```bash
python -m pytest -q
```

Regenerate sample examples and transaction vectors:

```bash
python scripts/generate_samples.py
```

Run performance benchmarks:

```bash
python scripts/bench.py
```

## Working with Snapshot Files

Inspect the initial ledger:

```bash
python -m utxolab inspect examples/snapshots/00_genesis.json
```

Validate a transaction without applying it:

```bash
python -m utxolab check-tx --state examples/snapshots/00_genesis.json --tx examples/tx_alice_pays_bob.json
```

Apply a transaction and save the updated ledger:

```bash
python -m utxolab apply-tx --state examples/snapshots/00_genesis.json --tx examples/tx_alice_pays_bob.json --out after.json --pretty
```

Try submitting the same transaction again:

```bash
python -m utxolab apply-tx --state after.json --tx examples/tx_alice_pays_bob.json
```

The second submission is rejected as a duplicate transaction.

Check the balance of an address:

```bash
python -m utxolab balance --state after.json --address <ADDRESS>
```

Replace `<ADDRESS>` with a valid wallet address from the sample data.

`check-tx` and `apply-tx` exit with status 1 and print `REJECTED code=... reason: ...` for invalid transactions.

## Library Use

The ledger and wallet can also be used directly from Python:

```python
from utxolab import Ledger, Wallet
from utxolab.tx import Output

# Assume alice and bob are initialized Wallet instances.

ledger = Ledger()

# Issue initial funds to Alice.
ledger.issue([Output(40, alice.pkhs[0])], memo="g1")

# Build a signed payment with change.
tx = alice.build_payment(
    ledger,
    bob.primary_address,
    85,
    fee=2
)

# Validate and apply the transaction atomically.
receipt = ledger.apply(tx)
```

`Wallet.from_seeds` and the demo seeds are intended for testing only. Use `Wallet.new_address()` with operating-system randomness for new addresses.

## Implementation Details

| Requirement | Implementation |
|---|---|
| Outpoints using transaction ID and output index; integer outputs with locking conditions | `tx.py` |
| Simple pay-to-public-key-hash (P2PKH) locking condition | `tx.py`, `ledger.validate` |
| Transaction ID from canonical serialized bytes | `TxBody.txid` (domain-tagged SHA-256 of canonical JSON) |
| Validate referenced outputs, signatures, duplicate inputs, value ranges, overflow, and inputs >= outputs | `Ledger.validate`; ordered validation table in `docs/DESIGN.md` |
| Calculate fees and update the UTXO set atomically only after successful validation | `Ledger.apply` |
| Deterministic coin selection and change output | `selection.py` (largest-first strategy), `wallet.py` |
| Persist and reload the UTXO set without changing its logical contents | `Ledger.save`, `Ledger.load`, `state_hash()` |
| Example: Alice spends 40 and 70 units, pays Bob 85, pays fee 2, and receives 23 change | `examples/trace.txt`, `tests/test_validation.py` |
| Validator, wallet-side transaction builder, at least 20 tests, snapshots, and transaction trace | `src/`, `tests/`, `examples/snapshots/`, `examples/trace.txt` |
| Reject nonexistent inputs, repeated outpoints, double spending, bad signatures, negative/overflowing values, incorrect change, and preserve state after failures | `Ledger.validate`, `Ledger.apply`, `examples/trace.txt`, `tests/test_validation.py` |

## Notes

- Transaction fees are burned and tracked in `ledger.fees`.
- The ledger invariant is `issued == unspent + fees`.
- Zero-value outputs are rejected; output values must be at least 1. There is no dust limit.
- Signatures are not part of the transaction ID (similar to SegWit).
- Non-canonical signatures with `S >= L` are rejected.
- Coin selection uses a deterministic largest-first strategy.
- Validation is performed before committing changes to the UTXO set, ensuring that a rejected transaction leaves the ledger state unchanged.

## Test Results

The automated test suite contains 74 test cases (53 test functions), including known-answer vectors.

Run the complete test suite using:

```bash
python -m pytest -v
```

All 74 tests passed in the verified test run.

## Performance

Performance measurements are generated using:

```bash
python scripts/bench.py
```

See [`PERFORMANCE.md`](PERFORMANCE.md) for the benchmark results.