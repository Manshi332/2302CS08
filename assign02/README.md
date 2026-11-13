# Assignment 2: Merkle Trees and Proofs of Inclusion (`merklelab`)

**Course:** Blockchain, Dr. Mayank Agarwal, CSE, IIT Patna (Jul-Dec 2026)
**Student:** `<YOUR NAME>` | **Roll number:** `<YOUR ROLL NO>`
**Demo video (YouTube, Unlisted):** `<PASTE YOUTUBE LINK HERE>`

A from-scratch Merkle tree library and CLI (`merkle root | prove | verify | bench`). No Merkle-tree package is used;
the only primitive is SHA-256 from Python's standard-library `hashlib`.

| Deliverable | Where |
|---|---|
| Library | `src/merklelab/` (`hashing.py`, `tree.py`, `proof.py`, `leafio.py`, `bench.py`) |
| CLI: `root`, `prove`, `verify` (+ `bench`) | `src/merklelab/cli.py` |
| Test vectors | `vectors/test_vectors.json` (15 sets), plus published RFC 6962 roots in the tests |
| Performance report | [`PERFORMANCE.md`](PERFORMANCE.md) |
| Diagram: exact proof path for five transactions | [`docs/proof_path_5_tx.svg`](docs/proof_path_5_tx.svg) (also `.png`) |

![Proof path for five transactions](docs/proof_path_5_tx.svg)

---

## 1. Requirements and setup

Python **3.11+**. No runtime dependencies (standard library only); `pytest` is needed only for tests.

```bash
# from inside this assignment folder
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # pytest (tests only)
pip install -e .                   # installs the `merkle` command
```

Without installing: `PYTHONPATH=src python3 -m merklelab <command>` (PowerShell: `$env:PYTHONPATH="src"`).

## 2. The specification (unambiguous)

| Item | Rule |
|---|---|
| Hash | SHA-256 |
| Leaf hash | `Hleaf(data) = SHA-256(0x00 ‖ data)` |
| Internal node | `Hnode(left, right) = SHA-256(0x01 ‖ left ‖ right)`; both children exactly 32 bytes |
| Pairing | Level by level, adjacent nodes paired left to right |
| **Odd count** | The last, unpaired node is **promoted to the next level unchanged** (not duplicated, not re-hashed) |
| Zero leaves | `root = SHA-256("")` = `e3b0c442...b855` |
| One leaf | `root = Hleaf(data)` |
| Next level size | `ceil(n / 2)`; stop when one node remains |
| Proof order | Siblings are listed **from the leaf level upward** |
| Direction | `side` is where the **sibling** sits: `"left"` means `h = Hnode(sibling, h)`; `"right"` means `h = Hnode(h, sibling)` |
| Unpaired node | Has **no sibling** at that level, so it contributes nothing to the proof |

This is exactly the tree defined in RFC 6962 (Certificate Transparency). The roots for 0 to 8 leaves match the published CT
test roots (checked in `tests/test_merklelab.py::test_rfc6962_ct_published_roots`).

**Why domain separation?** Without the `0x00`/`0x01` prefixes, a 64-byte value `left ‖ right` hashes the same as an internal node,
so an attacker can present an internal node as a "leaf" (second-preimage attack). With prefixes the two hashes live in different
domains (test: `test_domain_separation_blocks_node_as_leaf`).

**Why promote instead of duplicate?** Bitcoin-style duplication makes `[a, b, c]` and `[a, b, c, c]` share a root (CVE-2012-2459).
With promotion every leaf list has its own root (test: `test_no_duplicate_leaf_ambiguity`).

### How the verifier decides (Task 4 and 5)

`verify(leaf, proof, expected_root)` uses **only** those three inputs. It does **not** trust the proof's own claims about its shape:

1. From `(leaf_index, tree_size)` it recomputes the exact list of directions the path must have.
2. It **rejects** a proof with more siblings than that (**unnecessarily long**) or fewer (too short).
3. It **rejects** any sibling whose `side` differs from the recomputed direction (**invalid / wrong direction**).
4. It **rejects** an out-of-range `leaf_index` (**wrong index**). An in-range but wrong index changes the expected
   directions or the folded root, so it fails too.
5. Only then does it fold the leaf up and compare with the expected root, returning `True` or `False`.

> **Note on the sheet's example.** The assignment's example proof for `leaf_index: 2, tree_size: 5` shows two siblings.
> That is illustrative: a leaf in a 5-leaf tree needs **three** (leaf 3 on the right, hash of leaves 0+1 on the left,
> leaf 4 on the right), as the diagram shows. The JSON shape (`leaf_index`, `tree_size`, `siblings[{side, hash}]`) is identical.

## 3. Proof JSON format and validation

```json
{
  "leaf_index": 2,
  "tree_size": 5,
  "siblings": [
    {"side": "right", "hash": "2f390850473879f7703fb2c95a634ca1ac5ff9334e85793c22a0d366ee1f87a9"},
    {"side": "left",  "hash": "983a3d6975e5df6f54cd52814248dbb5d5d2e29b0b83cca6cc703d0e5ecaa6b5"},
    {"side": "right", "hash": "6689c56f30b7d572d08f4b1f7ac0911d9a375f865d93bee06f865bfe7634ebd0"}
  ]
}
```

