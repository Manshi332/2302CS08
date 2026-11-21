# Assignment 4 – A UTXO Ledger and Transaction Validator

### Project: UTXOLab

**Roll Number:** 2302CS08  
**Course:** Blockchain Engineering  
**Institution:** IIT Patna  
**Academic Session:** July–December 2026
**Demo Video:** https://youtu.be/A_tDITUGCsA

---

## 1. Overview

This assignment focuses on implementing an in-memory UTXO (Unspent Transaction Output) ledger and transaction validator using Python.

The ledger validates and applies transactions while ensuring that value is preserved, ownership is proven through a Pay-to-Public-Key-Hash (P2PKH) locking condition and an Ed25519 digital signature, and double spending is prevented.

The implementation reuses earlier work from:

- **Assignment 1:** Canonical JSON serialization.
- **Assignment 3:** Base58Check addresses and Ed25519 key generation and signing.

The reused components are copied into this assignment folder, making the project self-contained.

The implementation focuses on transaction validation, UTXO management, deterministic coin selection, fee calculation, atomic state updates, and ledger persistence.

**Note:** This assignment implements an in-memory ledger and transaction validator. Mining and peer-to-peer networking are not included.

For additional design details, refer to [`docs/DESIGN.md`](docs/DESIGN.md).

## 2. Technologies Used

| Technology | Purpose |
|---|---|
| Python 3.10+ | Core implementation |
| Ed25519 | Digital signatures and ownership verification |
| SHA-256 | Transaction ID generation |
| Canonical JSON | Deterministic transaction serialization |
| Base58Check | Wallet address encoding |
| UTXO Model | Transaction input and output management |
| pytest | Automated testing |

## 3. Key Features

- **UTXO Ledger:** Maintains the set of unspent transaction outputs.
- **Transaction Validation:** Validates transaction inputs, outputs, signatures, and spending rules.
- **P2PKH Locking:** Proves ownership using a public-key-hash locking condition.
- **Digital Signatures:** Uses Ed25519 signatures to authorize transactions.
- **Double-Spend Prevention:** Rejects transactions attempting to spend already-spent outputs.
- **Value Conservation:** Ensures that transaction inputs are greater than or equal to transaction outputs.
- **Fee Calculation:** Calculates and tracks transaction fees.
- **Deterministic Coin Selection:** Uses a largest-first strategy to select UTXOs.
- **Change Calculation:** Returns the remaining value to the sender.
- **Atomic State Updates:** Updates the UTXO set only after successful validation.
- **Ledger Persistence:** Supports saving and loading ledger snapshots.
- **Transaction Trace:** Demonstrates accepted and rejected transactions with rejection reasons.

## 4. Project Structure

```text
assign04/
│
├── README.md
├── .gitignore
├── pyproject.toml
├── requirements.txt
├── PERFORMANCE.md
│
├── docs/
│   └── DESIGN.md
│
├── examples/
│   ├── snapshots/
│   │   ├── 00_genesis.json
│   │   ├── 01_alice_paid_bob.json
│   │   └── 02_final.json
│   │
│   ├── alice_pays_bob.py
│   ├── trace.json
│   ├── trace.txt
│   ├── tx_alice_pays_bob.json
│   └── tx_bob_pays_carol.json
│
├── scripts/
│   ├── generate_samples.py
│   └── bench.py
│
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
│
├── tests/
│
└── vectors/
    └── tx_vectors.json
```

## 5. Setup and Installation

### Prerequisites

- Python 3.10 or later
- pip

### Windows (PowerShell)

Run the following commands from the `assign04` directory:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

If PowerShell blocks virtual environment activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

### Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

The editable installation provides the `utxolab` command.

Alternatively, the package can be executed using:

```bash
python -m utxolab
```

## 6. Running the Demonstration

### Step 1: Run the example transaction

```bash
python examples/alice_pays_bob.py
```

This demonstrates a transaction in which Alice sends funds to Bob.

### Step 2: Run the complete transaction demo

```bash
python -m utxolab demo
```

The demonstration executes accepted and rejected transactions and displays the transaction trace with corresponding rejection reasons.

### Step 3: Generate ledger snapshots

```bash
python -m utxolab demo --snapshot-dir out_snaps
```

This generates readable snapshots of the ledger at different stages of the demonstration.

## 7. Working with Snapshot Files

The project includes sample ledger snapshots that demonstrate the state of the UTXO ledger after different transactions.

### Step 1: Inspect the initial ledger

```bash
python -m utxolab inspect examples/snapshots/00_genesis.json
```

### Step 2: Validate a transaction without applying it

```bash
python -m utxolab check-tx --state examples/snapshots/00_genesis.json --tx examples/tx_alice_pays_bob.json
```

This checks whether the transaction is valid without modifying the ledger.

### Step 3: Apply a transaction and save the updated ledger

```bash
python -m utxolab apply-tx --state examples/snapshots/00_genesis.json --tx examples/tx_alice_pays_bob.json --out after.json --pretty
```

This validates and applies the transaction, then saves the updated ledger state.

### Step 4: Test duplicate transaction rejection

```bash
python -m utxolab apply-tx --state after.json --tx examples/tx_alice_pays_bob.json
```

The second submission is rejected because the transaction has already been applied.

### Step 5: Check an address balance

```bash
python -m utxolab balance --state after.json --address <ADDRESS>
```

Replace `<ADDRESS>` with a valid wallet address from the sample data.

