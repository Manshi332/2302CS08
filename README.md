# Assignment 1: Bytes, Hashes, and Reproducible Data (`hashlab`)

**Course:** Blockchain, Dr. Mayank Agarwal, CSE, IIT Patna (Jul-Dec 2026)

**Student:** `Manshi Prajapoati` | **Roll number:** `2302CS08`

**Demo video (YouTube, Unlisted):** `[YouTube Link ]`

`hashlab` is a command-line tool that produces SHA-256 diagnostics for text, hex byte strings, files, and canonical JSON. SHA-256 is **not** implemented here; the tool calls Python's standard-library `hashlib`. The work is in handling bytes correctly, making results reproducible, and demonstrating the properties blockchains rely on.

---

## 1. Requirements

- Python **3.11 or newer** (uses `int.bit_count()` and modern typing syntax)
- No third-party runtime dependencies (standard library only)
- `pytest` only if you want to run the tests

## 2. Setup

### Development Environment

The project was developed and tested using:

- Visual Studio Code (VS Code)
- Python 3.11 or newer
- Windows PowerShell (VS Code integrated terminal)
- Python virtual environment (`.venv`)
- pytest for automated testing

### Windows (VS Code + PowerShell)

**Step 1: Open the project**

1. Open Visual Studio Code.
2. Select **File → Open Folder**.
3. Select the `assign01` folder.
4. Open the integrated terminal using **Terminal → New Terminal**.

**Step 2: Create a virtual environment**

Run the following command in the VS Code PowerShell terminal:

```powershell
python -m venv .venv
```

**Step 3: Activate the virtual environment**

```powershell
.venv\Scripts\Activate.ps1
```

After successful activation, `(.venv)` appears at the beginning of the terminal prompt.

If PowerShell blocks script execution, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

**Step 4: Select the Python interpreter in VS Code**

1. Press `Ctrl + Shift + P` to open the Command Palette.
2. Search for `Python: Select Interpreter`.
3. Select the Python interpreter inside the project's `.venv` folder.

**Step 5: Install dependencies**

```powershell
pip install -r requirements.txt
```

This installs pytest for running the tests.

Install the project in editable mode:

```powershell
pip install -e .
```

This makes the `hashlab` command available in the terminal.

**Step 6: Run the project**

```powershell
python -m hashlab --help
```

You can now execute the different commands:

```powershell
python -m hashlab text "Alice pays Bob 10"
python -m hashlab hex 0xdeadbeef
python -m hashlab file examples/no_newline.txt
python -m hashlab demo
```

All examples below use the installed `hashlab` command; `python -m hashlab ...` is equivalent.

**Step 7: Run automated tests**

```powershell
python -m pytest -v
```

The test suite contains 44 tests, all passing.

### Linux / macOS (Alternative)

From inside the assignment folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Without installing, you can also run it directly from the folder:

**Windows PowerShell:**

```powershell
$env:PYTHONPATH="src"
python -m hashlab text "hello"
```

**Linux / macOS:**

```bash
PYTHONPATH=src python3 -m hashlab text "hello"
```

## 3. Usage

### 3.1 `text`, `hex`, `file`: hash and display diagnostics

Each prints the input byte length, SHA-256 in hexadecimal, and SHA-256 in Base64.

```console
$ hashlab text "Alice pays Bob 10"

bytes: 17

sha256: 69ad18dfd1ac4b3d711b02ee62caa00a82f0f67cc11ebacdd0c0ede0d8b6eaed

sha256_base64: aa0Y39GsSz1xGwLuYsqgCoLw9nzBHrrN0MDt4Ni26u0=


$ hashlab hex 0xdeadbeef

bytes: 4

sha256: 5f78c33274e43fa9de5659265c1d917e25c03722dcb0b8d27db8d5feaa813953

sha256_base64: X3jDMnTkP6neVlkmXB2RfiXANyLcsLjSfbjV/qqBOVM=


$ hashlab file examples/no_newline.txt

bytes: 17

sha256: 69ad18dfd1ac4b3d711b02ee62caa00a82f0f67cc11ebacdd0c0ede0d8b6eaed


$ hashlab file examples/with_newline.txt

bytes: 18

sha256: a559dd30f6cd021ebe7f50aa899b92a360968ff9195877190f1954140d4e1b39

```

> Note: `"Alice pays Bob 10"` is **17** bytes (5+1+4+1+3+1+2). The assignment sheet's example shows 18, which is the length *with* a trailing newline (see `examples/with_newline.txt`). That difference is exactly what this assignment is about.

