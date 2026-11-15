"""Wallet-side transaction builder: owns keys, selects coins, makes change, signs."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from . import keys
from .address import DEFAULT_NETWORK, address_from_pubkey, check_address, decode_address, pubkey_hash
from .errors import LedgerError, WalletError
from .ledger import Ledger
from .selection import STRATEGIES, Candidate, select_coins
from .tx import MAX_VALUE, Output, SignedTx, TxBody, sign_body


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


class Wallet:
    """A set of Ed25519 keys on one network. Holds no coins itself: it reads the ledger."""

    def __init__(self, network_id: str = DEFAULT_NETWORK, strategy: str = "largest_first"):
        if strategy not in STRATEGIES:
            raise LedgerError("bad_strategy", f"unknown coin selection strategy {strategy!r}")
        self.network_id = network_id
        self.strategy = strategy
        self._keys: dict[bytes, object] = {}      # pkh -> private key
        self._order: List[bytes] = []             # pkhs in creation order (first = primary)

    # ----------------------------------------------------------------- keys
    def add_key(self, private_key) -> str:
        pkh = pubkey_hash(keys.public_bytes(private_key))
        if pkh not in self._keys:
            self._keys[pkh] = private_key
            self._order.append(pkh)
        return address_from_pubkey(keys.public_bytes(private_key), self.network_id)

    def new_address(self) -> str:
        return self.add_key(keys.generate())

    @classmethod
    def from_seeds(cls, seeds: Sequence[bytes], network_id: str = DEFAULT_NETWORK,
                   strategy: str = "largest_first") -> "Wallet":
        """TEST/DEMO ONLY: deterministic wallet from 32-byte seeds."""
        w = cls(network_id, strategy)
        for s in seeds:
            w.add_key(keys.private_from_seed(s))
        return w

    @property
    def addresses(self) -> List[str]:
        from .address import address_from_pkh
        return [address_from_pkh(p, self.network_id) for p in self._order]

    @property
    def primary_address(self) -> str:
        if not self._order:
            raise LedgerError("no_keys", "wallet has no keys; call new_address() first")
        return self.addresses[0]

    @property
    def pkhs(self) -> List[bytes]:
        return list(self._order)

    # -------------------------------------------------------------- queries
    def spendable(self, ledger: Ledger) -> List[Candidate]:
        out: List[Candidate] = []
        for pkh in self._order:
            out.extend(ledger.outputs_for(pkh))
        return out

    def balance(self, ledger: Ledger) -> int:
        return sum(ledger.balance_of(p) for p in self._order)

    # ------------------------------------------------------------- building
    def build_payment(self, ledger: Ledger, to_address: str, amount: int, fee: int = 0, *,
                      change_address: Optional[str] = None, memo: str = "") -> SignedTx:
        return self.build_payments(ledger, [(to_address, amount)], fee,
                                   change_address=change_address, memo=memo)

    def build_payments(self, ledger: Ledger, payments: Sequence[Tuple[str, int]], fee: int = 0, *,
                       change_address: Optional[str] = None, memo: str = "") -> SignedTx:
        """Select coins, add exact change, sign every input. Never touches the ledger state.

            change = sum(selected inputs) - sum(payments) - fee        (a change output only if > 0)
        """
        if ledger.network_id != self.network_id:
            raise LedgerError("wrong_network", f"wallet is on {self.network_id!r}, "
                              f"ledger on {ledger.network_id!r}")
        if not payments:
            raise LedgerError("no_outputs", "at least one payment is required")
        if not _is_int(fee) or not 0 <= fee <= MAX_VALUE:
            raise LedgerError("bad_fee", f"fee must be an integer in 0..{MAX_VALUE}")
        outputs: List[Output] = []
        paid = 0
        for addr, amount in payments:
            if not _is_int(amount) or amount < 1:
                raise LedgerError("bad_amount", f"payment amount must be an integer >= 1, got {amount!r}")
            try:
                _, pkh = decode_address(addr)
                check_address(addr, self.network_id)
            except WalletError as exc:
                raise LedgerError("bad_address", str(exc)) from None
            outputs.append(Output(amount, pkh))
            paid += amount
        target = paid + fee
        if target > MAX_VALUE:
            raise LedgerError("value_overflow", f"amount + fee exceeds {MAX_VALUE}")

        selected, total_in = select_coins(self.spendable(ledger), target, self.strategy)
        change = total_in - target
        if change > 0:
            caddr = change_address or self.primary_address
            try:
                _, cpkh = decode_address(caddr)
                check_address(caddr, self.network_id)
            except WalletError as exc:
                raise LedgerError("bad_address", f"change address: {exc}") from None
            outputs.append(Output(change, cpkh))          # change is always the LAST output

        body = TxBody(self.network_id, tuple(op for op, _ in selected), tuple(outputs), memo)
        return sign_body(body, [self._keys[o.pkh] for _, o in selected])
