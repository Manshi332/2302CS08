"""Consensus parameters and the context-free block rules.

Chain-selection rule (see chain.py): the valid chain with the MOST CUMULATIVE WORK
wins, where work(block) = floor(2**256 / (target + 1)). Block count is irrelevant.

Simplification (documented in the report): real networks derive each block's
target from a retargeting rule. Here a block may carry ANY target that is not easier
than `pow_limit`; choosing a harder target is simply more work (and counts as more
work), so nothing can be gained by lying about it. This is what lets the tests build a
LONG low-work branch and a SHORT high-work branch.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Sequence

from .address import DEFAULT_NETWORK, version_byte
from .block import Block
from .errors import BlockError, WalletError
from .proofofwork import meets_target, target_from_bits
from .tx import Output, SignedTx, TxBody

GENESIS_PKH = hashlib.sha256(b"chainlab-genesis").digest()[:20]   # nobody holds this key
PARAM_FIELDS = ("network_id", "min_bits", "bits", "genesis_timestamp", "initial_subsidy",
                "halving_interval", "target_spacing", "max_block_txs", "mtp_window",
                "max_future_seconds")


@dataclass(frozen=True)
class ChainParams:
    network_id: str = DEFAULT_NETWORK
    min_bits: int = 1               # pow_limit: no block may be easier than this many zero bits
    bits: int = 4                   # difficulty of genesis and default for newly mined blocks
    genesis_timestamp: int = 1_700_000_000
    initial_subsidy: int = 50
    halving_interval: int = 0       # blocks per halving; 0 = never halve
    target_spacing: int = 600       # default seconds between mined blocks
    max_block_txs: int = 1000
    mtp_window: int = 11            # median-time-past window
    max_future_seconds: int = 7200

    def __post_init__(self) -> None:
        version_byte(self.network_id)
        for name in PARAM_FIELDS[1:]:
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise BlockError("bad_params", f"{name} must be a non-negative integer")
        if not 0 <= self.min_bits <= self.bits <= 255:
            raise BlockError("bad_params", "need 0 <= min_bits <= bits <= 255")
        if self.initial_subsidy < 1 or self.max_block_txs < 1 or self.mtp_window < 1:
            raise BlockError("bad_params", "initial_subsidy, max_block_txs, mtp_window must be >= 1")

    @property
    def pow_limit(self) -> int:
        return target_from_bits(self.min_bits)

    def subsidy(self, height: int) -> int:
        if not self.halving_interval:
            return self.initial_subsidy
        return self.initial_subsidy >> (height // self.halving_interval)

    def to_obj(self) -> dict:
        return {k: getattr(self, k) for k in PARAM_FIELDS}

    @classmethod
    def from_obj(cls, obj: Any) -> "ChainParams":
        if not isinstance(obj, dict) or set(obj) != set(PARAM_FIELDS):
            raise BlockError("bad_params", f"params must have exactly the fields {list(PARAM_FIELDS)}")
        try:
            return cls(**obj)
        except WalletError as exc:
            raise BlockError("bad_params", str(exc)) from None


def coinbase_memo(height: int) -> str:
    """Height in the memo makes every coinbase txid unique (BIP-34 idea)."""
    return f"coinbase:{height}"


def is_coinbase(tx: SignedTx) -> bool:
    return not tx.body.inputs


def make_coinbase(network_id: str, height: int, payouts: Sequence[tuple[int, bytes]]) -> SignedTx:
    body = TxBody(network_id, (), tuple(Output(v, pkh) for v, pkh in payouts), coinbase_memo(height))
    return SignedTx(body, ())


def check_block_structure(block: Block, params: ChainParams, height: int) -> None:
    """Rules that need only the block itself, the parameters and its height."""
    h = block.header
    if not 0 < h.target <= params.pow_limit:
        raise BlockError("bad_target", f"target is easier than the network limit "
                         f"(min_bits={params.min_bits})")
    if not meets_target(h.hash, h.target):
        raise BlockError("bad_pow", f"block hash {h.hash_hex[:16]}... is above the target: "
                         "not enough work")
    txs = block.txs
    if not txs:
        raise BlockError("no_transactions", "a block must contain at least the coinbase")
    if len(txs) > params.max_block_txs:
        raise BlockError("too_many_txs", f"{len(txs)} transactions; limit is {params.max_block_txs}")
    if not is_coinbase(txs[0]):
        raise BlockError("missing_coinbase", "the first transaction must be a coinbase (no inputs)")
    for n, tx in enumerate(txs[1:], 1):
        if is_coinbase(tx):
            raise BlockError("multiple_coinbase", f"transaction {n} has no inputs; "
                             "only transaction 0 may be a coinbase")
    ids = block.txids
    if len(set(ids)) != len(ids):
        raise BlockError("duplicate_txid", "the same transaction appears twice in the block")
    if h.merkle_root != block.computed_merkle_root():
        raise BlockError("bad_merkle", "header merkle_root does not match the block's transactions")
    cb = txs[0]
    if cb.witnesses:
        raise BlockError("bad_coinbase", "a coinbase carries no witnesses")
    if cb.body.network_id != params.network_id:
        raise BlockError("bad_coinbase", f"coinbase is for {cb.body.network_id!r}, chain is "
                         f"{params.network_id!r}")
    if cb.body.memo != coinbase_memo(height):
        raise BlockError("bad_coinbase", f"coinbase memo must be {coinbase_memo(height)!r} "
                         f"for height {height}")
