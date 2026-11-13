"""Regenerate vectors/header_vector.json (the pinned header layout / hash test vector)."""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from chainlab import Chain, ChainParams  # noqa: E402

h = Chain(ChainParams(bits=8)).genesis.header
doc = {"description": "Genesis block header of ChainParams(bits=8): pins the 112-byte layout and SHA-256d.",
       "header_hex": h.serialize().hex(), "block_hash": h.hash_hex, "work": h.work, "fields": h.to_obj()}
with open(os.path.join(ROOT, "vectors", "header_vector.json"), "w", encoding="utf-8", newline="\n") as fh:
    json.dump(doc, fh, indent=2)
    fh.write("\n")
print("wrote vectors/header_vector.json")
