import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from walletlab import keys, tx as T
from walletlab.address import address_from_pubkey, check_address, decode_address
from walletlab.base58 import b58check_decode, b58check_encode, b58decode, b58encode
from walletlab.canonical import canonicalize
from walletlab.cli import main
from walletlab.errors import WalletError

ROOT = Path(__file__).resolve().parent.parent
NET = "course-testnet"
ALICE = keys.private_from_seed(hashlib.sha256(b"walletlab test-only alice").digest())
BOB = keys.private_from_seed(hashlib.sha256(b"walletlab test-only bob").digest())
A = address_from_pubkey(keys.public_bytes(ALICE), NET)
B = address_from_pubkey(keys.public_bytes(BOB), NET)


def make_tx(**over):
    t = {"version": 1, "network_id": NET, "sender": A, "recipient": B,
         "amount_units": 1250000, "nonce": 7, "memo_hash": T.memo_hash("rent")}
    t.update(over)
    return t


def signed(tx=None, key=ALICE):
    tx = tx or make_tx()
    sig = keys.sign(key, T.signing_bytes(tx))
    return T.make_envelope(tx, keys.public_bytes(key), sig)


def raw(env):
    return json.dumps(env).encode()


def verify(env, network=NET, state=None):
    return T.verify_envelope(raw(env) if isinstance(env, dict) else env, network, state)


def rejects(env, text, **kw):
    with pytest.raises(WalletError, match=text):
        verify(env, **kw)


# ---- library sanity: RFC 8032 test vector 1 -----------------------------
def test_rfc8032_vector1():
    seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    k = keys.private_from_seed(seed)
    assert keys.public_bytes(k).hex() == "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    assert keys.sign(k, b"").hex() == (
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")


# ---- keys -----------------------------------------------------------------
def test_generate_is_random_and_32_bytes():
    a, b = keys.generate(), keys.generate()
    assert keys.public_bytes(a) != keys.public_bytes(b)
    assert len(keys.seed_bytes(a)) == 32


def test_keygen_public_only_by_default(tmp_path, capsys):
    assert main(["keygen", "--public-out", str(tmp_path / "p.json")]) == 0
    assert [p.name for p in tmp_path.iterdir()] == ["p.json"]
    assert "NOT saved" in capsys.readouterr().out


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_dev_private_key_is_0600_with_warning(tmp_path, capsys):
    k = tmp_path / "k.json"
    main(["keygen", "--public-out", str(tmp_path / "p.json"), "--dev-export-private", str(k)])
    assert stat.S_IMODE(k.stat().st_mode) == 0o600
    assert "TEST-ONLY" in k.read_text()
    assert "TEST-ONLY" in capsys.readouterr().err


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_loose_private_key_permissions_refused(tmp_path):
    k = tmp_path / "k.json"
    keys.write_private_dev(k, ALICE, NET)
    os.chmod(k, 0o644)
    with pytest.raises(WalletError, match="must be 0600"):
        keys.read_private(k)


def test_keygen_never_overwrites(tmp_path):
    p = tmp_path / "p.json"
    p.write_text("x")
    with pytest.raises(WalletError, match="refusing to overwrite"):
        keys.write_public(p, ALICE, NET)


# ---- base58 / address -------------------------------------------------------
def test_base58_known_values():
    assert b58encode(b"hello world") == "StV1DL6CwTryKyV"
    assert b58encode(b"\x00\x00\x01") == "112"
    assert b58decode("112") == b"\x00\x00\x01"


def test_base58check_roundtrip_and_bad_char():
    p = b"\x6f" + bytes(range(20))
    assert b58check_decode(b58check_encode(p)) == p
    with pytest.raises(WalletError, match="invalid Base58 character"):
        b58decode("0OIl")


def test_address_derivation_documented():
    pub = keys.public_bytes(ALICE)
    pkh = hashlib.sha256(pub).digest()[:20]
    payload = b"\x6f" + pkh
    chk = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    assert address_from_pubkey(pub, NET) == b58encode(payload + chk)
    assert decode_address(A) == (NET, pkh)


def test_address_network_prefix_differs():
    pub = keys.public_bytes(ALICE)
    assert address_from_pubkey(pub, "course-mainnet") != A
    with pytest.raises(WalletError, match="course-testnet"):
        check_address(address_from_pubkey(pub, "course-testnet"), "course-mainnet")


