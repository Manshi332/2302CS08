#!/usr/bin/env bash
# End-to-end run against a local Anvil node (start it first in another terminal: `anvil`).
# Needs: foundry (forge, cast), jq.  Uses Anvil's well-known dev accounts.
set -euo pipefail
cd "$(dirname "$0")/.."

RPC=${RPC:-http://127.0.0.1:8545}
BUYER_PK=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
ARBITER_PK=0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a
SELLER_PK=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d
BUYER=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
SELLER=0x70997970C51812dc3A010C7d01b50e0d17dc79C8
ARBITER=0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC
AMOUNT=$(cast to-wei 1 ether)

bal() { cast from-wei "$(cast balance "$1" --rpc-url "$RPC")"; }
gas() { echo "  gasUsed: $(cast receipt "$1" gasUsed --rpc-url "$RPC")"; }

echo "== deploy"
deploy() {  # newer forge needs --broadcast, older versions reject the flag
  forge create src/Escrow.sol:Escrow --rpc-url "$RPC" --private-key "$BUYER_PK" --broadcast --json \
      --constructor-args "$SELLER" "$ARBITER" "$AMOUNT" 2>/dev/null \
  || forge create src/Escrow.sol:Escrow --rpc-url "$RPC" --private-key "$BUYER_PK" --json \
      --constructor-args "$SELLER" "$ARBITER" "$AMOUNT"
}
OUT=$(deploy)
ESCROW=$(echo "$OUT" | jq -r .deployedTo)
DEPLOY_TX=$(echo "$OUT" | jq -r .transactionHash)
echo "  address: $ESCROW"; gas "$DEPLOY_TX"

echo "== verify deployed bytecode address"
CODE=$(cast code "$ESCROW" --rpc-url "$RPC")
echo "  code size: $(( (${#CODE}-2)/2 )) bytes, keccak: $(cast keccak "$CODE")"
CREATION=$(forge inspect Escrow bytecode)
INPUT=$(cast tx "$DEPLOY_TX" input --rpc-url "$RPC")
if [[ "$INPUT" == "$CREATION"* ]]; then echo "  creation tx input starts with compiled creation bytecode: OK"; else echo "  MISMATCH"; exit 1; fi

echo "== balances before"; echo "  escrow $(bal "$ESCROW")  seller $(bal "$SELLER")"

echo "== fund (buyer)"
TX=$(cast send "$ESCROW" "fund()" --value "$AMOUNT" --private-key "$BUYER_PK" --rpc-url "$RPC" --json | jq -r .transactionHash)
gas "$TX"; echo "  state: $(cast call "$ESCROW" "state()(uint8)" --rpc-url "$RPC")"

echo "== release (buyer)"
TX=$(cast send "$ESCROW" "release()" --private-key "$BUYER_PK" --rpc-url "$RPC" --json | jq -r .transactionHash)
gas "$TX"; echo "  state: $(cast call "$ESCROW" "state()(uint8)" --rpc-url "$RPC")  owed[seller]: $(cast call "$ESCROW" "owed(address)(uint256)" "$SELLER" --rpc-url "$RPC")"

echo "== withdraw (seller)"
TX=$(cast send "$ESCROW" "withdraw()" --private-key "$SELLER_PK" --rpc-url "$RPC" --json | jq -r .transactionHash)
gas "$TX"

echo "== balances after"; echo "  escrow $(bal "$ESCROW")  seller $(bal "$SELLER")"
echo "  liabilities: $(cast call "$ESCROW" "liabilities()(uint256)" --rpc-url "$RPC")"

echo "== emitted events"
cast logs --address "$ESCROW" --from-block 0 --rpc-url "$RPC" --json \
  | jq -r '.[] | "  topic0=\(.topics[0][0:12])...  block=\(.blockNumber)  tx=\(.transactionHash[0:12])..."'
echo "  decoded:"
for sig in "Funded(address,uint256)" "Released(address,uint256)" "Withdrawn(address,uint256)"; do
  echo "   $sig -> $(cast sig-event "$sig")"
done

echo
echo "== second escrow: dispute path (fund -> dispute -> arbiter resolves to buyer -> buyer withdraws)"
OUT2=$(deploy); E2=$(echo "$OUT2" | jq -r .deployedTo); echo "  address: $E2"
cast send "$E2" "fund()" --value "$AMOUNT" --private-key "$BUYER_PK" --rpc-url "$RPC" >/dev/null
TX=$(cast send "$E2" "dispute()" --private-key "$SELLER_PK" --rpc-url "$RPC" --json | jq -r .transactionHash); echo "  dispute"; gas "$TX"
TX=$(cast send "$E2" "resolve(bool)" true --private-key "$ARBITER_PK" --rpc-url "$RPC" --json | jq -r .transactionHash); echo "  resolve(true)"; gas "$TX"
echo "  state: $(cast call "$E2" "state()(uint8)" --rpc-url "$RPC")  (4 = ResolvedToBuyer)"
TX=$(cast send "$E2" "withdraw()" --private-key "$BUYER_PK" --rpc-url "$RPC" --json | jq -r .transactionHash); echo "  withdraw (buyer)"; gas "$TX"
echo "  escrow balance: $(bal "$E2")  liabilities: $(cast call "$E2" "liabilities()(uint256)" --rpc-url "$RPC")"
echo "  second withdraw must revert:"
cast send "$E2" "withdraw()" --private-key "$BUYER_PK" --rpc-url "$RPC" >/dev/null 2>&1 && echo "  UNEXPECTED SUCCESS" || echo "  reverted as expected (NothingToWithdraw)"
echo "done."
