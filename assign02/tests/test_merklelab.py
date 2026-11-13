import copy
import hashlib
import json
import pathlib

import pytest

from merklelab import (EMPTY_ROOT, MerkleError, MerkleTree, Proof, ProofError, ProofFormatError,
                       Sibling, expected_sides, hash_leaf, hash_node, merkle_root, verify)
from merklelab.bench import bench_size
from merklelab.cli import main
from merklelab.leafio import parse_leaves
from reference_rfc6962 import MTH, PATH

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
VECTORS = json.loads((ROOT_DIR / "vectors" / "test_vectors.json").read_text())


def sha(b):
    return hashlib.sha256(b).digest()


def leaves_n(n):
    return [f"tx-{i}".encode() for i in range(n)]


def run(capsys, *argv):
    code = main(list(argv))
    cap = capsys.readouterr()
    return code, cap.out, cap.err


# ---- Task 1: domain-separated hashes ----------------------------------------
def test_hash_definitions():
    assert hash_leaf(b"abc") == sha(b"\x00abc")
    a, b = sha(b"a"), sha(b"b")
    assert hash_node(a, b) == sha(b"\x01" + a + b)
    assert hash_leaf(b"") == sha(b"\x00")
    assert EMPTY_ROOT == sha(b"")


def test_hash_node_requires_32_byte_children():
    with pytest.raises(MerkleError):
        hash_node(b"\x00" * 31, b"\x00" * 33)  # same total length, different split
    with pytest.raises(TypeError):
        hash_leaf("text")


def test_domain_separation_blocks_node_as_leaf():
    """Classic second-preimage attack: present (left||right) as a single leaf."""
    a, b = b"a", b"b"
    root = merkle_root([a, b])
    fake_leaf = hash_leaf(a) + hash_leaf(b)  # 64 bytes = the preimage body of the root node
    assert merkle_root([fake_leaf]) != root
    proof = Proof(0, 1, ())
    assert verify(fake_leaf, proof, root) is False


# ---- Task 2: roots for zero / one / odd / even -----------------------------------
def test_zero_one_two_three_five_by_hand():
    l = [hash_leaf(x) for x in leaves_n(5)]
    n01, n23 = sha(b"\x01" + l[0] + l[1]), sha(b"\x01" + l[2] + l[3])
    assert merkle_root([]) == EMPTY_ROOT == MerkleTree([]).root
    assert merkle_root(leaves_n(1)) == l[0]
    assert merkle_root(leaves_n(2)) == n01
    assert merkle_root(leaves_n(3)) == sha(b"\x01" + n01 + l[2])          # l2 promoted, not duplicated
    assert merkle_root(leaves_n(4)) == sha(b"\x01" + n01 + n23)
    assert merkle_root(leaves_n(5)) == sha(b"\x01" + sha(b"\x01" + n01 + n23) + l[4])


def test_no_duplicate_leaf_ambiguity():
    """Bitcoin-style duplication would make these equal (CVE-2012-2459)."""
    a, b, c = b"a", b"b", b"c"
    assert merkle_root([a, b, c]) != merkle_root([a, b, c, c])
    assert merkle_root([a]) != merkle_root([a, a])


def test_order_and_content_matter():
    assert merkle_root([b"a", b"b"]) != merkle_root([b"b", b"a"])
    assert merkle_root(leaves_n(7)) != merkle_root(leaves_n(7)[:-1])


def test_tree_object_matches_function():
    for n in range(0, 40):
        t = MerkleTree(leaves_n(n))
        assert t.root == merkle_root(leaves_n(n)) and t.size == n


def test_rfc6962_ct_published_roots():
    """Roots published for the Certificate Transparency reference implementation."""
    known = {
        0: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        1: "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d",
        2: "fac54203e7cc696cf0dfcb42c92a1d9dbaf70ad9e621f4bd8d98662f00e3c125",
        3: "aeb6bcfe274b70a14fb067a5e5578264db0fa9b51af5e0ba159158f329e06e77",
        4: "d37ee418976dd95753c1c73862b9398fa2a2cf9b4ff0fdfe8b30cd95209614b7",
        5: "4e3bbb1f7b478dcfe71fb631631519a3bca12c9aefca1612bfce4c13a86264d4",
        6: "76e67dadbcdf1e10e1b74ddc608abd2f98dfb16fbce75277b5232a127f2087ef",
        7: "ddb89be403809e325750d3d263cd78929c2942b7942a34b77e122c9594a74c8c",
        8: "5dc9da79a70659a9ad559cb701ded9a2ab9d823aad2f4960cfe370eff4604328",
    }
    ct = ["", "00", "10", "2021", "3031", "40414243", "5051525354555657",
          "606162636465666768696a6b6c6d6e6f"]
    leaves = [bytes.fromhex(x) for x in ct]
    for n, root in known.items():
        assert merkle_root(leaves[:n]).hex() == root


