import copy
import os
import tempfile
import unittest
from dataclasses import replace

import helpers
from helpers import ALICE, BOB, CAROL, MINER, grow, new_chain
from chainlab import Block, Chain, ChainParams, make_block, mine_block, solve_block
from chainlab.consensus import ChainParams as CP
from chainlab.errors import BlockError
from chainlab.miner import solve_header
from chainlab.tx import MAX_VALUE, Output, OutPoint, TxBody, sign_body


def reject(test, chain, block, code, inner=None):
    before = (chain.tip, chain.ledger.state_hash(), chain.active_hashes(), len(chain.records()))
    with test.assertRaises(BlockError) as cm:
        chain.add_block(block)
    test.assertEqual(cm.exception.code, code)
    if inner:
        test.assertEqual(cm.exception.inner, inner)
    test.assertEqual(before[:3], (chain.tip, chain.ledger.state_hash(), chain.active_hashes()))
    return cm.exception


class Extend(unittest.TestCase):
    def test_genesis_deterministic(self):
        self.assertEqual(new_chain().genesis.hash, new_chain().genesis.hash)
        self.assertNotEqual(new_chain(4).genesis.hash, new_chain(5).genesis.hash)

    def test_extend_and_balances(self):
        c = new_chain()
        grow(c, 3)
        self.assertEqual((c.height, ALICE.balance(c.ledger)), (3, 150))
        c.ledger.check_invariants()
        self.assertEqual(c.tip_work, 16 * 4)

    def test_duplicate_is_idempotent(self):
        c = new_chain()
        b = grow(c, 1)[0]
        self.assertEqual(c.add_block(b).status, "duplicate")
        self.assertEqual(c.height, 1)

    def test_transaction_fee_goes_to_miner(self):
        c = new_chain()
        grow(c, 2)
        pay = ALICE.build_payment(c.ledger, BOB.primary_address, 30, fee=5)
        c.add_block(mine_block(c, MINER.primary_address, txs=[pay]).block)
        self.assertEqual(MINER.balance(c.ledger), 55)
        self.assertEqual(BOB.balance(c.ledger), 30)
        c.ledger.check_invariants()

    def test_coinbase_may_claim_less_and_burns_the_rest(self):
        c = new_chain()
        c.add_block(solve_block(make_block(c, ALICE.primary_address, coinbase_value=10)).block)
        self.assertEqual(c.ledger.fees, 40)
        c.ledger.check_invariants()

    def test_halving(self):
        c = Chain(ChainParams(bits=2, halving_interval=2), helpers.CLOCK)
        grow(c, 4)
        self.assertEqual([c.block_at(h).txs[0].body.outputs[0].value for h in range(5)], [50, 50, 25, 25, 12])