@pytest.mark.parametrize("bad", ["", "1", A[:-1], A + "1", "0" + A[1:], A[1:], " " + A])
def test_malformed_addresses_rejected(bad):
    with pytest.raises(WalletError):
        check_address(bad)


def test_every_single_char_typo_detected():
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    for i in range(len(A)):
        for c in alphabet[:6]:
            if c != A[i]:
                with pytest.raises(WalletError):
                    check_address(A[:i] + c + A[i + 1:])


# ---- canonical bytes ----------------------------------------------------
def test_canonical_independent_of_whitespace_and_order():
    a = b'{"b": 1,\n "a": [1, 2]}'
    b = b'{"a":[1,2],"b":1}'
    assert canonicalize(a) == canonicalize(b) == b'{"a":[1,2],"b":1}'


def test_float_amount_rejected():
    with pytest.raises(WalletError, match="floating-point"):
        verify(b'{"transaction":{"amount_units":1.5}}')


def test_duplicate_keys_rejected():
    with pytest.raises(WalletError, match="duplicate"):
        canonicalize(b'{"a":1,"a":2}')


def test_signing_bytes_exact_layout():
    t = make_tx()
    expected = (b"walletlab/tx/v1\x00"
                + ('{"amount_units":1250000,"memo_hash":"%s","network_id":"course-testnet",'
                   '"nonce":7,"recipient":"%s","sender":"%s","version":1}'
                   % (t["memo_hash"], B, A)).encode())
    assert T.signing_bytes(t) == expected


# ---- sign + verify -----------------------------------------------------
def test_valid_signature_verifies():
    assert verify(signed())["amount_units"] == 1250000


def test_signature_is_deterministic():
    assert signed() == signed()


def test_reordered_and_reformatted_json_same_signed_bytes():
    env = signed()
    pretty = json.dumps(env, indent=4, sort_keys=False).encode()
    reordered = json.dumps(
        {"signature": env["signature"], "transaction": dict(reversed(list(env["transaction"].items()))),
         "public_key": env["public_key"]}, separators=(", ", " : ")).encode()
    assert verify(pretty) == verify(reordered) == env["transaction"]
    assert T.signing_bytes(json.loads(pretty)["transaction"]) == T.signing_bytes(json.loads(reordered)["transaction"])


@pytest.mark.parametrize("field,value", [
    ("amount_units", 1250001), ("nonce", 8), ("recipient", A), ("sender", B),
    ("memo_hash", "0" * 64), ("version", 2),
])
def test_changing_any_signed_field_fails(field, value):
    env = signed()
    env["transaction"][field] = value
    with pytest.raises(WalletError):
        verify(env)


def test_changed_amount_message():
    env = signed()
    env["transaction"]["amount_units"] += 1
    rejects(env, "does not verify")


def test_wrong_network_rejected():
    rejects(signed(), "wrong network", network="course-mainnet")
    env = signed(make_tx(network_id="course-mainnet"))
    rejects(env, "wrong network")                                        # node is on testnet
    rejects(env, "address is for course-testnet", network="course-mainnet")  # tx says mainnet, but testnet addresses


def test_wrong_signer_rejected():
    env = signed()
    env["public_key"] = keys.public_bytes(BOB).hex()
    rejects(env, "wrong signer")


def test_signed_by_someone_else_for_alices_address():
    tx = make_tx()
    env = T.make_envelope(tx, keys.public_bytes(BOB), keys.sign(BOB, T.signing_bytes(tx)))
    rejects(env, "wrong signer")


def test_replayed_nonce_rejected_by_state(tmp_path):
    st = tmp_path / "st.json"
    env = signed()
    state = T.load_state(str(st))
    t = verify(env, state=state)
    state[t["sender"]] = t["nonce"]
    T.save_state(str(st), state)
    rejects(env, "replayed", state=T.load_state(str(st)))
    rejects(signed(make_tx(nonce=3)), "replayed", state=T.load_state(str(st)))
    assert verify(signed(make_tx(nonce=8)), state=T.load_state(str(st)))["nonce"] == 8


def test_replay_state_is_per_sender():
    state = {B: 100}
    assert verify(signed(), state=state)


