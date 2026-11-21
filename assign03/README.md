# Assignment 3 – Keys, Addresses, and Signed Transactions

### Project: WalletLab

**Student:** Manshi Prajapati  
**Roll Number:** 2302CS08  
**Course:** Blockchain Engineering – Dr. Mayank Agarwal  
**Department:** Computer Science and Engineering, IIT Patna  
**Academic Session:** July–December 2026

**Demo Video:** https://youtu.be/hZrmyZbqbFU

---

## 1. Overview

This assignment focuses on implementing an educational blockchain wallet using Python and the `cryptography` library.

The wallet supports secure Ed25519 key generation, Base58Check address derivation, canonical transaction serialization, digital transaction signing, and independent signature verification.

The main objective is to demonstrate how transactions can be signed by their owners and independently verified by anyone using only public information and the transaction specification, without requiring access to the private key.

All elliptic-curve operations and cryptographic randomness are provided by the maintained [`cryptography`](https://cryptography.io/) library. No cryptographic primitives are implemented from scratch.

### Key Features

- Ed25519 public-private key generation using the operating system's cryptographically secure random number generator (CSPRNG).
- Base58Check wallet address generation and validation.
- Canonical JSON serialization for consistent signing bytes.
- Digital transaction signing using Ed25519.
- Independent signature verification using public information.
- Network validation to distinguish testnet and mainnet addresses.
- Replay protection using transaction nonces and persistent state.
- Detection of transaction tampering, wrong signers, invalid addresses, and non-canonical signatures.

## 2. Technologies Used

| Technology | Purpose |
|---|---|
| Python 3.11+ | Core implementation |
| Ed25519 | Digital signatures and verification |
| SHA-256 | Public-key hashing and transaction integrity |
| Base58Check | Wallet address encoding |
| Canonical JSON | Deterministic transaction serialization |
| `cryptography` | Cryptographic operations |
| pytest | Automated testing |

## 3. Reuse from Assignment 1

The canonical JSON serialization rules from Assignment 1 (`hashlab`, canonical form v1) are copied into:

```text
src/walletlab/canonical.py
```

This makes Assignment 3 self-contained.

Canonical serialization ensures that JSON transactions differing only in whitespace or key ordering produce identical serialized bytes. This allows signatures to remain consistent across different JSON representations.

## 4. Project Structure

```text
assign03/
│
├── README.md
├── pyproject.toml
├── requirements.txt
│
├── src/
│   └── walletlab/
│       ├── __init__.py
│       ├── __main__.py
│       ├── address.py
│       ├── base58.py
│       ├── canonical.py
│       ├── cli.py
│       ├── errors.py
│       ├── keys.py
│       └── ...
│
├── tests/
│   └── test_walletlab.py
│
├── docs/
│   ├── TX_FORMAT.md
│   └── THREAT_MODEL.md
│
├── vectors/
│   └── test_vectors.json
│
└── examples/
    ├── tx.json
    ├── signed_tx.json
    ├── signed_tx_reordered.json
    │
    └── bad/
        ├── amount_changed.json
        ├── wrong_signer.json
        ├── wrong_network.json
        ├── bad_checksum_address.json
        ├── signature_non_canonical_S.json
        └── signature_uppercase.json
```

## 5. Setup and Installation

### Prerequisites

- Python 3.11 or later.
- pip.
- `cryptography` library.

### Windows (PowerShell)

Run the following commands from the `assign03` directory:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

The editable installation provides the `walletlab` command.

Alternatively, the package can be executed without installing it using:

**Linux / macOS:**

```bash
PYTHONPATH=src python3 -m walletlab <command>
```

**Windows PowerShell:**

```powershell
$env:PYTHONPATH="src"
python -m walletlab <command>
```

## 6. Command-Line Interface

The wallet provides four primary commands:

| Command | Description |
|---|---|
| `keygen` | Generates an Ed25519 key pair |
| `address` | Derives or validates a wallet address |
| `sign` | Signs a transaction using a private key |
| `verify` | Verifies a signed transaction using public information |
| `canonical` | Displays the canonical JSON representation of a file |

### 6.1 Key Generation

The `keygen` command generates an Ed25519 key pair using the operating system's CSPRNG.

By default, only the public key is saved.

```bash
walletlab keygen --public-out alice.pub.json
```

Example output:

```text
network: course-testnet
public_key: 5c8170ed...1c39
address: msQSCSB3ukWznXune7uzPjN1S6Yqq9uh5h
private key: NOT saved
```

To export a private key for development and testing:

```bash
walletlab keygen --public-out alice.pub.json --dev-export-private dev_private_key_alice.json
```

The program displays warnings because the exported private key is unencrypted and intended only for testing.

**Security properties:**

- Files are created exclusively and existing files are never overwritten.
- The private key file is created with permissions `0600`.
- The private-key loader refuses files with looser permissions.
- Private keys must never be committed to a repository or shared.

### 6.2 Address Generation and Validation

Generate a wallet address from a public-key file:

```bash
walletlab address --pub alice.pub.json
```

Alternatively, provide a public key in hexadecimal format:

```bash
walletlab address --public-key <64-HEX-PUBLIC-KEY>
```

Validate an address and check its network:

```bash
walletlab address --check <ADDRESS> --network-required course-testnet
```

Example output:

```text
valid: yes
```

#### Address Derivation

The public-key hash is calculated as:

\[
pkh=\operatorname{SHA256}(public\_key)[0:20]
\]

The address is generated using Base58Check encoding:

\[
address=\operatorname{Base58Check}(version\_byte\parallel pkh)
\]

| Network | Version Byte |
|---|---|
| Testnet | `0x6F` |
| Mainnet | `0x3F` |

### 6.3 Transaction Signing

The `sign` command signs a transaction using the corresponding private key.

```bash
walletlab sign --key dev_private_key_alice.json --tx examples/tx.json --out signed.json
```

Before generating the signature, the program:

1. Loads the private key.
2. Validates the transaction schema.
3. Checks whether the private key owns the transaction sender address.
4. Generates the canonical transaction bytes.
5. Creates an Ed25519 digital signature.
6. Saves the signed transaction.

The command refuses to sign a transaction if the private key does not correspond to the sender address.

### 6.4 Signature Verification

The `verify` command independently verifies a signed transaction using public information.

```bash
walletlab verify --signed examples/signed_tx.json
```

Example successful output:

```text
VALID
network: course-testnet
sender: <SENDER_ADDRESS>
```

To demonstrate tampering detection:

```bash
walletlab verify --signed examples/bad/amount_changed.json
```

Expected result:

```text
REJECTED: signature does not verify
```

The verification process does not require the sender's private key.

### 6.5 Replay Protection

Replay protection prevents an already accepted transaction from being accepted again.

The verifier maintains the last accepted nonce for each sender.

A transaction is rejected when:

\[
nonce \leq last\_nonce[sender]
\]

To verify a transaction and update the replay state:

```bash
walletlab verify --signed signed.json --state state.json --update-state
```

Example:

```text
VALID
nonce 7 stored
```

Verify the same transaction again:

```bash
walletlab verify --signed signed.json --state state.json
```

Expected result:

```text
REJECTED: replayed transaction
```

Stateless verification cannot detect replay attacks. Replay protection requires maintaining state using the `--state` option.

### 6.6 Canonical Serialization

Display the canonical JSON representation of a transaction:

```bash
walletlab canonical examples/tx.json
```

Canonical serialization ensures that JSON documents with different whitespace or key ordering produce identical signing bytes.

## 7. Rejection Requirements and Security Validation

The implementation supports several rejection conditions to prevent invalid or malicious transactions.

| Required Rejection | Validation Mechanism | Demonstration |
|---|---|---|
| Changed transaction amount or another signed field | Signature verification over canonical bytes | `examples/bad/amount_changed.json` |
| Wrong network | Validates `network_id` and address version | `examples/bad/wrong_network.json` |
| Wrong signer | Checks that the public-key-derived address matches the sender | `examples/bad/wrong_signer.json` |
| Replayed nonce | Checks `nonce <= last_nonce[sender]` using replay state | `test_replayed_nonce_rejected_by_state` |
| Malformed address or invalid checksum | Base58Check decoding, length, version, and canonical spelling checks | `examples/bad/bad_checksum_address.json` |
| Non-canonical signature encoding | Validates lowercase hexadecimal encoding, 64-byte signature length, and scalar `S < L` | `examples/bad/signature_non_canonical_S.json` and `signature_uppercase.json` |

### Canonical Serialization Acceptance Test

The implementation also verifies:

```text
examples/signed_tx_reordered.json
```

This file contains shuffled JSON keys and different whitespace formatting.

It must verify successfully and produce the same `signing_bytes_sha256` as:

```text
examples/signed_tx.json
```

This demonstrates that canonical serialization makes signatures independent of JSON formatting.

## 8. Automated Testing

Run the complete test suite:

```bash
python3 -m pytest -q
```

Expected result:

```text
57 passed
```

The tests cover:

- Key generation.
- Address derivation and validation.
- Canonical serialization.
- Transaction signing.
- Signature verification.
- Invalid signer rejection.
- Wrong network rejection.
- Tampering detection.
- Replay protection.
- Non-canonical signature rejection.
- Command-line end-to-end execution.

### Test Results

| Metric | Result |
|---|---:|
| Total Tests | 57 |
| Passed | 57 |
| Failed | 0 |

**Test Result: 57/57 tests passed.**

## 9. Test Vectors and Reproducibility

Regenerate the examples and test vectors using:

```bash
PYTHONPATH=src python3 scripts/gen_examples.py
```

On Windows PowerShell:

```powershell
$env:PYTHONPATH="src"
python scripts/gen_examples.py
```

Example keys are generated from public, test-only seeds:

```text
SHA-256("walletlab test-only alice")
SHA-256("walletlab test-only bob")
```

Ed25519 signing is deterministic. Therefore, the same test inputs produce identical signatures and serialized bytes.

The tests also verify RFC 8032 test vector 1 to confirm that the cryptographic library is being used correctly.

## 10. Design Notes and Security Limitations

### Why Ed25519?

Ed25519 was selected because it provides:

- Compact digital signatures.
- Deterministic signing without signing-time randomness.
- Simple key and signature encoding.
- Reliable implementation through the maintained `cryptography` library.

The assignment permits either secp256k1 or Ed25519.

### Address Hashing

The address uses the first 20 bytes of SHA-256 of the public key.

RIPEMD-160 is not used because it may not be available in some OpenSSL 3 environments.

### Replay Protection

Stateless signature verification cannot identify whether a valid transaction has already been processed.

Replay detection requires persistent nonce state. In a real blockchain system, this responsibility would belong to the transaction ledger.

### Private-Key Storage

Private keys exported by the development option are stored unencrypted.

These files are intended strictly for educational testing and must never be used to protect real funds.

For additional security details, refer to [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

## 11. Deliverables

| Deliverable | Location |
|---|---|
| Key generation and wallet implementation | `src/walletlab/keys.py` |
| Address derivation and validation | `src/walletlab/address.py` |
| Base58Check encoding | `src/walletlab/base58.py` |
| Canonical JSON serialization | `src/walletlab/canonical.py` |
| Transaction signing and verification commands | `src/walletlab/cli.py` |
| Automated tests | `tests/test_walletlab.py` |
| Transaction test vectors | `vectors/test_vectors.json` |
| Valid and invalid transaction examples | `examples/`, `examples/bad/` |
| Transaction format specification | `docs/TX_FORMAT.md` |
| Security threat model | `docs/THREAT_MODEL.md` |

## 12. Demonstration Video

**YouTube Demo:** https://youtu.be/hZrmyZbqbFU

The demonstration covers project structure, Ed25519 key generation, wallet address derivation, transaction preparation, digital signing, signature verification, tampering detection, replay protection, canonical serialization, and automated testing.

---

**Course:** Blockchain Engineering  
**Instructor:** Dr. Mayank Agarwal  
**Department:** Computer Science and Engineering  
**Institution:** Indian Institute of Technology Patna  
**Academic Session:** July–December 2026  
**Roll Number:** 2302CS08
