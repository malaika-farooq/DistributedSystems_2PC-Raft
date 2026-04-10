# Project 3: Two-Phase Commit (2PC) and Raft on a Microservice Architecture

## Overview

This project extends a microservice-based e-commerce application (ServerShop) with a full implementation of the **Two-Phase Commit (2PC)** distributed consensus protocol. 2PC is implemented on the **PlaceOrder** functionality, coordinating an atomic transaction across 5 distributed nodes using **gRPC** for all communication and **Docker** for containerization.

---

## How to Compile and Run

### Prerequisites
- Docker Desktop installed and running
- Docker Compose v2+

### Steps

```bash
# 1. Navigate to the project directory
cd Project2-main

# 2. Build all images (required first time, or after any code change)
docker compose build --no-cache

# 3. Start all containers
docker compose up
```

The web application will be available at: **http://127.0.0.1:5000**

To stop all containers:
```bash
docker compose down
```

---

## Project Structure

```
Project2-main/
├── proto/
│   ├── twopc.proto              # 2PC gRPC definitions (Q1 & Q2)
│   ├── orders.proto             # Original orders service
│   ├── usercarts.proto          # Original carts service
│   ├── auth.proto               # Original auth service
│   ├── productlisting.proto     # Original product listing service
│   └── admin.proto              # Original admin service
│
├── microservice-2pc-coordinator/
│   ├── coordinator.py           # 2PC Coordinator — Node 1
│   ├── Dockerfile
│   └── requirements.txt
│
├── microservice-2pc-participant/
│   ├── participant.py           # Generic 2PC Participant — Nodes 3, 4, 5
│   ├── Dockerfile
│   └── requirements.txt
│
├── microservice-orders/
│   ├── order_server.py          # 2PC Participant — Node 2 (saves orders)
│   ├── Dockerfile
│   └── requirements.txt
│
├── microservice-usercarts/      # Cart service (unchanged)
├── microservice-userauth/       # Auth service (unchanged)
├── microservice-productlisting/ # Product listing service (unchanged)
├── microservice-admin/          # Admin service (unchanged)
├── python-webapp/               # Flask web application
└── docker-compose.yml           # All 5 2PC nodes + app services
```

---

## 5-Node 2PC Architecture

The 2PC cluster consists of exactly **5 nodes**, each running as a separate Docker container:

| Node | Container | Role | Ports |
|------|-----------|------|-------|
| Node 1 | `microservice-2pc-coordinator` | Coordinator — drives both phases | 50060 |
| Node 2 | `microservice-orders` | Participant — saves order, clears cart | 50056 (voting), 50057 (decision) |
| Node 3 | `participant-carts` | Participant — carts readiness check | 50062 (voting), 50063 (decision) |
| Node 4 | `participant-3` (inventory-node) | Participant — inventory check | 50064 (voting), 50065 (decision) |
| Node 5 | `participant-4` (payment-node) | Participant — payment check | 50066 (voting), 50067 (decision) |

**Each participant node (2–5) runs two gRPC servers inside the same container:**
- **Voting Phase Server**: receives `RequestVote`, `Commit`, `Abort` from the coordinator
- **Decision Phase Server**: receives `DoCommit`, `DoAbort` from the voting phase (intra-node gRPC)

This intra-node gRPC communication satisfies Q2's requirement that voting and decision phases can be implemented in different languages and still communicate via gRPC on the same node.

---

## 2PC Protocol Flow

### Voting Phase (Q1)
1. Coordinator sends `RequestVote` to all 4 participants
2. Each participant checks local readiness and replies `vote-commit` or `vote-abort`

### Decision Phase (Q2)
3. Coordinator collects all votes:
   - All COMMIT → sends `global-commit` to all participants
   - Any ABORT → sends `global-abort` to all participants
4. Each participant's **voting phase** receives the decision, then calls its own **decision phase** via intra-node gRPC (`DoCommit` or `DoAbort`)
5. The decision phase executes the local work (save order, clear cart, etc.)

