import hashlib
import io
import tracemalloc
import unicodedata

import pytest

from hashlab.canonical import canonicalize
from hashlab.cli import main
from hashlab.core import (
    HashlabError,
    flip_bit,
    hamming_distance,
    hash_bytes,
    hash_file,
    hash_stream,
    parse_hex,
    text_to_bytes,
)

EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
ABC_SHA = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def run(capsys, *argv):
    code = main(list(argv))
    cap = capsys.readouterr()
    return code, cap.out, cap.err


# ---- basic modes / known vectors -------------------------------------------
def test_known_vectors():
    assert hash_bytes(b"").hex == EMPTY_SHA
    assert hash_bytes(b"abc").hex == ABC_SHA


def test_text_mode_output(capsys):
    code, out, _ = run(capsys, "text", "abc")
    assert code == 0
    assert "bytes: 3" in out
    assert f"sha256: {ABC_SHA}" in out
    assert "sha256_base64: ungWv48Bz+pBQUDeXa4iI7ADYaOWF3qctBD/YfIAFa0=" in out


def test_hex_matches_text():
    assert hash_bytes(parse_hex("616263")).hex == ABC_SHA
    assert parse_hex("0x616263") == b"abc"
    assert parse_hex("ABcd") == b"\xab\xcd"
    assert parse_hex("") == b""


@pytest.mark.parametrize("bad", ["abc", "zz", "12 34", "0x1", "12\n", "\u0661\u0662", "0xgg"])
def test_malformed_hex_rejected(bad, capsys):
    with pytest.raises(HashlabError):
        parse_hex(bad)
    code, out, err = run(capsys, "hex", bad)
    assert code == 1 and out == "" and "malformed hex" in err


