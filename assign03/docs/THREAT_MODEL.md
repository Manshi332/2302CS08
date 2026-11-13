# Threat model: `walletlab`

Scope: a teaching wallet for a toy chain. It is **not** production software; the notes below say
what it does about each threat and what it leaves open.

## 1. Key theft

*Threat:* whoever copies the private seed can sign anything as that address, forever; signatures
cannot be revoked.

*What the tool does*
- Public key is the only thing exported by default; `keygen` discards the private key unless
  `--dev-export-private` is given.
- The private file is created `0600`, never overwritten, labelled TEST-ONLY, with a warning on stderr;
  the loader refuses files readable by group/others; `.gitignore` blocks `dev_private_key*.json`.
- Nothing prints or logs the seed; signing needs the file explicitly.

*Left open:* the file is **unencrypted** on disk (malware, backups, shared machines, shell history of
`--dev-export-private` paths). Real wallets use encrypted keystores, OS keychains or hardware wallets,
and a recovery plan (multisig, key rotation). Never reuse a dev key for real value.

## 2. Weak randomness

*Threat:* predictable seeds (time-seeded PRNG, small seed space, repeated seeds) let an attacker
recompute the private key. For ECDSA a *repeated or biased nonce k* leaks the key outright (the 2010
PS3 and 2013 Android-wallet incidents).

*What the tool does:* seeds come only from the OS CSPRNG via `cryptography`; no custom RNG or curve code.
Ed25519 derives its per-signature nonce deterministically from seed and message (RFC 8032), so there is
no signing-time RNG to fail. Tests check two generated keys differ and pin the RFC 8032 vector.

*Left open:* a compromised OS RNG (VM clones, early-boot entropy starvation) or a tampered library.

## 3. Replay

*Threat A, same chain:* an observer re-submits a valid signed transaction to debit the sender again.
*Threat B, cross chain:* a testnet transaction is replayed on mainnet or another fork.

*What the tool does*
- `nonce` is signed; the verifier keeps `last_nonce[sender]` (`--state`, `--update-state`) and rejects
  `nonce <= last`. Changing the nonce breaks the signature.
- `network_id` is signed **and** address version bytes differ per network; a verifier on another
  network rejects before looking at the signature. The domain tag `walletlab/tx/v1\0` separates
  transaction signatures from any other protocol's.

*Left open:* `verify` without `--state` is stateless and cannot detect replay, which is a ledger's job.
The state file is local and not tamper-proof; nonce gaps and mempool ordering are not modelled. A
real chain also binds a chain/genesis hash or expiry height.

## 4. Phishing

*Threat:* the user is tricked into signing something they do not understand (a fake "claim airdrop"
site that submits a transaction paying the attacker), or into trusting a lookalike verifier.

*What the tool does:* `sign` re-validates the whole transaction and refuses unless the key owns
`sender`; `verify` prints sender, recipient, amount and nonce so a human can read what is authorized.
Strict schema (no unknown fields, no floats/strings for amounts) reduces "what you see ≠ what is signed".

*Left open:* no UI-level confirmation prompt, no address book, no hardware-screen display. Humans must
compare the recipient address out of band. Signing blindly is signing.

## 5. Clipboard address replacement

*Threat:* malware swaps the address on the clipboard for the attacker's. The attacker's address is
*valid*, so the checksum cannot catch it. (Checksums only catch typos, Base58Check detects any
single-character error with certainty and random multi-character errors with probability 1 − 2⁻³².)

*What the tool does:* validates checksum and network prefix on every address, so corrupted or wrong-network
addresses are refused. `address --check` lets users validate a pasted address.

*Mitigations outside the tool:* compare first and last several characters on a second device or channel,
send a small test amount first, use an address book / allow-list, keep the OS malware-free, prefer
signing devices that display the recipient.

## 6. Accidental mainnet use

*Threat:* a test key or test transaction is used on the real network (or real funds are sent to a
test address, where they are lost).

*What the tool does:* two independent barriers; (1) separate version bytes → different address prefixes
(`m`/`n…` for testnet, `S…` for mainnet) so addresses visibly differ and cannot be
cross-decoded as valid for the other network; (2) `network_id` is signed and `verify` defaults to
`course-testnet` and requires `--network course-mainnet` explicitly to accept mainnet transactions.
Private key files carry the TEST-ONLY warning and their network. `sign` refuses mismatches between
key network and transaction network.

*Left open:* nothing stops a user from deliberately passing `--network course-mainnet`, and a dev key can
still be copied into a mainnet context by hand. Real systems use separate key hierarchies per network.

## 7. Other (briefly)

| Threat | Handling |
|---|---|
| Signature malleability (`S + L`) | non-canonical `S` rejected before verification |
| Parser differentials (duplicate keys, 1.0 vs 1, odd whitespace) | strict parser + canonical bytes; duplicates/floats rejected |
| Uppercase / alternative hex spellings | only lowercase hex accepted for keys, signatures, `memo_hash` |
| Overwriting a key file | `O_EXCL` creation, no overwrite |
| Side channels, fault injection, supply-chain compromise of dependencies | out of scope; rely on `cryptography` and pinned versions |
