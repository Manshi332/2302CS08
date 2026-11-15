"""Node-local chain manager: block index, cumulative work, fork choice, reorganisation.

RULES
  * Every block that passes the context-free checks (PoW, Merkle root, coinbase shape,
    timestamp) and whose parent is known is stored in the block index, on whatever
    branch it extends.
  * Fork choice: the tip with the greatest CUMULATIVE WORK is the active chain. Work of
    a block = floor(2**256/(target+1)); a chain's work is the sum over its blocks.
    A competing tip must have STRICTLY more work to take over, so on a tie the branch seen
    first stays active (first-seen rule).
  * Full validation (every transaction, coinbase value) happens when a block is CONNECTED
    to the UTXO state, i.e. when it becomes part of the active chain. A block on a side
    branch is therefore only "structurally valid" until its branch wins.
  * Reorganisation = disconnect blocks from the old tip down to the fork point (using the
    stored undo data), then connect the new branch from the fork point up. If any block of
    the new branch fails, everything is rolled back to the old chain, the failing block and
    all its descendants are discarded and marked invalid, and BlockError is raised.
  * add_block never leaves the active chain or the UTXO state changed when it raises.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .block import Block, BlockHeader
from .canonical import parse_strict
from .consensus import ChainParams, check_block_structure
from .errors import BlockError, WalletError
from .miner import make_genesis
from .state import BlockUndo, ChainLedger
from .tx import SignedTx

CHAIN_FORMAT = "chainlab-chain-v1"


@dataclass(frozen=True)
class BlockRecord:
    block: Block
    height: int
    chain_work: int          # cumulative work from genesis to this block, inclusive

    @property
    def hash(self) -> bytes:
        return self.block.hash

    @property
    def header(self) -> BlockHeader:
        return self.block.header


@dataclass(frozen=True)
class AddResult:
    status: str                       # extended | reorganized | side_branch | duplicate
    hash: str
    height: int
    chain_work: int
    disconnected: tuple[str, ...] = ()
    connected: tuple[str, ...] = ()
    fork: Optional[str] = None        # hash of the common ancestor (reorganized only)
    returned_txs: tuple[SignedTx, ...] = ()   # txs of disconnected blocks not in the new branch


def _hb(h: "bytes | str") -> bytes:
    return bytes.fromhex(h) if isinstance(h, str) else h


class Chain:
    def __init__(self, params: Optional[ChainParams] = None, clock: Optional[Callable[[], float]] = None):
        self.params = params or ChainParams()
        self.clock = clock or time.time
        self.ledger = ChainLedger(self.params.network_id)
        self._index: dict[bytes, BlockRecord] = {}
        self._children: dict[bytes, list[bytes]] = {}
        self._undo: dict[bytes, BlockUndo] = {}
        self._active: list[bytes] = []
        self._active_height: dict[bytes, int] = {}
        self._arrival: list[bytes] = []
        self._invalid: set[bytes] = set()
        g = make_genesis(self.params)
        self.genesis = g
        rec = BlockRecord(g, 0, g.header.work)
        self._index[g.hash] = rec
        self._children[g.hash] = []
        self._connect(rec)

    # ------------------------------------------------------------- queries
    @property
    def tip(self) -> bytes:
        return self._active[-1]

    @property
    def tip_hex(self) -> str:
        return self.tip.hex()

    @property
    def tip_record(self) -> BlockRecord:
        return self._index[self.tip]

    @property
    def height(self) -> int:
        return len(self._active) - 1

    @property
    def tip_work(self) -> int:
        return self.tip_record.chain_work

    def record(self, h: "bytes | str") -> BlockRecord:
        try:
            return self._index[_hb(h)]
        except KeyError:
            raise BlockError("unknown_block", f"no block {h if isinstance(h, str) else h.hex()} "
                             "in the block index") from None

    def has(self, h: "bytes | str") -> bool:
        return _hb(h) in self._index

    def is_active(self, h: "bytes | str") -> bool:
        return _hb(h) in self._active_height

    def active_hashes(self) -> list[str]:
        return [h.hex() for h in self._active]

    def block_at(self, height: int) -> Block:
        return self._index[self._active[height]].block

    def tips(self) -> list[BlockRecord]:
        """Leaves of the block tree (one per branch), most work first."""
        leaves = [self._index[h] for h, kids in self._children.items() if not kids]
        return sorted(leaves, key=lambda r: (-r.chain_work, -r.height))

    def records(self) -> list[BlockRecord]:
        return [self._index[h] for h in self._arrival_with_genesis()]

    def _arrival_with_genesis(self) -> list[bytes]:
        return [self.genesis.hash] + self._arrival

    # --------------------------------------------------------------- state
    def state_at(self, h: "bytes | str") -> ChainLedger:
        """A COPY of the UTXO state as of block `h` (any known block, any branch)."""
        rec = self.record(h)
        branch: list[BlockRecord] = []
        r = rec
        while r.hash not in self._active_height:
            branch.append(r)
            r = self._index[r.header.prev_hash]
        led = copy.deepcopy(self.ledger)
        for hh in reversed(self._active[r.height + 1:]):
            led.disconnect_block(self._undo[hh])
        for b in reversed(branch):
            led.connect_block(b.block.txs, self.params.subsidy(b.height), b.height)
        return led

    # ------------------------------------------------------------- connect
    def _connect(self, rec: BlockRecord) -> None:
        undo = self.ledger.connect_block(rec.block.txs, self.params.subsidy(rec.height), rec.height)
        self._undo[rec.hash] = undo
        self._active.append(rec.hash)
        self._active_height[rec.hash] = rec.height

    def _disconnect_tip(self) -> bytes:
        h = self._active.pop()
        del self._active_height[h]
        self.ledger.disconnect_block(self._undo.pop(h))
        return h

    # ------------------------------------------------------------ add block
    def _median_time_past(self, parent: BlockRecord) -> int:
        stamps = []
        r: Optional[BlockRecord] = parent
        while r is not None and len(stamps) < self.params.mtp_window:
            stamps.append(r.header.timestamp)
            r = self._index.get(r.header.prev_hash)
        return sorted(stamps)[len(stamps) // 2]

    def add_block(self, block: Block) -> AddResult:
        bh = block.hash
        if bh in self._index:
            rec = self._index[bh]
            return AddResult("duplicate", bh.hex(), rec.height, rec.chain_work)
        if bh in self._invalid:
            raise BlockError("known_invalid", "this block was already rejected as invalid")
        prev = block.header.prev_hash
        if prev in self._invalid:
            raise BlockError("invalid_ancestor", "the parent block was rejected as invalid")
        parent = self._index.get(prev)
        if parent is None:
            raise BlockError("unknown_parent", f"parent {prev.hex()[:16]}... is not known; "
                             "submit the missing ancestors first")
        height = parent.height + 1
        check_block_structure(block, self.params, height)
        ts = block.header.timestamp
        mtp = self._median_time_past(parent)
        if ts <= mtp:
            raise BlockError("timestamp_too_old", f"timestamp {ts} is not after the median of the "
                             f"previous {self.params.mtp_window} blocks ({mtp})")
        if ts > int(self.clock()) + self.params.max_future_seconds:
            raise BlockError("timestamp_too_far_future",
                             f"timestamp {ts} is more than {self.params.max_future_seconds}s ahead of this node's clock")

        rec = BlockRecord(block, height, parent.chain_work + block.header.work)
        self._index[bh] = rec
        self._children[bh] = []
        self._children[parent.hash].append(bh)
        self._arrival.append(bh)

        if rec.chain_work <= self.tip_record.chain_work:
            return AddResult("side_branch", bh.hex(), height, rec.chain_work)
        if prev == self.tip:
            try:
                self._connect(rec)
            except BlockError:
                self._discard(rec)
                raise
            return AddResult("extended", bh.hex(), height, rec.chain_work)
        return self._reorganize(rec)

    def _discard(self, rec: BlockRecord) -> None:
        """Forget `rec` and all its descendants; remember them as invalid."""
        stack = [rec.hash]
        while stack:
            h = stack.pop()
            stack.extend(self._children.get(h, []))
            r = self._index.pop(h, None)
            self._children.pop(h, None)
            if r is not None:
                siblings = self._children.get(r.header.prev_hash)
                if siblings and h in siblings:
                    siblings.remove(h)
            if h in self._arrival:
                self._arrival.remove(h)
            self._invalid.add(h)

    def _reorganize(self, new_tip: BlockRecord) -> AddResult:
        new_branch: list[BlockRecord] = []
        r = new_tip
        while r.hash not in self._active_height:
            new_branch.append(r)
            r = self._index[r.header.prev_hash]
        new_branch.reverse()
        fork = r
        old_branch = self._active[fork.height + 1:]
        old_txs = [tx for h in old_branch for tx in self._index[h].block.txs[1:]]

        for _ in old_branch:
            self._disconnect_tip()
        connected: list[BlockRecord] = []
        try:
            for rec in new_branch:
                self._connect(rec)
                connected.append(rec)
        except BlockError:
            failing = new_branch[len(connected)]
            for _ in connected:
                self._disconnect_tip()
            for h in old_branch:                       # these were valid before; they are again
                self._connect(self._index[h])
            self._discard(failing)
            raise
        new_ids = {t.txid for rec in new_branch for t in rec.block.txs}
        returned = tuple(tx for tx in old_txs if tx.txid not in new_ids)
        return AddResult("reorganized", new_tip.hash.hex(), new_tip.height, new_tip.chain_work,
                         tuple(h.hex() for h in reversed(old_branch)),
                         tuple(r.hash.hex() for r in new_branch), fork.hash.hex(), returned)

    # ------------------------------------------------------------- display
    def render_tree(self, short: int = 8) -> str:
        """ASCII picture of the block tree. '*' marks blocks on the active chain."""
        lines: list[str] = []

        def label(rec: BlockRecord) -> str:
            mark = "*" if rec.hash in self._active_height else " "
            zeros = 256 - rec.header.target.bit_length()
            tip = "  <- TIP" if rec.hash == self.tip else ""
            return (f"{mark} h={rec.height} {rec.hash.hex()[:short]} "
                    f"[work {rec.header.work}, zero-bits~{zeros}, cumulative {rec.chain_work}]{tip}")

        def walk(h: bytes, prefix: str, last: bool, root: bool) -> None:
            rec = self._index[h]
            lines.append(label(rec) if root else f"{prefix}{'`-- ' if last else '|-- '}{label(rec)}")
            kids = self._children[h]
            ext = "" if root else prefix + ("    " if last else "|   ")
            for i, k in enumerate(kids):
                walk(k, ext, i == len(kids) - 1, False)

        walk(self.genesis.hash, "", True, True)
        return "\n".join(lines)

    def render_mermaid(self, short: int = 6) -> str:
        out = ["graph LR"]
        for rec in self.records():
            name = f"b{rec.hash.hex()[:short]}"
            style = "active" if rec.hash in self._active_height else "side"
            out.append(f'  {name}["h={rec.height}<br/>{rec.hash.hex()[:short]}<br/>work {rec.header.work}"]:::{style}')
        for rec in self.records()[1:]:
            out.append(f"  b{rec.header.prev_hash.hex()[:short]} --> b{rec.hash.hex()[:short]}")
        out += ["  classDef active fill:#d4edda,stroke:#28a745", "  classDef side fill:#f8d7da,stroke:#dc3545"]
        return "\n".join(out)

    # --------------------------------------------------------- persistence
    def to_obj(self) -> dict:
        return {"format": CHAIN_FORMAT, "params": self.params.to_obj(),
                "blocks": [self._index[h].block.to_obj() for h in self._arrival]}

    def save(self, path: "str | os.PathLike[str]") -> None:
        text = json.dumps(self.to_obj(), indent=1, sort_keys=True) + "\n"
        folder = os.path.dirname(os.path.abspath(path))
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".chain-")
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

    @classmethod
    def load(cls, path: "str | os.PathLike[str]", clock: Optional[Callable[[], float]] = None) -> "Chain":
        """Rebuild a chain by RE-VALIDATING every stored block in arrival order."""
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            raise BlockError("chain_unreadable", f"cannot read {path}: {exc.strerror or exc}") from exc
        try:
            doc = parse_strict(raw)
        except WalletError as exc:
            raise BlockError("bad_chain_file", str(exc)) from None
        if not isinstance(doc, dict) or set(doc) != {"format", "params", "blocks"} \
                or doc["format"] != CHAIN_FORMAT or not isinstance(doc["blocks"], list):
            raise BlockError("bad_chain_file", f"not a {CHAIN_FORMAT} file")
        chain = cls(ChainParams.from_obj(doc["params"]), clock)
        for obj in doc["blocks"]:
            chain.add_block(Block.from_obj(obj))
        return chain