def test_trailing_newline_distinguished(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_bytes(b"Alice pays Bob 10")
    b.write_bytes(b"Alice pays Bob 10\n")
    ra, rb = hash_file(str(a)), hash_file(str(b))
    assert (ra.length, rb.length) == (17, 18)
    assert ra.digest != rb.digest


def test_escapes_flag_adds_newline():
    assert text_to_bytes(r"x\n", escapes=True) == b"x\n"
    assert text_to_bytes(r"x\n") == b"x\\n"


def test_normalization_option():
    nfd = unicodedata.normalize("NFD", "caf\u00e9")
    assert text_to_bytes(nfd) != text_to_bytes("caf\u00e9")
    assert text_to_bytes(nfd, normalize="NFC") == text_to_bytes("caf\u00e9")


# ---- files / streaming -------------------------------------------------------
def test_file_matches_hashlib_for_odd_chunk_sizes(tmp_path):
    data = bytes(range(256)) * 1000 + b"tail"
    p = tmp_path / "f.bin"
    p.write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()
    for chunk in (1, 7, 4096, len(data), len(data) + 1):
        res = hash_file(str(p), chunk_size=chunk)
        assert res.hex == expected and res.length == len(data)


def test_empty_file(tmp_path):
    p = tmp_path / "e"
    p.write_bytes(b"")
    assert hash_file(str(p)).hex == EMPTY_SHA


def test_missing_file(capsys):
    code, _, err = run(capsys, "file", "/no/such/file")
    assert code == 1 and "cannot read" in err


def test_100mb_file_streams_with_constant_memory(tmp_path):
    p = tmp_path / "big.bin"
    block = hashlib.sha256(b"seed").digest() * (1024 * 32)  # 1 MiB
    ref = hashlib.sha256()
    with open(p, "wb") as fh:
        for _ in range(100):
            fh.write(block)
            ref.update(block)
    del block
    tracemalloc.start()
    res = hash_file(str(p))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert res.length == 100 * 1024 * 1024
    assert res.hex == ref.hexdigest()
    assert peak < 8 * 1024 * 1024, f"peak {peak} bytes: file was not streamed"


# ---- avalanche -------------------------------------------------------------
def test_flip_bit_msb_first():
    assert flip_bit(b"\x00", 0) == b"\x80"
    assert flip_bit(b"\x00", 7) == b"\x01"
    assert flip_bit(b"\x00\x00", 8) == b"\x00\x80"
    with pytest.raises(HashlabError):
        flip_bit(b"\x00", 8)
    with pytest.raises(HashlabError):
        flip_bit(b"\x00", -1)


def test_hamming_distance():
    assert hamming_distance(b"\x00", b"\xff") == 8
    assert hamming_distance(b"\x0f\x00", b"\x00\x01") == 5
    assert hamming_distance(b"abc", b"abc") == 0


def test_avalanche_cli_range_and_correctness(capsys):
    code, out, _ = run(capsys, "avalanche", "--text", "Alice pays Bob 10", "--bit", "7")
    assert code == 0
    changed = int(out.split("changed_bits_in_digest:")[1].split()[0])
    assert 0 <= changed <= 256
    expected = hamming_distance(
        hashlib.sha256(b"Alice pays Bob 10").digest(),
        hashlib.sha256(flip_bit(b"Alice pays Bob 10", 7)).digest(),
    )
    assert changed == expected


def test_avalanche_file_matches_in_memory(tmp_path, capsys):
    data = b"x" * 5000 + b"Alice pays Bob 10"
    p = tmp_path / "f"
    p.write_bytes(data)
    bit = 8 * 4999 + 3  # crosses chunk boundaries with a tiny chunk size
    flipped = hash_file(str(p), chunk_size=64, flip=bit)
    assert flipped.hex == hashlib.sha256(flip_bit(data, bit)).hexdigest()
    code, out, _ = run(capsys, "avalanche", "--file", str(p), "--bit", str(bit))
    assert code == 0 and "changed_bits_in_digest" in out


def test_avalanche_bad_bit(capsys):
    code, _, err = run(capsys, "avalanche", "--text", "a", "--bit", "8")
    assert code == 1 and "out of range" in err
    code, _, err = run(capsys, "avalanche", "--text", "a")
    assert code == 1 and "--bit is required" in err


def test_avalanche_sweep_mean_near_128(capsys):
    code, out, _ = run(capsys, "avalanche", "--text", "Alice pays Bob 10", "--sweep")
    assert code == 0
    mean = float(out.split("changed_bits_mean:")[1].split()[0])
    assert 118 < mean < 138


# ---- canonical JSON -----------------------------------------------------------
def test_key_order_and_whitespace_irrelevant():
    a = canonicalize(b'{"to":"Bob","from":"Alice","amount":10}')
    b = canonicalize(b'{\n "amount": 10,\n "from": "Alice",\n "to": "Bob"\n}\n')
    assert a == b == b'{"amount":10,"from":"Alice","to":"Bob"}'


def test_nested_sorted_and_arrays_keep_order():
    out = canonicalize(b'{"b":[3,1,2],"a":{"z":null,"y":true,"x":false}}')
    assert out == b'{"a":{"x":false,"y":true,"z":null},"b":[3,1,2]}'


def test_integer_vs_string_differ():
    assert canonicalize(b'{"amount":10}') != canonicalize(b'{"amount":"10"}')


def test_unicode_not_normalized_and_literal_utf8():
    nfc = canonicalize('{"k":"caf\u00e9"}'.encode())
    nfd = canonicalize(('{"k":"%s"}' % unicodedata.normalize("NFD", "caf\u00e9")).encode())
    assert nfc != nfd
    assert "caf\u00e9".encode() in nfc
    assert canonicalize(b'{"k":"\\u00e9"}') == '{"k":"\u00e9"}'.encode()


def test_string_escapes():
    assert canonicalize(b'{"k":"a\\n\\"\\\\\\u0001"}') == b'{"k":"a\\n\\"\\\\\\u0001"}'


@pytest.mark.parametrize("raw", [
    b'{"a":1.0}', b'{"a":1e3}', b'{"a":NaN}', b'{"a":Infinity}',
    b'{"a":9007199254740993}', b'{"a":1,"a":2}', b'[1,2]', b'"str"', b'{', b'',
    b'\xef\xbb\xbf{"a":1}', b'\xff\xfe', b'{"a":"\\ud800"}',
])
def test_canonical_rejections(raw):
    with pytest.raises(HashlabError):
        canonicalize(raw)


def test_canonical_cli(tmp_path, capsys):
    p = tmp_path / "t.json"
    p.write_text('{"to":"Bob","from":"Alice","amount":10}\n')
    code, out, _ = run(capsys, "canonical-json", str(p))
    expected = hashlib.sha256(b'{"amount":10,"from":"Alice","to":"Bob"}').hexdigest()
    assert code == 0 and f"sha256: {expected}" in out and "bytes: 39" in out


def test_canonical_cli_stdin(monkeypatch, capsys):
    class FakeStdin:
        buffer = io.BytesIO(b'{"b":1,"a":2}')

    monkeypatch.setattr("sys.stdin", FakeStdin)
    code, out, _ = run(capsys, "canonical-json")
    assert code == 0 and 'canonical: {"a":2,"b":1}' in out


# ---- demo ----------------------------------------------------------------------
def test_demo_runs_and_shows_differences(capsys):
    code, out, _ = run(capsys, "demo")
    assert code == 0
    assert out.count("identical bytes: NO") == 6
    assert out.count("identical bytes: yes") == 1
