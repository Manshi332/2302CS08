"""Command-line interface for hashlab."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from . import __version__
from .canonical import canonicalize
from .core import (
    NORMAL_FORMS,
    HashlabError,
    HashResult,
    bit_mask,
    check_bit_in_range,
    flip_bit,
    hamming_distance,
    hash_bytes,
    hash_file,
    parse_hex,
    text_to_bytes,
)
from .demo import run_demo

MAX_SWEEP_BYTES = 64 * 1024


def _print_result(res: HashResult) -> None:
    print(f"bytes: {res.length}")
    print(f"sha256: {res.hex}")
    print(f"sha256_base64: {res.base64}")


def _read_all(path: str) -> bytes:
    try:
        if path == "-":
            return sys.stdin.buffer.read()
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        raise HashlabError(f"cannot read {path!r}: {exc.strerror or exc}") from exc


# ---- command handlers ------------------------------------------------------
def cmd_text(args: argparse.Namespace) -> int:
    _print_result(hash_bytes(text_to_bytes(args.value, args.normalize, args.escapes)))
    return 0


def cmd_hex(args: argparse.Namespace) -> int:
    _print_result(hash_bytes(parse_hex(args.value)))
    return 0


def cmd_file(args: argparse.Namespace) -> int:
    _print_result(hash_file(args.path, chunk_size=args.chunk_size))
    return 0


def cmd_canonical(args: argparse.Namespace) -> int:
    canon = canonicalize(_read_all(args.path))
    if not args.no_print:
        print(f"canonical: {canon.decode('utf-8')}")
    _print_result(hash_bytes(canon))
    return 0


def cmd_demo(_args: argparse.Namespace) -> int:
    run_demo(sys.stdout)
    return 0


def cmd_avalanche(args: argparse.Namespace) -> int:
    if args.sweep and args.file is not None:
        raise HashlabError("--sweep works on --text/--hex only (it re-hashes the input 8*N times)")
    if not args.sweep and args.bit is None:
        raise HashlabError("--bit is required (or use --sweep)")

    if args.file is not None:
        original = hash_file(args.file)
        check_bit_in_range(args.bit, original.length)
        flipped = hash_file(args.file, flip=args.bit)
        data = None
    else:
        data = (text_to_bytes(args.text, args.normalize, args.escapes)
                if args.text is not None else parse_hex(args.hex))
        original = hash_bytes(data)

    if args.sweep:
        return _sweep(data, original)

    if data is not None:
        check_bit_in_range(args.bit, len(data))
        flipped = hash_bytes(flip_bit(data, args.bit))

    dist = hamming_distance(original.digest, flipped.digest)
    print(f"input_bytes: {original.length}")
    print(f"bit_flipped: {args.bit} (byte {args.bit >> 3}, mask 0x{bit_mask(args.bit):02x})")
    print(f"original_sha256: {original.hex}")
    print(f"flipped_sha256:  {flipped.hex}")
    print(f"changed_bits_in_digest: {dist}")
    print(f"changed_fraction: {dist / 256:.3f} (ideal avalanche is about 0.5)")
    return 0


def _sweep(data: bytes, original: HashResult) -> int:
    if len(data) == 0:
        raise HashlabError("cannot flip a bit of empty input")
    if len(data) > MAX_SWEEP_BYTES:
        raise HashlabError(f"--sweep limited to {MAX_SWEEP_BYTES} bytes")
    dists = [
        hamming_distance(original.digest, hash_bytes(flip_bit(data, b)).digest)
        for b in range(len(data) * 8)
    ]
    print(f"input_bytes: {len(data)}")
    print(f"bits_tested: {len(dists)}")
    print(f"changed_bits_min: {min(dists)}")
    print(f"changed_bits_max: {max(dists)}")
    print(f"changed_bits_mean: {sum(dists) / len(dists):.2f} (ideal 128.00)")
    return 0


# ---- parser ---------------------------------------------------------------
def _chunk_size(value: str) -> int:
    n = int(value)
    if n <= 0:
        raise argparse.ArgumentTypeError("chunk size must be positive")
    return n


def _add_text_opts(p: argparse.ArgumentParser) -> None:
    p.add_argument("--normalize", choices=NORMAL_FORMS,
                   help="apply Unicode normalization before UTF-8 encoding (default: none)")
    p.add_argument("--escapes", action="store_true",
                   help=r"interpret \n \r \t \\ in the text (handy for testing newlines)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hashlab",
        description="SHA-256 byte diagnostics for blockchain engineering (uses hashlib; "
                    "SHA-256 is not re-implemented).",
    )
    parser.add_argument("--version", action="version", version=f"hashlab {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p = sub.add_parser("text", help="hash UTF-8 text")
    p.add_argument("value", help="text to hash")
    _add_text_opts(p)
    p.set_defaults(func=cmd_text)

    p = sub.add_parser("hex", help="hash a hexadecimal byte string (optional 0x prefix)")
    p.add_argument("value", help="hex digits, even length, no spaces")
    p.set_defaults(func=cmd_hex)

    p = sub.add_parser("file", help="hash a file as a stream ('-' = stdin)")
    p.add_argument("path")
    p.add_argument("--chunk-size", type=_chunk_size, default=1024 * 1024, metavar="BYTES",
                   help="read buffer size (default 1048576)")
    p.set_defaults(func=cmd_file)

    p = sub.add_parser("avalanche", help="flip one input bit; report digest Hamming distance")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--text")
    src.add_argument("--hex")
    src.add_argument("--file")
    p.add_argument("--bit", type=int, help="bit index; 0 = most significant bit of byte 0")
    p.add_argument("--sweep", action="store_true",
                   help="flip every bit in turn; print min/max/mean distance")
    _add_text_opts(p)
    p.set_defaults(func=cmd_avalanche)

    p = sub.add_parser("canonical-json", help="canonicalize a JSON object, then hash it")
    p.add_argument("path", nargs="?", default="-", help="JSON file (default: stdin)")
    p.add_argument("--no-print", action="store_true", help="do not print the canonical text")
    p.set_defaults(func=cmd_canonical)

    p = sub.add_parser("demo", help="show look-alike inputs with different bytes")
    p.set_defaults(func=cmd_demo)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except HashlabError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
