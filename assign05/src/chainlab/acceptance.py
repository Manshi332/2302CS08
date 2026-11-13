"""The assignment's acceptance checks, executed and printed as a PASS/FAIL trace.

Every 'reject' check records the chain's tip and complete state hash BEFORE the bad
block is submitted and proves both are bit-for-bit identical AFTER the rejection.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Callable

from .block import Block, BlockHeader
from .chain import Chain
from .consensus import ChainParams
from .errors import BlockError
from .miner import make_block, mine_block, solve_block, solve_header
from .simulate import FIXED_CLOCK, run_work_vs_length
from .testkeys import demo_wallet
from .tx import MAX_VALUE, OutPoint, Output, SignedTx, TxBody, sign_body

Emit = Callable[[str], None]


class _Checks:
    def __init__(self, emit: Emit):
        self.emit = emit
        self.results: list[tuple[str, bool, str]] = []

    def record(self, name: str, ok: bool, detail: str) -> None:
        self.results.append((name, ok, detail))
        self.emit(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    def expect_reject(self, name: str, chain: Chain, block: Block, code: str,
                      inner: str | None = None) -> None:
        before = (chain.tip, chain.ledger.state_hash(), chain.active_hashes())
        try:
            chain.add_block(block)
        except BlockError as exc:
            unchanged = before == (chain.tip, chain.ledger.state_hash(), chain.active_hashes())
            ok = exc.code == code and (inner is None or exc.inner == inner) and unchanged
            tag = exc.code + (f"/{exc.inner}" if exc.inner else "")
            self.record(name, ok, f"rejected with {tag}; active chain and state unchanged: {unchanged}")
        else:
            self.record(name, False, "block was ACCEPTED but should have been rejected")


def run_acceptance(emit: Emit = print) -> list[tuple[str, bool, str]]:
    ck = _Checks(emit)
    params = ChainParams(bits=4)
    alice, bob, carol = demo_wallet("alice"), demo_wallet("bob"), demo_wallet("carol")
    miner = demo_wallet("miner")
    chain = Chain(params, FIXED_CLOCK)
    for _ in range(3):
        chain.add_block(mine_block(chain, alice.primary_address).block)
    emit("acceptance checks (chain at height 3, Alice owns 3 coinbase outputs of 50)")
    emit("=" * 72)

    # ---- 1. work beats length -------------------------------------------------
    emit("\n1. A longer but lower-work branch must lose to a shorter higher-work branch")
    quiet = run_work_vs_length(emit=lambda _m: None)
    n1, n2 = quiet["node1"], quiet["node2"]
    ck.record("longer low-work branch loses",
              n1.height == 2 and quiet["low_statuses"] == ["side_branch"] * 5,
              f"node 1 stayed on the 2-block chain (work {n1.tip_work}); all 5 blocks of the longer "
              f"branch (work {quiet['low_work']}) were stored as side branch")
    ck.record("high-work branch wins by reorg", quiet["same"] and n2.height == 2,
              f"node 2 reorganised from 5 blocks to 2; both nodes share tip and UTXO state: {quiet['same']}")

    # ---- 2. bad merkle root ---------------------------------------------------
    emit("\n2. Incorrect Merkle root rejects the whole block")
    good = make_block(chain, miner.primary_address)
    forged = replace(good.header, merkle_root=b"\x13" * 32)
    ck.expect_reject("Merkle root does not match txs (valid PoW)", chain,
                     Block(solve_header(forged)[0], good.txs), "bad_merkle")
    pay = alice.build_payment(chain.ledger, bob.primary_address, 20, fee=2)
    blk = make_block(chain, miner.primary_address, txs=[pay])
    swapped = Block(blk.header, (blk.txs[0],))      # header commits to 2 txs, body only has 1
    ck.expect_reject("a transaction removed after mining", chain,
                     Block(solve_header(blk.header)[0], swapped.txs), "bad_merkle")

    # ---- 3. excess coinbase ---------------------------------------------------
    emit("\n3. Excess coinbase value rejects the whole block")
    ok_sub = params.subsidy(4)
    greedy = make_block(chain, miner.primary_address, coinbase_value=ok_sub + 1)
    ck.expect_reject(f"coinbase claims {ok_sub + 1} (subsidy {ok_sub}, no fees)", chain,
                     solve_block(greedy).block, "coinbase_excess")
    greedy_fee = make_block(chain, miner.primary_address, txs=[pay], coinbase_value=ok_sub + 2 + 1)
    ck.expect_reject("coinbase claims subsidy + fee + 1", chain, solve_block(greedy_fee).block,
                     "coinbase_excess")

    # ---- 4. invalid transactions ---------------------------------------------
    emit("\n4. An invalid transaction rejects the whole block")
    obj = copy.deepcopy(pay.to_obj())
    obj["body"]["outputs"][0]["value"] += 1                  # edited after signing
    edited = SignedTx.from_obj(obj)
    ck.expect_reject("transaction edited after signing", chain,
                     solve_block(make_block(chain, miner.primary_address, txs=[edited], check_txs=False)).block,
                     "invalid_tx", "bad_signature")
    coin = chain.ledger.outputs_for(alice.pkhs[0])[-1][0]          # a different coin than `pay` spends
    over = sign_body(TxBody(chain.params.network_id, (coin,), (Output(51, bob.pkhs[0]),), "over"),
                     [alice._keys[alice.pkhs[0]]])
    ck.expect_reject("outputs exceed inputs", chain,
                     solve_block(make_block(chain, miner.primary_address, txs=[over], check_txs=False)).block,
                     "invalid_tx", "outputs_exceed_inputs")
    ghost = sign_body(TxBody(chain.params.network_id, (OutPoint("ab" * 32, 0),), (Output(1, bob.pkhs[0]),), "g"),
                      [alice._keys[alice.pkhs[0]]])
    ck.expect_reject("spends a nonexistent output", chain,
                     solve_block(make_block(chain, miner.primary_address, txs=[ghost], check_txs=False)).block,
                     "invalid_tx", "input_not_found")
    dbl = alice.build_payment(chain.ledger, carol.primary_address, 20, fee=2)   # same coin as `pay`
    ck.expect_reject("double spend inside one block", chain,
                     solve_block(make_block(chain, miner.primary_address, txs=[pay, dbl], check_txs=False)).block,
                     "invalid_tx", "input_already_spent")
    # first tx is fine, second is bad: the first must not stay applied (atomicity)
    ck.expect_reject("valid tx followed by an invalid one: nothing is applied", chain,
                     solve_block(make_block(chain, miner.primary_address, txs=[pay, over], check_txs=False)).block,
                     "invalid_tx", "outputs_exceed_inputs")

    # ---- 5. other block-level rules ------------------------------------------
    emit("\n5. Other block rules")
    nopow = make_block(chain, miner.primary_address)
    bad = nopow.header
    while True:                                           # find a nonce that does NOT meet the target
        bad = bad.with_nonce(bad.nonce + 1)
        if int.from_bytes(bad.hash, "big") > bad.target:
            break
    ck.expect_reject("insufficient proof of work", chain, Block(bad, nopow.txs), "bad_pow")
    orphan = replace(good.header, prev_hash=b"\x77" * 32)
    ck.expect_reject("unknown parent", chain, Block(solve_header(orphan)[0], good.txs), "unknown_parent")
    old = make_block(chain, miner.primary_address, timestamp=chain.tip_record.header.timestamp - 10_000)
    ck.expect_reject("timestamp not after median time past", chain, solve_block(old).block, "timestamp_too_old")
    fut = make_block(chain, miner.primary_address, timestamp=FIXED_CLOCK() + 10_000)
    ck.expect_reject("timestamp too far in the future", chain, solve_block(fut).block,
                     "timestamp_too_far_future")
    two = make_block(chain, miner.primary_address)
    body = (two.txs[0], two.txs[0])
    hdr = replace(two.header, merkle_root=Block(two.header, body).computed_merkle_root())
    ck.expect_reject("second coinbase in a block", chain, solve_block(Block(hdr, body)).block,
                     "multiple_coinbase")

    # ---- 6. reorg correctness -------------------------------------------------
    emit("\n6. A reorganisation produces the correct final UTXO set")
    base = Chain(params, FIXED_CLOCK)
    for _ in range(2):
        base.add_block(mine_block(base, alice.primary_address).block)
    node = copy.deepcopy(base)
    p_old = alice.build_payment(node.ledger, bob.primary_address, 30, fee=1)
    old1 = mine_block(node, miner.primary_address, txs=[p_old]).block
    node.add_block(old1)
    rival = copy.deepcopy(base)
    p_new = alice.build_payment(rival.ledger, carol.primary_address, 45, fee=3)   # conflicting spend
    new1 = mine_block(rival, miner.primary_address, txs=[p_new]).block
    rival.add_block(new1)
    new2 = mine_block(rival, carol.primary_address).block
    rival.add_block(new2)
    node.add_block(new1)
    res = node.add_block(new2)
    fresh = Chain(params, FIXED_CLOCK)
    for h in rival.active_hashes()[1:]:
        fresh.add_block(rival.record(h).block)
    ck.record("reorg status", res.status == "reorganized" and len(res.disconnected) == 1 and len(res.connected) == 2,
              f"disconnected {len(res.disconnected)}, connected {len(res.connected)}")
    ck.record("UTXO set equals a fresh replay of the winning chain",
              node.ledger.state_hash() == fresh.ledger.state_hash() and node.ledger.utxo_digest() == fresh.ledger.utxo_digest(),
              f"state {node.ledger.state_hash()[:16]}... == {fresh.ledger.state_hash()[:16]}...")
    ck.record("conflicting payment resolved", bob.balance(node.ledger) == 0 and carol.balance(node.ledger) >= 45
              and p_old.txid in {t.txid for t in res.returned_txs},
              f"bob={bob.balance(node.ledger)}, carol={carol.balance(node.ledger)}; the old payment returned to the mempool")
    node.ledger.check_invariants()

    # ---- 7. failed reorg rolls back ------------------------------------------
    emit("\n7. A heavier branch containing an invalid block cannot take over")
    node = copy.deepcopy(base)
    node.add_block(mine_block(node, miner.primary_address).block)
    node.add_block(mine_block(node, miner.primary_address).block)       # active: base + 2 blocks
    rival = copy.deepcopy(base)
    x1 = mine_block(rival, carol.primary_address).block
    rival.add_block(x1)
    x2 = mine_block(rival, carol.primary_address).block
    rival.add_block(x2)
    coin = rival.ledger.outputs_for(alice.pkhs[0])[0][0]
    over = sign_body(TxBody(params.network_id, (coin,), (Output(MAX_VALUE, bob.pkhs[0]),), "x"),
                     [alice._keys[alice.pkhs[0]]])
    x3 = solve_block(make_block(rival, carol.primary_address, txs=[over], check_txs=False)).block
    node.add_block(x1)
    node.add_block(x2)
    ck.expect_reject("branch X1,X2,X3 where X3 is invalid (3 blocks > 2 of work)", node, x3, "invalid_tx")
    ck.record("rest of the failed branch stays out of the active chain",
              not node.is_active(x1.hash) and not node.is_active(x2.hash) and node.height == base.height + 2,
              "active chain is still the original one; the invalid block was forgotten")
    node.ledger.check_invariants()

    passed = sum(1 for _, ok, _ in ck.results if ok)
    emit(f"\n{passed}/{len(ck.results)} checks passed")
    return ck.results
