"""Regenerate vectors/test_vectors.json from the INDEPENDENT reference (tests/reference_rfc6962.py).

Run from the assignment folder:  python scripts/gen_vectors.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from reference_rfc6962 import MTH, PATH  # noqa: E402

CT_LEAVES = ["", "00", "10", "2021", "3031", "40414243", "5051525354555657",
             "606162636465666768696a6b6c6d6e6f"]


def side_list(m, n):
    sides, idx = [], m
    while n > 1:
        if idx & 1:
            sides.append("left")
        elif idx + 1 < n:
            sides.append("right")
        idx >>= 1
        n = (n + 1) >> 1
    return sides


def vector_set(name, leaves_hex):
    leaves = [bytes.fromhex(x) for x in leaves_hex]
    out = {"name": name, "leaves_hex": leaves_hex, "size": len(leaves), "root": MTH(leaves).hex(), "proofs": []}
    for i in range(len(leaves)):
        path = PATH(i, leaves)
        sides = side_list(i, len(leaves))
        assert len(path) == len(sides)
        out["proofs"].append({
            "leaf_index": i,
            "tree_size": len(leaves),
            "siblings": [{"side": s, "hash": h.hex()} for s, h in zip(sides, path)],
        })
    return out


sets = []
for n in range(0, 9):
    sets.append(vector_set(f"rfc6962-ct-{n}", CT_LEAVES[:n]))
tx = ["Alice pays Bob 10", "Bob pays Carol 4", "Carol pays Dave 7", "Dave pays Erin 2", "Erin pays Alice 5"]
sets.append(vector_set("five-transactions", [t.encode().hex() for t in tx]))
for n in (9, 10, 11, 16, 17):
    sets.append(vector_set(f"tx-{n}", [f"tx-{i}".encode().hex() for i in range(n)]))

(ROOT / "vectors").mkdir(exist_ok=True)
(ROOT / "vectors" / "test_vectors.json").write_text(json.dumps({"hash": "SHA-256",
    "leaf_prefix": "00", "node_prefix": "01", "empty_root": MTH([]).hex(), "sets": sets}, indent=1) + "\n")
print("wrote vectors/test_vectors.json with", len(sets), "sets")