class Invalid(unittest.TestCase):
    def setUp(self):
        self.c = new_chain()
        grow(self.c, 3)

    def test_bad_merkle(self):
        good = make_block(self.c, MINER.primary_address)
        forged = replace(good.header, merkle_root=b"\x13" * 32)
        reject(self, self.c, Block(solve_header(forged)[0], good.txs), "bad_merkle")

    def test_bad_pow(self):
        b = make_block(self.c, MINER.primary_address)
        h = b.header
        while int.from_bytes(h.hash, "big") <= h.target:
            h = h.with_nonce(h.nonce + 1)
        reject(self, self.c, Block(h, b.txs), "bad_pow")

    def test_target_easier_than_limit(self):
        c = Chain(ChainParams(min_bits=4, bits=4), helpers.CLOCK)
        b = solve_block(make_block(c, ALICE.primary_address, bits=2)).block
        reject(self, c, b, "bad_target")

    def test_excess_coinbase(self):
        reject(self, self.c, solve_block(make_block(self.c, MINER.primary_address, coinbase_value=51)).block,
               "coinbase_excess")

    def test_excess_coinbase_with_fees(self):
        pay = ALICE.build_payment(self.c.ledger, BOB.primary_address, 20, fee=2)
        b = solve_block(make_block(self.c, MINER.primary_address, txs=[pay], coinbase_value=53)).block
        reject(self, self.c, b, "coinbase_excess")
        ok = solve_block(make_block(self.c, MINER.primary_address, txs=[pay], coinbase_value=52)).block
        self.assertEqual(self.c.add_block(ok).status, "extended")

    def test_invalid_transaction_codes(self):
        coin = self.c.ledger.outputs_for(ALICE.pkhs[0])[0][0]
        net = self.c.params.network_id
        key = ALICE._keys[ALICE.pkhs[0]]
        cases = {
            "outputs_exceed_inputs": sign_body(TxBody(net, (coin,), (Output(51, BOB.pkhs[0]),), "x"), [key]),
            "input_not_found": sign_body(TxBody(net, (OutPoint("ab" * 32, 0),), (Output(1, BOB.pkhs[0]),), "x"), [key]),
            "pubkey_hash_mismatch": sign_body(TxBody(net, (coin,), (Output(1, BOB.pkhs[0]),), "x"),
                                              [BOB._keys[BOB.pkhs[0]]]),
        }
        for inner, tx in cases.items():
            b = solve_block(make_block(self.c, MINER.primary_address, txs=[tx], check_txs=False)).block
            reject(self, self.c, b, "invalid_tx", inner)

    def test_double_spend_in_block(self):
        a = ALICE.build_payment(self.c.ledger, BOB.primary_address, 20, fee=1)
        b = ALICE.build_payment(self.c.ledger, CAROL.primary_address, 20, fee=1)
        blk = solve_block(make_block(self.c, MINER.primary_address, txs=[a, b], check_txs=False)).block
        reject(self, self.c, blk, "invalid_tx", "input_already_spent")

    def test_valid_then_invalid_tx_is_atomic(self):
        good = ALICE.build_payment(self.c.ledger, BOB.primary_address, 20, fee=1)
        coin = self.c.ledger.outputs_for(ALICE.pkhs[0])[-1][0]
        bad = sign_body(TxBody(self.c.params.network_id, (coin,), (Output(MAX_VALUE, BOB.pkhs[0]),), "x"),
                        [ALICE._keys[ALICE.pkhs[0]]])
        blk = solve_block(make_block(self.c, MINER.primary_address, txs=[good, bad], check_txs=False)).block
        reject(self, self.c, blk, "invalid_tx")
        self.assertEqual(BOB.balance(self.c.ledger), 0)
        self.c.ledger.check_invariants()

    def test_structure_rules(self):
        b = make_block(self.c, MINER.primary_address)
        cb = b.txs[0]
        two = Block(replace(b.header, merkle_root=Block(b.header, (cb, cb)).computed_merkle_root()), (cb, cb))
        reject(self, self.c, solve_block(two).block, "multiple_coinbase")
        pay = ALICE.build_payment(self.c.ledger, BOB.primary_address, 20, fee=1)
        nocb = Block(replace(b.header, merkle_root=Block(b.header, (pay,)).computed_merkle_root()), (pay,))
        reject(self, self.c, solve_block(nocb).block, "missing_coinbase")
        empty = Block(replace(b.header, merkle_root=Block(b.header, ()).computed_merkle_root()), ())
        reject(self, self.c, solve_block(empty).block, "no_transactions")
        wrong_h = make_block(self.c, MINER.primary_address)
        other = make_block(self.c, MINER.primary_address, parent=self.c.block_at(1).hash)   # coinbase for height 2
        mixed = Block(replace(wrong_h.header, merkle_root=Block(wrong_h.header, other.txs).computed_merkle_root()), other.txs)
        reject(self, self.c, solve_block(mixed).block, "bad_coinbase")

    def test_unknown_parent_and_timestamps(self):
        b = make_block(self.c, MINER.primary_address)
        reject(self, self.c, Block(solve_header(replace(b.header, prev_hash=b"\x77" * 32))[0], b.txs), "unknown_parent")
        old = make_block(self.c, MINER.primary_address, timestamp=self.c.tip_record.header.timestamp - 5000)
        reject(self, self.c, solve_block(old).block, "timestamp_too_old")
        eq = make_block(self.c, MINER.primary_address, timestamp=self.c.block_at(2).header.timestamp)
        reject(self, self.c, solve_block(eq).block, "timestamp_too_old")
        fut = make_block(self.c, MINER.primary_address, timestamp=helpers.CLOCK() + 7201)
        reject(self, self.c, solve_block(fut).block, "timestamp_too_far_future")

    def test_rejected_block_is_remembered(self):
        blk = solve_block(make_block(self.c, MINER.primary_address, coinbase_value=99)).block
        reject(self, self.c, blk, "coinbase_excess")
        reject(self, self.c, blk, "known_invalid")
        child_hdr = replace(make_block(self.c, MINER.primary_address).header, prev_hash=blk.hash)
        reject(self, self.c, Block(solve_header(child_hdr)[0], make_block(self.c, MINER.primary_address).txs), "invalid_ancestor")


