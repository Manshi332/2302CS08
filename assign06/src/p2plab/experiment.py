"""Example experiment: partition five nodes (2 + 3), mine on both sides, heal, converge.

    python -m p2plab experiment [--out logs/experiment.jsonl]
"""

from __future__ import annotations

import asyncio
import time

from chainlab import ChainParams
from chainlab.testkeys import demo_wallet

from .log import EventLog
from .node import Node, NodeConfig


async def wait_until(cond, timeout: float = 30.0, what: str = "condition") -> None:
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return
        await asyncio.sleep(0.1)
    raise TimeoutError(f"timed out waiting for {what}")


def show(title: str, nodes) -> None:
    print(f"\n== {title}")
    for n in nodes:
        print(f"  {n.id}: height={n.chain.height} tip={n.chain.tip_hex[:12]} "
              f"mempool={len(n.mempool)} peers={len(n.ready_peers())}")


async def run(out: str = "logs/experiment.jsonl") -> dict:
    log = EventLog(out)
    params = ChainParams(bits=4)
    cfg = NodeConfig(latency=(0.01, 0.05), tick=0.3, ping_interval=2.0, pong_timeout=3.0)
    nodes = [Node(f"n{i}", params, config=cfg, log=log) for i in range(5)]
    for n in nodes:
        await n.start()
    for n in nodes[1:]:                       # everyone bootstraps from n0 and discovers the rest
        n.seeds.append((nodes[0].host, nodes[0].port))
    for n in nodes[1:]:
        await n.connect(nodes[0].host, nodes[0].port)
    await wait_until(lambda: all(len(n.ready_peers()) >= 4 for n in nodes), 30, "full mesh via discovery")
    show("connected (discovery)", nodes)

    alice, bob = demo_wallet("alice"), demo_wallet("bob")
    miner_a, miner_b = demo_wallet("miner"), demo_wallet("carol")
    side_a, side_b = nodes[:2], nodes[2:]

    nodes[0].mine(alice.primary_address)                      # common history: alice gets coins
    await wait_until(lambda: all(n.chain.height == 1 for n in nodes), 20, "block 1 everywhere")
    pay = alice.build_payment(nodes[0].chain.ledger, bob.primary_address, 30, fee=1)

    ids_a, ids_b = [n.id for n in side_a], [n.id for n in side_b]
    for n in side_a:
        n.set_partition(ids_b)
    for n in side_b:
        n.set_partition(ids_a)
    log.log("sim", "partition_start", groups=[ids_a, ids_b])

    nodes[0].submit_tx(pay)                                   # tx exists only on side A
    await wait_until(lambda: pay.txid in nodes[1].mempool, 10, "tx relay inside side A")
    nodes[0].mine(miner_a.primary_address)                    # A mines 1 block (contains the tx)
    nodes[2].mine(miner_b.primary_address)                    # B mines 1 block ...
    await wait_until(lambda: all(n.chain.height == 2 for n in nodes), 20, "one block per side")
    nodes[3].mine(miner_b.primary_address)                    # ... and one more on branch B
    await wait_until(lambda: all(n.chain.height == 3 for n in side_b), 20, "extra block on B")
    await wait_until(lambda: nodes[1].chain.height == 2, 5, "A side stable")
    show("partitioned (A has 2 blocks, B has 3)", nodes)
    assert len({n.chain.tip_hex for n in nodes}) == 2

    for n in nodes:
        n.heal_partition()
    log.log("sim", "partition_healed")
    for n in nodes:
        await n.resync()
    await wait_until(lambda: len({n.chain.tip_hex for n in nodes}) == 1 and nodes[0].chain.height == 3
                     and all(pay.txid in n.mempool for n in nodes), 30, "convergence + tx back in mempools")
    show("healed (converged)", nodes)

    summary = {"tip": nodes[0].chain.tip_hex, "height": nodes[0].chain.height,
               "tx_back_in_all_mempools": all(pay.txid in n.mempool for n in nodes),
               "reorgs": sum(1 for e in log.events if e["event"] == "reorg")}
    print("\nresult:", summary)
    log.log("sim", "experiment_done", **summary)
    for n in nodes:
        await n.stop()
    log.close()
    return summary
