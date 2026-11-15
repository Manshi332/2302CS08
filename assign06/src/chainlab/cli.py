"""Command-line interface for chainlab.

  init        create a new chain file (deterministic genesis)
  address     TEST-ONLY deterministic address of a demo wallet (alice, bob, ...)
  pay         build a signed payment from a demo wallet against the chain's UTXO set
  mine        MINER COMMAND: assemble a block, search a nonce, add it to the chain
  submit      add a block file received from someone else (validate / side-branch / reorg)
  info        height, tip, work, branches, balances; --tree draws the block tree
  dump-header annotated hex dump of a block header
  fork-sim    two miners, a fork, and its resolution by a reorganisation
  work-sim    a longer low-work branch versus a shorter high-work branch
  acceptance  run every acceptance check and print PASS/FAIL
  bench       hashes per second and expected vs observed attempts
  report      write the full Markdown report (docs/REPORT.md)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Sequence

from . import __version__
from .acceptance import run_acceptance
from .bench import DEFAULT_BITS, format_table, hash_rate, machine_info, run_bench
from .block import Block, BlockHeader, hexdump_header
from .chain import Chain
from .consensus import ChainParams
from .errors import BlockError, WalletError
from .miner import mine_block
from .proofofwork import target_from_bits
from .report import generate_report
from .simulate import run_fork_simulation, run_work_vs_length
from .testkeys import demo_address, demo_wallet
from .tx import SignedTx


def _read(path: str) -> bytes:
    try:
        if path == "-":
            return sys.stdin.buffer.read()
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        raise BlockError("unreadable", f"cannot read {path!r}: {exc.strerror or exc}") from exc


def _write(path: str, text: str, overwrite: bool = True) -> None:
    if not overwrite and os.path.exists(path):
        raise BlockError("exists", f"{path} already exists (use --force to overwrite)")
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    except OSError as exc:
        raise BlockError("unwritable", f"cannot write {path!r}: {exc.strerror or exc}") from exc


def _print_add(res) -> None:
    print(f"{res.status.upper()} block {res.hash} height={res.height} cumulative_work={res.chain_work}")
    if res.status == "reorganized":
        print(f"  fork point: {res.fork}")
        print(f"  disconnected (tip first): {', '.join(h[:12] for h in res.disconnected)}")
        print(f"  connected: {', '.join(h[:12] for h in res.connected)}")
        print(f"  transactions returned to the mempool: {len(res.returned_txs)}")
        for tx in res.returned_txs:
            print(f"    {tx.txid}")


# ---- handlers ----------------------------------------------------------------
def cmd_init(a: argparse.Namespace) -> int:
    if os.path.exists(a.chain) and not a.force:
        raise BlockError("exists", f"{a.chain} already exists (use --force to overwrite)")
    chain = Chain(ChainParams(min_bits=a.min_bits, bits=a.bits, initial_subsidy=a.subsidy))
    chain.save(a.chain)
    print(f"created {a.chain}")
    print(f"genesis: {chain.genesis.hash_hex}  (difficulty {a.bits} bits, subsidy {a.subsidy})")
    return 0


def cmd_address(a: argparse.Namespace) -> int:
    print(demo_address(a.name, a.network))
    return 0


def cmd_pay(a: argparse.Namespace) -> int:
    chain = Chain.load(a.chain)
    w = demo_wallet(a.sender, chain.params.network_id)
    tx = w.build_payment(chain.ledger, a.to, a.amount, fee=a.fee)
    text = json.dumps(tx.to_obj(), indent=2, sort_keys=True) + "\n"
    if a.out:
        _write(a.out, text)
        print(f"signed transaction {tx.txid} written to {a.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


def cmd_mine(a: argparse.Namespace) -> int:
    chain = Chain.load(a.chain)
    txs = [SignedTx.from_json(_read(p)) for p in a.tx]
    parent = a.parent if a.parent else None
    ts = a.timestamp
    if ts is None and parent is None:
        ts = max(chain.tip_record.header.timestamp + 1, int(time.time()))
    target = int(a.target, 16) if a.target else None
    res = mine_block(chain, a.address, parent=parent, txs=txs, bits=a.bits, target=target,
                     timestamp=ts, max_attempts=a.max_attempts)
    blk = res.block
    print(f"mined block {blk.hash_hex}")
    print(f"  attempts: {res.attempts}   time: {res.seconds:.3f}s   rate: {res.hashrate:,.0f} H/s")
    print(f"  transactions: {len(blk.txs)} (1 coinbase + {len(blk.txs) - 1})   nonce: {blk.header.nonce}")
    if a.out:
        _write(a.out, blk.to_json() + "\n")
        print(f"  block written to {a.out}")
    _print_add(chain.add_block(blk))
    if not a.no_save:
        chain.save(a.chain)
    return 0


def cmd_submit(a: argparse.Namespace) -> int:
    chain = Chain.load(a.chain)
    res = chain.add_block(Block.from_json(_read(a.block)))
    _print_add(res)
    chain.save(a.chain)
    return 0


def cmd_info(a: argparse.Namespace) -> int:
    chain = Chain.load(a.chain)
    led = chain.ledger
    print(f"network: {chain.params.network_id}")
    print(f"height: {chain.height}")
    print(f"tip: {chain.tip_hex}")
    print(f"cumulative_work: {chain.tip_work}")
    print(f"blocks_known: {len(chain.records())}   branches: {len(chain.tips())}")
    print(f"utxos: {len(led.utxos)}   issued: {led.issued}   unspent: {led.total_unspent()}   burned: {led.fees}")
    print(f"state_sha256: {led.state_hash()}")
    for name in a.names:
        w = demo_wallet(name, chain.params.network_id)
        print(f"balance[{name}]: {w.balance(led)}")
    if a.tree:
        print("\nblock tree (* = active chain):")
        print(chain.render_tree())
    return 0


def cmd_dump(a: argparse.Namespace) -> int:
    if a.hex:
        header = BlockHeader.parse(bytes.fromhex(a.hex))
    else:
        header = Block.from_json(_read(a.block)).header
    print(hexdump_header(header))
    return 0


def cmd_fork_sim(a: argparse.Namespace) -> int:
    out = run_fork_simulation(a.bits)
    if a.out_dir:
        os.makedirs(a.out_dir, exist_ok=True)
        for name, blk in out["blocks"].items():
            _write(os.path.join(a.out_dir, f"{name}.json"), blk.to_json() + "\n")
        out["node_a"].save(os.path.join(a.out_dir, "node_a_chain.json"))
        out["node_b"].save(os.path.join(a.out_dir, "node_b_chain.json"))
        print(f"\nwrote blocks and both chain files to {a.out_dir}")
    return 0 if out["converged"] else 1


def cmd_work_sim(_a: argparse.Namespace) -> int:
    return 0 if run_work_vs_length()["same"] else 1


def cmd_acceptance(_a: argparse.Namespace) -> int:
    return 0 if all(ok for _, ok, _ in run_acceptance()) else 1


def cmd_bench(a: argparse.Namespace) -> int:
    try:
        bits = [int(x) for x in a.bits.split(",")]
    except ValueError:
        raise BlockError("bad_args", "--bits must be comma-separated integers, e.g. 8,12,16") from None
    if any(not 1 <= b <= 28 for b in bits):
        raise BlockError("bad_args", "--bits values must be between 1 and 28")
    hps = hash_rate()
    rows = run_bench(bits, a.trials, log=lambda m: print(m, file=sys.stderr))
    print(f"# {machine_info()}; raw SHA-256d header hashing: {hps:,.0f} hashes/second")
    print(format_table(rows, markdown=a.markdown))
    return 0


def cmd_report(a: argparse.Namespace) -> int:
    text = generate_report(trials=a.trials, log=lambda m: print(m, file=sys.stderr))
    _write(a.out, text)
    print(f"report written to {a.out}")
    return 0


# ---- parser -----------------------------------------------------------------
def _positive(v: str) -> int:
    n = int(v)
    if n < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return n


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="chainlab", description="Blocks, toy Proof of Work, forks and "
                                "reorganisation on top of the Assignment 4 UTXO ledger (educational).")
    p.add_argument("--version", action="version", version=f"chainlab {__version__}")
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    s = sub.add_parser("init", help="create a chain file")
    s.add_argument("chain", metavar="CHAIN")
    s.add_argument("--bits", type=int, default=4, help="difficulty of genesis / default mining (default 4)")
    s.add_argument("--min-bits", type=int, default=1, help="easiest difficulty any block may use (default 1)")
    s.add_argument("--subsidy", type=_positive, default=50)
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("address", help="address of a TEST-ONLY deterministic demo wallet")
    s.add_argument("name")
    s.add_argument("--network", default="course-testnet")
    s.set_defaults(func=cmd_address)

    s = sub.add_parser("pay", help="build a signed payment from a demo wallet")
    s.add_argument("--chain", required=True)
    s.add_argument("--from", dest="sender", required=True, metavar="NAME")
    s.add_argument("--to", required=True, metavar="ADDRESS")
    s.add_argument("--amount", type=_positive, required=True)
    s.add_argument("--fee", type=int, default=0)
    s.add_argument("--out", metavar="FILE")
    s.set_defaults(func=cmd_pay)

    s = sub.add_parser("mine", help="mine a block, add it to the chain, optionally write it to a file")
    s.add_argument("--chain", required=True)
    s.add_argument("--address", required=True, help="coinbase reward address")
    s.add_argument("--tx", action="append", default=[], metavar="FILE", help="signed tx to include (repeatable)")
    s.add_argument("--bits", type=int, help="difficulty in zero bits (default: the chain's)")
    s.add_argument("--target", metavar="HEX", help="explicit 256-bit target in hex (overrides --bits)")
    s.add_argument("--parent", metavar="HASH", help="build on this block instead of the tip (creates a fork)")
    s.add_argument("--timestamp", type=int)
    s.add_argument("--max-attempts", type=_positive)
    s.add_argument("--out", metavar="FILE", help="also write the block JSON here")
    s.add_argument("--no-save", action="store_true", help="do not update the chain file")
    s.set_defaults(func=cmd_mine)

    s = sub.add_parser("submit", help="validate and add a block received from a peer")
    s.add_argument("--chain", required=True)
    s.add_argument("block", metavar="BLOCK_FILE")
    s.set_defaults(func=cmd_submit)

    s = sub.add_parser("info", help="chain summary")
    s.add_argument("--chain", required=True)
    s.add_argument("--tree", action="store_true", help="draw the block tree")
    s.add_argument("--names", nargs="*", default=[], metavar="NAME", help="demo wallets whose balance to show")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("dump-header", help="annotated hex dump of a block header")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("block", nargs="?", metavar="BLOCK_FILE")
    g.add_argument("--hex", metavar="HEX224", help="the raw 112-byte header as hex")
    s.set_defaults(func=cmd_dump)

    s = sub.add_parser("fork-sim", help="two miners race, the network forks, a reorg resolves it")
    s.add_argument("--bits", type=int, default=8)
    s.add_argument("--out-dir", metavar="DIR", help="write the blocks and both chain files here")
    s.set_defaults(func=cmd_fork_sim)

    s = sub.add_parser("work-sim", help="longer low-work branch vs shorter high-work branch")
    s.set_defaults(func=cmd_work_sim)

    s = sub.add_parser("acceptance", help="run all acceptance checks")
    s.set_defaults(func=cmd_acceptance)

    s = sub.add_parser("bench", help="hash rate and expected vs observed attempts")
    s.add_argument("--bits", default=",".join(str(b) for b in DEFAULT_BITS))
    s.add_argument("--trials", type=_positive, default=20)
    s.add_argument("--markdown", action="store_true")
    s.set_defaults(func=cmd_bench)

    s = sub.add_parser("report", help="generate the Markdown report")
    s.add_argument("--out", default="docs/REPORT.md")
    s.add_argument("--trials", type=_positive, default=30)
    s.set_defaults(func=cmd_report)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except BlockError as exc:
        print(f"REJECTED code={exc.code}\nreason: {exc.reason}", file=sys.stderr)
        return 1
    except WalletError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
