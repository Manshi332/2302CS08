import contextlib
import io
import json
import math
import os
import tempfile
import unittest

import helpers  # noqa: F401
from chainlab.acceptance import run_acceptance
from chainlab.bench import bench_bits, hash_rate
from chainlab.cli import main
from chainlab.simulate import run_fork_simulation, run_work_vs_length
from chainlab.testkeys import demo_address


class Simulations(unittest.TestCase):
    def test_fork_simulation_converges(self):
        out = run_fork_simulation(6, emit=lambda _m: None)
        self.assertTrue(out["converged"])
        self.assertEqual(out["reorg"].status, "reorganized")
        self.assertEqual(len(out["reorg"].returned_txs), 1)

    def test_fork_simulation_is_deterministic(self):
        a = run_fork_simulation(6, emit=lambda _m: None)
        b = run_fork_simulation(6, emit=lambda _m: None)
        self.assertEqual(a["node_a"].tip, b["node_a"].tip)
        self.assertEqual(a["node_a"].ledger.state_hash(), b["node_a"].ledger.state_hash())

    def test_work_vs_length(self):
        out = run_work_vs_length(emit=lambda _m: None)
        self.assertTrue(out["same"])
        self.assertEqual(out["low_statuses"], ["side_branch"] * 5)

    def test_all_acceptance_checks_pass(self):
        results = run_acceptance(emit=lambda _m: None)
        failed = [n for n, ok, _ in results if not ok]
        self.assertEqual(failed, [])
        self.assertGreaterEqual(len(results), 20)


class Bench(unittest.TestCase):
    def test_observed_attempts_match_expectation(self):
        row = bench_bits(8, trials=60)
        self.assertEqual(row.expected, 256)
        self.assertLess(abs(row.z), 4.0)                # >4 standard errors would mean a broken PoW check
        self.assertGreater(row.mean, 100)
        self.assertLess(row.mean, 600)

    def test_attempt_counts_reproducible(self):
        self.assertEqual(bench_bits(6, 10).mean, bench_bits(6, 10).mean)

    def test_hash_rate_positive(self):
        self.assertGreater(hash_rate(count=20_000, repeat=1), 1000)

    def test_harder_target_needs_more_attempts(self):
        self.assertGreater(bench_bits(10, 20).mean, bench_bits(6, 20).mean)


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class Cli(unittest.TestCase):
    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            p = lambda n: os.path.join(d, n)  # noqa: E731
            alice, bob, carol = (demo_address(n) for n in ("alice", "bob", "carol"))
            self.assertEqual(run_cli("init", p("c.json"), "--bits", "4")[0], 0)
            self.assertEqual(run_cli("init", p("c.json"))[0], 1)                       # refuses to overwrite
            for _ in range(2):
                code, out, _ = run_cli("mine", "--chain", p("c.json"), "--address", alice)
                self.assertEqual(code, 0)
                self.assertIn("EXTENDED", out)
            code, _, _ = run_cli("pay", "--chain", p("c.json"), "--from", "alice", "--to", bob,
                                 "--amount", "30", "--fee", "1", "--out", p("tx.json"))
            self.assertEqual(code, 0)
            code, out, _ = run_cli("mine", "--chain", p("c.json"), "--address", carol,
                                   "--tx", p("tx.json"), "--out", p("b3.json"))
            self.assertEqual((code, "1 coinbase + 1" in out), (0, True))
            code, out, _ = run_cli("info", "--chain", p("c.json"), "--names", "alice", "bob", "carol", "--tree")
            self.assertIn("height: 3", out)
            self.assertIn("balance[bob]: 30", out)
            self.assertIn("balance[carol]: 51", out)
            self.assertIn("<- TIP", out)
            # a competing branch built on block 2 (a fork), then extended so it has more work
            from chainlab import Chain
            parent = Chain.load(p("c.json")).block_at(2).hash.hex()
            code, out, _ = run_cli("mine", "--chain", p("c.json"), "--address", bob, "--parent", parent)
            self.assertEqual(code, 0)
            self.assertIn("SIDE_BRANCH", out)
            rival_hash = out.split("mined block ")[1].split()[0]
            code, out, _ = run_cli("mine", "--chain", p("c.json"), "--address", bob, "--parent", rival_hash)
            self.assertEqual(code, 0)
            self.assertIn("REORGANIZED", out)
            self.assertIn("transactions returned to the mempool: 1", out)
            code, out, _ = run_cli("info", "--chain", p("c.json"), "--names", "bob")
            self.assertIn("height: 4", out)
            self.assertIn("balance[bob]: 100", out)         # payment orphaned; bob mined two blocks

    def test_submit_and_errors(self):
        with tempfile.TemporaryDirectory() as d:
            p = lambda n: os.path.join(d, n)  # noqa: E731
            alice = demo_address("alice")
            run_cli("init", p("a.json"))
            run_cli("init", p("b.json"))
            code, _, _ = run_cli("mine", "--chain", p("a.json"), "--address", alice, "--out", p("blk.json"))
            self.assertEqual(code, 0)
            code, out, _ = run_cli("submit", "--chain", p("b.json"), p("blk.json"))
            self.assertEqual((code, "EXTENDED" in out), (0, True))
            code, out, _ = run_cli("submit", "--chain", p("b.json"), p("blk.json"))
            self.assertIn("DUPLICATE", out)
            with open(p("blk.json")) as fh:
                bad = json.load(fh)
            bad["header"]["merkle_root"] = "00" * 32
            with open(p("bad.json"), "w") as fh:
                json.dump(bad, fh)
            code, _, err = run_cli("submit", "--chain", p("b.json"), p("bad.json"))
            self.assertEqual(code, 1)
            self.assertIn("REJECTED", err)
            code, _, err = run_cli("submit", "--chain", p("b.json"), p("nope.json"))
            self.assertEqual(code, 1)

    def test_dump_header_and_sims(self):
        with tempfile.TemporaryDirectory() as d:
            p = lambda n: os.path.join(d, n)  # noqa: E731
            run_cli("init", p("a.json"))
            run_cli("mine", "--chain", p("a.json"), "--address", demo_address("alice"), "--out", p("b.json"))
            code, out, _ = run_cli("dump-header", p("b.json"))
            self.assertEqual(code, 0)
            self.assertIn("hash <= target: True", out)
            code, out, _ = run_cli("fork-sim", "--bits", "6", "--out-dir", p("sim"))
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(p("sim/node_a_chain.json")))
            self.assertEqual(run_cli("work-sim")[0], 0)
            code, out, _ = run_cli("bench", "--bits", "6,8", "--trials", "5")
            self.assertEqual(code, 0)
            self.assertIn("hashes/second", out)
            self.assertEqual(run_cli("bench", "--bits", "x")[0], 1)


if __name__ == "__main__":
    unittest.main()
