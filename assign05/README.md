# Assignment 5 – Blocks, Proof of Work, Forks and Reorganisation

### Project: ChainLab

**Roll Number:** 2302CS08  
**Course:** Blockchain Engineering  
**Institution:** IIT Patna  
**Academic Session:** July–December 2026

---

## 1. Overview

This assignment extends the UTXO-based transaction validator developed in Assignment 4 into a complete blockchain system.

The implementation introduces:

- Block headers and Proof of Work (PoW) mining.
- Merkle roots for transaction commitment.
- Cumulative chain work calculation.
- Fork detection and resolution.
- Blockchain reorganisation.
- Validation of blocks and transactions before updating the active chain state.

The primary objective is to demonstrate that the valid blockchain is selected based on **the greatest cumulative work**, rather than simply the number of blocks.

The implementation also ensures that invalid blocks and transactions cannot modify the active blockchain state.

## 2. Project Structure

```text
assign05/
│
├── README.md
│
├── chainlab/
│   ├── __init__.py
│   ├── __main__.py
│   ├── block.py
│   ├── chain.py
│   ├── miner.py
│   ├── merkle.py
│   ├── node.py
│   ├── validation.py
│   └── ...
│
├── tests/
│   ├── test_block.py
│   ├── test_chain.py
│   ├── test_mining.py
│   ├── test_reorg.py
│   └── ...
│
├── docs/
│   └── REPORT.md
│
├── requirements.txt
└── pyproject.toml
```

The project reuses the UTXO transaction and wallet functionality developed in Assignment 4, including transaction creation, signing, verification, and address handling.

## 3. Technologies Used

| Technology | Purpose |
|---|---|
| Python | Core implementation |
| SHA-256 | Double SHA-256 hashing for block headers |
| Ed25519 | Transaction signing and signature verification |
| Merkle Tree | Transaction commitment inside block headers |
| pytest / unittest | Automated testing |

## 4. Setup and Installation

### Prerequisites

- Python 3.10 or later
- pip

### Windows (PowerShell)

Run the following commands from the `assign05` directory:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

### Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## 5. Running the Tests

Run the complete test suite using pytest:

```bash
python -m pytest -v
```

Alternatively, use unittest:

```bash
python -m unittest discover -s tests
```

### Test Results

| Metric | Result |
|---|---:|
| Total Tests | 55 |
| Passed | 55 |
| Failed | 0 |

All 55 tests passed successfully using both test runners.

## 6. Command-Line Interface

The project provides the following commands:

| Command | Description |
|---|---|
| `init` | Initializes a new blockchain with a genesis block |
| `address` | Generates or displays a wallet address |
| `pay` | Creates and signs a UTXO transaction |
| `mine` | Mines a new block using Proof of Work |
| `submit` | Submits a block to the chain manager |
| `info` | Displays blockchain information |
| `dump-header` | Displays block header fields and hexadecimal representation |
| `fork-sim` | Simulates competing miners and chain reorganisation |
| `work-sim` | Compares chains with different cumulative work |
| `acceptance` | Runs the assignment acceptance checks |
| `bench` | Measures mining performance and observed attempts |
| `report` | Generates the assignment report |

To see all available commands:

```bash
python -m chainlab --help
```

## 7. Quick Walkthrough

The following commands demonstrate the main blockchain workflow.

### Step 1: Initialize the blockchain

```bash
python -m chainlab init chain.json --bits 6
```

This creates a new blockchain with a genesis block and a toy mining difficulty of 6 bits.

### Step 2: Generate wallet addresses

```bash
python -m chainlab address alice
python -m chainlab address bob
python -m chainlab address carol
```

### Step 3: Mine blocks

Mine the first two blocks and reward Alice:

```bash
python -m chainlab mine --chain chain.json --address <alice-address>
python -m chainlab mine --chain chain.json --address <alice-address>
```

### Step 4: Create a transaction

Create a signed transaction from Alice to Bob:

```bash
python -m chainlab pay --chain chain.json --from alice --to <bob-address> --amount 30 --fee 1 --out pay.json
```

### Step 5: Mine a block containing the transaction

```bash
python -m chainlab mine --chain chain.json --address <carol-address> --tx pay.json --out block3.json
```

The mined block includes the transaction and a coinbase transaction.

### Step 6: Inspect the block header

```bash
python -m chainlab dump-header block3.json
```

This displays the block header fields, their offsets, sizes, and hexadecimal representation.

### Step 7: Run acceptance checks

```bash
python -m chainlab acceptance
```

### Step 8: Run simulations and benchmarks

```bash
python -m chainlab work-sim
python -m chainlab fork-sim
python -m chainlab bench
```

### Step 9: Generate the report

```bash
python -m chainlab report
```

The generated report is saved at:

```text
docs/REPORT.md
```

## 8. Block Header and Proof of Work

Each block contains a header with the following fields:

| Field | Size |
|---|---:|
| Version | 4 bytes |
| Previous Block Hash | 32 bytes |
| Merkle Root | 32 bytes |
| Timestamp | 8 bytes |
| Target | 32 bytes |
| Nonce | 4 bytes |
| **Total** | **112 bytes** |

