"""Regenerate examples/ and vectors/ deterministically (Ed25519 signing is deterministic).

The seeds below are TEST-ONLY and public on purpose, so every student/instructor
gets identical bytes. The private key files are NOT written to examples/.

    PYTHONPATH=src python3 scripts/gen_examples.py
"""

import hashlib
import json
from pathlib import Path

from walletlab import keys, tx as T
from walletlab.address import address_from_pubkey

ROOT = Path(__file__).resolve().parent.parent
NET = "course-testnet"
ALICE = keys.private_from_seed(hashlib.sha256(b"walletlab test-only alice").digest())
BOB = keys.private_from_seed(hashlib.sha256(b"walletlab test-only bob").digest())
A = address_from_pubkey(keys.public_bytes(ALICE), NET)
B = address_from_pubkey(keys.public_bytes(BOB), NET)

TX = {
    "version": 1, "network_id": NET, "sender": A, "recipient": B,
    "amount_units": 1250000, "nonce": 7, "memo_hash": T.memo_hash("rent for November"),
}


def dump(path, obj):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def main():
    ex = ROOT / "examples"
    for name, k in (("alice", ALICE), ("bob", BOB)):
        dump(ex / f"{name}.pub.json", keys.public_record(keys.public_bytes(k), NET))
    env = T.make_envelope(TX, keys.public_bytes(ALICE), keys.sign(ALICE, T.signing_bytes(TX)))
    dump(ex / "tx.json", TX)
    dump(ex / "signed_tx.json", env)
    # Same transaction, different key order and whitespace: must verify identically.
    (ex / "signed_tx_reordered.json").write_text(
        '{"signature":"%s","public_key":"%s",\n\t"transaction":{"nonce":7,"memo_hash":"%s",'
        '"amount_units":1250000,"recipient":"%s","sender":"%s","network_id":"%s","version":1}}'
        % (env["signature"], env["public_key"], TX["memo_hash"], B, A, NET), encoding="utf-8")

    # Tamper cases that must be REJECTED (expected reason substring recorded).
    def bad(name, mutate, why):
        e = json.loads(json.dumps(env))
        mutate(e)
        dump(ex / "bad" / f"{name}.json", e)
        return {"file": f"examples/bad/{name}.json", "reject_contains": why}

    s = env["signature"]
    L = keys.GROUP_ORDER_L
    s_malleable = s[:64] + (int.from_bytes(bytes.fromhex(s[64:]), "little") + L).to_bytes(32, "little").hex()
    mut = lambda f: (lambda e: f(e["transaction"]))
    cases = [
        bad("amount_changed", mut(lambda t: t.update(amount_units=1250001)), "does not verify"),
        bad("nonce_changed", mut(lambda t: t.update(nonce=8)), "does not verify"),
        bad("recipient_changed", mut(lambda t: t.update(recipient=A)), "does not verify"),
        bad("memo_changed", mut(lambda t: t.update(memo_hash=T.memo_hash("other"))), "does not verify"),
        bad("wrong_network", mut(lambda t: t.update(network_id="course-mainnet")), "wrong network"),
        bad("wrong_signer", lambda e: e.update(public_key=keys.public_bytes(BOB).hex()), "wrong signer"),
        bad("bad_checksum_address", mut(lambda t: t.update(recipient=B[:-1] + ("2" if B[-1] != "2" else "3"))), "checksum"),
        bad("signature_short", lambda e: e.update(signature=s[:-2]), "malformed signature"),
        bad("signature_uppercase", lambda e: e.update(signature=s.upper()), "malformed signature"),
        bad("signature_non_canonical_S", lambda e: e.update(signature=s_malleable), "non-canonical signature"),
        bad("extra_field", mut(lambda t: t.update(fee=1)), "unknown field"),
    ]
    dump(ROOT / "vectors" / "test_vectors.json", {
        "note": "TEST-ONLY seeds = SHA-256 of the quoted strings. Ed25519 is deterministic.",
        "network_id": NET,
        "alice_seed_sha256_of": "walletlab test-only alice",
        "alice_public_key": keys.public_bytes(ALICE).hex(), "alice_address": A,
        "bob_public_key": keys.public_bytes(BOB).hex(), "bob_address": B,
        "canonical_transaction": T.signing_bytes(TX)[len(T.DOMAIN_TAG):].decode(),
        "domain_tag_hex": T.DOMAIN_TAG.hex(),
        "signing_bytes_sha256": hashlib.sha256(T.signing_bytes(TX)).hexdigest(),
        "signature": env["signature"],
        "must_verify": ["examples/signed_tx.json", "examples/signed_tx_reordered.json"],
        "must_reject": cases,
    })
    print("alice:", A, "\nbob:  ", B)


if __name__ == "__main__":
    main()