| Command | Notes |
|---|---|
| `hashlab text VALUE` | UTF-8 encodes `VALUE`. Options: `--normalize {NFC,NFD,NFKC,NFKD}` applies Unicode normalization first (default: none). `--escapes` interprets `\n \r \t \\` so you can test newlines on any shell. |
| `hashlab hex VALUE` | **Strict** hex: optional `0x` prefix, even number of digits, characters `0-9a-fA-F` only. No spaces. Anything else is rejected with exit code 1. |
| `hashlab file PATH` | Streams the file in 1 MiB chunks (`--chunk-size BYTES` to change). `-` reads standard input. |

Rejecting malformed hex:

```console
$ hashlab hex abc

error: malformed hex: odd number of digits (3); each byte needs exactly two hex digits

$ hashlab hex 0xZZ

error: malformed hex: invalid character 'Z'
```

### 3.2 `avalanche`: flip one bit, measure the digest change

```console
$ hashlab avalanche --text "Alice pays Bob 10" --bit 7

input_bytes: 17

bit_flipped: 7 (byte 0, mask 0x01)

original_sha256: 69ad18df...

flipped_sha256: effa3a72...

changed_bits_in_digest: 119

changed_fraction: 0.465 (ideal avalanche is about 0.5)
```

- Input source: exactly one of `--text`, `--hex`, `--file`.
- **Bit numbering:** bit 0 is the **most significant** bit of byte 0; bit 7 is the least significant bit of byte 0; bit 8 is the MSB of byte 1, and so on. So `--bit 7` on `"Alice..."` changes `A` (0x41) to `@` (0x40).
- `changed_bits_in_digest` is the **Hamming distance** between the two 256-bit digests (XOR, then count 1-bits). Valid range 0-256; for a good hash it is about 128.
- `--sweep` flips **every** bit in turn (text/hex only) and prints min / max / mean distance. For the same input: min 111, max 149, mean 127.90, close to the ideal 128.
- `--file` works too; the bit is flipped on the fly while streaming, so the file is never fully loaded.
- Out-of-range bits give a clear error (`bit index 136 out of range ...`).

### 3.3 `canonical-json`: deterministic serialization, then hash

```console
$ hashlab canonical-json examples/tx_a.json
# {"to":"Bob","from":"Alice","amount":10}

canonical: {"amount":10,"from":"Alice","to":"Bob"}

bytes: 39

sha256: 92667ec28793c1b4fc03f672093fd1b16f1d46ef0756f181c7e15eec0269ef72

sha256_base64: kmZ+woeTwbT8A/ZyCT/RsW8dRu8HVvGBx+Fe7AJp73I=


$ hashlab canonical-json examples/tx_b.json --no-print
# same object, pretty-printed, different key order

bytes: 39

sha256: 92667ec28793c1b4fc03f672093fd1b16f1d46ef0756f181c7e15eec0269ef72
# identical


$ hashlab canonical-json examples/tx_amount_string.json --no-print
# "amount":"10" (string)

bytes: 41

sha256: 539df383...
# different
```

Reads the file argument, or standard input if omitted (`cat tx.json | hashlab canonical-json`).

**Canonicalization rules (v1)**: a strict subset of RFC 8785 (JCS):

1. Input must be valid UTF-8 (no BOM); the top-level value must be a JSON **object**.
2. Allowed values: object, array, string, integer, `true`, `false`, `null`.
3. **Floats are rejected** (`1.0`, `1e3`): float text formatting differs between languages. Use integers or strings.
4. Integers must lie within +/-(2^53 - 1) so every language represents them exactly.
5. `NaN`, `Infinity`, and **duplicate keys** are rejected.
6. Object keys are sorted by **UTF-16 code units** (as in JCS), at every nesting level. Array order is preserved.
7. **No whitespace** anywhere; separators are `,` and `:`.
8. Strings use minimal escapes: `\"` `\\` `\b` `\f` `\n` `\r` `\t`, and `\u00xx` (lowercase hex) for other control characters. Non-ASCII characters are written literally as UTF-8, not as `\uXXXX`.
9. Unicode is **not** normalized: `"é"` (NFC) and `"é"` (NFD) remain different, on purpose, because silently changing data would be a worse bug.
10. No trailing newline. The hashed bytes are exactly the UTF-8 of the printed canonical text.

### 3.4 `demo`: same-looking input, different bytes

```console
$ hashlab demo
```

Shows pairs that look identical to a human but hash differently:

| # | Case | Bytes differ because |
|---|---|---|
| 1 | trailing newline | extra `0a` (17 vs 18 bytes) |
| 2 | LF vs CRLF | `0a` vs `0d 0a` |
| 3 | Unicode normalization | `é` as `c3 a9` (NFC) vs `65 cc 81` (NFD) |
| 4 | look-alike letters | Latin `a` (`61`) vs Cyrillic `а` (`d0 b0`) |
| 5 | integer vs string | `{"amount":10}` vs `{"amount":"10"}` |
| 6a | key order, naive `json.dumps` | same object, different insertion order, different bytes |
| 6b | key order, canonical | sorted keys + no whitespace: **same** bytes, same hash |

### 3.5 Exit codes

`0` success, `1` input error (message on stderr; nothing on stdout), `2` command-line usage error (from `argparse`).

## 4. Large files: streaming design

`hash_stream()` allocates **one** 1 MiB `bytearray` and repeatedly calls `readinto()` on it, feeding each filled slice to `hashlib.sha256().update()`. Memory use is O(chunk size), independent of file size.

Measured on a 100 MB (104,857,600-byte) random file (peak resident memory of the whole process):

| Process | Peak RSS |
|---|---|
| bare `python -c pass` | ~10 MB |
| **`hashlab file big.bin`** | **~19 MB** |
| naive `sha256(open(f,'rb').read())` | ~115 MB |

So `hashlab` adds under 10 MB over the interpreter, versus about 100 MB for the naive approach.

## 5. Verifying correctness

### 5.1 Against an independent utility

On Linux/macOS/WSL:

```bash
printf 'Alice pays Bob 10' | sha256sum
./scripts/verify_100mb.sh
```

The first command should produce a hash matching `hashlab text`. The verification script creates a 100 MB file, compares its hash with `sha256sum`, and prints peak RSS.

`verify_100mb.sh` needs Linux/macOS/WSL. The peak-RSS line needs GNU `time` (`/usr/bin/time -v`); if missing, it is skipped.

On Windows PowerShell, compare a file using:

```powershell
Get-FileHash .\examples\no_newline.txt -Algorithm SHA256
```

### 5.2 Automated tests

Run from the VS Code integrated terminal with the virtual environment activated:

```powershell
python -m pytest -q
```

44 tests, all passing. They cover:

- known SHA-256 vectors (empty string, `abc`);
- `text`/`hex`/`file` agreement and Base64 output;
- **malformed hex rejected** (odd length, bad characters, spaces, newline, Unicode digits, bare `0x`);
- **trailing newline distinguished** (17 vs 18 bytes, different digests);
- file hashing equal to `hashlib` for chunk sizes 1, 7, 4096, and boundaries; empty file; missing file;
- **100 MB file hashed with peak traced memory < 8 MiB** (and digest verified);
- avalanche: bit-flip correctness (MSB-first), Hamming distance, range errors, streaming flip equals in-memory flip across chunk boundaries, sweep mean near 128;
- canonical JSON: key order, whitespace, nesting, int vs string, no normalization, escapes, and 13 rejection cases (floats, NaN, duplicates, big ints, non-object, BOM, invalid UTF-8, lone surrogate...);
- the `demo` output.

## 6. Project structure

```text
assign01/
├── README.md                  <- this file
├── requirements.txt           <- test dependency (pytest); runtime is stdlib only
├── pyproject.toml              <- package metadata, `hashlab` entry point, pytest config
├── .gitignore
├── src/hashlab/
│   ├── __init__.py
│   ├── __main__.py             <- enables `python -m hashlab`
│   ├── cli.py                  <- argparse commands and output formatting
│   ├── core.py                 <- hex parsing, streaming SHA-256, bit flip, Hamming distance
│   ├── canonical.py            <- canonical JSON rules
│   └── demo.py                 <- look-alike-input demonstration
├── tests/test_hashlab.py
├── scripts/verify_100mb.sh     <- cross-check with sha256sum + memory report
└── examples/                   <- sample JSON / text files used in this README
```

## 7. Why this matters for blockchains

- A hash commits to **bytes**, not to what humans see. Two nodes must therefore agree on one exact byte encoding of every transaction or block before hashing (hence canonical serialization).
- **Avalanche effect:** flipping one input bit changes about half the digest bits, so any tampering with a block is obvious and a hash cannot be "nudged" toward a target.
- **Streaming** matters because chain data and files can be far larger than RAM.

---

**Assignment 1 — Blockchain Engineering**  
IIT Patna | Jul-Dec 2026