class ForkChoice(unittest.TestCase):
    def test_equal_work_first_seen_wins(self):
        c = new_chain()
        grow(c, 2)
        base = c.tip
        first = mine_block(c, ALICE.primary_address).block
        second = mine_block(c, BOB.primary_address, parent=base).block
        self.assertEqual(c.add_block(first).status, "extended")
        self.assertEqual(c.add_block(second).status, "side_branch")
        self.assertEqual(c.tip, first.hash)
        self.assertEqual(len(c.tips()), 2)

    def test_longer_but_lower_work_loses(self):
        params = ChainParams(bits=4)
        hi, lo = Chain(params, helpers.CLOCK), Chain(params, helpers.CLOCK)
        hi_blocks, lo_blocks = grow(hi, 2, bits=10), grow(lo, 5, bits=4)
        node = Chain(params, helpers.CLOCK)
        for b in hi_blocks:
            node.add_block(b)
        for b in lo_blocks:
            self.assertEqual(node.add_block(b).status, "side_branch")
        self.assertEqual((node.height, node.tip), (2, hi.tip))
        self.assertLess(5 * 16, 2 * 1024)

    def test_shorter_higher_work_takes_over_from_longer(self):
        params = ChainParams(bits=4)
        hi, lo = Chain(params, helpers.CLOCK), Chain(params, helpers.CLOCK)
        hi_blocks, lo_blocks = grow(hi, 1, bits=9), grow(lo, 5, bits=4)
        node = Chain(params, helpers.CLOCK)
        for b in lo_blocks:
            node.add_block(b)
        self.assertEqual(node.height, 5)
        res = node.add_block(hi_blocks[0])
        self.assertEqual((res.status, len(res.disconnected), len(res.connected)), ("reorganized", 5, 1))
        self.assertEqual((node.height, node.tip), (1, hi.tip))
        self.assertEqual(node.ledger.state_hash(), hi.ledger.state_hash())

    def test_nonuniform_targets_sum_work(self):
        c = new_chain()
        grow(c, 1, bits=6)
        grow(c, 1, bits=8)
        self.assertEqual(c.tip_work, 16 + 64 + 256)


class Reorg(unittest.TestCase):
    def setUp(self):
        self.base = new_chain()
        grow(self.base, 2)

    def test_reorg_restores_outputs_and_returns_transactions(self):
        node = copy.deepcopy(self.base)
        pay = ALICE.build_payment(node.ledger, BOB.primary_address, 30, fee=1)
        node.add_block(mine_block(node, MINER.primary_address, txs=[pay]).block)
        self.assertEqual(BOB.balance(node.ledger), 30)
        rival = copy.deepcopy(self.base)
        r1, r2 = grow(rival, 2, wallet=CAROL)
        self.assertEqual(node.add_block(r1).status, "side_branch")
        res = node.add_block(r2)
        self.assertEqual(res.status, "reorganized")
        self.assertEqual([t.txid for t in res.returned_txs], [pay.txid])
        self.assertEqual((BOB.balance(node.ledger), ALICE.balance(node.ledger), CAROL.balance(node.ledger)), (0, 100, 100))
        self.assertEqual(node.ledger.state_hash(), rival.ledger.state_hash())
        node.ledger.check_invariants()

    def test_transaction_in_both_branches_is_not_returned(self):
        node = copy.deepcopy(self.base)
        pay = ALICE.build_payment(node.ledger, BOB.primary_address, 30, fee=1)
        node.add_block(mine_block(node, MINER.primary_address, txs=[pay]).block)
        rival = copy.deepcopy(self.base)
        r1 = mine_block(rival, CAROL.primary_address, txs=[pay]).block
        rival.add_block(r1)
        r2 = grow(rival, 1)[0]
        node.add_block(r1)
        res = node.add_block(r2)
        self.assertEqual((res.status, res.returned_txs), ("reorganized", ()))
        self.assertEqual(BOB.balance(node.ledger), 30)

    def test_conflicting_spends_resolved_by_work(self):
        node = copy.deepcopy(self.base)
        p1 = ALICE.build_payment(node.ledger, BOB.primary_address, 30, fee=1)
        p2 = ALICE.build_payment(node.ledger, CAROL.primary_address, 45, fee=3)   # same coin as p1
        node.add_block(mine_block(node, MINER.primary_address, txs=[p1]).block)
        rival = copy.deepcopy(self.base)
        r1 = mine_block(rival, MINER.primary_address, txs=[p2]).block
        rival.add_block(r1)
        r2 = grow(rival, 1)[0]
        node.add_block(r1)
        node.add_block(r2)
        self.assertEqual((BOB.balance(node.ledger), CAROL.balance(node.ledger)), (0, 45))

    def test_failed_reorg_rolls_back_completely(self):
        node = copy.deepcopy(self.base)
        grow(node, 2, wallet=MINER)
        before = (node.tip, node.ledger.state_hash(), node.ledger.utxo_digest(), node.active_hashes())
        rival = copy.deepcopy(self.base)
        x1, x2 = grow(rival, 2, wallet=CAROL)
        coin = rival.ledger.outputs_for(ALICE.pkhs[0])[0][0]
        over = sign_body(TxBody(rival.params.network_id, (coin,), (Output(MAX_VALUE, BOB.pkhs[0]),), "x"),
                         [ALICE._keys[ALICE.pkhs[0]]])
        x3 = solve_block(make_block(rival, CAROL.primary_address, txs=[over], check_txs=False)).block
        node.add_block(x1)
        node.add_block(x2)
        with self.assertRaises(BlockError) as cm:
            node.add_block(x3)                       # 3 blocks of work > 2 -> reorg attempt -> x3 fails
        self.assertEqual((cm.exception.code, cm.exception.inner), ("invalid_tx", "outputs_exceed_inputs"))
        self.assertEqual(before, (node.tip, node.ledger.state_hash(), node.ledger.utxo_digest(), node.active_hashes()))
        node.ledger.check_invariants()
        reject(self, node, x3, "known_invalid")
        self.assertEqual(node.add_block(x1).status, "duplicate")     # valid part of the branch is still known

    def test_deep_reorg_matches_fresh_replay(self):
        node = copy.deepcopy(self.base)
        for _ in range(4):
            pay = ALICE.build_payment(node.ledger, BOB.primary_address, 10, fee=1)
            node.add_block(mine_block(node, MINER.primary_address, txs=[pay]).block)
        rival = copy.deepcopy(self.base)
        branch = []
        for i in range(5):
            tx = [ALICE.build_payment(rival.ledger, CAROL.primary_address, 7 + i, fee=2)] if i % 2 == 0 else []
            b = mine_block(rival, CAROL.primary_address, txs=tx).block
            rival.add_block(b)
            branch.append(b)
        for b in branch[:-1]:
            self.assertEqual(node.add_block(b).status, "side_branch")
        res = node.add_block(branch[-1])
        self.assertEqual((res.status, len(res.disconnected), len(res.connected)), ("reorganized", 4, 5))
        fresh = Chain(node.params, helpers.CLOCK)
        for h in rival.active_hashes()[1:]:
            fresh.add_block(rival.record(h).block)
        self.assertEqual(node.ledger.state_hash(), fresh.ledger.state_hash())
        self.assertEqual(node.ledger.utxo_digest(), fresh.ledger.utxo_digest())

    def test_state_at_any_block(self):
        node = copy.deepcopy(self.base)
        pay = ALICE.build_payment(node.ledger, BOB.primary_address, 30, fee=1)
        side = mine_block(node, MINER.primary_address, txs=[pay]).block
        node.add_block(side)
        rival_first = mine_block(node, CAROL.primary_address, parent=self.base.tip).block
        node.add_block(rival_first)
        st = node.state_at(rival_first.hash)
        self.assertEqual((BOB.balance(st), CAROL.balance(st)), (0, 50))
        self.assertEqual(BOB.balance(node.ledger), 30)             # active state not disturbed
        self.assertEqual(node.state_at(node.tip).state_hash(), node.ledger.state_hash())


