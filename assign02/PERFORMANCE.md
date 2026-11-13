# Performance report: construction time and proof size

**Setup.** Pure Python 3.12.3, standard-library `hashlib` SHA-256, single thread, Linux x86_64
(Intel Xeon @ 2.1 GHz, 1 core, shared sandbox VM). Leaves are the strings `transaction-<i>`.
Times are the best of 5 runs (best of 2 for 1,000,000). Reproduce with:

```bash
merkle bench --sizes 8,1024,100000 --repeat 5 --markdown
merkle bench --sizes 1000000 --repeat 2 --markdown
```

## Results

| leaves | build (ms) | root-only (ms) | SHA-256 calls | prove (us) | verify (us) | siblings | ceil(log2 n) | proof raw (B) | proof JSON (B) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 0.01 | 0.01 | 15 | 7.7 | 5.7 | 3 | 3 | 96 | 316 |
| 1,024 | 1.04 | 1.05 | 2,047 | 12.5 | 8.3 | 10 | 10 | 320 | 956 |
| **100,000** | **116.40** | 114.42 | 199,999 | 36.0 | 13.0 | 17 | 17 | 544 | 1,595 |
| 1,000,000 (extra) | 1,194.24 | 1,180.52 | 1,999,999 | 569.3 | 25.3 | 20 | 20 | 640 | 1,869 |

Column meanings: **build** = hash all leaves and build and keep every level (`MerkleTree`);
**root-only** = `merkle_root()`, which keeps just one level at a time; **prove / verify** = mean time
for one proof over up to 200 evenly spread indexes (every proof also verified, as a self-check);
**siblings** = longest proof in the sample; **proof raw** = 32 bytes per sibling hash;
**proof JSON** = the same proof as compact JSON (hex-encoded hashes plus directions and field names).

## Observations

1. **Construction is linear.** A tree of `n` leaves needs exactly `n` leaf hashes and `n - 1` node hashes
   (every pairing removes one node; promoted nodes are not hashed), i.e. `2n - 1` SHA-256 calls.
   Going from 1,024 to 100,000 leaves (about 98x more) raised build time from 1.04 ms to 116 ms
   (about 112x), and 1,000,000 leaves (10x more again) took about 10.3x longer. That is roughly 0.6 us per hash call,
   dominated by Python overhead, not by SHA-256 itself.
2. **Proof size is logarithmic.** Siblings = `ceil(log2 n)` in every row: 3, 10, 17, 20.
   Raw proof size is 96 B, 320 B, 544 B, 640 B: for 100,000 transactions you transmit 544 bytes
   instead of the 100,000 leaves (about 1.7 MB of raw leaf text at this leaf size, or 3.2 MB of leaf hashes).
   Multiplying the leaf count by 10 adds only about 3.3 siblings (106 bytes).
3. **JSON costs about 3x the raw size** (hex doubles each hash, plus `"side"`/`"hash"` keys and punctuation): 1,595 bytes at 100,000 leaves.
   Still tiny; a binary encoding would be the choice if bandwidth mattered.
4. **Verification is cheap and nearly flat:** 13 us at 100,000 leaves (17 hashes + checks). Verifying needs
   no tree, only the leaf, proof, and root.
5. **Keeping all levels costs almost nothing in time** (build and root-only agree within about 2%) but roughly doubles memory
   (about 2n hashes stored), which is the price of O(log n) proof generation.
6. **Prove time at 1,000,000 leaves (569 us) is much higher than the trend** (36 us at 100,000).
   I did not profile this; the likely cause is memory effects (two million separate hash objects spread over memory, so
   sampled lookups miss CPU caches, and garbage collection of a large heap). The tree-building and verification
   numbers do not show it.

## Caveats

- One machine, one run configuration; absolute numbers will differ on yours. The shapes (linear build, logarithmic proof) will not.
- Pure Python is much slower than a native implementation; the assignment asked for correctness and measurement, not speed.
- Timings exclude generating the input strings and reading files.
