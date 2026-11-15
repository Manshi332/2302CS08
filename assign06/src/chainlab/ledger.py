"""In-memory UTXO ledger and transaction validator.

State
    utxos    outpoint -> Output           the unspent outputs (the only spendable things)
    spent    outpoint -> txid             history: which transaction consumed an output
    applied  [txid, ...]                  every accepted transaction, in order
    issued   total units created by issuance (the only way value enters the system)
    fees     total units paid as fees and burned

Invariant (checked by check_invariants, on every load, and in tests):
    issued == sum(value of utxos) + fees        and      utxos  and  spent  are disjoint

Validation is a PURE function (``validate``): it reads the state and returns a
``Plan`` or raises ``LedgerError``. ``apply`` = validate, then commit the plan.
The commit step only touches keys that validation proved exist/absent, so it
cannot fail half-way: a rejected transaction leaves the state bit-for-bit unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from . import keys
from .address import DEFAULT_NETWORK, pubkey_hash, version_byte
from .canonical import canonicalize_value, parse_strict
from .errors import LedgerError, WalletError
from .tx import (MAX_VALUE, Output, OutPoint, SignedTx, TxBody, coerce_signed, _lower_hex)

SNAPSHOT_FORMAT = "utxolab-snapshot-v1"
Pair = Tuple[OutPoint, Output]


@dataclass(frozen=True)
class Plan:
    """The result of a successful validation: exactly what ``apply`` will commit."""
    txid: str
    fee: int
    total_in: int
    total_out: int
    spent: Tuple[Pair, ...]
    created: Tuple[Pair, ...]


@dataclass(frozen=True)
class Receipt:
    txid: str
    fee: int
    spent: Tuple[OutPoint, ...]
    created: Tuple[OutPoint, ...]


class Ledger:
    def __init__(self, network_id: str = DEFAULT_NETWORK):
        try:
            version_byte(network_id)
        except WalletError as exc:
            raise LedgerError("unknown_network", str(exc)) from None
        self.network_id = network_id
        self.utxos: Dict[OutPoint, Output] = {}
        self.spent: Dict[OutPoint, str] = {}
        self.applied: List[str] = []
        self._applied_set: Set[str] = set()
        self._by_pkh: Dict[bytes, Set[OutPoint]] = {}
        self.issued = 0
        self.fees = 0

    # ------------------------------------------------------------ queries
    def get(self, op: OutPoint) -> Optional[Output]:
        return self.utxos.get(op)

    def outputs_for(self, pkh: bytes) -> List[Pair]:
        return sorted(((op, self.utxos[op]) for op in self._by_pkh.get(pkh, ())),
                      key=lambda p: p[0])

    def balance_of(self, pkh: bytes) -> int:
        return sum(self.utxos[op].value for op in self._by_pkh.get(pkh, ()))

    def total_unspent(self) -> int:
        return sum(o.value for o in self.utxos.values())

    # --------------------------------------------------------- validation
    def validate(self, tx: "SignedTx | dict | bytes | str") -> Plan:
        """Check every rule; mutate nothing. Raises LedgerError(code, reason)."""
        tx = coerce_signed(tx)
        body = tx.body

        if body.network_id != self.network_id:
            raise LedgerError("wrong_network", f"transaction is for {body.network_id!r}, "
                              f"this ledger is {self.network_id!r}")
        if not body.inputs:
            raise LedgerError("no_inputs", "a transaction must spend at least one output "
                              "(new value can only enter through Ledger.issue)")
        txid = body.txid
        if txid in self._applied_set:
            raise LedgerError("duplicate_transaction", f"transaction {txid[:8]} was already applied; "
                              "resubmitting it would not pay anyone twice")

        seen: Set[OutPoint] = set()
        for op in body.inputs:
            if op in seen:
                raise LedgerError("duplicate_input", f"outpoint {op.short()} is listed more than once "
                                  "in the same transaction")
            seen.add(op)

        spent_pairs: List[Pair] = []
        for op in body.inputs:
            out = self.utxos.get(op)
            if out is None:
                by = self.spent.get(op)
                if by is not None:
                    raise LedgerError("input_already_spent", f"outpoint {op.short()} was already spent "
                                      f"by transaction {by[:8]}")
                raise LedgerError("input_not_found", f"outpoint {op.short()} does not exist")
            spent_pairs.append((op, out))

        if len(tx.witnesses) != len(body.inputs):
            raise LedgerError("bad_witness", f"{len(tx.witnesses)} witness(es) for "
                              f"{len(body.inputs)} input(s); need exactly one per input")

        total_in = 0
        for op, out in spent_pairs:
            total_in += out.value
            if total_in > MAX_VALUE:
                raise LedgerError("value_overflow", f"sum of input values exceeds {MAX_VALUE}")
        total_out = 0
        for out in body.outputs:
            total_out += out.value
            if total_out > MAX_VALUE:
                raise LedgerError("value_overflow", f"sum of output values exceeds {MAX_VALUE}")
        if total_out > total_in:
            raise LedgerError("outputs_exceed_inputs", f"outputs total {total_out} but inputs total only "
                              f"{total_in}; {total_out - total_in} unit(s) would be created from nothing")

        msg = body.signing_bytes
        for n, ((op, out), w) in enumerate(zip(spent_pairs, tx.witnesses)):
            if pubkey_hash(w.public_key) != out.pkh:
                raise LedgerError("pubkey_hash_mismatch", f"input {n} ({op.short()}): public key does not "
                                  "hash to the output's locking pubkey hash")
            if not keys.signature_is_canonical(w.signature):
                raise LedgerError("noncanonical_signature", f"input {n} ({op.short()}): signature scalar "
                                  "S is not reduced mod L")
            if not keys.verify(w.public_key, msg, w.signature):
                raise LedgerError("bad_signature", f"input {n} ({op.short()}): signature does not verify "
                                  "over this transaction")

        created = tuple((OutPoint(txid, i), o) for i, o in enumerate(body.outputs))
        return Plan(txid, total_in - total_out, total_in, total_out, tuple(spent_pairs), created)

    # ------------------------------------------------------------- commit
    def _commit(self, plan: Plan) -> Receipt:
        for op, out in plan.spent:
            del self.utxos[op]
            self._by_pkh[out.pkh].discard(op)
            self.spent[op] = plan.txid
        for op, out in plan.created:
            self.utxos[op] = out
            self._by_pkh.setdefault(out.pkh, set()).add(op)
        self.applied.append(plan.txid)
        self._applied_set.add(plan.txid)
        self.fees += plan.fee
        return Receipt(plan.txid, plan.fee, tuple(op for op, _ in plan.spent),
                       tuple(op for op, _ in plan.created))

    def apply(self, tx: "SignedTx | dict | bytes | str") -> Receipt:
        """Validate and, only if EVERY rule passes, update the UTXO set."""
        return self._commit(self.validate(tx))

    def issue(self, outputs: Sequence[Output], memo: str = "") -> Receipt:
        """Create new coins (genesis / coinbase-style). The only source of value."""
        body = TxBody(self.network_id, (), tuple(outputs), memo)
        if body.txid in self._applied_set:
            raise LedgerError("duplicate_transaction", "this issuance was already applied "
                              "(use a different memo for an otherwise identical issuance)")
        total = sum(o.value for o in body.outputs)
        if total > MAX_VALUE or self.issued + total > MAX_VALUE:
            raise LedgerError("value_overflow", f"total issued would exceed {MAX_VALUE}")
        plan = Plan(body.txid, 0, 0, total, (),
                    tuple((OutPoint(body.txid, i), o) for i, o in enumerate(body.outputs)))
        self.issued += total
        return self._commit(plan)

    # ----------------------------------------------------------- snapshot
    def to_state(self) -> dict:
        return {
            "network_id": self.network_id,
            "issued": self.issued,
            "fees": self.fees,
            "utxos": {str(op): o.to_obj() for op, o in self.utxos.items()},
            "spent": {str(op): t for op, t in self.spent.items()},
            "applied": list(self.applied),
        }

    def state_hash(self) -> str:
        """SHA-256 of the canonical snapshot: equal hash <=> equal logical contents."""
        return hashlib.sha256(canonicalize_value(self.to_state())).hexdigest()

    def check_invariants(self) -> None:
        if self.issued != self.total_unspent() + self.fees:
            raise LedgerError("invariant_violation", f"issued {self.issued} != unspent "
                              f"{self.total_unspent()} + fees {self.fees}")
        both = set(self.utxos) & set(self.spent)
        if both:
            raise LedgerError("invariant_violation", f"{len(both)} outpoint(s) are both unspent and spent")
        if len(self._applied_set) != len(self.applied):
            raise LedgerError("invariant_violation", "duplicate txid in the applied list")
        indexed = {op for s in self._by_pkh.values() for op in s}
        if indexed != set(self.utxos):
            raise LedgerError("invariant_violation", "address index does not match the UTXO set")

    @classmethod
    def from_state(cls, state: Any) -> "Ledger":
        def bad(msg: str) -> LedgerError:
            return LedgerError("bad_snapshot", msg)
        if not isinstance(state, dict) or set(state) != {"network_id", "issued", "fees", "utxos",
                                                         "spent", "applied"}:
            raise bad("state must have exactly network_id, issued, fees, utxos, spent, applied")
        if not isinstance(state["network_id"], str):
            raise bad("network_id must be a string")
        try:
            led = cls(state["network_id"])
        except LedgerError as exc:
            raise bad(exc.reason) from None
        for name in ("issued", "fees"):
            v = state[name]
            if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= MAX_VALUE:
                raise bad(f"{name} must be an integer in 0..{MAX_VALUE}")
        if not isinstance(state["utxos"], dict) or not isinstance(state["spent"], dict) \
                or not isinstance(state["applied"], list):
            raise bad("utxos/spent must be objects and applied a list")
        try:
            for key, obj in state["utxos"].items():
                op = OutPoint.parse(key)
                if str(op) != key:
                    raise bad(f"non-canonical outpoint key {key!r}")
                out = Output.from_obj(obj)
                led.utxos[op] = out
                led._by_pkh.setdefault(out.pkh, set()).add(op)
            for key, by in state["spent"].items():
                op = OutPoint.parse(key)
                if str(op) != key or not _lower_hex(by, 32):
                    raise bad(f"bad spent entry {key!r}")
                led.spent[op] = by
        except LedgerError as exc:
            if exc.code == "bad_snapshot":
                raise
            raise bad(f"{exc.code}: {exc.reason}") from None
        for t in state["applied"]:
            if not _lower_hex(t, 32):
                raise bad("applied contains a malformed txid")
            led.applied.append(t)
            led._applied_set.add(t)
        led.issued, led.fees = state["issued"], state["fees"]
        try:
            led.check_invariants()
        except LedgerError as exc:
            raise bad(exc.reason) from None
        return led

    # -------------------------------------------------------- persistence
    def save(self, path: "str | os.PathLike[str]", pretty: bool = False) -> str:
        """Atomically write the snapshot (temp file + fsync + rename). Returns the state hash."""
        state = self.to_state()
        digest = hashlib.sha256(canonicalize_value(state)).hexdigest()
        doc = {"format": SNAPSHOT_FORMAT, "state": state, "state_sha256": digest}
        text = (json.dumps(doc, indent=2, sort_keys=True) + "\n") if pretty \
            else canonicalize_value(doc).decode("utf-8")
        folder = os.path.dirname(os.path.abspath(path))
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".snapshot-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        return digest

    @classmethod
    def load(cls, path: "str | os.PathLike[str]") -> "Ledger":
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            raise LedgerError("snapshot_unreadable", f"cannot read {path}: {exc.strerror or exc}") from exc
        try:
            doc = parse_strict(raw)
        except LedgerError:
            raise
        except WalletError as exc:
            raise LedgerError("bad_snapshot", str(exc)) from None
        if not isinstance(doc, dict) or set(doc) != {"format", "state", "state_sha256"}:
            raise LedgerError("bad_snapshot", "file must have exactly format, state, state_sha256")
        if doc["format"] != SNAPSHOT_FORMAT:
            raise LedgerError("bad_snapshot", f"unknown snapshot format {doc['format']!r}")
        try:
            digest = hashlib.sha256(canonicalize_value(doc["state"])).hexdigest()
        except WalletError as exc:
            raise LedgerError("bad_snapshot", str(exc)) from None
        if digest != doc["state_sha256"]:
            raise LedgerError("snapshot_corrupt", "state_sha256 does not match the state "
                              "(file was modified or damaged)")
        return cls.from_state(doc["state"])
