# Assignment 1 – Bytes, Hashes, and Reproducible Data

### Project: HashLab

**Student:** Manshi Prajapati  
**Roll Number:** 2302CS08  
**Course:** Blockchain Engineering  
**Instructor:** Dr. Mayank Agarwal  
**Department:** Computer Science and Engineering, IIT Patna  
**Academic Session:** July–December 2026

**Demo Video:** [Watch Assignment 1 Demonstration](<[ASSIGNMENT_01_VIDEO_LINK](https://youtu.be/40wSlgal36w)>)

---

## 1. Overview

`hashlab` is a Python command-line tool that generates SHA-256 diagnostics for text, hexadecimal byte strings, files, and canonical JSON.

The project focuses on understanding how cryptographic hashing works and why exact byte representation is important in blockchain systems.

SHA-256 is not implemented from scratch. Instead, the project uses Python's standard-library `hashlib` module.

The main emphasis is on:

- Correct handling of bytes and text.
- SHA-256 hash generation.
- Hexadecimal and Base64 digest representation.
- Avalanche effect demonstration.
- Deterministic JSON serialization.
- Streaming large files efficiently.
- Reproducible hashing across different inputs and environments.

## 2. Technologies and Requirements

| Technology | Purpose |
|---|---|
| Python 3.11+ | Core implementation |
| `hashlib` | SHA-256 hashing |
| `base64` | Base64 digest representation |
| `json` | JSON parsing and serialization |
| `pytest` | Automated testing |
| Visual Studio Code | Development environment |
| PowerShell | Windows command-line execution |

**Dependencies:** No third-party runtime dependencies are required. `pytest` is needed only for running the test suite.

## 3. Development Environment and Setup

The project was developed and tested using:

- Visual Studio Code (VS Code).
- Python 3.11 or newer.
- Windows PowerShell (VS Code integrated terminal).
- Python virtual environment (`.venv`).
- pytest for automated testing.

### 3.1 Windows Setup (VS Code + PowerShell)

**Step 1: Open the project**

1. Open Visual Studio Code.
2. Select **File → Open Folder**.
3. Open the `assign01` folder.
4. Open the integrated terminal using **Terminal → New Terminal**.

**Step 2: Create a virtual environment**

```powershell
python -m venv .venv
```

**Step 3: Activate the virtual environment**

```powershell
.venv\Scripts\Activate.ps1
```

After successful activation, `(.venv)` should appear at the beginning of the terminal prompt.

If PowerShell blocks script execution, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

**Step 4: Select the Python interpreter in VS Code**

1. Press `Ctrl + Shift + P`.
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

**Step 6: Verify the installation**

```powershell
python -m hashlab --help
```

You can now execute the project commands:

```powershell
python -m hashlab text "Alice pays Bob 10"
python -m hashlab hex 0xdeadbeef
python -m hashlab file examples/no_newline.txt
python -m hashlab demo
```

All examples below use the installed `hashlab` command. Running `python -m hashlab` is equivalent.

**Step 7: Run automated tests**

```powershell
python -m pytest -v
```

The test suite contains **44 tests, all passing**.

### 3.2 Linux / macOS Setup (Alternative)

From inside the assignment folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### 3.3 Running Without Installing

The project can also be executed directly from the source directory.

**Windows PowerShell:**

```powershell
$env:PYTHONPATH="src"
python -m hashlab text "hello"
```

**Linux / macOS:**

```bash
PYTHONPATH=src python3 -m hashlab text "hello"
```

## 4. Command-Line Usage

The project provides the following main commands:

| Command | Description |
|---|---|
| `hashlab text` | Hashes text after UTF-8 encoding |
| `hashlab hex` | Hashes hexadecimal byte input |
| `hashlab file` | Hashes file contents using streaming |
| `hashlab avalanche` | Demonstrates the avalanche effect |
| `hashlab canonical-json` | Canonicalizes JSON and calculates its hash |
| `hashlab demo` | Demonstrates how visually similar inputs can produce different hashes |

### 4.1 Text, Hexadecimal, and File Hashing

The `text`, `hex`, and `file` commands calculate SHA-256 and display:

- Input byte length.
- SHA-256 digest in hexadecimal.
- SHA-256 digest in Base64.

**A. Hashing text**

```powershell
hashlab text "Alice pays Bob 10"
```

Example output:

```text
bytes: 17

sha256: 69ad18dfd1ac4b3d711b02ee62caa00a82f0f67cc11ebacdd0c0ede0d8b6eaed

sha256_base64: aa0Y39GsSz1xGwLuYsqgCoLw9nzBHrrN0MDt4Ni26u0=
```

**B. Hashing hexadecimal input**

```powershell
hashlab hex 0xdeadbeef
```

Example output:

```text
bytes: 4

sha256: 5f78c33274e43fa9de5659265c1d917e25c03722dcb0b8d27db8d5feaa813953

sha256_base64: X3jDMnTkP6neVlkmXB2RfiXANyLcsLjSfbjV/qqBOVM=
```

**C. Hashing a file**

```powershell
hashlab file examples/no_newline.txt
```

Example output:

```text
bytes: 17

sha256: 69ad18dfd1ac4b3d711b02ee62caa00a82f0f67cc11ebacdd0c0ede0d8b6eaed
```

For a file containing a trailing newline:

```powershell
hashlab file examples/with_newline.txt
```

Example output:

```text
bytes: 18

sha256: a559dd30f6cd021ebe7f50aa899b92a360968ff9195877190f1954140d4e1b39
```

**Important observation:** `"Alice pays Bob 10"` contains 17 bytes. Adding a trailing newline increases the size to 18 bytes and changes the SHA-256 digest.

This demonstrates that hashing operates on exact bytes, not on how text appears visually.

### Command Options

| Command | Functionality |
|---|---|
| `hashlab text VALUE` | Converts text to UTF-8 before hashing. |
| `--normalize {NFC,NFD,NFKC,NFKD}` | Applies Unicode normalization before hashing. Default: none. |
| `--escapes` | Interprets escape sequences such as `\n`, `\r`, `\t`, and `\\`. |
| `hashlab hex VALUE` | Accepts strict hexadecimal input with an optional `0x` prefix. |
| `hashlab file PATH` | Streams and hashes a file. |
| `--chunk-size BYTES` | Changes the file-reading chunk size. |
| `-` | Reads file input from standard input. |

Hexadecimal input must contain an even number of valid hexadecimal digits. Spaces and invalid characters are rejected.

**Examples of invalid hexadecimal input:**

```text
hashlab hex abc
```

Output:

```text
error: malformed hex: odd number of digits (3); each byte needs exactly two hex digits
```

```text
hashlab hex 0xZZ
```

Output:

```text
error: malformed hex: invalid character 'Z'
```

### 4.2 Avalanche Effect

The avalanche effect is an important property of cryptographic hash functions.

It means that changing even one bit in the input should change approximately half of the bits in the resulting hash.

Run:

```powershell
hashlab avalanche --text "Alice pays Bob 10" --bit 7
```

Example output:

```text
input_bytes: 17

bit_flipped: 7 (byte 0, mask 0x01)

original_sha256: 69ad18df...

flipped_sha256: effa3a72...

changed_bits_in_digest: 119

changed_fraction: 0.465 (ideal avalanche is about 0.5)
```

**Implementation details:**

- Exactly one input source is required: `--text`, `--hex`, or `--file`.
- Bit numbering starts at 0.
- Bit 0 represents the most significant bit of byte 0.
- Bit 7 represents the least significant bit of byte 0.
- Bit 8 represents the most significant bit of byte 1.
- `changed_bits_in_digest` measures the Hamming distance between the original and modified 256-bit digests.
- The expected Hamming distance for a good hash function is approximately 128 bits.

To flip every input bit and calculate the minimum, maximum, and average digest distance:

```powershell
hashlab avalanche --text "Alice pays Bob 10" --sweep
```

For the same input, the recorded results were:

| Metric | Result |
|---|---:|
| Minimum changed bits | 111 |
| Maximum changed bits | 149 |
| Mean changed bits | 127.90 |
| Ideal mean | 128 |

The file-based mode also supports streaming bit flips without loading the entire file into memory.

### 4.3 Canonical JSON

Canonical JSON ensures that logically identical JSON objects produce exactly the same serialized bytes and therefore the same SHA-256 hash.

This is important in blockchain systems because different nodes must generate identical transaction bytes before hashing or signing.

Run:

```powershell
hashlab canonical-json examples/tx_a.json
```

Example output:

```text
# {"to":"Bob","from":"Alice","amount":10}

canonical: {"amount":10,"from":"Alice","to":"Bob"}

bytes: 39

sha256: 92667ec28793c1b4fc03f672093fd1b16f1d46ef0756f181c7e15eec0269ef72

sha256_base64: kmZ+woeTwbT8A/ZyCT/RsW8dRu8HVvGBx+Fe7AJp73I=
```

Now run the command on the same object with a different key order and formatting:

```powershell
hashlab canonical-json examples/tx_b.json --no-print
```

The resulting canonical byte length and SHA-256 hash remain identical.

However, changing the amount from an integer to a string produces a different result:

```powershell
hashlab canonical-json examples/tx_amount_string.json --no-print
```

For example:

- `"amount": 10` is an integer.
- `"amount": "10"` is a string.

These represent different JSON values and therefore produce different canonical bytes and hashes.

#### Canonicalization Rules (Version 1)

The implementation follows a strict subset of RFC 8785 (JSON Canonicalization Scheme).

1. Input must be valid UTF-8 without a BOM.
2. The top-level JSON value must be an object.
3. Supported values are objects, arrays, strings, integers, booleans, and null.
4. Floating-point numbers are rejected.
5. Integers must be within the range \(\pm(2^{53}-1)\).
6. `NaN`, `Infinity`, and duplicate object keys are rejected.
7. Object keys are sorted by UTF-16 code units at every nesting level.
8. Array order is preserved.
9. Whitespace is removed from the canonical representation.
10. Strings use minimal escaping for quotes, backslashes, and control characters.
11. Unicode characters are not normalized automatically.
12. The canonical output does not contain a trailing newline.

The exact UTF-8 bytes of the canonical JSON string are used for hashing.

### 4.4 Demonstration Mode

Run:

```powershell
hashlab demo
```

This command demonstrates cases where visually similar inputs produce different byte sequences and SHA-256 hashes.

| Case | Demonstration | Reason |
|---|---|---|
| 1 | Trailing newline | Adds an extra `0a` byte |
| 2 | LF vs CRLF | Different line-ending bytes |
| 3 | Unicode normalization | NFC and NFD representations differ |
| 4 | Look-alike letters | Latin and Cyrillic characters have different encodings |
| 5 | Integer vs string | Different JSON data types |
| 6a | Different JSON key order | Naive serialization can produce different bytes |
| 6b | Canonical JSON | Sorted keys and removed whitespace produce identical bytes |

This demonstration highlights why deterministic serialization is necessary for blockchain transactions.

### 4.5 Exit Codes

| Exit Code | Meaning |
|---:|---|
| `0` | Successful operation |
| `1` | Input error; error message is written to stderr |
| `2` | Command-line usage error from argparse |

## 5. Large File Hashing: Streaming Design

The project implements efficient file hashing using a streaming approach.

The `hash_stream()` function:

1. Allocates a single 1 MiB `bytearray`.
2. Reads file contents using `readinto()`.
3. Passes each filled buffer slice to `hashlib.sha256().update()`.
4. Continues until the entire file has been processed.

Instead of loading the complete file into memory, the implementation processes it in chunks.

This keeps memory usage proportional to the chunk size rather than the total file size.

### Memory Benchmark

The following measurements were recorded for a 100 MB (104,857,600-byte) random file.

| Process | Peak Resident Memory |
|---|---:|
| Bare `python -c pass` | ~10 MB |
| `hashlab file big.bin` | ~19 MB |
| Naive `sha256(open(f,'rb').read())` | ~115 MB |

The streaming implementation adds less than 10 MB over the Python interpreter, compared with approximately 100 MB of additional memory for the naive approach.

## 6. Verifying Correctness

The implementation is validated using independent SHA-256 utilities and automated tests.

### 6.1 Verification Using an Independent Utility

On Linux, macOS, or WSL:

```bash
printf 'Alice pays Bob 10' | sha256sum
```

The generated hash should match the result from:

```powershell
hashlab text "Alice pays Bob 10"
```

To verify large-file hashing:

```bash
./scripts/verify_100mb.sh
```

This script:

- Creates a 100 MB test file.
- Calculates its SHA-256 hash.
- Compares the result against `sha256sum`.
- Reports peak resident memory usage.

The script requires Linux, macOS, or WSL. Peak memory reporting requires GNU `time` (`/usr/bin/time -v`); if unavailable, that measurement is skipped.

On Windows PowerShell, compare a file using:

```powershell
Get-FileHash .\examples\no_newline.txt -Algorithm SHA256
```

### 6.2 Automated Testing

Run the complete test suite from the VS Code integrated terminal with the virtual environment activated:

```powershell
python -m pytest -q
```

<badge color="success">44 tests passed</badge>

The tests cover:

- Known SHA-256 test vectors, including the empty string and `abc`.
- Agreement between text, hexadecimal, and file hashing.
- Base64 digest generation.
- Rejection of malformed hexadecimal input.
- Difference between files with and without trailing newlines.
- File hashing across multiple chunk sizes.
- Empty files and missing-file handling.
- Large-file hashing with bounded memory usage.
- Avalanche effect and Hamming distance calculations.
- Bit-flipping correctness across chunk boundaries.
- Canonical JSON key ordering and whitespace handling.
- Integer versus string representation.
- Unicode normalization behavior.
- Invalid JSON rejection, including floats, NaN, duplicate keys, oversized integers, BOM, and invalid UTF-8.
- Demonstration command output.

## 7. Project Structure

```text
assign01/
│
├── README.md
├── requirements.txt
├── pyproject.toml
├── .gitignore
│
├── src/
│   └── hashlab/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── core.py
│       ├── canonical.py
│       └── demo.py
│
├── tests/
│   └── test_hashlab.py
│
├── scripts/
│   └── verify_100mb.sh
│
└── examples/
    ├── no_newline.txt
    ├── with_newline.txt
    ├── tx_a.json
    ├── tx_b.json
    └── tx_amount_string.json
```

### Main Source Files

| File | Responsibility |
|---|---|
| `core.py` | Hex parsing, SHA-256 hashing, streaming, bit flipping, and Hamming distance |
| `canonical.py` | Canonical JSON serialization |
| `cli.py` | Command-line argument parsing and output formatting |
| `demo.py` | Demonstrations of visually similar but byte-different inputs |
| `__main__.py` | Enables execution through `python -m hashlab` |
| `test_hashlab.py` | Automated test suite |

## 8. Relevance to Blockchain Technology

The concepts implemented in this assignment are fundamental to blockchain systems.

### 8.1 Hashing and Data Integrity

A cryptographic hash produces a fixed-length digest from input data. Even a small change in the input results in a significantly different digest.

This helps detect unauthorized changes to transactions and blocks.

### 8.2 Canonical Serialization

Blockchain nodes must agree on the exact byte representation of transactions and blocks before hashing or signing them.

Canonical serialization ensures that equivalent JSON objects produce identical bytes, regardless of key order or formatting.

### 8.3 Avalanche Effect

The avalanche effect ensures that changing even one input bit significantly changes the resulting hash.

This makes tampering detectable and is an important property of cryptographic hash functions.

### 8.4 Streaming

Blockchain data and transaction files can become very large.

Streaming allows data to be processed in chunks without loading the entire file into memory, making the implementation more memory-efficient.

## 9. Submission Checklist

- [ ] Assignment folder is named `assign01/` and placed at the root of the private roll-number repository.
- [ ] Source code and all required project files are included.
- [ ] `README.md` contains the final project documentation.
- [ ] All 44 automated tests pass.
- [ ] Example files and verification script are included.
- [ ] Collaborator `blockchain.iitp.20261@atomicmail.io` has been added.
- [ ] Demonstration video has been uploaded to YouTube as **Unlisted**.
- [ ] YouTube link has been added to this README.
- [ ] Video link has been submitted through the official MS Form: https://forms.cloud.microsoft/r/huBck9hkD7

---

**Assignment 1 – Blockchain Engineering**  
**Indian Institute of Technology Patna**  
**July–December 2026**  
**Roll Number:** 2302CS08
