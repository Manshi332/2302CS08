# Assignment 7 – Solidity Escrow: From Specification to Deployment

### Blockchain Engineering | IIT Patna | July–December 2026

**Roll Number:** 2302CS08

## 1. Overview

This assignment focuses on designing, implementing, testing, and deploying a secure escrow smart contract using Solidity and Foundry.

The escrow contract facilitates secure transactions between three participants: a buyer, a seller, and an arbiter. The buyer deposits funds into the contract, and the funds can be released to the seller, cancelled, or resolved by the arbiter in case of a dispute.

The implementation focuses on secure fund management, access control, state transitions, reentrancy protection, and comprehensive testing.

## 2. Technologies Used

- **Solidity:** 0.8.24
- **Development Framework:** Foundry
- **Testing:** Forge
- **Local Blockchain:** Anvil
- **Interaction Tools:** Cast
- **Security Library:** OpenZeppelin Contracts v5.0.2
- **Scripting:** Bash

## 3. Features

- **Escrow Creation:** Establishes an escrow between a buyer, seller, and arbiter.
- **Fund Deposit:** Allows the buyer to deposit the required amount into the contract.
- **Cancellation:** Supports cancellation through the defined approval process.
- **Fund Release:** Allows funds to be released to the seller.
- **Dispute Handling:** Allows disputes to be raised and resolved by the arbiter.
- **Secure Withdrawals:** Uses a pull-payment mechanism for withdrawing credited funds.
- **Access Control:** Restricts operations to authorized participants.
- **Reentrancy Protection:** Uses OpenZeppelin's `ReentrancyGuard`.
- **Event Logging:** Emits events for important escrow operations.

## 4. Escrow State Flow

The contract follows a defined state machine:

```text
Created
   |
   ├── Funded
   |     |
   |     ├── Released
   |     |
   |     └── Disputed
   |             |
   |             └── Resolved
   |
   └── Cancelled
```

The arbiter resolves disputes in favour of either the buyer or the seller.

## 5. Project Structure

```text
assign09/
│
├── README.md
├── foundry.toml
├── run_tests.sh
├── gas-report.txt
│
├── src/
│   └── Escrow.sol
│
├── test/
│   ├── Escrow.t.sol
│   └── Escrow.invariant.t.sol
│
├── script/
│   └── Deploy.s.sol
│
├── scripts/
│   └── demo.sh
│
└── docs/
    ├── SPEC.md
    └── THREAT_MODEL.md
```

## 6. Setup and Installation

Install Foundry if it is not already installed:

```bash
curl -L https://foundry.paradigm.xyz | bash
source ~/.bashrc
foundryup
```

Navigate to the assignment directory:

```bash
cd /mnt/c/Users/Hp/Desktop/ROLLNO/ROLLNO/assign09
```

## 7. Running the Tests

Execute the test script:

```bash
./run_tests.sh
```

This script installs the required dependencies if they are missing, compiles the contracts, executes the test suite, and generates a gas report.

Run the gas report separately:

```bash
forge test --gas-report
```

Create a gas snapshot:

```bash
forge snapshot
```

**Test Results:**

- 22 unit, fuzz, and reentrancy tests passed.
- 1 invariant test passed.
- Total: 23 tests passed, 0 failed.

The invariant tests check balance and liability consistency, payout limits, and terminal-state fund accounting.

## 8. Local Deployment and Demonstration

Start a local blockchain using Anvil in Terminal 1:

```bash
anvil
```

Keep this terminal running.

Open a second terminal and navigate to the assignment directory:

```bash
cd /mnt/c/Users/Hp/Desktop/ROLLNO/ROLLNO/assign09
```

Run the demonstration script:

```bash
./scripts/demo.sh
```

The demonstration covers:

1. Escrow deployment.
2. Buyer funding.
3. Successful fund release to the seller.
4. Seller withdrawal.
5. Dispute creation.
6. Arbiter dispute resolution.
7. Buyer withdrawal after dispute resolution.
8. Verification of escrow balance and liabilities.

The demo uses local Anvil accounts for the buyer, seller, and arbiter.

## 9. Security Considerations

The implementation incorporates several security measures:

- Reentrancy protection using OpenZeppelin's `ReentrancyGuard`.
- Checks-Effects-Interactions pattern.
- Role-based access restrictions.
- Custom errors and event emissions.
- Pull-based payment withdrawals.
- Exact funding validation.
- Prevention of unauthorized fund transfers.
- Invariant testing for escrow accounting.

The threat model and security assumptions are documented in `docs/THREAT_MODEL.md`.

## 10. Documentation

The project includes:

- `docs/SPEC.md` – Describes the escrow requirements, functionality, and state transitions.
- `docs/THREAT_MODEL.md` – Describes security assumptions, possible threats, and mitigation strategies.

## 11. Demonstration Video

**YouTube Demo:** [Watch Assignment 7 Demonstration](<ASSIGNMENT_07_VIDEO_LINK>)

The demonstration video covers the project structure, smart contract implementation, test execution, local deployment, and escrow transaction flows.

---

**Course:** Blockchain Engineering  
**Institution:** Indian Institute of Technology Patna (IIT Patna)  
**Academic Session:** July–December 2026  
**Roll Number:** 2302CS08