**Note:** The `check-tx` and `apply-tx` commands exit with status 1 and print `REJECTED code=... reason: ...` for invalid transactions.

## 8. Library Usage

The ledger and wallet can also be used directly from Python.

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

`Wallet.from_seeds` and the demonstration seeds are intended for testing only. Use `Wallet.new_address()` with operating-system randomness for generating new addresses.

## 9. Implementation Details

| Requirement | Implementation |
|---|---|
| Outpoints using transaction ID and output index; integer outputs with locking conditions | `tx.py` |
| Pay-to-public-key-hash (P2PKH) locking condition | `tx.py`, `ledger.validate` |
| Transaction ID from canonical serialized bytes | `TxBody.txid` – domain-tagged SHA-256 of canonical JSON |
| Validate referenced outputs, signatures, duplicate inputs, value ranges, overflow, and input/output balance | `Ledger.validate` |
| Calculate fees and update the UTXO set atomically after successful validation | `Ledger.apply` |
| Deterministic coin selection and change output | `selection.py`, `wallet.py` |
| Persist and reload the UTXO set without changing its logical contents | `Ledger.save`, `Ledger.load`, `state_hash()` |
| Alice spends 40 and 70 units, pays Bob 85, pays a fee of 2, and receives 23 change | `examples/trace.txt`, `tests/test_validation.py` |
| Validator, wallet-side transaction builder, tests, snapshots, and transaction trace | `src/`, `tests/`, `examples/` |
| Reject nonexistent inputs, repeated outpoints, double spending, invalid signatures, negative or overflowing values, and incorrect change | `Ledger.validate`, `Ledger.apply`, `tests/test_validation.py` |

## 10. Transaction Validation and Ledger Rules

The implementation enforces the following rules:

| Validation Rule | Description |
|---|---|
| UTXO Reference | Every transaction input must reference an existing unspent output |
| Ownership Verification | The spender must prove ownership using the P2PKH locking condition |
| Digital Signature | Ed25519 signatures must be valid |
| Duplicate Inputs | Repeated references to the same outpoint are rejected |
| Double Spending | Previously spent outputs cannot be spent again |
| Value Conservation | Total input value must be greater than or equal to total output value |
| Value Range | Negative, zero-value outputs, and overflowing values are rejected |
| Fee Calculation | The difference between inputs and outputs is tracked as a fee |
| Atomic Updates | Rejected transactions must not modify ledger state |
| Transaction ID | Generated from canonical transaction body serialization |

### Ledger Invariant

The ledger maintains the following invariant:

\[
\text{Issued}=\text{Unspent}+\text{Fees}
\]

This ensures that all issued value is accounted for, either as unspent outputs or accumulated transaction fees.

## 11. Additional Notes

- Transaction fees are burned and tracked in `ledger.fees`.
- Zero-value outputs are rejected.
- Output values must be at least 1; there is no dust limit.
- Signatures are not part of the transaction ID, similar to the SegWit design.
- Non-canonical signatures with `S >= L` are rejected.
- Coin selection uses a deterministic largest-first strategy.
- Validation is performed before committing changes to the UTXO set.
- A rejected transaction leaves the ledger state unchanged.

## 12. Running Automated Tests

Run the complete test suite using pytest:

```bash
python -m pytest -v
```

Alternatively:

```bash
python -m pytest -q
```

### Test Results

| Metric | Result |
|---|---:|
| Test Functions | 53 |
| Total Test Cases | 74 |
| Passed | 74 |
| Failed | 0 |

The automated test suite includes known-answer vectors and covers transaction validation, signatures, UTXO management, double-spend prevention, and ledger state consistency.

**Test Result: 74/74 tests passed.**

## 13. Sample Generation and Transaction Vectors

Regenerate the sample examples and transaction vectors using:

```bash
python scripts/generate_samples.py
```

The generated examples and vectors are useful for verifying transaction serialization and demonstrating the ledger workflow.

## 14. Performance Benchmarking

Run the performance benchmark using:

```bash
python scripts/bench.py
```

The benchmark evaluates the performance of the UTXO ledger and transaction operations.

For detailed benchmark results, refer to [`PERFORMANCE.md`](PERFORMANCE.md).

## 15. Deliverables

| Deliverable | Location |
|---|---|
| UTXO ledger implementation | `src/utxolab/ledger.py` |
| Transaction structures and validation | `src/utxolab/tx.py` |
| Wallet and transaction builder | `src/utxolab/wallet.py` |
| Address and key management | `src/utxolab/address.py`, `src/utxolab/keys.py` |
| Deterministic coin selection | `src/utxolab/selection.py` |
| Automated tests | `tests/` |
| Transaction vectors | `vectors/tx_vectors.json` |
| Ledger snapshots | `examples/snapshots/` |
| Transaction trace | `examples/trace.txt`, `examples/trace.json` |
| Design documentation | `docs/DESIGN.md` |
| Performance report | `PERFORMANCE.md` |

## 16. Demonstration Video

**YouTube Demo:** https://youtu.be/A_tDITUGCsA

The demonstration covers the project structure, UTXO ledger initialization, wallet operations, transaction creation, signature verification, transaction validation, double-spend prevention, ledger snapshots, automated tests, and performance benchmarking.

---

**Course:** Blockchain Engineering  
**Institution:** Indian Institute of Technology Patna (IIT Patna)  
**Academic Session:** July–December 2026  
**Roll Number:** 2302CS08
