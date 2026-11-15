# Assignment 6 – A Peer-to-Peer Mempool and Block Relay Network

### Blockchain Engineering | IIT Patna | July–December 2026

**Roll Number:** 2302CS08

## 1. Overview

This assignment focuses on implementing a peer-to-peer (P2P) network that enables multiple blockchain nodes to communicate over localhost TCP connections using Python's `asyncio` framework.

The network consists of five or more nodes that discover peers, exchange transactions and blocks, maintain their mempools, and synchronize their blockchain state.

The implementation also handles malformed messages, network partitions, peer reconnections, and chain reorganization. It reuses the blockchain implementation from Assignment 5 (`src/chainlab`) without modifications. The new P2P networking functionality is implemented in `src/p2plab`.

## 2. Technologies Used

- **Programming Language:** Python 3.10+
- **Networking:** TCP Sockets
- **Asynchronous Programming:** Python `asyncio`
- **Blockchain:** Assignment 5 Chain Implementation
- **Cryptography:** Python `cryptography` library
- **Testing:** Python `unittest`
- **Data Logging:** JSON Lines (JSONL)

## 3. Features

- **Peer Discovery:** Nodes discover other peers using `getaddr` and `addr` messages.
- **P2P Communication:** Nodes communicate over localhost TCP connections.
- **Versioned Messages:** Implements structured messages for network communication.
- **Safe Message Framing:** Uses a 4-byte big-endian length prefix and a maximum message size of 1 MB.
- **Mempool Management:** Supports transaction validation, duplicate suppression, fee-rate ordering, expiry, conflict handling, and eviction.
- **Transaction Relay:** Uses inventory announcements and requests to relay missing transactions.
- **Block Relay:** Supports block propagation and orphan block handling.
- **Peer Protection:** Implements rate limiting, timeouts, peer scoring, penalties, and temporary bans.
- **Network Partition Simulation:** Allows communication between selected groups of nodes to be interrupted.
- **Partition Recovery:** Reconnects nodes and synchronizes their state after the network is healed.
- **Chain Reorganization:** Selects the chain with the most cumulative work.
- **Structured Logging:** Records network events in JSON Lines format.

## 4. Requirements

- Python 3.10 or higher.
- `cryptography` library, required by the reused Assignment 5 chain implementation.

Install dependencies:

```bash
pip install -r requirements.txt
```

For Windows PowerShell, set the Python source path using:

```powershell
$env:PYTHONPATH="src"
```

For Linux or macOS:

```bash
export PYTHONPATH=src
```

## 5. Quick Start

Run the following commands from the Assignment 6 folder.

**Step 1: Install dependencies**

```bash
pip install -r requirements.txt
```

**Step 2: Set the Python path**

Windows PowerShell:

```powershell
$env:PYTHONPATH="src"
```

Linux/macOS:

```bash
export PYTHONPATH=src
```

**Step 3: Run the test suite**

```bash
python -m unittest discover -s tests -v
```

The project includes 13 tests covering the P2P networking functionality.

**Step 4: Run the partition and recovery experiment**

```bash
python -m p2plab experiment
```

This experiment starts five nodes, simulates a network partition, and demonstrates their synchronization after the partition is healed.

## 6. Expected Experiment Output

The experiment displays the network state at three important stages:

**Connected (Discovery):**

All five nodes discover one another and establish peer connections.

```text
== connected (discovery)    all nodes: height=0, peers=4
```

**Partitioned:**

The network is divided into two groups, which independently extend their chains.

```text
== partitioned              n0,n1: height=2 | n2,n3,n4: height=3 (different tips)
```

**Healed (Converged):**

The network reconnects, nodes synchronize to the chain with the most cumulative work, and the transaction from the stale block is returned to the mempool.

```text
== healed (converged)       all nodes: height=3, same tip, mempool=1
result: {... 'tx_back_in_all_mempools': True, 'reorgs': 2}
```

**Note:** Hashes and some experiment values may differ between runs.

The experiment also generates a structured log at:

```text
logs/experiment.jsonl
```

## 7. Running Individual Nodes

Nodes can also be started manually in separate terminals.

**Terminal 1 – Start Node A:**

```bash
python -m p2plab node --id a --port 9000 --log a.jsonl
```

**Terminal 2 – Start Node B:**

```bash
python -m p2plab node --id b --port 9001 --seed 127.0.0.1:9000
```

**Terminal 3 – Start Node C with mining enabled:**

```bash
python -m p2plab node --id c --port 9002 --seed 127.0.0.1:9000 --mine-every 5 --mine-address <address>
```

Node C mines a block every five seconds.

Nodes discover other peers through the seed node using `getaddr` and `addr` messages. They connect to up to `max_outbound` peers, which defaults to 4.

Network events are displayed in the terminal as JSON lines.

## 8. Mapping to Assignment Requirements

