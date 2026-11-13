"""UTXO state with block-level connect / disconnect (the reorganisation engine).

ChainLedger extends the Assignment 4 Ledger. Everything that validates ONE
transaction (inputs exist, no double spend, signatures, value conservation) is
inherited unchanged. This class adds:

  connect_block(txs, subsidy, height)  all-or-nothing: either every transaction and
        the coinbase are applied, or the state is restored bit for bit and BlockError
        is raised. Returns a BlockUndo.
  disconnect_block(undo)               exact inverse of connect_block: removes the
        outputs the block created, restores the outputs it spent and removes their
        "spent" history entries.

Coinbase rule:  sum(coinbase outputs) <= subsidy(height) + sum(fees of the block's txs).
Accounting:     issued == unspent + burned   where `fees` (inherited name) now means
                "burned": fees not claimed by the miner plus unclaimed subsidy. A block
                that claims everything burns nothing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Sequence

from .canonical import canonicalize_value
from .consensus import coinbase_memo
from .errors import BlockError, LedgerError
from .ledger import Ledger, Plan
from .tx import MAX_VALUE, OutPoint, SignedTx


@dataclass(frozen=True)
class BlockUndo:
    plans: tuple[Plan, ...]      # regular transactions, in block order
    coinbase: Plan
    subsidy: int


class ChainLedger(Ledger):
    # ------------------------------------------------------------ rollback
    def _rollback(self, plan: Plan) -> None:
        """Exact inverse of Ledger._commit(plan). Must be applied in reverse commit order."""
        if not self.applied or self.applied[-1] != plan.txid:
            raise AssertionError("rollback out of order (internal error)")
        for op, out in plan.created:
            del self.utxos[op]
            self._by_pkh[out.pkh].discard(op)
        for op, out in plan.spent:
            self.utxos[op] = out
            self._by_pkh.setdefault(out.pkh, set()).add(op)
            del self.spent[op]
        self.applied.pop()
        self._applied_set.discard(plan.txid)
        self.fees -= plan.fee

    # ------------------------------------------------------------- connect
    def connect_block(self, txs: Sequence[SignedTx], subsidy: int, height: int) -> BlockUndo:
        done: list[Plan] = []
        try:
            block_fees = 0
            for n, tx in enumerate(txs[1:], 1):
                try:
                    plan = self.validate(tx)
                except LedgerError as exc:
                    raise BlockError("invalid_tx", f"transaction {n} ({tx.txid[:8]}) rejected: "
                                     f"{exc.code}: {exc.reason}", inner=exc.code) from None
                self._commit(plan)
                done.append(plan)
                block_fees += plan.fee
            cb_plan = self._coinbase_plan(txs[0], subsidy, height, block_fees)
        except BaseException:
            for plan in reversed(done):
                self._rollback(plan)
            raise
        self._commit(cb_plan)
        self.issued += subsidy
        self.fees += subsidy - cb_plan.total_out        # unclaimed part is burned
        return BlockUndo(tuple(done), cb_plan, subsidy)

    def _coinbase_plan(self, cb: SignedTx, subsidy: int, height: int, block_fees: int) -> Plan:
        body = cb.body
        if body.inputs or cb.witnesses or body.memo != coinbase_memo(height):
            raise BlockError("bad_coinbase", "malformed coinbase")
        claimed = sum(o.value for o in body.outputs)
        limit = subsidy + block_fees
        if claimed > limit or claimed > MAX_VALUE:
            raise BlockError("coinbase_excess", f"coinbase claims {claimed} but subsidy {subsidy} + "
                             f"fees {block_fees} = {limit} is the most it may claim")
        if body.txid in self._applied_set:
            raise BlockError("duplicate_transaction", "coinbase txid already exists in this chain")
        return Plan(body.txid, 0, 0, claimed, (),
                    tuple((OutPoint(body.txid, i), o) for i, o in enumerate(body.outputs)))

    # ---------------------------------------------------------- disconnect
    def disconnect_block(self, undo: BlockUndo) -> None:
        cb = undo.coinbase
        self._rollback(cb)
        self.issued -= undo.subsidy
        self.fees -= undo.subsidy - cb.total_out
        for plan in reversed(undo.plans):
            self._rollback(plan)

    # -------------------------------------------------------------- digest
    def utxo_digest(self) -> str:
        """SHA-256 of the canonical UTXO set + issued + burned (history-independent)."""
        state = {"issued": self.issued, "burned": self.fees,
                 "utxos": {str(op): o.to_obj() for op, o in self.utxos.items()}}
        return hashlib.sha256(canonicalize_value(state)).hexdigest()
