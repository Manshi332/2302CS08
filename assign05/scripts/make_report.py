"""Regenerate docs/REPORT.md and PERFORMANCE.md.   Usage: python scripts/make_report.py [--trials 30]"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from chainlab.bench import format_table, hash_rate, machine_info, run_bench  # noqa: E402
from chainlab.report import generate_report  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=30)
    args = ap.parse_args()
    log = lambda m: print(m, file=sys.stderr)  # noqa: E731
    with open(os.path.join(ROOT, "docs", "REPORT.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(generate_report(trials=args.trials, log=log))
    hps = hash_rate()
    rows = run_bench((8, 12, 16, 20), 10, log=log)
    text = ("# Performance\n\n"
            f"Machine: {machine_info()}\n\n"
            f"Raw SHA-256d header hashing: **{hps:,.0f} hashes/second** (best of 3 x 200,000 hashes).\n\n"
            "Expected vs observed attempts (10 trials per row; each row is a fresh set of fixed "
            "pseudo-headers, so attempt counts are reproducible and only the time column varies):\n\n"
            + format_table(rows, markdown=True) + "\n\n"
            "Mining time at difficulty `b` bits is about `2^b / hash_rate`: the toy targets used in "
            "the tests (4 to 10 bits) take microseconds to milliseconds, and 20 bits takes about a "
            "second per block on this machine.\n")
    with open(os.path.join(ROOT, "PERFORMANCE.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("wrote docs/REPORT.md and PERFORMANCE.md")


if __name__ == "__main__":
    main()
