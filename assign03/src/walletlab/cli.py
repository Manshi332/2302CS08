"""Command-line interface: keygen, address, sign, verify."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from . import __version__, keys, tx as txmod
from .address import DEFAULT_NETWORK, NETWORK_VERSION, address_from_pubkey, check_address
from .canonical import canonicalize
from .errors import WalletError


def _read(path: str) -> bytes:
    try:
        if path == "-":
            return sys.stdin.buffer.read()
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        raise WalletError(f"cannot read {path!r}: {exc.strerror or exc}") from exc


def cmd_keygen(args: argparse.Namespace) -> int:
    key = keys.generate()
    keys.write_public(args.public_out, key, args.network)
    pub = keys.public_bytes(key)
    if args.dev_export_private:
        keys.write_private_dev(args.dev_export_private, key, args.network)
    print(f"network: {args.network}")
    print(f"public_key: {pub.hex()}")
    print(f"address: {address_from_pubkey(pub, args.network)}")
    print(f"public_file: {args.public_out}")
    if not args.dev_export_private:
        print("private key: NOT saved (use --dev-export-private PATH for a test-only key file)")
    return 0


def cmd_address(args: argparse.Namespace) -> int:
    if args.check is not None:
        net = check_address(args.check, args.network_required)
        print(f"valid: yes\nnetwork: {net}\naddress: {args.check}")
        return 0
    if args.public_key is not None:
        pub = keys.parse_pubkey_hex(args.public_key)
    elif args.pub is not None:
        pub, _ = keys.read_public(args.pub)
    else:
        raise WalletError("give --pub FILE, --public-key HEX, or --check ADDRESS")
    print(address_from_pubkey(pub, args.network))
    return 0


def cmd_sign(args: argparse.Namespace) -> int:
    key, key_net = keys.read_private(args.key)
    env = txmod.sign_transaction(_read(args.tx), key, args.network or key_net or None)
    text = json.dumps(env, indent=2) + "\n"
    if args.out:
        keys.write_new_file(args.out, text, 0o644)
        print(f"signed: {args.out}")
    else:
        sys.stdout.write(text)
    print(f"signing_bytes_sha256: {_sha(txmod.signing_bytes(env['transaction']))}", file=sys.stderr)
    return 0


def _sha(b: bytes) -> str:
    import hashlib
    return hashlib.sha256(b).hexdigest()


def cmd_verify(args: argparse.Namespace) -> int:
    state = txmod.load_state(args.state) if args.state else None
    t = txmod.verify_envelope(_read(args.signed), args.network, state)
    print("VALID")
    print(f"network: {t['network_id']}")
    print(f"sender: {t['sender']}")
    print(f"recipient: {t['recipient']}")
    print(f"amount_units: {t['amount_units']}")
    print(f"nonce: {t['nonce']}")
    print(f"signing_bytes_sha256: {_sha(txmod.signing_bytes(t))}")
    if args.update_state:
        if not args.state:
            raise WalletError("--update-state requires --state FILE")
        state[t["sender"]] = t["nonce"]
        txmod.save_state(args.state, state)
        print(f"state updated: last_nonce[{t['sender']}] = {t['nonce']}")
    return 0


def cmd_canonical(args: argparse.Namespace) -> int:
    """Debug helper: print the exact canonical bytes (as text) of a JSON file."""
    print(canonicalize(_read(args.path)).decode("utf-8"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    nets = sorted(NETWORK_VERSION)
    parser = argparse.ArgumentParser(
        prog="walletlab",
        description="Educational wallet: Ed25519 keys, addresses, signed transactions. "
                    "Curve math and randomness come from the `cryptography` library.",
    )
    parser.add_argument("--version", action="version", version=f"walletlab {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p = sub.add_parser("keygen", help="generate a key pair (public key only is saved by default)")
    p.add_argument("--network", choices=nets, default=DEFAULT_NETWORK)
    p.add_argument("--public-out", required=True, metavar="FILE", help="public key file to create")
    p.add_argument("--dev-export-private", metavar="FILE",
                   help="ALSO write an unencrypted TEST-ONLY private key (mode 0600)")
    p.set_defaults(func=cmd_keygen)

    p = sub.add_parser("address", help="derive an address from a public key, or validate one")
    p.add_argument("--pub", metavar="FILE", help="public key file from keygen")
    p.add_argument("--public-key", metavar="HEX", help="raw public key, 64 hex chars")
    p.add_argument("--network", choices=nets, default=DEFAULT_NETWORK)
    p.add_argument("--check", metavar="ADDRESS", help="validate checksum/format of an address")
    p.add_argument("--network-required", choices=nets,
                   help="with --check: also require this network")
    p.set_defaults(func=cmd_address)

    p = sub.add_parser("sign", help="sign a transaction JSON with a dev private key")
    p.add_argument("--key", required=True, metavar="FILE", help="dev private key file")
    p.add_argument("--tx", required=True, metavar="FILE", help="transaction JSON ('-' = stdin)")
    p.add_argument("--network", choices=nets, help="expected network (default: the key's)")
    p.add_argument("--out", metavar="FILE", help="write envelope here (default: stdout)")
    p.set_defaults(func=cmd_sign)

    p = sub.add_parser("verify", help="verify a signed transaction using only public data")
    p.add_argument("--signed", required=True, metavar="FILE", help="signed envelope ('-' = stdin)")
    p.add_argument("--network", choices=nets, default=DEFAULT_NETWORK,
                   help=f"network this node is on (default {DEFAULT_NETWORK})")
    p.add_argument("--state", metavar="FILE", help="replay-protection state (last nonce per sender)")
    p.add_argument("--update-state", action="store_true",
                   help="after a VALID result, record the nonce in --state")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("canonical", help="print the canonical JSON text of a file (debug aid)")
    p.add_argument("path", nargs="?", default="-")
    p.set_defaults(func=cmd_canonical)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except WalletError as exc:
        print(f"REJECTED: {exc}" if args.command == "verify" else f"error: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
