"""Scenario runners: fork race between two miners, and 'work beats length'.

Both are fully deterministic (fixed wallets, fixed timestamps, nonces searched from 0),
so the trace, block hashes and final state hashes are identical on every run.
Each runner prints a trace through `emit` and returns the data the report needs.
"""

from __future__ import annotations

from typing import Callable

from .chain import Chain
from .consensus import ChainParams
from .miner import mine_block
from .testkeys import demo_wallet

Emit = Callable[[str], None]
FIXED_CLOCK = lambda: 4_000_000_000  # noqa: E731  (year 2096: never rejects a sim timestamp)


def _short(h: str) -> str:
    return h[:8]


def run_fork_simulation(bits: int = 8, emit: Emit = print) -> dict:
    """Two miners find a block at the same height at (almost) the same time."""
    params = ChainParams(bits=min(bits, 8))
    alice, bob = demo_wallet("alice"), demo_wallet("bob")
    miner_a, miner_b = demo_wallet("miner-a"), demo_wallet("miner-b")
    node_a, node_b = Chain(params, FIXED_CLOCK), Chain(params, FIXED_CLOCK)
    out: dict = {"node_a": node_a, "node_b": node_b, "trees": {}, "blocks": {}}

    def step(title: str) -> None:
        emit(f"\n[{title}]")

    def balances(chain: Chain, label: str) -> str:
        return (f"{label}: alice={alice.balance(chain.ledger)} bob={bob.balance(chain.ledger)} "
                f"miner-a={miner_a.balance(chain.ledger)} miner-b={miner_b.balance(chain.ledger)}")

    emit(f"fork simulation: two nodes, two miners, difficulty {bits} bits (~{2 ** bits} attempts/block)")
    emit("=" * 72)
    step("0. both nodes start from the same genesis")
    assert node_a.tip == node_b.tip
    emit(f"    genesis {_short(node_a.tip_hex)}")

    step("1. shared history: Alice mines blocks 1 and 2, both nodes accept them")
    for n in (1, 2):
        r = mine_block(node_a, alice.primary_address, bits=bits)
        for node in (node_a, node_b):
            node.add_block(r.block)
        emit(f"    block {n}: {_short(r.block.hash_hex)}  attempts={r.attempts}")
    emit("    " + balances(node_a, "balances"))
    common = node_a.tip

    step("2. fork: both miners build on block 2 at the same time")
    pay = alice.build_payment(node_a.ledger, bob.primary_address, 30, fee=1)
    ra = mine_block(node_a, miner_a.primary_address, txs=[pay], bits=bits)
    rb = mine_block(node_b, miner_b.primary_address, bits=bits)
    out["blocks"].update(a3=ra.block, b3=rb.block)
    emit(f"    Miner A: block A3 {_short(ra.block.hash_hex)} contains Alice->Bob 30 (fee 1), attempts={ra.attempts}")
    emit(f"    Miner B: block B3 {_short(rb.block.hash_hex)} coinbase only,           attempts={rb.attempts}")
    node_a.add_block(ra.block)
    node_b.add_block(rb.block)
    emit(f"    node A tip = {_short(node_a.tip_hex)} (A3)   node B tip = {_short(node_b.tip_hex)} (B3)")
    emit("    " + balances(node_a, "node A sees"))
    emit("    " + balances(node_b, "node B sees"))

    step("3. the blocks cross on the network: equal work, first seen stays active")
    res_a = node_a.add_block(rb.block)
    res_b = node_b.add_block(ra.block)
    emit(f"    node A receives B3 -> {res_a.status}; node B receives A3 -> {res_b.status}")
    emit(f"    tips still differ: A={_short(node_a.tip_hex)} B={_short(node_b.tip_hex)} "
         f"(cumulative work {node_a.tip_work} vs {node_b.tip_work})")
    out["trees"]["split"] = node_a.render_tree()
    out["mermaid_split"] = node_a.render_mermaid()
    emit("    node A's block tree:\n" + "\n".join("      " + ln for ln in out["trees"]["split"].splitlines()))

    step("4. Miner B finds B4 on top of B3 and broadcasts it")
    r4 = mine_block(node_b, miner_b.primary_address, bits=bits)
    out["blocks"]["b4"] = r4.block
    node_b.add_block(r4.block)
    res = node_a.add_block(r4.block)
    out["reorg"] = res
    emit(f"    B4 {_short(r4.block.hash_hex)} (attempts={r4.attempts})")
    emit(f"    node A receives B4 -> {res.status}: fork point {_short(res.fork)}, "
         f"disconnected {[_short(h) for h in res.disconnected]}, connected {[_short(h) for h in res.connected]}")
    emit(f"    transactions returned to the mempool: {[t.txid[:8] for t in res.returned_txs]}")
    emit("    " + balances(node_a, "node A now"))
    emit("    (Bob's payment is gone: its block was orphaned; Alice's coins are spendable again)")
    out["trees"]["resolved"] = node_a.render_tree()
    out["mermaid_resolved"] = node_a.render_mermaid()
    emit("    node A's block tree:\n" + "\n".join("      " + ln for ln in out["trees"]["resolved"].splitlines()))

    step("5. the orphaned payment is re-mined on the winning branch")
    r5 = mine_block(node_a, miner_b.primary_address, txs=list(res.returned_txs), bits=bits)
    node_a.add_block(r5.block)
    node_b.add_block(r5.block)
    out["blocks"]["b5"] = r5.block
    emit(f"    B5 {_short(r5.block.hash_hex)} includes the returned transaction; both nodes accept it")
    emit("    " + balances(node_a, "node A"))
    emit("    " + balances(node_b, "node B"))

    converged = (node_a.tip == node_b.tip and node_a.ledger.state_hash() == node_b.ledger.state_hash())
    node_a.ledger.check_invariants()
    node_b.ledger.check_invariants()
    emit(f"\nconverged: same tip {_short(node_a.tip_hex)} and same ledger state hash: {converged}")
    emit(f"state hash {node_a.ledger.state_hash()}")
    out["converged"] = converged
    out["trees"]["final"] = node_a.render_tree()
    out["common"] = common
    return out