The block header is serialized into 112 bytes and hashed using double SHA-256.

### Mining Condition

A block is considered valid only when:

\[
\operatorname{Hash}(\operatorname{Header}) \leq \operatorname{Target}
\]

For the toy difficulty parameter `bits`, the target is:

\[
\operatorname{Target}=2^{256-\text{bits}}-1
\]

The miner repeatedly changes the nonce until the hash satisfies the target condition.

### Expected Number of Attempts

The expected number of mining attempts is approximately:

\[
E[\text{Attempts}]=2^{\text{bits}}
\]

### Cumulative Chain Work

The work contributed by an individual block is:

\[
W=\left\lfloor\frac{2^{256}}{\operatorname{Target}+1}\right\rfloor
\]

The cumulative work of a chain is:

\[
\text{Chain Work}=\sum_{i=1}^{n}W_i
\]

The chain with the greatest cumulative work is selected as the active chain.

## 9. Fork Simulation and Chain Reorganisation

The implementation supports competing branches created by different miners.

When two valid branches exist, the chain manager compares their cumulative work.

- If both branches have equal work, the first-seen branch remains active.
- When a branch accumulates more work, it becomes the active chain.
- Blocks from the old active branch are disconnected.
- Their spent UTXOs are restored.
- Blocks from the winning branch are connected.
- Transactions from disconnected blocks can return to the mempool if they remain valid.

The `fork-sim` command demonstrates this process using two simulated nodes and miners.

The `work-sim` command demonstrates why a shorter chain can win over a longer chain when it has greater cumulative work.

**Important:** The manual fork experiment should be performed using a fresh chain or a separate chain file. The walkthrough modifies `chain.json`, so it should not be treated as an untouched chain for a later fork experiment.

## 10. Mining Performance and Benchmark Results

The `bench` command measures the mining hash rate and compares expected attempts with observed attempts at three difficulty levels.

The benchmark uses 20 trials for each target.

| Difficulty (bits) | Expected Attempts | Observed Mean Attempts |
|---:|---:|---:|
| 8 | 256 | 306.3 |
| 12 | 4,096 | 6,528.1 |
| 16 | 65,536 | 76,260.4 |

**Measured mining performance:**

525,575 SHA-256d hashes per second.

The observed number of attempts varies between trials because Proof of Work is probabilistic. The expected attempts represent the average over a sufficiently large number of trials, not a guaranteed number for an individual block.

The `report` command also generates benchmark results as part of the final report.

## 11. Validation Rules

The implementation validates blocks before accepting them into the active chain.

| Validation Rule | Description |
|---|---|
| Block Header | Checks the structure and validity of the block header |
| Proof of Work | Ensures the block hash satisfies the target |
| Merkle Root | Verifies that the Merkle root matches the transactions |
| Previous Hash | Checks that the parent block exists and is valid |
| Timestamp | Rejects invalid timestamps |
| Transaction Validation | Verifies signatures, inputs, outputs, and spending rules |
| Coinbase Rules | Ensures the coinbase transaction is first, has no inputs, and does not exceed the allowed reward plus fees |
| Double Spending | Rejects repeated spending of the same UTXO |
| Chain Selection | Selects the valid branch with the greatest cumulative work |
| Reorganisation | Restores and reapplies UTXO state when switching branches |

An invalid block must not modify the active chain or its UTXO state.

## 12. Acceptance Checks

The `acceptance` command executes the assignment's acceptance scenarios.

The following cases were successfully verified:

1. A longer branch with lower cumulative work loses to a shorter branch with higher cumulative work.
2. An incorrect Merkle root causes block rejection.
3. Invalid Proof of Work causes block rejection.
4. Excessive coinbase rewards are rejected.
5. Invalid transaction signatures are rejected.
6. Transactions with outputs exceeding their inputs are rejected.
7. Non-existent UTXO references are rejected.
8. Double spending within a block is rejected.
9. Invalid timestamps and unknown parents are rejected.
10. Multiple coinbase transactions in a block are rejected.
11. Reorganisation restores spent outputs and correctly applies the winning branch.
12. Invalid blocks cannot take over the active chain, even if their branch appears to have greater work.

**Acceptance Result: 21/21 checks passed.**

## 13. Deliverables

| Deliverable | Location |
|---|---|
| Blockchain and block implementation | `chainlab/` |
| Mining implementation | `chainlab/` |
| Fork simulation | `chainlab/` |
| Chain reorganisation logic | `chainlab/` |
| Automated tests | `tests/` |
| Assignment report | `docs/REPORT.md` |
| Block header hexadecimal dump | Generated using `dump-header` |
| Mining benchmarks | Generated using `bench` and included in the report |

## 14. Demonstration Video

**YouTube Demo:** [Watch Assignment 5 Demonstration](<ASSIGNMENT_05_VIDEO_LINK>)

The demonstration covers the project structure, blockchain initialization, wallet addresses, transaction creation, block mining, Proof of Work, fork simulation, chain reorganisation, acceptance checks, and mining benchmarks.

---

**Course:** Blockchain Engineering  
**Institution:** Indian Institute of Technology Patna (IIT Patna)  
**Academic Session:** July–December 2026  
**Roll Number:** 2302CS08