| # | Task | Implementation |
|---|---|---|
| 1 | Versioned network messages: `version`, `verack`, `getaddr`, `addr`, `inv`, `getdata`, `notfound`, `tx`, `block`, `ping`, `pong`, and `error` | `src/p2plab/messages.py` |
| 2 | Safe message framing, 4-byte big-endian length prefix, 1 MB size limit, canonical JSON, duplicate-key rejection, and payload validation | `src/p2plab/messages.py` |
| 3 | Mempool validation, duplicate suppression, fee-rate ordering, expiry, conflict handling, eviction, and reconciliation | `src/p2plab/mempool.py` |
| 4 | Inventory-first transaction and block relay using `inv` and `getdata`; orphan block handling | `src/p2plab/node.py` |
| 5 | Rate limiting, handshake and request timeouts, malformed-message handling, peer scoring, and temporary bans | `src/p2plab/node.py` |
| 6 | Simulated latency, network partition, reconnection, resynchronization, and chain convergence | `src/p2plab/node.py`, `src/p2plab/experiment.py` |
| — | Structured event logging | `src/p2plab/log.py` |

## 9. Partition and Recovery Experiment

The experiment in `experiment.py` demonstrates how the network behaves during a partition and how nodes recover afterward.

The experiment follows these steps:

1. Five nodes start and bootstrap through node `n0`. They discover one another and establish peer connections with simulated latency.
2. Node `n0` mines the first block, which funds Alice. All nodes synchronize with the new block.
3. The network is partitioned into two groups: `{n0, n1}` and `{n2, n3, n4}`. A payment transaction is relayed and mined into a block on the first side.
4. The second group mines two blocks on its own branch, making its chain heavier.
5. The partition is healed. Nodes exchange inventory and synchronize with the chain having the most cumulative work.
6. The transaction from the stale block is re-admitted to the mempool because it is still valid and is relayed to the other nodes.
7. All five nodes converge to the same chain tip, and the transaction becomes pending in every node's mempool.

## 10. Useful Log Events

The structured logs record important network and blockchain events, including:

- `peer_ready`
- `inv_received`
- `block_sent`
- `block_accepted`
- `reorg`
- `tx_accepted`
- `tx_rejected`
- `tx_expired`
- `orphan_stored`
- `drop_partition`
- `rate_limited`
- `protocol_error`
- `peer_penalized`
- `peer_banned`
- `peer_timeout`
- `request_timeout`
- `partition_set`
- `partition_healed`
- `resync`

Example command to filter reorganization events:

```bash
grep '"event": "reorg"' logs/experiment.jsonl
```

## 11. Configuration

The `NodeConfig` class in `src/p2plab/node.py` provides configurable networking and mempool parameters.

| Parameter | Description |
|---|---|
| `max_outbound` | Maximum number of outbound peer connections |
| `max_peers` | Maximum number of connected peers |
| `handshake_timeout` | Handshake timeout |
| `ping_interval` | Interval between ping messages |
| `pong_timeout` | Timeout for receiving pong responses |
| `request_timeout` | Timeout for outstanding requests |
| `rate_per_sec` | Allowed message rate per second |
| `rate_burst` | Token-bucket burst capacity |
| `ban_threshold` | Peer score threshold for banning |
| `ban_seconds` | Temporary ban duration |
| `latency` | Simulated message latency range |
| `mempool_ttl` | Mempool transaction expiration time |
| `mempool_max` | Maximum mempool capacity |
| `min_fee_rate` | Minimum accepted transaction fee rate |

## 12. Project Structure

```text
assign06/
│
├── README.md
├── requirements.txt
├── pyproject.toml
│
├── src/
│   ├── chainlab/              # Assignment 5 blockchain implementation
│   │
│   └── p2plab/                # New P2P networking implementation
│       ├── messages.py
│       ├── mempool.py
│       ├── node.py
│       ├── log.py
│       ├── experiment.py
│       └── __main__.py
│
├── tests/
│   └── test_p2p.py
│
└── logs/
    └── experiment.jsonl
```

## 13. Limitations

- The implementation is designed for localhost networking only.
- Peer connections do not use encryption or peer authentication.
- The proof-of-work difficulty is intentionally low (`bits=4`) for educational experimentation.
- The mempool does not support chains of unconfirmed transactions. Each transaction must spend confirmed outputs.

## 14. Demonstration Video

**YouTube Demo:** [Watch Assignment 6 Demonstration](<ASSIGNMENT_06_VIDEO_LINK>)

The demonstration covers the project structure, P2P node communication, peer discovery, transaction and block relay, test execution, network partition simulation, and recovery through chain convergence.

---

**Course:** Blockchain Engineering  
**Institution:** Indian Institute of Technology Patna (IIT Patna)  
**Academic Session:** July–December 2026  
**Roll Number:** 2302CS08