# ---- cross-check against the independent recursive reference ---------------------------
@pytest.mark.parametrize("n", list(range(0, 66)) + [100, 127, 128, 129, 255, 1000])
def test_matches_independent_reference(n):
    leaves = leaves_n(n)
    tree = MerkleTree(leaves)
    assert tree.root == MTH(leaves)
    for i in range(n if n <= 66 else 40):
        i = i if n <= 66 else (i * 25) % n
        proof = tree.prove(i)
        assert [s.hash for s in proof.siblings] == PATH(i, leaves)
        assert verify(leaves[i], proof, tree.root) is True


# ---- Task 3/4: proofs --------------------------------------------------------------
def test_five_leaf_proof_for_index_2():
    leaves = leaves_n(5)
    t = MerkleTree(leaves)
    p = t.prove(2)
    assert [s.side for s in p.siblings] == ["right", "left", "right"]
    l = [hash_leaf(x) for x in leaves]
    assert p.siblings[0].hash == l[3]
    assert p.siblings[1].hash == sha(b"\x01" + l[0] + l[1])
    assert p.siblings[2].hash == l[4]


def test_unpaired_last_leaf_has_short_proof():
    t = MerkleTree(leaves_n(5))
    assert [s.side for s in t.prove(4).siblings] == ["left"]
    assert t.prove(4).siblings[0].hash == MTH(leaves_n(5)[:4])


def test_single_leaf_proof_is_empty():
    t = MerkleTree(leaves_n(1))
    p = t.prove(0)
    assert p.siblings == () and verify(b"tx-0", p, t.root)


def test_every_leaf_every_size_verifies_and_wrong_leaf_fails():
    for n in range(1, 34):
        t = MerkleTree(leaves_n(n))
        for i in range(n):
            p = t.prove(i)
            assert verify(leaves_n(n)[i], p, t.root) is True
            assert verify(b"not a leaf", p, t.root) is False


def test_proof_length_is_log():
    t = MerkleTree(leaves_n(1000))
    assert max(len(t.prove(i).siblings) for i in range(1000)) == 10


def test_verify_uses_only_leaf_proof_root():
    t = MerkleTree(leaves_n(9))
    p = Proof.from_json(t.prove(6).to_json())  # round-tripped, no access to the tree
    assert verify(b"tx-6", p, bytes.fromhex(t.root.hex())) is True


def test_wrong_root_fails():
    t = MerkleTree(leaves_n(6))
    assert verify(b"tx-3", t.prove(3), sha(b"other")) is False


def test_prove_errors():
    t = MerkleTree(leaves_n(3))
    for bad in (-1, 3, 99):
        with pytest.raises(MerkleError):
            t.prove(bad)
    with pytest.raises(MerkleError):
        MerkleTree([]).prove(0)
    with pytest.raises(MerkleError):
        t.prove(True)


# ---- tampering ---------------------------------------------------------------------
def test_tampered_sibling_hash_fails():
    t = MerkleTree(leaves_n(13))
    p = t.prove(5)
    for k in range(len(p.siblings)):
        sibs = list(p.siblings)
        sibs[k] = Sibling(sibs[k].side, bytes([sibs[k].hash[0] ^ 1]) + sibs[k].hash[1:])
        assert verify(b"tx-5", Proof(5, 13, tuple(sibs)), t.root) is False


def test_wrong_direction_rejected():
    t = MerkleTree(leaves_n(5))
    p = t.prove(2)
    flipped = [Sibling("left" if s.side == "right" else "right", s.hash) for s in p.siblings]
    with pytest.raises(ProofError, match="direction"):
        verify(b"tx-2", Proof(2, 5, tuple(flipped)), t.root)


