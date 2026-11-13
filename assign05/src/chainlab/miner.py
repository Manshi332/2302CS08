"""Block assembly and nonce search (the `mine` command's engine).

make_block   builds an UNSOLVED block (nonce 0) on any known parent, not only the tip,
             so competing branches can be produced.
solve_block  searches nonces until SHA-256d(header) <= target. Deterministic: nonces are
             tried in order 0, 1, 2, ... (if all 2**32 fail the timestamp is bumped by 1,
             the toy equivalent of Bitcoin's extra-nonce).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Optional, Sequence

from .address import check_address, decode_address
from .block import Block, BlockHeader, ZERO_HASH
from .consensus import GENESIS_PKH, ChainParams, make_coinbase
from .errors import BlockError
from .merkle import merkle_root
from .proofofwork import search_nonce, target_from_bits
from .tx import SignedTx


@dataclass(frozen=True)
class MineResult:
    block: Block
    attempts: int
    seconds: float

    @property
    def hashrate(self) -> float:
        return self.attempts / self.seconds if self.seconds > 0 else float("inf")


def solve_header(header: BlockHeader, max_attempts: Optional[int] = None) -> tuple[BlockHeader, int]:
    total = 0
    h = header
    while True:
        budget = None if max_attempts is None else max_attempts - total
        nonce, n = search_nonce(h.serialize()[:-4], h.target, 0, budget)
        total += n
        if nonce is not None:
            return h.with_nonce(nonce), total
        if max_attempts is not None and total >= max_attempts:
            raise BlockError("mining_gave_up", f"no valid nonce found in {max_attempts} attempts")
        h = replace(h, timestamp=h.timestamp + 1)


def solve_block(block: Block, max_attempts: Optional[int] = None) -> MineResult:
    t0 = time.perf_counter()
    header, attempts = solve_header(block.header, max_attempts)
    return MineResult(Block(header, block.txs), attempts, time.perf_counter() - t0)


def make_genesis(params: ChainParams) -> Block:
    """Deterministic genesis: same params -> same block, byte for byte."""
    cb = make_coinbase(params.network_id, 0, [(params.subsidy(0), GENESIS_PKH)])
    header = BlockHeader(1, ZERO_HASH, merkle_root([bytes.fromhex(cb.txid)]),
                         params.genesis_timestamp, target_from_bits(params.bits), 0)
    return solve_block(Block(header, (cb,))).block


def make_block(chain, address: str, *, parent: "bytes | str | None" = None,
               txs: Sequence[SignedTx] = (), bits: Optional[int] = None,
               target: Optional[int] = None, timestamp: Optional[int] = None,
               coinbase_value: Optional[int] = None, check_txs: bool = True) -> Block:
    """Assemble an unsolved block on `parent` (default: the active tip).

    check_txs=True  validates `txs` against the state at `parent` to compute their fees
                    (raises if one is invalid). check_txs=False skips that and assumes
                    zero fees, which lets tests build deliberately invalid blocks.
    coinbase_value  override the claimed amount (default: subsidy + fees). Tests use it
                    to build a block that claims too much.
    """
    params = chain.params
    prec = chain.record(parent if parent is not None else chain.tip)
    height = prec.height + 1
    check_address(address, params.network_id)
    _, pkh = decode_address(address)
    fees = 0
    if txs and check_txs:
        scratch = chain.state_at(prec.hash)
        for tx in txs:
            plan = scratch.validate(tx)
            scratch._commit(plan)
            fees += plan.fee
    value = params.subsidy(height) + fees if coinbase_value is None else coinbase_value
    tgt = target if target is not None else target_from_bits(params.bits if bits is None else bits)
    ts = prec.header.timestamp + params.target_spacing if timestamp is None else timestamp
    cb = make_coinbase(params.network_id, height, [(value, pkh)])
    body = (cb, *txs)
    header = BlockHeader(1, prec.hash, merkle_root([bytes.fromhex(t.txid) for t in body]), ts, tgt, 0)
    return Block(header, body)


def mine_block(chain, address: str, *, max_attempts: Optional[int] = None, **kwargs) -> MineResult:
    return solve_block(make_block(chain, address, **kwargs), max_attempts)