def run_work_vs_length(low_bits: int = 4, high_bits: int = 10, low_blocks: int = 5,
                       high_blocks: int = 2, emit: Emit = print) -> dict:
    """A LONGER chain of easy blocks loses to a SHORTER chain of hard blocks."""
    params = ChainParams(min_bits=1, bits=low_bits)
    w = demo_wallet("alice")
    low_miner, high_miner = Chain(params, FIXED_CLOCK), Chain(params, FIXED_CLOCK)
    low = []
    for _ in range(low_blocks):
        b = mine_block(low_miner, w.primary_address, bits=low_bits).block
        low_miner.add_block(b)
        low.append(b)
    high = []
    for _ in range(high_blocks):
        b = mine_block(high_miner, w.primary_address, bits=high_bits).block
        high_miner.add_block(b)
        high.append(b)
    emit(f"work vs length: branch L = {low_blocks} blocks at {low_bits} bits "
         f"(work {2 ** low_bits} each, total {low_blocks * 2 ** low_bits}); "
         f"branch H = {high_blocks} blocks at {high_bits} bits "
         f"(work {2 ** high_bits} each, total {high_blocks * 2 ** high_bits})")
    emit("=" * 72)

    emit("\n[node 1 sees H first, then the longer L]")
    n1 = Chain(params, FIXED_CLOCK)
    for b in high:
        emit(f"    H block -> {n1.add_block(b).status}")
    low_statuses = []
    for i, b in enumerate(low, 1):
        r = n1.add_block(b)
        low_statuses.append(r.status)
        emit(f"    L block {i} (height {r.height}) -> {r.status}   active tip height {n1.height}, work {n1.tip_work}")
    emit(f"    result: node 1 stays on H although L is {low_blocks - high_blocks} blocks longer")
    out = {"node1": n1}

    emit("\n[node 2 sees L first (it is active), then H]")
    n2 = Chain(params, FIXED_CLOCK)
    for b in low:
        n2.add_block(b)
    emit(f"    after L: height {n2.height}, work {n2.tip_work}")
    for i, b in enumerate(high, 1):
        r = n2.add_block(b)
        extra = (f": disconnected {len(r.disconnected)} L block(s), connected {len(r.connected)} H block(s)"
                 if r.status == "reorganized" else "")
        emit(f"    H block {i} -> {r.status}{extra}   active tip height {n2.height}, work {n2.tip_work}")
    same = n1.tip == n2.tip and n1.ledger.state_hash() == n2.ledger.state_hash()
    emit(f"\nboth nodes end on the same tip and the same UTXO state: {same}")
    out.update(node2=n2, same=same, tree=n1.render_tree(), low_statuses=low_statuses,
               low_work=low_blocks * 2 ** low_bits, high_work=high_blocks * 2 ** high_bits)
    return out
