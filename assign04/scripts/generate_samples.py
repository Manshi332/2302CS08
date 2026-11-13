"""Regenerate everything under examples/ and vectors/ (deterministic; safe to re-run).

    python scripts/generate_samples.py
"""
import hashlib
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from utxolab import keys                                   # noqa: E402
from utxolab.demo import demo_wallet, run_scenario         # noqa: E402
from utxolab.tx import DOMAIN_SIG, DOMAIN_TXID             # noqa: E402


def main() -> None:
    ex = os.path.join(ROOT, "examples")
    snap_dir = os.path.join(ex, "snapshots")
    for f in os.listdir(snap_dir) if os.path.isdir(snap_dir) else []:
        os.unlink(os.path.join(snap_dir, f))
    lines = []
    res = run_scenario(snap_dir, emit=lines.append)
    with open(os.path.join(ex, "trace.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(os.path.join(ex, "trace.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(res["records"], fh, indent=2)
        fh.write("\n")
    for name, tx in (("tx_alice_pays_bob.json", res["pay_tx"]), ("tx_bob_pays_carol.json", res["good_tx"])):
        with open(os.path.join(ex, name), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(tx.to_obj(), fh, indent=2)
            fh.write("\n")

    pay = res["pay_tx"]
    alice, bob = demo_wallet("alice"), demo_wallet("bob")
    vec = {
        "description": "Known-answer vectors. TEST-ONLY seeds: sha256('utxolab-demo-<name>').",
        "network_id": "course-testnet",
        "alice_seed": hashlib.sha256(b"utxolab-demo-alice").hexdigest(),
        "alice_address": alice.primary_address,
        "bob_address": bob.primary_address,
        "txid_domain_hex": DOMAIN_TXID.hex(),
        "sig_domain_hex": DOMAIN_SIG.hex(),
        "tx_alice_pays_bob": {
            "canonical_body": pay.body.canonical_bytes.decode("utf-8"),
            "txid": pay.txid,
            "signing_bytes_sha256": hashlib.sha256(pay.body.signing_bytes).hexdigest(),
            "signed_tx": pay.to_obj(),
        },
    }
    with open(os.path.join(ROOT, "vectors", "tx_vectors.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(vec, fh, indent=2)
        fh.write("\n")
    print("wrote examples/ (trace, snapshots, signed txs) and vectors/tx_vectors.json")


if __name__ == "__main__":
    main()
