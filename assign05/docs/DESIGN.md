# Design: blocks, Proof of Work, chain selection, reorganisation

This document is the specification the code follows. File names refer to `src/chainlab/`.

## 1. Layers

```
cli.py  simulate.py  acceptance.py  bench.py  report.py      commands, scenarios, measurements
chain.py        block index, cumulative work, fork choice, reorg           (new)
miner.py        block assembly + nonce search                              (new)
state.py        ChainLedger: connect_block / disconnect_block              (new, extends Assignment 4)
consensus.py    ChainParams + context-free block rules                     (new)
block.py  proofofwork.py  merkle.py                                        (new)
ledger.py tx.py wallet.py keys.py address.py base58.py canonical.py selection.py   (Assignment 4, UNCHANGED)
```

Single-transaction validation (inputs exist, no double spend, `pkh` match, canonical Ed25519
signature, value conservation, overflow limits) is exactly the Assignment 4 `Ledger.validate`.

## 2. Block header (112 bytes, big-endian)

| offset | size | field | rule |
|---:|---:|---|---|
| 0 | 4 | version | must be 1 |
| 4 | 32 | prev_hash | parent block hash (32 zero bytes for genesis) |
| 36 | 32 | merkle_root | root over the txids of the block's transactions |
| 68 | 8 | timestamp | Unix seconds, `0 .. 2^53-1` |
| 76 | 32 | target | 256-bit unsigned integer, `1 .. 2^256-1` |
| 108 | 4 | nonce | `0 .. 2^32-1` |

`block_hash = SHA-256(SHA-256(header))`. The digest is interpreted as a **big-endian** integer
(no byte reversal), so the hex string you read is the number that is compared with the target.

## 3. Proof of Work

* Valid when `int(block_hash) <= target`.
* `target_from_bits(b) = 2^(256-b) - 1`: the first `b` bits of the hash are zero, success
  probability per attempt `2^-b`, expected attempts `2^b`.
* `work(target) = floor(2^256 / (target + 1))` = expected attempts.
* Mining tries nonces `0, 1, 2, ...`. If all `2^32` fail the timestamp is incremented (toy
  extra-nonce). The search is deterministic, so tests and traces are reproducible.
* `pow_limit`: no block may use a target easier than `ChainParams.min_bits`. Between `pow_limit`
  and the hardest target any value is allowed (see limitations).

## 4. Merkle root

Same tree as Assignment 2: leaf = `SHA-256(0x00 || txid)`, node = `SHA-256(0x01 || l || r)`, an
unpaired last node is promoted unchanged (never duplicated). Leaves are the raw 32-byte txids in
block order. `[a,b,c]` and `[a,b,c,c]` therefore have different roots.

## 5. Block validity

Context-free (`consensus.check_block_structure`), in this order:

1. `0 < target <= pow_limit` (`bad_target`)
2. hash <= target (`bad_pow`)
3. at least one transaction, at most `max_block_txs` (`no_transactions`, `too_many_txs`)
4. `txs[0]` is a coinbase (no inputs) and no other tx is (`missing_coinbase`, `multiple_coinbase`)
5. no duplicate txids (`duplicate_txid`)
6. `merkle_root` equals the recomputed root (`bad_merkle`)
7. coinbase has no witnesses, right network, memo `coinbase:<height>` (`bad_coinbase`)

Contextual (`Chain.add_block`): parent known (`unknown_parent`), parent not invalid
(`invalid_ancestor`), `timestamp > median of the last 11 ancestors` (`timestamp_too_old`),
`timestamp <= node clock + 7200 s` (`timestamp_too_far_future`).

State transition (`ChainLedger.connect_block`), applied only when the block joins the active chain:

1. For each non-coinbase transaction, in order: `Ledger.validate` then commit. Later transactions
   may spend outputs created by earlier ones in the same block. Any failure gives `invalid_tx`
   (with the Assignment 4 code in `BlockError.inner`).
2. Coinbase: `sum(outputs) <= subsidy(height) + sum(fees)` (`coinbase_excess`).
3. If anything fails, every transaction already applied is rolled back in reverse order. The
   state is bit-for-bit what it was before.

Accounting: `issued == unspent + burned`. A miner that claims less than allowed burns the rest.

## 6. Chain selection

* Each stored block has `chain_work = parent.chain_work + work(block)`.
* The active tip is the known block with the greatest `chain_work`; a challenger needs
  **strictly more**, so on a tie the first-seen branch stays active.
* Block count never enters the rule. A 5-block branch of 16-work blocks (80) loses to a 1-block
  branch of 1024 work.

## 7. Reorganisation (`Chain._reorganize`)

1. Walk back from the new tip until a block on the active chain is found: the fork point.
2. Disconnect active blocks from the tip down to the fork point (`disconnect_block` applies the
   stored `BlockUndo`: remove created outputs, restore spent ones, delete their "spent" history,
   undo the coinbase accounting).
3. Connect the new branch block by block with full validation.
4. Failure at any block: disconnect what was connected, reconnect the old branch, forget the
   failing block and all its descendants (they are remembered as invalid), raise `BlockError`.
5. Success: return `AddResult(status="reorganized", ...)` including the transactions of the
   disconnected blocks that the new branch does not contain, so the caller can re-queue them.

Because the undo data is exact, `ledger.state_hash()` after a reorganisation equals the state
hash of a fresh node that replayed only the winning branch (tested).

## 8. Persistence

`Chain.save` writes `{format, params, blocks}` where `blocks` is every non-genesis block in arrival
order (side branches included). `Chain.load` rebuilds the chain by re-validating each block, so a
doctored file is rejected at load time. Genesis is regenerated deterministically from the params.

## 9. Limitations (deliberate)

* Any target between `pow_limit` and 2^256-1 is accepted instead of a retargeting rule. Harder
  targets count as more work, so this cannot be exploited, but real chains derive the target.
* Side-branch blocks are only fully validated when their branch becomes the best one.
* No networking, no mempool (reorgs return the orphaned transactions to the caller), no coinbase
  maturity, no signature-hash types.
* The toy difficulties (4 to 20 bits) are far below anything secure. This is a demonstration, not
  cryptocurrency mining software.
