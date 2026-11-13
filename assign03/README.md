# Assignment 3: Keys, Addresses, and Signed Transactions (`walletlab`)

**Course:** Blockchain, Dr. Mayank Agarwal, CSE, IIT Patna (Jul-Dec 2026)
**Student:** `<YOUR NAME>` | **Roll number:** `<YOUR ROLL NO>`
**Demo video (YouTube, Unlisted):** `<PASTE YOUTUBE LINK HERE>`

An educational wallet: it generates Ed25519 keys, derives Base58Check addresses, builds a canonical
transaction, signs it, and lets anyone verify it **using only public data and the specification**.
All elliptic-curve math and randomness come from the maintained
[`cryptography`](https://cryptography.io) library; none is implemented here.

| Deliverable | Where |
|---|---|
| Commands `keygen`, `address`, `sign`, `verify` | `src/walletlab/cli.py` |
| Tests (57) | `tests/test_walletlab.py` |
| Byte-level transaction-format document | [`docs/TX_FORMAT.md`](docs/TX_FORMAT.md) |
| Threat-model note | [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) |
| Test vectors + tamper cases | `vectors/test_vectors.json`, `examples/`, `examples/bad/` |

**Reuse from Assignment 1:** the canonical-JSON rules (`hashlab` canonical form v1) are copied into
`src/walletlab/canonical.py` so this folder is self-contained. They give identical signed bytes for JSON
that differs only in whitespace or key order.

---

## 1. Setup

Python **3.11+**; one runtime dependency (`cryptography`).

```bash
# from inside this assignment folder
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # cryptography + pytest
pip install -e .                   # installs the `walletlab` command
```

Without installing: `PYTHONPATH=src python3 -m walletlab <command>` (PowerShell: `$env:PYTHONPATH="src"`).

## 2. Usage

### `keygen`: key pair from the OS CSPRNG (public key only by default)

```console
$ walletlab keygen --public-out alice.pub.json
network: course-testnet
public_key: 5c8170ed...1c39
address: msQSCSB3ukWznXune7uzPjN1S6Yqq9uh5h
private key: NOT saved (use --dev-export-private PATH for a test-only key file)

$ walletlab keygen --public-out alice.pub.json --dev-export-private dev_private_key_alice.json
WARNING: wrote UNENCRYPTED private key to dev_private_key_alice.json (mode 0600).
WARNING: TEST-ONLY DEVELOPMENT KEY. Never use for real funds, never commit, never share.
```

Files are created exclusively (no overwrite). The private file is `0600` and the loader refuses looser modes.

### `address`: derive or validate

```console
$ walletlab address --pub alice.pub.json            # or --public-key <64 hex>
$ walletlab address --check msQSCSB3ukWznXune7uzPjN1S6Yqq9uh5h --network-required course-testnet
valid: yes
```

`pkh = SHA-256(pubkey)[:20]`; `address = Base58Check(version_byte ‖ pkh)`; testnet `0x6F`, mainnet `0x3F`.

### `sign`

```console
$ walletlab sign --key dev_private_key_alice.json --tx examples/tx.json --out signed.json
```

Refuses unless the key owns `sender` and the transaction passes the strict schema.

### `verify`: needs only the signed file (public data) and the specification

```console
$ walletlab verify --signed examples/signed_tx.json
VALID
network: course-testnet
sender: mjX8sCthdoF8Xj36VvX8ZLoMWUVr1kBtmr
...
$ walletlab verify --signed examples/bad/amount_changed.json
REJECTED: signature does not verify (a signed field was changed, or wrong key)     # exit status 1
```

Replay protection (stateful): `--state state.json` rejects `nonce <= last accepted` for that sender;
add `--update-state` to record a newly accepted nonce.

```console
$ walletlab verify --signed signed.json --state state.json --update-state   # VALID, nonce 7 stored
$ walletlab verify --signed signed.json --state state.json                  # REJECTED: replayed ...
```

`walletlab canonical FILE` prints the canonical JSON text, a debugging aid.

## 3. How each rejection requirement is met

| Required rejection | Check | Demonstrated by |
|---|---|---|
| Changed amount (any field) | signature over canonical bytes fails | `examples/bad/amount_changed.json`, `test_changing_any_signed_field_fails` |
| Wrong network | `network_id` ≠ verifier's network; address version bytes | `bad/wrong_network.json`, `test_wrong_network_rejected` |
| Wrong signer | `address(public_key) ≠ sender` | `bad/wrong_signer.json`, `test_wrong_signer_rejected` |
| Replayed nonce | `nonce <= last_nonce[sender]` with `--state` | `test_replayed_nonce_rejected_by_state`, `test_cli_end_to_end` |
| Malformed address / invalid checksum | Base58Check decode, length, version, canonical spelling | `bad/bad_checksum_address.json`, `test_every_single_char_typo_detected` |
| Non-canonical signature encoding | lowercase hex, 64 bytes, scalar `S < L` | `bad/signature_non_canonical_S.json`, `bad/signature_uppercase.json` |

Acceptance: `examples/signed_tx_reordered.json` (shuffled keys, tabs/newlines) verifies with the same
`signing_bytes_sha256` as `examples/signed_tx.json`.

## 4. Tests and reproducibility

```bash
python3 -m pytest -q          # 57 passed
PYTHONPATH=src python3 scripts/gen_examples.py   # regenerate examples/ and vectors/ (deterministic)
```

Example keys come from public, test-only seeds (`SHA-256("walletlab test-only alice")`, `... bob`);
Ed25519 signing is deterministic, so everyone obtains identical bytes. The tests also pin the
RFC 8032 test vector 1 to prove the library is used correctly.

## 5. Design notes and limits

- **Why Ed25519:** small, deterministic signatures (no signing-time RNG), simple encoding. The assignment
  allows secp256k1 or Ed25519.
- Address hash is SHA-256 truncated to 20 bytes (no RIPEMD-160, which OpenSSL 3 may not ship).
- Stateless `verify` cannot detect replay; use `--state` (a real ledger would own that state).
- Private keys are stored **unencrypted** (development only). See [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).