class Persistence(unittest.TestCase):
    def test_save_load_replays_everything(self):
        node = new_chain()
        grow(node, 2)
        pay = ALICE.build_payment(node.ledger, BOB.primary_address, 30, fee=1)
        node.add_block(mine_block(node, MINER.primary_address, txs=[pay]).block)
        side = mine_block(node, CAROL.primary_address, parent=node.block_at(2).hash).block
        node.add_block(side)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "chain.json")
            node.save(path)
            again = Chain.load(path, helpers.CLOCK)
        self.assertEqual((again.tip, again.active_hashes()), (node.tip, node.active_hashes()))
        self.assertEqual(again.ledger.state_hash(), node.ledger.state_hash())
        self.assertEqual(len(again.records()), len(node.records()))

    def test_tampered_chain_file_is_rejected(self):
        node = new_chain()
        grow(node, 2)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "chain.json")
            node.save(path)
            import json
            with open(path) as fh:
                doc = json.load(fh)
            doc["blocks"][0]["header"]["merkle_root"] = "00" * 32      # forge a header field
            with open(path, "w") as fh:
                json.dump(doc, fh)
            with self.assertRaises(BlockError) as cm:
                Chain.load(path, helpers.CLOCK)
            self.assertEqual(cm.exception.code, "bad_merkle")
            with self.assertRaises(BlockError):
                Chain.load(os.path.join(d, "missing.json"))


class Render(unittest.TestCase):
    def test_tree_marks_active_branch(self):
        node = new_chain()
        grow(node, 2)
        node.add_block(mine_block(node, BOB.primary_address, parent=node.block_at(1).hash).block)
        tree = node.render_tree()
        self.assertEqual(tree.count("<- TIP"), 1)
        self.assertEqual(sum(1 for ln in tree.splitlines() if "* h=" in ln), 3)
        self.assertEqual(len(tree.splitlines()), 4)
        self.assertIn("graph LR", node.render_mermaid())


if __name__ == "__main__":
    unittest.main()
