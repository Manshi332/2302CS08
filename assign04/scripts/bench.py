"""Measure validation/apply throughput and snapshot save/load time.

    python scripts/bench.py [--utxos 1000,10000,100000] [--txs 2000]
"""
import argparse
import hashlib
import os
import platform
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from utxolab import Ledger, Wallet            # noqa: E402
from utxolab.tx import Output                 # noqa: E402


def wallet(name):
    return Wallet.from_seeds([hashlib.sha256(name.encode()).digest()])


def bench_apply(n):
    a, b = wallet("a"), wallet("b")
    led = Ledger()
    for i in range(n):
        led.issue([Output(1000, a.pkhs[0])], f"g{i}")
    # pre-build n independent transactions (each spends a different coin), then time apply() only
    from utxolab.tx import TxBody, sign_body
    txs = []
    key = a._keys[a.pkhs[0]]
    for (op, out) in a.spendable(led)[:n]:
        body = TxBody(led.network_id, (op,), (Output(990, b.pkhs[0]),), "")
        txs.append(sign_body(body, [key]))
    t0 = time.perf_counter()
    for tx in txs:
        led.apply(tx)
    dt = time.perf_counter() - t0
    return len(txs) / dt, dt / len(txs) * 1e6


def bench_snapshot(n):
    a = wallet("a")
    led = Ledger()
    for i in range(n):
        led.issue([Output(5, a.pkhs[0])], f"g{i}")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "s.json")
        t0 = time.perf_counter(); led.save(p); t_save = time.perf_counter() - t0
        size = os.path.getsize(p)
        t0 = time.perf_counter(); back = Ledger.load(p); t_load = time.perf_counter() - t0
        assert back.state_hash() == led.state_hash()
    return t_save, t_load, size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--utxos", default="1000,10000,50000")
    ap.add_argument("--txs", type=int, default=2000)
    args = ap.parse_args()
    print(f"# Python {platform.python_version()} on {platform.system()} {platform.machine()}")
    rate, us = bench_apply(args.txs)
    print(f"apply (1 input, 1 output, Ed25519 verify): {rate:,.0f} tx/s  ({us:,.0f} us/tx)  [{args.txs} txs]")
    print("\n| UTXOs | save (ms) | load+verify (ms) | file size (KB) |\n|---:|---:|---:|---:|")
    for n in (int(x) for x in args.utxos.split(",")):
        s, l, size = bench_snapshot(n)
        print(f"| {n:,} | {s * 1e3:,.0f} | {l * 1e3:,.0f} | {size / 1024:,.0f} |")


if __name__ == "__main__":
    main()
