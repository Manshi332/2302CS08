"""Run with:  PYTHONPATH=src python -m unittest discover -s tests -v"""
import asyncio
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chainlab import ChainParams, Chain, mine_block  # noqa: E402
from chainlab.testkeys import demo_wallet  # noqa: E402
from p2plab import messages as M  # noqa: E402
from p2plab.mempool import Mempool, MempoolReject  # noqa: E402
from p2plab.node import Node, NodeConfig  # noqa: E402

P = ChainParams(bits=4)
ALICE, BOB = demo_wallet("alice"), demo_wallet("bob")


def funded_chain():
    c = Chain(P)
    c.add_block(mine_block(c, ALICE.primary_address).block)
    return c


async def until(cond, t=10):
    for _ in range(int(t * 20)):
        if cond():
            return
        await asyncio.sleep(0.05)
    raise TimeoutError


class FramingTests(unittest.TestCase):
    def test_roundtrip(self):
        raw = M.encode("ping", {"nonce": 7})
        (n,) = struct.unpack(">I", raw[:4])
        self.assertEqual(n, len(raw) - 4)
        self.assertEqual(M.decode(raw[4:]), ("ping", {"nonce": 7}))

    def test_rejects_bad_messages(self):
        for body in (b"not json", b'{"v":1,"type":"ping","payload":{"nonce":1.5}}',
                     b'{"v":2,"type":"ping","payload":{"nonce":1}}',
                     b'{"v":1,"type":"nope","payload":{}}',
                     b'{"v":1,"type":"inv","payload":{"items":[{"kind":"tx","id":"zz"}]}}'):
            with self.assertRaises(M.ProtocolError):
                M.decode(body)

    def test_oversized_length_rejected_before_read(self):
        async def go():
            r = asyncio.StreamReader()
            r.feed_data(struct.pack(">I", M.MAX_MESSAGE_SIZE + 1))
            with self.assertRaises(M.ProtocolError) as cm:
                await M.read_frame(r)
            self.assertTrue(cm.exception.fatal)
        asyncio.run(go())


class MempoolTests(unittest.TestCase):
    def setUp(self):
        self.chain = funded_chain()
        self.t = [1000.0]
        self.mp = Mempool(self.chain, lambda: self.t[0], ttl=100)

    def pay(self, fee, amount=10):
        return ALICE.build_payment(self.chain.ledger, BOB.primary_address, amount, fee=fee)

    def test_duplicate_and_ordering(self):
        tx = self.pay(1)
        self.mp.add(tx)
        with self.assertRaises(MempoolReject) as cm:
            self.mp.add(tx)
        self.assertEqual(cm.exception.code, "duplicate")

    def test_conflict_replacement_by_fee_rate(self):
        low, high = self.pay(1), self.pay(5, amount=11)
        self.mp.add(low)
        _, replaced = self.mp.add(high)
        self.assertEqual(replaced, [low.txid])
        self.assertIn(high.txid, self.mp)
        with self.assertRaises(MempoolReject) as cm:
            self.mp.add(self.pay(2, amount=12))
        self.assertEqual(cm.exception.code, "conflict")

    def test_expiry(self):
        tx = self.pay(1)
        self.mp.add(tx)
        self.t[0] += 101
        self.assertEqual(self.mp.expire(), [tx.txid])
        self.assertEqual(len(self.mp), 0)

    def test_invalid_rejected(self):
        with self.assertRaises(MempoolReject):
            self.mp.add({"garbage": 1})


class NodeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        cfg = NodeConfig(tick=0.2, rate_per_sec=5, rate_burst=10, ban_threshold=-30)
        self.a, self.b = Node("a", P, config=cfg), Node("b", P, config=cfg)
        await self.a.start()
        await self.b.start()

    async def asyncTearDown(self):
        await self.a.stop()
        await self.b.stop()

    async def test_handshake_and_block_relay(self):
        await self.b.connect("127.0.0.1", self.a.port)
        await until(lambda: self.a.ready_peers() and self.b.ready_peers())
        self.a.mine(ALICE.primary_address)
        await until(lambda: self.b.chain.height == 1)
        self.assertEqual(self.a.chain.tip, self.b.chain.tip)

    async def test_tx_inv_then_getdata(self):
        await self.b.connect("127.0.0.1", self.a.port)
        await until(lambda: self.a.ready_peers() and self.b.ready_peers())
        self.a.mine(ALICE.primary_address)
        await until(lambda: self.b.chain.height == 1)
        tx = ALICE.build_payment(self.a.chain.ledger, BOB.primary_address, 5, fee=1)
        self.a.submit_tx(tx)
        await until(lambda: tx.txid in self.b.mempool)
        ev = [e["event"] for e in self.a.events.events]
        self.assertIn("tx_sent", ev)

    async def test_malformed_and_oversized_input(self):
        r, w = await asyncio.open_connection("127.0.0.1", self.a.port)
        w.write(struct.pack(">I", M.MAX_MESSAGE_SIZE + 5))     # lying length prefix
        await w.drain()
        await until(lambda: any(e["event"] == "protocol_error" and e["code"] == "oversized"
                                for e in self.a.events.events))
        w.close()

    async def test_wrong_network_rejected(self):
        other = Node("c", ChainParams(bits=4, initial_subsidy=49))
        await other.start()
        try:
            await other.connect("127.0.0.1", self.a.port)
            await until(lambda: any(e["event"] == "protocol_error" and e["code"] == "wrong_network"
                                    for e in self.a.events.events + other.events.events))
            self.assertFalse(self.a.ready_peers())
        finally:
            await other.stop()

    async def test_rate_limit_and_ban(self):
        await self.b.connect("127.0.0.1", self.a.port)
        await until(lambda: self.a.ready_peers() and self.b.ready_peers())
        peer = self.b.peers["a"]
        for _ in range(200):                                     # flood pings
            self.b._send(peer, "ping", {"nonce": 1})
        await until(lambda: any(e["event"] == "peer_banned" for e in self.a.events.events))
        self.assertIn("b", self.a.banned)

    async def test_ping_pong(self):
        self.a.cfg.ping_interval = 0.3
        await self.b.connect("127.0.0.1", self.a.port)
        await until(lambda: any(e["event"] == "pong" for e in self.a.events.events), 5)


if __name__ == "__main__":
    unittest.main()