def test_wrong_index_rejected_or_fails():
    t = MerkleTree(leaves_n(8))
    p = t.prove(3)
    for wrong in (0, 1, 2, 4, 5, 6, 7):
        forged = Proof(wrong, 8, p.siblings)
        try:
            assert verify(b"tx-3", forged, t.root) is False
        except ProofError:
            pass


def test_unnecessarily_long_and_short_rejected():
    t = MerkleTree(leaves_n(5))
    p = t.prove(2)
    with pytest.raises(ProofError, match="unnecessarily long"):
        verify(b"tx-2", Proof(2, 5, p.siblings + (p.siblings[0],)), t.root)
    with pytest.raises(ProofError, match="too short"):
        verify(b"tx-2", Proof(2, 5, p.siblings[:-1]), t.root)
    # a single leaf needs zero siblings; extra siblings must not be tolerated
    with pytest.raises(ProofError, match="unnecessarily long"):
        verify(b"tx-0", Proof(0, 1, (p.siblings[0],)), merkle_root([b"tx-0"]))
    # an unpaired last leaf has a SHORTER proof than its neighbours; padding must be rejected
    t5 = MerkleTree(leaves_n(5)).prove(4)
    with pytest.raises(ProofError):
        verify(b"tx-4", Proof(4, 5, t5.siblings + t5.siblings), t.root)


def test_tree_size_pinning():
    t = MerkleTree(leaves_n(5))
    p = t.prove(2)
    assert verify(b"tx-2", p, t.root, tree_size=5) is True
    with pytest.raises(ProofError, match="tree_size"):
        verify(b"tx-2", p, t.root, tree_size=6)
    # The root alone does NOT commit to the size: the same siblings also fold to the size-5 root
    # when the claim is "size 6, index 2" (same path shape). Pinning tree_size is what catches it.
    forged = Proof(2, 6, p.siblings)
    assert verify(b"tx-2", forged, t.root) is True
    with pytest.raises(ProofError):
        verify(b"tx-2", forged, t.root, tree_size=5)


def test_bad_expected_root_length():
    with pytest.raises(ProofFormatError):
        verify(b"x", Proof(0, 1, ()), b"\x00" * 31)


# ---- Task 5: JSON ----------------------------------------------------------------
def good_obj():
    return MerkleTree(leaves_n(5)).prove(2).to_obj()


def test_json_roundtrip_and_shape():
    p = MerkleTree(leaves_n(5)).prove(2)
    obj = json.loads(p.to_json())
    assert list(obj) == ["leaf_index", "tree_size", "siblings"]
    assert list(obj["siblings"][0]) == ["side", "hash"]
    assert Proof.from_json(p.to_json()) == p
    assert Proof.from_json(p.to_json(compact=True)) == p
    assert Proof.from_json(p.to_json().encode()) == p


def test_uppercase_hex_accepted_but_output_lowercase():
    obj = good_obj()
    obj["siblings"][0]["hash"] = obj["siblings"][0]["hash"].upper()
    p = Proof.from_obj(obj)
    assert p.siblings[0].hash.hex() == obj["siblings"][0]["hash"].lower()
    assert p.to_obj()["siblings"][0]["hash"].islower()


def mutate(fn):
    obj = copy.deepcopy(good_obj())
    fn(obj)
    return obj


MALFORMED = {
    "hash too short": lambda o: o["siblings"][0].__setitem__("hash", "ab" * 31),
    "hash too long": lambda o: o["siblings"][0].__setitem__("hash", "ab" * 33),
    "hash non-hex": lambda o: o["siblings"][0].__setitem__("hash", "g" * 64),
    "hash with 0x": lambda o: o["siblings"][0].__setitem__("hash", "0x" + "ab" * 31),
    "hash with space": lambda o: o["siblings"][0].__setitem__("hash", " " + "ab" * 31 + " "[:0]),
    "hash is int": lambda o: o["siblings"][0].__setitem__("hash", 12345),
    "hash is null": lambda o: o["siblings"][0].__setitem__("hash", None),
    "hash trailing newline": lambda o: o["siblings"][0].__setitem__("hash", "ab" * 32 + "\n"),
    "side Left": lambda o: o["siblings"][0].__setitem__("side", "Left"),
    "side up": lambda o: o["siblings"][0].__setitem__("side", "up"),
    "side empty": lambda o: o["siblings"][0].__setitem__("side", ""),
    "side null": lambda o: o["siblings"][0].__setitem__("side", None),
    "side number": lambda o: o["siblings"][0].__setitem__("side", 0),
    "negative index": lambda o: o.__setitem__("leaf_index", -1),
    "index == size": lambda o: o.__setitem__("leaf_index", 5),
    "index float": lambda o: o.__setitem__("leaf_index", 2.0),
    "index string": lambda o: o.__setitem__("leaf_index", "2"),
    "index bool": lambda o: o.__setitem__("leaf_index", True),
    "size zero": lambda o: o.__setitem__("tree_size", 0),
    "size negative": lambda o: o.__setitem__("tree_size", -5),
    "size string": lambda o: o.__setitem__("tree_size", "5"),
    "size too big": lambda o: o.__setitem__("tree_size", 2**64),
    "missing leaf_index": lambda o: o.pop("leaf_index"),
    "missing siblings": lambda o: o.pop("siblings"),
    "extra top key": lambda o: o.__setitem__("note", "hi"),
    "siblings not list": lambda o: o.__setitem__("siblings", "abc"),
    "sibling not object": lambda o: o["siblings"].__setitem__(0, "abc"),
    "sibling extra key": lambda o: o["siblings"][0].__setitem__("x", 1),
    "sibling missing hash": lambda o: o["siblings"][0].pop("hash"),
}


