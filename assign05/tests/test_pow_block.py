import json
import os
import unittest

import helpers  # noqa: F401
from chainlab.block import Block, BlockHeader, HEADER_SIZE, hexdump_header
from chainlab.errors import BlockError
from chainlab.merkle import EMPTY_ROOT, leaf_hash, merkle_root, node_hash
from chainlab.miner import solve_header
from chainlab.proofofwork import (bits_from_target, meets_target, search_nonce, sha256d,
                                  target_from_bits, work_from_target)

HERE = os.path.dirname(os.path.abspath(__file__))


class TargetsAndWork(unittest.TestCase):
    def test_target_from_bits(self):
        self.assertEqual(target_from_bits(0), 2**256 - 1)
        self.assertEqual(target_from_bits(8), 2**248 - 1)
        with self.assertRaises(BlockError):
            target_from_bits(256)
        with self.assertRaises(BlockError):
            target_from_bits(-1)

    def test_work_is_expected_attempts(self):
        for b in (1, 4, 10, 20):
            self.assertEqual(work_from_target(target_from_bits(b)), 2**b)
        self.assertAlmostEqual(bits_from_target(target_from_bits(12)), 12.0)

    def test_harder_target_more_work(self):
        self.assertGreater(work_from_target(target_from_bits(9)), work_from_target(target_from_bits(8)))

    def test_meets_target_is_integer_comparison(self):
        t = 1000
        self.assertTrue(meets_target((1000).to_bytes(32, "big"), t))
        self.assertFalse(meets_target((1001).to_bytes(32, "big"), t))

    def test_search_nonce_finds_valid_and_is_deterministic(self):
        prefix = bytes(range(108))
        t = target_from_bits(10)
        n1, a1 = search_nonce(prefix, t)
        n2, a2 = search_nonce(prefix, t)
        self.assertEqual((n1, a1), (n2, a2))
        self.assertEqual(a1, n1 + 1)
        self.assertTrue(meets_target(sha256d(prefix + n1.to_bytes(4, "big")), t))
        for n in range(n1):                                   # no earlier nonce works
            self.assertFalse(meets_target(sha256d(prefix + n.to_bytes(4, "big")), t))

    def test_search_budget(self):
        n, a = search_nonce(bytes(108), 0, 0, 100)
        self.assertEqual((n, a), (None, 100))


class MerkleTests(unittest.TestCase):
    def test_shapes(self):
        a, b, c = (bytes([i]) * 32 for i in (1, 2, 3))
        self.assertEqual(merkle_root([]), EMPTY_ROOT)
        self.assertEqual(merkle_root([a]), leaf_hash(a))
        self.assertEqual(merkle_root([a, b]), node_hash(leaf_hash(a), leaf_hash(b)))
        self.assertEqual(merkle_root([a, b, c]),                      # c promoted, not duplicated
                         node_hash(node_hash(leaf_hash(a), leaf_hash(b)), leaf_hash(c)))
        self.assertNotEqual(merkle_root([a, b, c]), merkle_root([a, b, c, c]))


class HeaderTests(unittest.TestCase):
    def header(self, **kw):
        d = dict(version=1, prev_hash=b"\x01" * 32, merkle_root=b"\x02" * 32, timestamp=1_700_000_000,
                 target=target_from_bits(8), nonce=5)
        d.update(kw)
        return BlockHeader(**d)

    def test_layout_and_roundtrip(self):
        h = self.header()
        raw = h.serialize()
        self.assertEqual(len(raw), HEADER_SIZE)
        self.assertEqual(raw[:4], b"\x00\x00\x00\x01")
        self.assertEqual(raw[4:36], b"\x01" * 32)
        self.assertEqual(raw[36:68], b"\x02" * 32)
        self.assertEqual(int.from_bytes(raw[68:76], "big"), 1_700_000_000)
        self.assertEqual(int.from_bytes(raw[76:108], "big"), target_from_bits(8))
        self.assertEqual(int.from_bytes(raw[108:], "big"), 5)
        self.assertEqual(BlockHeader.parse(raw), h)
        self.assertEqual(BlockHeader.from_obj(json.loads(json.dumps(h.to_obj()))), h)
        self.assertEqual(h.hash, sha256d(raw))

    def test_any_field_change_changes_hash(self):
        base = self.header().hash
        for kw in (dict(nonce=6), dict(timestamp=1_700_000_001), dict(prev_hash=b"\x09" * 32),
                   dict(merkle_root=b"\x09" * 32), dict(target=target_from_bits(9))):
            self.assertNotEqual(self.header(**kw).hash, base)

    def test_rejects_malformed(self):
        for kw in (dict(version=2), dict(prev_hash=b"\x00" * 31), dict(timestamp=-1), dict(target=0),
                   dict(target=2**256), dict(nonce=2**32), dict(nonce=True)):
            with self.assertRaises(BlockError, msg=str(kw)):
                self.header(**kw)
        with self.assertRaises(BlockError):
            BlockHeader.parse(b"\x00" * 111)

    def test_solve_header(self):
        h, attempts = solve_header(self.header(nonce=0))
        self.assertTrue(meets_target(h.hash, h.target))
        self.assertEqual(attempts, h.nonce + 1)

    def test_hexdump_mentions_everything(self):
        text = hexdump_header(solve_header(self.header(nonce=0))[0])
        for word in ("version", "prev_hash", "merkle_root", "timestamp", "target", "nonce", "hash <= target: True"):
            self.assertIn(word, text)

    def test_published_vector(self):
        """vectors/header_vector.json pins the byte layout and the double-SHA-256."""
        with open(os.path.join(HERE, "..", "vectors", "header_vector.json")) as fh:
            vec = json.load(fh)
        h = BlockHeader.parse(bytes.fromhex(vec["header_hex"]))
        self.assertEqual(h.hash_hex, vec["block_hash"])
        self.assertEqual(h.work, vec["work"])
        self.assertTrue(meets_target(h.hash, h.target))


class BlockJson(unittest.TestCase):
    def test_roundtrip_and_strictness(self):
        chain = helpers.new_chain()
        blk = helpers.grow(chain, 1)[0]
        again = Block.from_json(blk.to_json())
        self.assertEqual(again.hash, blk.hash)
        self.assertEqual(again.txids, blk.txids)
        obj = blk.to_obj()
        obj["extra"] = 1
        with self.assertRaises(BlockError):
            Block.from_obj(obj)
        with self.assertRaises(BlockError):
            Block.from_json(b"not json")
        obj = blk.to_obj()
        obj["header"]["target"] = "ff"
        with self.assertRaises(BlockError):
            Block.from_obj(obj)


if __name__ == "__main__":
    unittest.main()
