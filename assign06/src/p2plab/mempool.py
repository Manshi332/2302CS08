"""Mempool: validation, duplicate suppression, fee-rate ordering, expiry, conflict handling.

Every entry is validated against the UTXO state at the current chain tip, so any set of
entries the pool holds together is spendable together (conflicting spends are never
both admitted).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from chainlab.canonical import canonicalize_value
from chainlab.errors import LedgerError, WalletError
from chainlab.tx import OutPoint, SignedTx, coerce_signed


class MempoolReject(Exception):
    def __init__(self, code: str, reason: str = ""):
        super().__init__(f"{code}: {reason}")
        self.code, self.reason = code, reason


@dataclass
class Entry:
    tx: SignedTx
    txid: str
    fee: int
    size: int
    added: float
    spends: tuple[OutPoint, ...]

    @property
    def fee_rate(self) -> float:
        return self.fee / self.size


class Mempool:
    def __init__(self, chain, clock: Callable[[], float] = time.time, *, max_txs: int = 1000,
                 ttl: float = 3600.0, min_fee_rate: float = 0.0, max_tx_size: int = 100_000):
        self.chain, self.clock = chain, clock
        self.max_txs, self.ttl, self.min_fee_rate, self.max_tx_size = max_txs, ttl, min_fee_rate, max_tx_size
        self.entries: dict[str, Entry] = {}
        self._spent: dict[OutPoint, str] = {}

    def __len__(self) -> int:
        return len(self.entries)

    def __contains__(self, txid: str) -> bool:
        return txid in self.entries

    def get(self, txid: str) -> Optional[SignedTx]:
        e = self.entries.get(txid)
        return e.tx if e else None

    def ids(self) -> list[str]:
        return list(self.entries)

    # ------------------------------------------------------------------ add
    def add(self, tx: "SignedTx | dict | bytes | str") -> tuple[Entry, list[str]]:
        """Admit a tx. Returns (entry, ids of conflicting txs it replaced). Raises MempoolReject."""
        try:
            tx = coerce_signed(tx)
        except WalletError as exc:
            raise MempoolReject("malformed_tx", str(exc)) from None
        txid = tx.txid
        if txid in self.entries:
            raise MempoolReject("duplicate", "already in the mempool")
        size = len(canonicalize_value(tx.to_obj()))
        if size > self.max_tx_size:
            raise MempoolReject("too_large", f"{size} bytes")
        try:
            plan = self.chain.ledger.validate(tx)
        except LedgerError as exc:
            raise MempoolReject(exc.code, exc.reason) from None
        entry = Entry(tx, txid, plan.fee, size, self.clock(), tuple(op for op, _ in plan.spent))
        if entry.fee_rate < self.min_fee_rate:
            raise MempoolReject("low_fee", f"fee rate {entry.fee_rate:.4f} below minimum {self.min_fee_rate}")

        conflicts = {self._spent[op] for op in entry.spends if op in self._spent}
        if conflicts:
            best = max(self.entries[c].fee_rate for c in conflicts)
            if entry.fee_rate <= best:
                raise MempoolReject("conflict", "double-spends a pooled tx and does not pay a higher fee rate")
        replaced = sorted(conflicts)
        for c in replaced:
            self._remove(c)
        if len(self.entries) >= self.max_txs:
            worst = min(self.entries.values(), key=lambda e: e.fee_rate)
            if entry.fee_rate <= worst.fee_rate:
                raise MempoolReject("mempool_full", "pool is full and fee rate is not above the lowest")
            self._remove(worst.txid)
            replaced.append(worst.txid)
        self._insert(entry)
        return entry, replaced

    def _insert(self, e: Entry) -> None:
        self.entries[e.txid] = e
        for op in e.spends:
            self._spent[op] = e.txid

    def _remove(self, txid: str) -> None:
        e = self.entries.pop(txid, None)
        if e:
            for op in e.spends:
                self._spent.pop(op, None)

    # --------------------------------------------------------------- expiry
    def expire(self) -> list[str]:
        now = self.clock()
        old = [t for t, e in self.entries.items() if now - e.added > self.ttl]
        for t in old:
            self._remove(t)
        return old

    # ------------------------------------------------------------ selection
    def select(self, limit: int) -> list[SignedTx]:
        """Highest fee rate first; entries never conflict so any subset is valid together."""
        ranked = sorted(self.entries.values(), key=lambda e: (-e.fee_rate, e.added, e.txid))
        return [e.tx for e in ranked[:limit]]

    # ------------------------------------------------------------ new tip
    def reconcile(self, returned: Iterable[SignedTx] = ()) -> tuple[list[str], list[str]]:
        """Re-check the pool against the (possibly new) tip and re-admit txs returned by a reorg.

        Returns (txids that are in the pool afterwards but were not before, txids dropped).
        """
        before = dict(self.entries)
        candidates = sorted(before.values(), key=lambda e: -e.fee_rate)
        self.entries.clear()
        self._spent.clear()
        now = self.clock()
        for e in candidates:
            try:
                new, _ = self.add(e.tx)
                new.added = e.added          # keep the original arrival time so expiry still works
            except MempoolReject:
                pass
        for tx in returned:
            try:
                self.add(tx)
            except MempoolReject:
                pass
        gained = [t for t in self.entries if t not in before]
        dropped = [t for t in before if t not in self.entries]
        return gained, dropped
