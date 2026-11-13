"""Shared test setup: make src/ importable and provide small fixtures."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from chainlab import Chain, ChainParams, mine_block  # noqa: E402
from chainlab.testkeys import demo_wallet  # noqa: E402

CLOCK = lambda: 4_000_000_000  # noqa: E731

ALICE, BOB, CAROL, MINER = (demo_wallet(n) for n in ("alice", "bob", "carol", "miner"))


def new_chain(bits: int = 4, **kw) -> Chain:
    return Chain(ChainParams(bits=bits, **kw), CLOCK)


def grow(chain: Chain, n: int, wallet=ALICE, **kw):
    blocks = []
    for _ in range(n):
        b = mine_block(chain, wallet.primary_address, **kw).block
        chain.add_block(b)
        blocks.append(b)
    return blocks