@pytest.mark.parametrize("name", list(MALFORMED))
def test_malformed_proofs_rejected(name):
    with pytest.raises(ProofFormatError):
        Proof.from_obj(mutate(MALFORMED[name]))


@pytest.mark.parametrize("text", ["", "not json", "[]", "null", "42", '"str"', "{", '{"leaf_index":1,}',
                                  '{"leaf_index":2,"leaf_index":2,"tree_size":5,"siblings":[]}',
                                  '{"leaf_index":NaN,"tree_size":5,"siblings":[]}'])
def test_malformed_json_text_rejected(text):
    with pytest.raises(ProofFormatError):
        Proof.from_json(text)


def test_bad_utf8_rejected():
    with pytest.raises(ProofFormatError):
        Proof.from_json(b"\xff\xfe{}")


# ---- test vectors ----------------------------------------------------------------
@pytest.mark.parametrize("vs", VECTORS["sets"], ids=lambda s: s["name"])
def test_published_vectors(vs):
    leaves = [bytes.fromhex(x) for x in vs["leaves_hex"]]
    tree = MerkleTree(leaves)
    assert tree.size == vs["size"] and tree.root.hex() == vs["root"]
    for pv in vs["proofs"]:
        built = tree.prove(pv["leaf_index"]).to_obj()
        assert built == pv
        assert verify(leaves[pv["leaf_index"]], Proof.from_obj(pv), bytes.fromhex(vs["root"]))
    assert vs["size"] or vs["root"] == VECTORS["empty_root"]


# ---- leaf file parsing + CLI ------------------------------------------------------------
def test_line_rules():
    assert parse_leaves(b"") == []
    assert parse_leaves(b"\n") == [b""]
    assert parse_leaves(b"a\nb") == parse_leaves(b"a\nb\n") == [b"a", b"b"]
    assert parse_leaves(b"a\r\nb\r\n") == [b"a", b"b"]
    assert parse_leaves(b"a\n\nb\n") == [b"a", b"", b"b"]
    assert parse_leaves(b"00\nff\n\n", "hex") == [b"\x00", b"\xff", b""]
    for bad in (b"abc\n", b"zz\n", b"12 34\n", b"0x12\n"):
        with pytest.raises(MerkleError):
            parse_leaves(bad, "hex")


@pytest.fixture
def five(tmp_path):
    f = tmp_path / "tx.txt"
    f.write_bytes((ROOT_DIR / "examples" / "transactions.txt").read_bytes())
    return f


def test_cli_root_sizes(tmp_path, capsys):
    for content, n in ((b"", 0), (b"only\n", 1), (b"a\nb\nc\n", 3), (b"a\nb\nc\nd\n", 4)):
        f = tmp_path / "x.txt"
        f.write_bytes(content)
        code, out, _ = run(capsys, "root", "--leaves", str(f))
        assert code == 0 and f"leaves: {n}" in out
        assert f"root: {merkle_root(parse_leaves(content)).hex()}" in out