Strict parsing rejects: invalid JSON; duplicate keys; `NaN`; non-object top level; missing or **extra** keys;
`leaf_index` / `tree_size` that are not plain integers (floats, strings, booleans); `tree_size` < 1 or > 2^64-1;
`leaf_index` out of range; `siblings` not a list; a sibling that is not exactly `{side, hash}`;
`side` anything other than exactly `"left"` or `"right"` (so `"Left"`, `"up"`, `null`, `0` fail);
`hash` that is not exactly **64 hex characters** (wrong length, non-hex, `0x` prefix, whitespace, non-string).
Uppercase hex is accepted on input; output is always lowercase.

## 4. CLI usage

Leaves come from a file, **one leaf per line** (`-` = stdin). Rules: raw line bytes (no decoding or Unicode normalization);
CRLF = LF; a final line terminator does not start another leaf; blank lines in the middle are empty leaves; an empty file has
zero leaves. `--encoding hex` reads each line as strict hex bytes instead.

`examples/transactions.txt`:

```
Alice pays Bob 10
Bob pays Carol 4
Carol pays Dave 7
Dave pays Erin 2
Erin pays Alice 5
```

### `merkle root`

```console
$ merkle root --leaves examples/transactions.txt
leaves: 5
root: 78c00d2ca02b959884ad83513a0f566abcc72b95f02e5400df4da618ca36d248
```

### `merkle prove`

```console
$ merkle prove --leaves examples/transactions.txt --index 2 --out examples/proof_index2.json
proof written to examples/proof_index2.json (root 78c00d2c...)      # message goes to stderr
$ merkle prove --leaves examples/transactions.txt --index 2         # without --out: pure JSON on stdout
```

### `merkle verify`

```console
$ merkle verify --root 78c00d2ca02b959884ad83513a0f566abcc72b95f02e5400df4da618ca36d248 \
      --leaf "Carol pays Dave 7" --proof examples/proof_index2.json --tree-size 5
VALID: leaf at index 2 is included in a tree of 5 leaves with root 78c00d2c...

$ merkle verify --root 78c0... --leaf "Carol pays Dave 8" --proof examples/proof_index2.json
INVALID: proof is well-formed but does not match the expected root
  computed root: 245c790b01b04f158612ce23b7d63b7d9e67d257293fc094c1b74a862bfa002a
  expected root: 78c00d2ca02b959884ad83513a0f566abcc72b95f02e5400df4da618ca36d248
```

Leaf input: `--leaf TEXT` (UTF-8), `--leaf-hex HEX`, or `--leaf-file FILE` (exact bytes). Proof: `--proof FILE` or `-` for stdin.
`--tree-size N` (optional) additionally requires the proof to claim that size (see section 6).
Exit codes: `0` valid / success; `1` invalid proof or input error; `2` command-line usage error.

Malformed proofs in `examples/bad_proofs/` are each rejected with a specific message
(root and leaf as above):

| File | Result |
|---|---|
| `malformed_hash_short.json` | `INVALID: siblings[0]: malformed hash; need exactly 64 hex characters` |
| `malformed_hash_chars.json` | `INVALID: siblings[1]: malformed hash; need exactly 64 hex characters` |
| `invalid_direction_value.json` | `INVALID: siblings[0]: invalid direction 'up'; must be 'left' or 'right'` |
| `wrong_direction.json` | `INVALID: siblings[0]: direction 'left' is wrong for leaf_index 2 in a tree of 5 leaves (expected 'right')` |
| `index_out_of_range.json` | `INVALID: leaf_index 9 out of range for tree_size 5` |
| `wrong_index.json` | `INVALID: siblings[0]: direction 'right' is wrong for leaf_index 1 in a tree of 5 leaves (expected 'left')` |
| `too_long.json` | `INVALID: proof is unnecessarily long: 4 siblings, but leaf_index 2 in a tree of 5 leaves needs exactly 3` |
| `too_short.json` | `INVALID: proof is too short: 2 siblings, but leaf_index 2 in a tree of 5 leaves needs exactly 3` |

### `merkle bench` (Task 6)

```console
$ merkle bench --sizes 8,1024,100000 --repeat 5 --markdown
```

Full table, method, and analysis in [`PERFORMANCE.md`](PERFORMANCE.md). Headline numbers on the test machine
(pure Python, one core):

| leaves | build time | siblings | proof size (raw / JSON) |
|---:|---:|---:|---:|
| 8 | 0.01 ms | 3 | 96 B / 316 B |
| 1,024 | 1.04 ms | 10 | 320 B / 956 B |
| 100,000 | 116 ms | 17 | 544 B / 1,595 B |
| 1,000,000 (extra) | 1.19 s | 20 | 640 B / 1,869 B |

Construction is linear (`2n - 1` hash calls); proofs grow logarithmically.

