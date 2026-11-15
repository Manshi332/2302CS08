#!/usr/bin/env bash
# Clean checkout -> full test suite with one command:   ./run_tests.sh
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d lib/forge-std ] || [ ! -d lib/openzeppelin-contracts ]; then
  [ -d .git ] || git init -q
  forge install foundry-rs/forge-std OpenZeppelin/openzeppelin-contracts@v5.0.2 \
    || forge install --no-commit foundry-rs/forge-std OpenZeppelin/openzeppelin-contracts@v5.0.2
fi
forge test -vv
forge test --gas-report > gas-report.txt
echo "gas report written to gas-report.txt"