### Log Format (Q2)
Every gRPC call prints:
```
# Client side:
Phase <phase> of Node <node_id> sends RPC <rpc_name> to Phase <phase> of Node <node_id>

# Server side:
Phase <phase> of Node <node_id> receives RPC <rpc_name> from Phase <phase> of Node <node_id>
```

---

## gRPC Proto File (twopc.proto)

All 2PC RPCs are defined in `proto/twopc.proto`:

**Services:**
- `CoordinatorService.PlaceOrderTransaction` — webapp triggers 2PC
- `ParticipantService.RequestVote` — voting phase
- `ParticipantService.Commit` — decision phase (commit)
- `ParticipantService.Abort` — decision phase (abort)
- `IntraNodeDecisionService.DoCommit` — intra-node: execute commit
- `IntraNodeDecisionService.DoAbort` — intra-node: execute abort

---

## 2PC Testing

### Test 1 — Happy Path (All Commit)
1. Register/login, add a product to cart, go to Cart, click **Place Order**
2. Expected: green modal showing all 5 nodes voted COMMIT
3. Terminal shows full voting + decision phase logs

### Test 2 — Force Abort (Stop a Participant)
```bash
docker stop project2-main-participant-3-1
# Place an order → coordinator cannot reach inventory-node → ABORT
docker start project2-main-participant-3-1
```

### Test 3 — Empty Cart Abort
Click Place Order with empty cart → orders-node votes ABORT → red modal

### Test 4 — Verify All 5 Nodes
```bash
docker compose ps
docker compose logs microservice-2pc-coordinator
```

### Test 5 — Intra-Node gRPC Verification
Watch terminal for logs like:
```
Phase decision of Node orders-node sends RPC DoCommit to Phase decision of Node orders-node
Phase decision of Node orders-node receives RPC DoCommit from Phase voting of Node orders-node
```

---

## External References

- [gRPC Python documentation](https://grpc.io/docs/languages/python/)
- [Protocol Buffers documentation](https://protobuf.dev/)
- [Docker Compose documentation](https://docs.docker.com/compose/)
- [Two-Phase Commit Protocol — Distributed Systems Concepts](https://en.wikipedia.org/wiki/Two-phase_commit_protocol)

---

## GitHub

[[Repository Link](https://github.com/malaika-farooq/DistributedSystems_2PC-Raft)]

## Notes for TA

- The `--no-cache` flag is required on first build to ensure `twopc.proto` is compiled fresh in all containers
- All 2PC log messages appear in the Docker terminal — run `docker compose logs -f` to follow them
- The web UI shows a modal with the 5-node cluster status after each PlaceOrder attempt
- `productlisting_data/` must be empty (or not exist) on first run so products re-seed with correct image paths

---

## Running the  2pc Test cases

The automated test suite covers all 5 test cases required for documentation.

### Prerequisites
```bash
pip install requests
```

### Run all tests (while docker compose up is running)
```bash
python test_2pc.py
```

### What is tested for 2PC

| Test | What It Verifies |
|------|-----------------|
| 1. Happy Path | All 5 nodes commit — cart cleared, order saved |
| 2. Node Failure | If a participant is unreachable → coordinator aborts, cart preserved |
| 3. Empty Cart Abort | orders-node votes ABORT → transaction rolls back |
| 4. Latency | Measures min/avg/max 2PC transaction time across 5 runs |
| 5. Atomicity | No partial commits — either all nodes commit or none do |

### Manual Testing Commands

**Test 2 — Force abort by stopping a participant:**
```bash
docker stop project2-main-participant-3-1
# Place an order in browser → should see ABORT modal
docker start project2-main-participant-3-1
```

**View logs from all 2PC nodes:**
```bash
docker compose logs microservice-2pc-coordinator
docker compose logs microservice-orders
docker compose logs participant-carts
docker compose logs participant-3
docker compose logs participant-4
```

**Follow live logs:**
```bash
docker compose logs --follow
```