## 5. Library use

```python
from merklelab import MerkleTree, Proof, verify

leaves = [b"Alice pays Bob 10", b"Bob pays Carol 4", b"Carol pays Dave 7"]
tree = MerkleTree(leaves)              # or merkle_root(leaves) when you only need the root
proof = tree.prove(2)                  # Proof(leaf_index=2, tree_size=3, siblings=(...))
text = proof.to_json()                 # serialize
ok = verify(leaves[2], Proof.from_json(text), tree.root)   # True; no access to the tree needed
```

Errors: `ProofFormatError` (malformed proof), `ProofError` (wrong shape / direction / length / index / size),
both subclasses of `MerkleError`. `verify` returns `False` only for a well-formed, consistent proof that folds to a different root.

## 6. Security notes and limits

- **The root does not commit to the number of leaves.** A proof for index 2 in a tree of 5 has the same path shape as
  index 2 in a tree of 6, so the same siblings also verify against the 5-leaf root if the proof *claims* `tree_size = 6`
  (demonstrated in `test_tree_size_pinning`). Real systems publish the size together with the root (for example the
  signed tree head in Certificate Transparency). Pass `--tree-size N` / `tree_size=N` to make the verifier enforce it.
- Leaves are raw bytes. Different byte encodings of the "same" text give different roots (see Assignment 1). Normalize before building the tree.
- A text-mode line cannot end in a literal `\r` (one trailing CR is treated as part of CRLF); use `--encoding hex` for such leaves.
- No timing-attack concerns: all hashes are public.

## 7. Tests and test vectors

```bash
pytest -q          # 161 tests, all passing
```

- **Independent reference:** `tests/reference_rfc6962.py` is a separate recursive implementation of RFC 6962 (written differently
  and sharing no code). Roots match it for sizes 0-65 and for 100, 127, 128, 129, 255, 1000; **every** proof matches for sizes 0-65, and 40 spread-out proofs for each larger size.
- **Published vectors:** roots for 0-8 leaves match the Certificate Transparency reference roots.
- **`vectors/test_vectors.json`:** 15 leaf sets (CT sizes 0-8, the five transactions, sizes 9, 10, 11, 16, 17) with root and
  every inclusion proof, generated by the independent reference (`python scripts/gen_vectors.py`).
- Hand-computed roots for 0, 1, 2, 3, 4, 5 leaves; odd/even; promotion vs duplication; domain separation attack.
- Proofs for every leaf of every size 1-33 verify, wrong leaf/root fail, every sibling tampering is caught.
- Rejections: wrong direction, wrong index, too long, too short, 29 malformed-field cases, malformed JSON text, bad UTF-8.
- CLI behaviour, exit codes, CRLF handling, hex leaves, and all eight files in `examples/bad_proofs/`.
- 100,000 leaves built; root checked against the independent reference; seven spread-out proofs (including the 65,535/65,536 boundary) verified.

## 8. Project structure

```
assign02/
├── README.md
├── PERFORMANCE.md             <- performance report
├── requirements.txt           <- pytest (tests only); runtime is stdlib only
├── pyproject.toml             <- package metadata, `merkle` entry point, pytest config
├── .gitignore
├── src/merklelab/
│   ├── hashing.py             <- Hleaf, Hnode, EMPTY_ROOT, MerkleError
│   ├── tree.py                <- MerkleTree, merkle_root, proof generation
│   ├── proof.py               <- Proof/Sibling, strict JSON, expected_sides, verify
│   ├── leafio.py              <- one-leaf-per-line file rules
│   ├── bench.py               <- benchmark
│   ├── cli.py                 <- root / prove / verify / bench
│   └── __main__.py
├── tests/                     <- test_merklelab.py, reference_rfc6962.py
├── vectors/test_vectors.json
├── examples/                  <- transactions.txt, proof_index2.json, bad_proofs/
├── docs/                      <- proof_path_5_tx.svg / .png
└── scripts/                   <- gen_vectors.py, make_diagram.py
```

## 9. Demo video checklist (with audio, Unlisted on YouTube)

1. Setup and `pytest -q` passing; mention the independent RFC 6962 cross-check.
2. Show the specification: prefixes, promotion rule, zero/one leaf roots.
3. `merkle root` and `merkle prove --index 2`; walk through the diagram (three siblings, directions).
4. `merkle verify` VALID; change one character of the leaf -> INVALID.
5. Run the bad proofs in `examples/bad_proofs/` (malformed hash, direction, index, too long).
6. `merkle bench`; explain linear build and logarithmic proofs (see `PERFORMANCE.md`).
7. Explain why the tree size should be pinned (`--tree-size`).

## 10. Submission checklist

- [ ] This folder is `assign02/` at the root of your private roll-number repo (like `assign01`...`assign07` in the reference repo)
- [ ] Collaborator `blockchain.iitp.20261@atomicmail.io` added
- [ ] YouTube link above filled in, video **Unlisted**
- [ ] Link submitted on the MS Form: https://forms.cloud.microsoft/r/huBck9hkD7
