# Threat model

| Threat | Mitigation |
|---|---|
| Reentrancy via `withdraw` | credit zeroed before the external call + `ReentrancyGuard`; test `test_reentrancy_on_withdraw` |
| Unauthorized transitions | per-function role checks; fuzzed over arbitrary callers |
| Double payment | credits created once; `withdraw` zeroes them; terminal states reject all transitions |
| Wrong / repeated funding | exact `msg.value == amount`, only in `Created`, only buyer |
| Zero addresses / role overlap | constructor reverts (`ZeroAddress`, `RoleOverlap`, `ZeroAmount`) |
| Funds locked | every non-terminal state has an exit (see SPEC); no ETH accepted outside `fund()` |
| Malicious payee (reverting receiver) | pull payments: a failing receiver only blocks its own withdrawal, not the other party |
| Forced ETH (selfdestruct / coinbase) | accounting uses recorded liabilities, not `balance ==`; extra ETH is stranded, never claimable |
| `tx.origin`, timestamps, unbounded loops, low-level call results | not used / call result checked (`TransferFailed`) |

**Trust assumptions.** The arbiter is fully trusted to resolve disputes and can be unresponsive (a disputed escrow then stays disputed; a timeout/recovery path is out of scope). The buyer can always dispute rather than release; the seller can dispute to freeze an unwanted release path. No upgradeability, no admin keys.
