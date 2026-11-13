"""Command-line interface: merkle root | prove | verify | bench."""

from __future__ import annotations

import argparse
import re
import sys
from typing import Sequence

from . import __version__
from .bench import DEFAULT_SIZES, format_table, machine_info, run_bench
from .hashing import MerkleError
from .leafio import read_bytes, read_leaves
from .proof import Proof, ProofError, ProofFormatError, compute_root, verify
from .tree import MerkleTree

_HASH_RE = re.compile(r"[0-9a-fA-F]{64}")


def _parse_hash(value: str, what: str) -> bytes:
    if not _HASH_RE.fullmatch(value):
        raise MerkleError(f"malformed {what}: need exactly 64 hex characters")
    return bytes.fromhex(value)


def _parse_hex_bytes(value: str) -> bytes:
    if len(value) % 2 or not re.fullmatch(r"[0-9a-fA-F]*", value):
        raise MerkleError("malformed hex leaf: need an even number of 0-9a-fA-F digits")
    return bytes.fromhex(value)


# ---- commands -------------------------------------------------------------
def cmd_root(args: argparse.Namespace) -> int:
    tree = MerkleTree(read_leaves(args.leaves, args.encoding))
    print(f"leaves: {tree.size}")
    print(f"root: {tree.root.hex()}")
    return 0


def cmd_prove(args: argparse.Namespace) -> int:
    tree = MerkleTree(read_leaves(args.leaves, args.encoding))
    proof = tree.prove(args.index)
    text = proof.to_json()
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text + "\n")
        except OSError as exc:
            raise MerkleError(f"cannot write {args.out!r}: {exc.strerror or exc}") from exc
        print(f"proof written to {args.out} (root {tree.root.hex()})", file=sys.stderr)
    else:
        print(text)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    try:
        root = _parse_hash(args.root, "root")
        if args.leaf is not None:
            leaf = args.leaf.encode("utf-8")
        elif args.leaf_hex is not None:
            leaf = _parse_hex_bytes(args.leaf_hex)
        else:
            leaf = read_bytes(args.leaf_file)
        proof = Proof.from_json(read_bytes(args.proof))
        ok = verify(leaf, proof, root, tree_size=args.tree_size)
    except (ProofFormatError, ProofError) as exc:
        print(f"INVALID: {exc}")
        return 1
    if ok:
        print(f"VALID: leaf at index {proof.leaf_index} is included in a tree of "
              f"{proof.tree_size} leaves with root {root.hex()}")
        return 0
    print("INVALID: proof is well-formed but does not match the expected root")
    print(f"  computed root: {compute_root(leaf, proof).hex()}")
    print(f"  expected root: {root.hex()}")
    return 1


def cmd_bench(args: argparse.Namespace) -> int:
    try:
        sizes = [int(s.replace("_", "")) for s in args.sizes.split(",")]
    except ValueError:
        raise MerkleError("--sizes must be comma-separated integers, e.g. 8,1024,100000") from None
    if any(n < 1 for n in sizes):
        raise MerkleError("--sizes must all be >= 1")
    rows = run_bench(sizes, args.repeat, log=lambda m: print(m, file=sys.stderr))
    print(f"# {machine_info()}; best of {args.repeat}")
    print(format_table(rows, markdown=args.markdown))
    return 0


# ---- parser ---------------------------------------------------------------
def _nonneg(value: str) -> int:
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return n


def _positive(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return n


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="merkle",
        description="Merkle tree root, inclusion proofs, and verification "
                    "(SHA-256, domain separated: Hleaf = H(0x00||data), Hnode = H(0x01||l||r)).",
    )
    parser.add_argument("--version", action="version", version=f"merkle {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def add_leaves(p: argparse.ArgumentParser) -> None:
        p.add_argument("--leaves", required=True, metavar="FILE",
                       help="file with one leaf per line ('-' = stdin)")
        p.add_argument("--encoding", choices=("text", "hex"), default="text",
                       help="how each line is turned into leaf bytes (default: text = raw line bytes)")

    p = sub.add_parser("root", help="print the Merkle root of the leaves")
    add_leaves(p)
    p.set_defaults(func=cmd_root)

    p = sub.add_parser("prove", help="print the inclusion proof (JSON) for one leaf")
    add_leaves(p)
    p.add_argument("--index", type=_nonneg, required=True, help="0-based leaf index")
    p.add_argument("--out", metavar="FILE", help="write the proof to FILE instead of stdout")
    p.set_defaults(func=cmd_prove)

    p = sub.add_parser("verify", help="verify a proof from leaf + proof + expected root only")
    p.add_argument("--root", required=True, metavar="HEX64", help="expected Merkle root")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--leaf", metavar="TEXT", help="leaf as UTF-8 text")
    src.add_argument("--leaf-hex", metavar="HEX", help="leaf as hex bytes")
    src.add_argument("--leaf-file", metavar="FILE", help="leaf = exact bytes of FILE")
    p.add_argument("--proof", required=True, metavar="FILE", help="proof JSON file ('-' = stdin)")
    p.add_argument("--tree-size", type=_positive, metavar="N",
                   help="also require the proof to claim this tree size (trusted with the root)")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("bench", help="measure construction time and proof size")
    p.add_argument("--sizes", default=",".join(str(s) for s in DEFAULT_SIZES),
                   help="comma-separated leaf counts (default: 8,1024,100000)")
    p.add_argument("--repeat", type=_positive, default=3, help="repetitions; best time is reported")
    p.add_argument("--markdown", action="store_true", help="print a Markdown table")
    p.set_defaults(func=cmd_bench)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except MerkleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
