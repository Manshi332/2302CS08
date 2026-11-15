"""A P2P node: handshake, peer discovery, inventory relay, mempool, blocks, scoring.

One asyncio TCP server per node. Every connection is a Peer with its own send queue
(so simulated latency never reorders messages) and its own token-bucket rate limiter.

Relay rule: announce `inv` first; a peer sends `getdata` only for objects it does not have;
only then is the full `tx` / `block` sent.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Callable, Optional

from chainlab import Block, BlockError, Chain, ChainParams, mine_block
from chainlab.errors import WalletError

from . import messages as M
from .log import EventLog
from .mempool import Mempool, MempoolReject


@dataclass
class NodeConfig:
    max_outbound: int = 4
    max_peers: int = 8
    connect_timeout: float = 3.0
    handshake_timeout: float = 5.0
    ping_interval: float = 5.0
    pong_timeout: float = 5.0
    request_timeout: float = 5.0
    tick: float = 0.5                      # maintenance loop period
    rate_per_sec: float = 50.0             # token bucket refill
    rate_burst: float = 100.0
    ban_threshold: int = -100
    ban_seconds: float = 60.0
    max_orphans: int = 100
    latency: tuple[float, float] = (0.0, 0.0)   # per-message send delay range (seconds)
    mempool_ttl: float = 3600.0
    mempool_max: int = 1000
    min_fee_rate: float = 0.0


# penalties for rejected objects, by reject code (anything unlisted costs 10)
_FREE = {"duplicate", "duplicate_transaction"}
_MINOR = {"conflict", "mempool_full", "low_fee", "too_large", "missing_input", "unknown_input"}
_MAX_SCORE = 20


class TokenBucket:
    def __init__(self, rate: float, burst: float, now: float):
        self.rate, self.burst, self.tokens, self.t = rate, burst, burst, now

    def allow(self, now: float) -> bool:
        self.tokens = min(self.burst, self.tokens + (now - self.t) * self.rate)
        self.t = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class Peer:
    def __init__(self, reader, writer, outbound: bool, cfg: NodeConfig, now: float):
        self.reader, self.writer, self.outbound = reader, writer, outbound
        self.id: Optional[str] = None
        self.listen: Optional[tuple[str, int]] = None
        self.got_version = self.got_verack = self.ready = False
        self.score = 0
        self.known: set[str] = set()                 # object ids this peer has told us / been told
        self.bucket = TokenBucket(cfg.rate_per_sec, cfg.rate_burst, now)
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self.ping_nonce: Optional[int] = None
        self.ping_sent = 0.0
        self.last_ping = now
        self.closed = False
        self.writer_task: Optional[asyncio.Task] = None


class Node:
    def __init__(self, node_id: str, params: Optional[ChainParams] = None, *, host: str = "127.0.0.1",
                 port: int = 0, config: Optional[NodeConfig] = None, log: Optional[EventLog] = None,
                 clock: Callable[[], float] = time.time):
        self.id, self.host, self.port = node_id, host, port
        self.cfg = config or NodeConfig()
        self.clock = clock
        self.events = log or EventLog(clock=clock)
        self.chain = Chain(params or ChainParams(), clock)
        self.mempool = Mempool(self.chain, clock, max_txs=self.cfg.mempool_max, ttl=self.cfg.mempool_ttl,
                               min_fee_rate=self.cfg.min_fee_rate)
        self.peers: dict[str, Peer] = {}
        self.known_addrs: dict[str, tuple[str, int]] = {}
        self.banned: dict[str, float] = {}
        self.blocked: set[str] = set()                # simulated partition: drop traffic with these ids
        self.link_latency: dict[str, tuple[float, float]] = {}
        self.requested: dict[str, tuple[Optional[str], float]] = {}    # object id -> (peer id, deadline)
        self.orphans: dict[bytes, Block] = {}
        self.seeds: list[tuple[str, int]] = []
        self._connecting: set[tuple[str, int]] = set()
        self._server: Optional[asyncio.AbstractServer] = None
        self._tasks: set[asyncio.Task] = set()
        self._maint: Optional[asyncio.Task] = None
        self._running = False

    # ---------------------------------------------------------------- utils
    def log(self, event: str, peer: Optional[str] = None, obj: Optional[str] = None, **kw) -> None:
        self.events.log(self.id, event, peer, obj, **kw)

    def _spawn(self, coro) -> asyncio.Task:
        t = asyncio.ensure_future(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        return t

    def ready_peers(self) -> list[Peer]:
        return [p for p in self.peers.values() if p.ready and not p.closed]

    # ------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        self._server = await asyncio.start_server(lambda r, w: self._handle(r, w, False), self.host, self.port)
        self.port = self._server.sockets[0].getsockname()[1]
        self._running = True
        self._maint = self._spawn(self._maintenance())
        self.log("node_started", port=self.port)

    async def stop(self) -> None:
        self._running = False
        if self._server:
            self._server.close()
        for p in list(self.peers.values()):
            self._close(p, "node_stopping")
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self.log("node_stopped")

    async def connect(self, host: str, port: int) -> None:
        key = (host, port)
        if key in self._connecting or (host, port) == (self.host, self.port):
            return
        self._connecting.add(key)
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), self.cfg.connect_timeout)
        except (OSError, asyncio.TimeoutError) as exc:
            self.log("connect_failed", addr=f"{host}:{port}", error=type(exc).__name__)
            return
        finally:
            self._connecting.discard(key)
        self._spawn(self._handle(reader, writer, True))

    # ----------------------------------------------------------- connection
    async def _handle(self, reader, writer, outbound: bool) -> None:
        peer = Peer(reader, writer, outbound, self.cfg, self.clock())
        addr = writer.get_extra_info("peername")
        if not outbound and len(self.peers) >= self.cfg.max_peers:
            self.log("connection_refused", addr=str(addr), reason="max_peers")
            writer.close()
            return
        self.log("connection_open", addr=str(addr), direction="out" if outbound else "in")
        peer.writer_task = asyncio.ensure_future(self._writer(peer))
        self._send(peer, "version", {"proto": M.PROTO_VERSION, "node_id": self.id, "port": self.port,
                                     "network": self.chain.params.network_id,
                                     "genesis": self.chain.genesis.hash_hex,
                                     "height": self.chain.height, "tip": self.chain.tip_hex})
        try:
            while not peer.closed:
                idle = self.cfg.handshake_timeout if not peer.ready else \
                    2 * (self.cfg.ping_interval + self.cfg.pong_timeout)
                try:
                    body = await asyncio.wait_for(M.read_frame(reader), idle)
                except asyncio.TimeoutError:
                    self.log("peer_timeout", peer=peer.id, reason="handshake" if not peer.ready else "idle")
                    break
                except (asyncio.IncompleteReadError, ConnectionError):
                    break
                await self._on_frame(peer, body)
        except M.ProtocolError as exc:                      # fatal framing error
            self._protocol_error(peer, exc)
        except Exception as exc:                            # never let one peer kill the node
            self.log("handler_exception", peer=peer.id, error=f"{type(exc).__name__}: {exc}")
        finally:
            self._close(peer, "connection_ended")

    async def _writer(self, peer: Peer) -> None:
        try:
            while True:
                data = await peer.queue.get()
                if data is None:
                    break
                lo, hi = self.link_latency.get(peer.id or "", self.cfg.latency)
                if hi > 0:
                    await asyncio.sleep(random.uniform(lo, hi))
                peer.writer.write(data)
                await peer.writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            peer.closed = True

    def _send(self, peer: Peer, mtype: str, payload: dict) -> None:
        if peer.closed:
            return
        if peer.id in self.blocked:
            self.log("drop_partition", peer=peer.id, direction="out", type=mtype)
            return
        try:
            peer.queue.put_nowait(M.encode(mtype, payload))
        except asyncio.QueueFull:
            self.log("send_queue_full", peer=peer.id, type=mtype)
        except M.ProtocolError as exc:
            self.log("encode_failed", peer=peer.id, type=mtype, error=exc.code)

    def _close(self, peer: Peer, reason: str) -> None:
        if peer.closed and peer.id not in self.peers:
            return
        if not peer.closed:
            peer.closed = True
        try:
            peer.queue.put_nowait(None)
        except asyncio.QueueFull:
            pass
        try:
            peer.writer.close()
        except Exception:
            pass
        if peer.id and self.peers.get(peer.id) is peer:
            del self.peers[peer.id]
            self.log("peer_disconnected", peer=peer.id, reason=reason)

    # ------------------------------------------------------------ scoring
    def _penalize(self, peer: Peer, points: int, reason: str) -> None:
        if points <= 0:
            return
        peer.score -= points
        self.log("peer_penalized", peer=peer.id, points=points, reason=reason, score=peer.score)
        if peer.score <= self.cfg.ban_threshold:
            if peer.id:
                self.banned[peer.id] = self.clock() + self.cfg.ban_seconds
            self.log("peer_banned", peer=peer.id, seconds=self.cfg.ban_seconds)
            self._send(peer, "error", {"code": "banned", "reason": "misbehaviour score too low"})
            self._close(peer, "banned")

    def _reward(self, peer: Peer) -> None:
        peer.score = min(_MAX_SCORE, peer.score + 1)

    def _reject_penalty(self, code: str) -> int:
        return 0 if code in _FREE else 2 if code in _MINOR else 10

    def _protocol_error(self, peer: Peer, exc: M.ProtocolError) -> None:
        self.log("protocol_error", peer=peer.id, code=exc.code, reason=exc.reason, fatal=exc.fatal)
        self._send(peer, "error", {"code": exc.code, "reason": exc.reason[:200]})
        if exc.code in ("duplicate_connection", "self_connection"):   # not misbehaviour: just hang up
            self._close(peer, exc.code)
            return
        self._penalize(peer, 100 if exc.fatal else 20, exc.code)
        if exc.fatal:
            self._close(peer, exc.code)

    # --------------------------------------------------------------- inbound
    async def _on_frame(self, peer: Peer, body: bytes) -> None:
        if peer.id in self.blocked:
            self.log("drop_partition", peer=peer.id, direction="in")
            return
        if not peer.bucket.allow(self.clock()):
            self.log("rate_limited", peer=peer.id)
            self._penalize(peer, 5, "rate_limit")
            return
        try:
            mtype, payload = M.decode(body)
            if not peer.ready and mtype not in ("version", "verack", "error"):
                raise M.ProtocolError("handshake_required", f"{mtype} before handshake completed", fatal=True)
            self.log("msg_in", peer=peer.id, type=mtype)
            getattr(self, "_on_" + mtype)(peer, payload)
        except M.ProtocolError as exc:
            self._protocol_error(peer, exc)

    def _on_version(self, peer: Peer, p: dict) -> None:
        if peer.got_version:
            raise M.ProtocolError("duplicate_version", "version sent twice")
        if p["proto"] != M.PROTO_VERSION:
            raise M.ProtocolError("unsupported_version", f"proto {p['proto']}", fatal=True)
        if p["network"] != self.chain.params.network_id or p["genesis"] != self.chain.genesis.hash_hex:
            raise M.ProtocolError("wrong_network", "network or genesis mismatch", fatal=True)
        if p["node_id"] == self.id:
            raise M.ProtocolError("self_connection", "connected to ourselves", fatal=True)
        if self.banned.get(p["node_id"], 0) > self.clock():
            raise M.ProtocolError("banned", "peer is banned", fatal=True)
        if p["node_id"] in self.peers and not self.peers[p["node_id"]].closed:
            raise M.ProtocolError("duplicate_connection", "already connected", fatal=True)
        peer.id = p["node_id"]
        peername = peer.writer.get_extra_info("peername")
        peer.listen = (peername[0] if peername else "127.0.0.1", p["port"])
        peer.got_version = True
        self.peers[peer.id] = peer
        self.known_addrs[peer.id] = peer.listen
        self._send(peer, "verack", {})
        self._maybe_ready(peer)

    def _on_verack(self, peer: Peer, p: dict) -> None:
        peer.got_verack = True
        self._maybe_ready(peer)

    def _maybe_ready(self, peer: Peer) -> None:
        if peer.ready or not (peer.got_version and peer.got_verack):
            return
        peer.ready = True
        self.log("peer_ready", peer=peer.id, direction="out" if peer.outbound else "in")
        self._send(peer, "getaddr", {})
        self.announce_all(peer)

    def _on_getaddr(self, peer: Peer, p: dict) -> None:
        peers = [{"id": i, "host": h, "port": pt} for i, (h, pt) in self.known_addrs.items()
                 if i != peer.id][:M.MAX_ADDRS]
        self._send(peer, "addr", {"peers": peers})

    def _on_addr(self, peer: Peer, p: dict) -> None:
        added = 0
        for e in p["peers"]:
            if e["id"] != self.id and e["id"] not in self.known_addrs and len(self.known_addrs) < 1000:
                self.known_addrs[e["id"]] = (e["host"], e["port"])
                added += 1
        self.log("addr_received", peer=peer.id, count=len(p["peers"]), new=added)

    def _on_ping(self, peer: Peer, p: dict) -> None:
        self._send(peer, "pong", {"nonce": p["nonce"]})

    def _on_pong(self, peer: Peer, p: dict) -> None:
        if peer.ping_nonce is not None and p["nonce"] == peer.ping_nonce:
            peer.ping_nonce = None
            self.log("pong", peer=peer.id, rtt=round(self.clock() - peer.ping_sent, 4))
        else:
            self._penalize(peer, 1, "unsolicited_pong")

    def _on_error(self, peer: Peer, p: dict) -> None:
        self.log("peer_error", peer=peer.id, code=p["code"], reason=p["reason"])

    def _on_notfound(self, peer: Peer, p: dict) -> None:
        for it in p["items"]:
            self.requested.pop(it["id"], None)
        self.log("notfound", peer=peer.id, count=len(p["items"]))

    # ---------------------------------------------------------- inventory
    def _have(self, kind: str, oid: str) -> bool:
        if kind == "tx":
            return oid in self.mempool
        return self.chain.has(oid) or bytes.fromhex(oid) in self.orphans

    def _on_inv(self, peer: Peer, p: dict) -> None:
        want = []
        for it in p["items"]:
            peer.known.add(it["id"])
            if self._have(it["kind"], it["id"]) or it["id"] in self.requested:
                continue
            want.append(it)
            self.requested[it["id"]] = (peer.id, self.clock() + self.cfg.request_timeout)
        self.log("inv_received", peer=peer.id, count=len(p["items"]), requested=len(want))
        if want:
            self._send(peer, "getdata", {"items": want})

    def _on_getdata(self, peer: Peer, p: dict) -> None:
        missing = []
        for it in p["items"]:
            oid = it["id"]
            if it["kind"] == "block" and self.chain.has(oid):
                self._send(peer, "block", {"block": self.chain.record(oid).block.to_obj()})
                self.log("block_sent", peer=peer.id, obj=oid)
            elif it["kind"] == "tx" and self.mempool.get(oid) is not None:
                self._send(peer, "tx", {"tx": self.mempool.get(oid).to_obj()})
                self.log("tx_sent", peer=peer.id, obj=oid)
            else:
                missing.append(it)
            peer.known.add(oid)
        if missing:
            self._send(peer, "notfound", {"items": missing})

    def _inv_items(self, kind: str, ids) -> list[dict]:
        return [{"kind": kind, "id": i} for i in ids]

    def announce(self, items: list[dict], exclude: Optional[str] = None) -> None:
        for peer in self.ready_peers():
            if peer.id == exclude:
                continue
            fresh = [it for it in items if it["id"] not in peer.known]
            for i in range(0, len(fresh), M.MAX_INV_ITEMS):
                chunk = fresh[i:i + M.MAX_INV_ITEMS]
                peer.known.update(it["id"] for it in chunk)
                self._send(peer, "inv", {"items": chunk})

    def announce_all(self, peer: Peer) -> None:
        """Offer everything we have (active chain + mempool). Used on connect and after a partition heals."""
        items = self._inv_items("block", self.chain.active_hashes()[1:]) + \
            self._inv_items("tx", self.mempool.ids())
        for i in range(0, len(items), M.MAX_INV_ITEMS):
            self._send(peer, "inv", {"items": items[i:i + M.MAX_INV_ITEMS]})

    async def resync(self) -> None:
        """Re-offer our inventory to every peer (called after healing a partition)."""
        for peer in self.ready_peers():
            peer.known.clear()
            self.announce_all(peer)
        self.log("resync", peers=len(self.ready_peers()))

    # -------------------------------------------------------------- objects
    def _on_tx(self, peer: Peer, p: dict) -> None:
        try:
            from chainlab.tx import SignedTx
            txid = SignedTx.from_obj(p["tx"]).txid
        except WalletError as exc:
            self._penalize(peer, 20, "malformed_tx")
            self.log("tx_rejected", peer=peer.id, code="malformed_tx", reason=str(exc))
            return
        self.requested.pop(txid, None)
        peer.known.add(txid)
        self._admit_tx(p["tx"], source=peer)

    def _admit_tx(self, tx, source: Optional[Peer] = None) -> Optional[str]:
        try:
            entry, replaced = self.mempool.add(tx)
        except MempoolReject as exc:
            txid = getattr(tx, "txid", None)
            self.log("tx_rejected", peer=source.id if source else None, obj=txid, code=exc.code, reason=exc.reason)
            if source:
                self._penalize(source, self._reject_penalty(exc.code), "tx_" + exc.code)
            return None
        self.log("tx_accepted", peer=source.id if source else None, obj=entry.txid, fee=entry.fee,
                 fee_rate=round(entry.fee_rate, 5), replaced=replaced)
        if source:
            self._reward(source)
        self.announce(self._inv_items("tx", [entry.txid]), exclude=source.id if source else None)
        return entry.txid

    def _on_block(self, peer: Peer, p: dict) -> None:
        try:
            block = Block.from_obj(p["block"])
        except WalletError as exc:
            self._penalize(peer, 20, "malformed_block")
            self.log("block_rejected", peer=peer.id, code="malformed_block", reason=str(exc))
            return
        self.requested.pop(block.hash_hex, None)
        peer.known.add(block.hash_hex)
        self._accept_block(block, peer)

    def _accept_block(self, block: Block, source: Optional[Peer] = None) -> None:
        bh = block.hash_hex
        try:
            res = self.chain.add_block(block)
        except BlockError as exc:
            if exc.code == "unknown_parent":
                self._store_orphan(block, source)
                return
            self.log("block_rejected", peer=source.id if source else None, obj=bh, code=exc.code, reason=exc.reason)
            if source:
                self._penalize(source, 20 if exc.code.startswith("timestamp") else 50, "block_" + exc.code)
            return
        if res.status == "duplicate":
            return
        self.log("block_accepted", peer=source.id if source else None, obj=bh, status=res.status,
                 height=res.height, tip=self.chain.tip_hex)
        if source:
            self._reward(source)
        if res.status in ("extended", "reorganized"):
            gained, dropped = self.mempool.reconcile(res.returned_txs)
            if res.status == "reorganized":
                self.log("reorg", obj=bh, fork=res.fork, disconnected=list(res.disconnected),
                         connected=list(res.connected), returned_to_mempool=gained)
            ids = list(res.connected) if res.status == "reorganized" else [bh]
            self.announce(self._inv_items("block", ids), exclude=source.id if source else None)
            if gained:
                self.announce(self._inv_items("tx", gained))
        # a new block may be the parent of orphans we were holding
        for child in [b for b in self.orphans.values() if b.header.prev_hash == block.hash]:
            del self.orphans[child.hash]
            self._accept_block(child, source)

    def _store_orphan(self, block: Block, source: Optional[Peer]) -> None:
        if len(self.orphans) >= self.cfg.max_orphans:
            self.orphans.pop(next(iter(self.orphans)))
        self.orphans[block.hash] = block
        parent = block.header.prev_hash.hex()
        self.log("orphan_stored", peer=source.id if source else None, obj=block.hash_hex, parent=parent)
        if source and parent not in self.requested:
            self.requested[parent] = (source.id, self.clock() + self.cfg.request_timeout)
            self._send(source, "getdata", {"items": [{"kind": "block", "id": parent}]})

    # -------------------------------------------------------- local actions
    def submit_tx(self, tx) -> Optional[str]:
        """A transaction created at this node (e.g. by a wallet)."""
        return self._admit_tx(tx)

    def mine(self, address: str) -> Block:
        txs = self.mempool.select(self.chain.params.max_block_txs - 1)
        block = mine_block(self.chain, address, txs=txs).block
        self.log("block_mined", obj=block.hash_hex, txs=len(txs))
        self._accept_block(block)
        return block

    def set_partition(self, blocked_ids) -> None:
        self.blocked = set(blocked_ids)
        self.log("partition_set", blocked=sorted(self.blocked))

    def heal_partition(self) -> None:
        self.blocked.clear()
        self.log("partition_healed")

    # ---------------------------------------------------------- maintenance
    async def _maintenance(self) -> None:
        while self._running:
            await asyncio.sleep(self.cfg.tick)
            now = self.clock()
            for pid in [i for i, t in self.banned.items() if t <= now]:
                del self.banned[pid]
            for oid in [o for o, (_, dl) in self.requested.items() if dl <= now]:
                pid, _ = self.requested.pop(oid)
                self.log("request_timeout", peer=pid, obj=oid)
                if pid in self.peers:
                    self._penalize(self.peers[pid], 1, "request_timeout")
            for txid in self.mempool.expire():
                self.log("tx_expired", obj=txid)
            for peer in self.ready_peers():
                if peer.ping_nonce is not None and now - peer.ping_sent > self.cfg.pong_timeout:
                    self.log("peer_timeout", peer=peer.id, reason="pong")
                    self._close(peer, "pong_timeout")
                elif peer.ping_nonce is None and now - peer.last_ping >= self.cfg.ping_interval:
                    peer.ping_nonce, peer.ping_sent, peer.last_ping = random.getrandbits(32), now, now
                    self._send(peer, "ping", {"nonce": peer.ping_nonce})
            if not self.peers:
                for h, pt in self.seeds:
                    self._spawn(self.connect(h, pt))
            outbound = sum(1 for p in self.peers.values() if p.outbound)
            if outbound < self.cfg.max_outbound:
                for pid, (h, pt) in list(self.known_addrs.items()):
                    if pid in self.peers or pid in self.banned or pid == self.id or pid in self.blocked:
                        continue
                    if (h, pt) in self._connecting:
                        continue
                    self._spawn(self.connect(h, pt))
                    break