def test_malformed_recipient_checksum_rejected():
    bad = B[:-1] + ("2" if B[-1] != "2" else "3")
    rejects(signed(make_tx(recipient=bad)), "checksum")


@pytest.mark.parametrize("mutate,text", [
    (lambda s: s[:-2], "malformed signature"),
    (lambda s: s + "00", "malformed signature"),
    (lambda s: s.upper(), "malformed signature"),
    (lambda s: "zz" + s[2:], "malformed signature"),
])
def test_malformed_signature_encoding(mutate, text):
    env = signed()
    env["signature"] = mutate(env["signature"])
    rejects(env, text)


def test_non_canonical_signature_S_rejected():
    env = signed()
    r, s = env["signature"][:64], int.from_bytes(bytes.fromhex(env["signature"][64:]), "little")
    env["signature"] = r + (s + keys.GROUP_ORDER_L).to_bytes(32, "little").hex()
    rejects(env, "non-canonical signature")


def test_uppercase_public_key_rejected():
    env = signed()
    env["public_key"] = env["public_key"].upper()
    rejects(env, "public_key")


@pytest.mark.parametrize("over,text", [
    ({"amount_units": 0}, "amount_units"), ({"amount_units": -5}, "amount_units"),
    ({"amount_units": True}, "amount_units"), ({"amount_units": "100"}, "amount_units"),
    ({"nonce": -1}, "nonce"), ({"nonce": 2**53}, "outside safe range"),
    ({"memo_hash": "AB" * 32}, "memo_hash"), ({"version": 1.0}, "floating"),
    ({"extra": 1}, "unknown field"),
])
def test_schema_violations(over, text):
    t = make_tx()
    t.update(over)
    env = {"transaction": t, "public_key": keys.public_bytes(ALICE).hex(), "signature": "00" * 64}
    rejects(env, text)


def test_missing_field():
    t = make_tx()
    del t["nonce"]
    rejects({"transaction": t, "public_key": "00" * 32, "signature": "00" * 64}, "missing field")


def test_sign_refuses_foreign_sender():
    with pytest.raises(WalletError, match="does not own"):
        T.sign_transaction(json.dumps(make_tx()).encode(), BOB)


# ---- shipped vectors / examples (instructor flow: public data only) ------
def test_shipped_vectors():
    v = json.loads((ROOT / "vectors/test_vectors.json").read_text())
    assert v["alice_address"] == A and v["bob_address"] == B
    assert T.signing_bytes(make_tx(memo_hash=T.memo_hash("rent for November"))).hex() != ""
    for rel in v["must_verify"]:
        assert T.verify_envelope((ROOT / rel).read_bytes(), NET)["nonce"] == 7
    for case in v["must_reject"]:
        with pytest.raises(WalletError, match=case["reject_contains"]):
            T.verify_envelope((ROOT / case["file"]).read_bytes(), NET)


# ---- CLI end to end -----------------------------------------------------
@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_cli_end_to_end(tmp_path, capsys):
    d = tmp_path
    assert main(["keygen", "--public-out", str(d / "a.pub"), "--dev-export-private", str(d / "a.key")]) == 0
    assert main(["keygen", "--public-out", str(d / "b.pub")]) == 0
    capsys.readouterr()
    main(["address", "--pub", str(d / "a.pub")]); a = capsys.readouterr().out.strip()
    main(["address", "--pub", str(d / "b.pub")]); b = capsys.readouterr().out.strip()
    (d / "tx.json").write_text(json.dumps(make_tx(sender=a, recipient=b)))
    assert main(["sign", "--key", str(d / "a.key"), "--tx", str(d / "tx.json"), "--out", str(d / "s.json")]) == 0
    capsys.readouterr()
    st = str(d / "state.json")
    assert main(["verify", "--signed", str(d / "s.json"), "--state", st, "--update-state"]) == 0
    assert "VALID" in capsys.readouterr().out
    assert main(["verify", "--signed", str(d / "s.json"), "--state", st]) == 1
    assert "replayed" in capsys.readouterr().err
    assert main(["verify", "--signed", str(d / "s.json"), "--network", "course-mainnet"]) == 1
    assert main(["address", "--check", a]) == 0
    assert main(["address", "--check", a[:-1] + "x"]) == 1
