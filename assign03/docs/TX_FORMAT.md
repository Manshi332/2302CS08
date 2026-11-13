# Transaction format (byte level), `walletlab` v1

An independent implementation needs only this document and the sender's public data.

## 1. Cryptographic choices

| Item | Choice |
|---|---|
| Signature scheme | Ed25519 (RFC 8032), pure/deterministic; library: `cryptography` (OpenSSL) |
| Key sizes | private seed 32 B, public key 32 B (raw, RFC 8032 encoding), signature 64 B = `R(32) ‖ S(32)` |
| Randomness | OS CSPRNG through `Ed25519PrivateKey.generate()`; nothing home-made |
| Hash | SHA-256 (`hashlib`) |

## 2. Address (version "walletlab-addr-v1")

```
pkh      = SHA-256(public_key)[0:20]               20 bytes
payload  = version_byte ‖ pkh                      21 bytes
checksum = SHA-256(SHA-256(payload))[0:4]
address  = Base58(payload ‖ checksum)              Bitcoin alphabet, leading 0x00 -> '1'
```

| network_id | version byte | first character |
|---|---|---|
| `course-testnet` | `0x6F` | `m` or `n` |
| `course-mainnet` | `0x3F` | `S` |

A decoder MUST reject: characters outside the alphabet, decoded length ≠ 25 bytes, bad checksum,
unknown version byte, and any spelling that does not re-encode to the identical string.

## 3. Transaction object

Exactly these seven fields, no others:

| Field | Type | Rule |
|---|---|---|
| `version` | integer | must be `1` |
| `network_id` | string | `course-testnet` or `course-mainnet` |
| `sender` | string | valid address whose version byte matches `network_id` |
| `recipient` | string | same rule |
| `amount_units` | integer | `1 … 2^53−1`, smallest unit (no decimals, no floats, no strings) |
| `nonce` | integer | `0 … 2^53−1`; per sender, must exceed the last accepted nonce |
| `memo_hash` | string | 64 **lowercase** hex = SHA-256 of the off-chain memo (UTF-8) |

## 4. Canonical bytes

The Assignment 1 canonical form (strict subset of RFC 8785):

1. UTF-8, top-level object; floats, NaN, Infinity, duplicate keys rejected; integers within ±(2^53−1).
2. Keys sorted by UTF-16 code units; separators exactly `,` and `:`; **no whitespace**.
3. Strings with minimal escapes (`\" \\ \b \f \n \r \t`, `\u00xx` lowercase for other controls); non-ASCII literal; no Unicode normalization.
4. No trailing newline.

Because of rule 2 the same transaction always yields the same bytes regardless of the input's
whitespace or key order.

## 5. Signed message

```
message   = "walletlab/tx/v1" ‖ 0x00 ‖ canonical_json(transaction)
            (domain tag hex: 77616c6c65746c61622f74782f763100)
signature = Ed25519_sign(private_key, message)
```

The domain tag stops a signature made for a transaction from being valid for any other kind of message
(and vice versa). `network_id` is inside the signed JSON, so a testnet signature is useless on mainnet.

Worked example (from `vectors/test_vectors.json`):

```
canonical JSON : {"amount_units":1250000,"memo_hash":"b300…d620","network_id":"course-testnet","nonce":7,
                  "recipient":"mpDU…sm","sender":"mjX8…mr","version":1}
SHA-256(message): f3150e379702f4bdc8da32058a1f3d8a96cbde4e848c8b9ddb07e8b67f08079c
```

## 6. Signed envelope (what is transmitted)

```json
{ "transaction": { ...seven fields... },
  "public_key": "<64 lowercase hex>",
  "signature":  "<128 lowercase hex>" }
```

## 7. Verification algorithm (all steps must pass, in order)

1. Parse strictly (UTF-8, no duplicate keys, no floats). Envelope has exactly the three fields.
2. Transaction schema (§3) is valid; `network_id` equals the verifier's network.
3. `sender`/`recipient` have valid checksums and the network's version byte.
4. `public_key` and `signature` are lowercase hex of exactly 32 / 64 bytes.
5. **Canonical signature:** integer `S = signature[32:64]` (little-endian) is `< L`, where
   `L = 2^252 + 27742317777372353535851937790883648493`. Otherwise `S + L` would be a second valid
   encoding of the same signature (malleability).
6. `address(public_key, network_id) == sender` — else *wrong signer*.
7. Ed25519 verify over `message` (§5).
8. *(optional, stateful)* `nonce` > last accepted nonce for `sender` — else *replay*.

## 8. Dev private-key file (test-only)

```json
{ "WARNING": "TEST-ONLY DEVELOPMENT KEY. ...", "algorithm": "ed25519",
  "network_id": "course-testnet", "private_key_seed": "<64 hex>" }
```

Created with `O_EXCL` (never overwrites) and mode `0600`; the loader refuses group/world-readable files.
