"""Command-line interface: demo | inspect | balance | check-tx | apply-tx."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from . import __version__
from .address import address_from_pkh, check_address, decode_address
from .demo import run_scenario
from .errors import LedgerError, WalletError
from .ledger import Ledger


def _read(path: str) -> bytes:
    try:
        if path == "-":
            return sys.stdin.buffer.read()
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        raise LedgerError("unreadable", f"cannot read {path!r}: {exc.strerror or exc}") from exc


def cmd_demo(args: argparse.Namespace) -> int:
    run_scenario(args.snapshot_dir)
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    led = Ledger.load(args.state)
    print(f"network: {led.network_id}")
    print(f"utxos: {len(led.utxos)}   applied_txs: {len(led.applied)}   spent_outpoints: {len(led.spent)}")
    print(f"issued: {led.issued}   unspent: {led.total_unspent()}   fees_burned: {led.fees}")
    print(f"state_sha256: {led.state_hash()}")
    for op in sorted(led.utxos):
        o = led.utxos[op]
        print(f"  {op}  value={o.value}  owner={address_from_pkh(o.pkh, led.network_id)}")
    return 0


def cmd_balance(args: argparse.Namespace) -> int:
    led = Ledger.load(args.state)
    try:
        check_address(args.address, led.network_id)
        _, pkh = decode_address(args.address)
    except WalletError as exc:
        raise LedgerError("bad_address", str(exc)) from None
    print(f"balance: {led.balance_of(pkh)}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    led = Ledger.load(args.state)
    plan = led.validate(_read(args.tx))
    print("VALID")
    print(f"txid: {plan.txid}\ninputs_total: {plan.total_in}\noutputs_total: {plan.total_out}\nfee: {plan.fee}")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    led = Ledger.load(args.state)
    r = led.apply(_read(args.tx))
    out = args.out or args.state
    led.save(out, pretty=args.pretty)
    print(f"ACCEPTED txid={r.txid} fee={r.fee}")
    print(f"state written to {out} (sha256 {led.state_hash()})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="utxolab", description="UTXO ledger and transaction validator (educational).")
    p.add_argument("--version", action="version", version=f"utxolab {__version__}")
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    s = sub.add_parser("demo", help="run the Alice/Bob scenario and print the accepted/rejected trace")
    s.add_argument("--snapshot-dir", metavar="DIR", help="also write pretty ledger snapshots here")
    s.set_defaults(func=cmd_demo)

    s = sub.add_parser("inspect", help="load a snapshot (verifying it) and list its UTXOs")
    s.add_argument("state", metavar="SNAPSHOT")
    s.set_defaults(func=cmd_inspect)

    s = sub.add_parser("balance", help="balance of an address in a snapshot")
    s.add_argument("--state", required=True, metavar="SNAPSHOT")
    s.add_argument("--address", required=True)
    s.set_defaults(func=cmd_balance)

    s = sub.add_parser("check-tx", help="validate a signed transaction against a snapshot (no changes)")
    s.add_argument("--state", required=True, metavar="SNAPSHOT")
    s.add_argument("--tx", required=True, metavar="FILE", help="signed transaction JSON ('-' = stdin)")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("apply-tx", help="validate and apply a signed transaction, then save the snapshot")
    s.add_argument("--state", required=True, metavar="SNAPSHOT")
    s.add_argument("--tx", required=True, metavar="FILE")
    s.add_argument("--out", metavar="FILE", help="write here instead of replacing --state")
    s.add_argument("--pretty", action="store_true", help="human-readable snapshot")
    s.set_defaults(func=cmd_apply)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except LedgerError as exc:
        print(f"REJECTED code={exc.code}\nreason: {exc.reason}", file=sys.stderr)
        return 1
    except WalletError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