def test_cli_prove_verify_roundtrip(five, tmp_path, capsys):
    _, out, _ = run(capsys, "root", "--leaves", str(five))
    root = out.split("root: ")[1].strip()
    assert root == MTH([l.encode() for l in (ROOT_DIR / "examples" / "transactions.txt").read_text().splitlines()]).hex()
    pf = tmp_path / "p.json"
    code, _, _ = run(capsys, "prove", "--leaves", str(five), "--index", "2", "--out", str(pf))
    assert code == 0
    code, out, _ = run(capsys, "verify", "--root", root, "--leaf", "Carol pays Dave 7",
                       "--proof", str(pf), "--tree-size", "5")
    assert code == 0 and out.startswith("VALID")
    code, out, _ = run(capsys, "verify", "--root", root, "--leaf", "Carol pays Dave 8", "--proof", str(pf))
    assert code == 1 and out.startswith("INVALID") and "computed root" in out
    code, out, _ = run(capsys, "verify", "--root", root, "--leaf-hex", "Carol".encode().hex(), "--proof", str(pf))
    assert code == 1


def test_cli_prove_stdout_is_pure_json(five, capsys):
    code, out, _ = run(capsys, "prove", "--leaves", str(five), "--index", "4")
    assert code == 0 and Proof.from_json(out).leaf_index == 4


def test_cli_prove_errors(five, tmp_path, capsys):
    code, _, err = run(capsys, "prove", "--leaves", str(five), "--index", "5")
    assert code == 1 and "out of range" in err
    empty = tmp_path / "e.txt"
    empty.write_bytes(b"")
    code, _, err = run(capsys, "prove", "--leaves", str(empty), "--index", "0")
    assert code == 1 and "empty" in err
    code, _, err = run(capsys, "root", "--leaves", "/no/such/file")
    assert code == 1 and "cannot read" in err


def test_cli_verify_rejects_example_bad_proofs(capsys):
    root = "78c00d2ca02b959884ad83513a0f566abcc72b95f02e5400df4da618ca36d248"
    expect = {
        "malformed_hash_short.json": "malformed hash", "malformed_hash_chars.json": "malformed hash",
        "invalid_direction_value.json": "invalid direction", "wrong_direction.json": "direction",
        "index_out_of_range.json": "out of range", "wrong_index.json": "direction",
        "too_long.json": "unnecessarily long", "too_short.json": "too short",
    }
    for name, msg in expect.items():
        path = ROOT_DIR / "examples" / "bad_proofs" / name
        code, out, _ = run(capsys, "verify", "--root", root, "--leaf", "Carol pays Dave 7", "--proof", str(path))
        assert code == 1 and out.startswith("INVALID") and msg in out, name
    code, _, err = run(capsys, "verify", "--root", "abc", "--leaf", "x",
                       "--proof", str(ROOT_DIR / "examples" / "proof_index2.json"))
    assert code == 1 and "malformed root" in err


def test_cli_crlf_same_root(tmp_path, capsys):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b"x\ny\nz\n")
    b.write_bytes(b"x\r\ny\r\nz\r\n")
    assert run(capsys, "root", "--leaves", str(a))[1] == run(capsys, "root", "--leaves", str(b))[1]


def test_cli_hex_encoding(tmp_path, capsys):
    f = tmp_path / "h"
    f.write_text("00\n10\n2021\n")
    code, out, _ = run(capsys, "root", "--leaves", str(f), "--encoding", "hex")
    assert code == 0 and merkle_root([b"\x00", b"\x10", b"\x20\x21"]).hex() in out
    f.write_text("0\n")
    assert run(capsys, "root", "--leaves", str(f), "--encoding", "hex")[0] == 1


# ---- Task 6: benchmark ------------------------------------------------------------------
def test_bench_small(capsys):
    r = bench_size(8, repeat=1)
    assert r.siblings_max == 3 and r.proof_raw_bytes == 96 and r.hashes == 15
    code, out, _ = run(capsys, "bench", "--sizes", "8,1024", "--repeat", "1")
    assert code == 0 and "1,024" in out
    assert run(capsys, "bench", "--sizes", "x")[0] == 1


def test_100k_leaves_build_and_prove():
    leaves = leaves_n(100_000)
    t = MerkleTree(leaves)
    assert t.size == 100_000 and t.height == 17
    for i in (0, 1, 49_999, 65_535, 65_536, 99_998, 99_999):
        p = t.prove(i)
        assert len(p.siblings) <= 17
        assert verify(leaves[i], p, t.root)
    assert t.root == MTH(leaves)
