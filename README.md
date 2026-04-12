# Project 3: Making Systems Fault Tolerant via 2PC & Raft

## Overview

This project extends a microservice-based e-commerce application (ServerShop) with implementations of two distributed consensus protocols:

- **Two-Phase Commit (2PC)** — coordinating atomic PlaceOrder transactions across 5 nodes (Q1 & Q2)
- **Raft** — fault-tolerant leader election and log replication across 5 nodes (Q3 & Q4)

All inter-node communication uses **gRPC**. Every node runs as a separate **Docker** container orchestrated by Docker Compose.

### Team Members (Group #8)

| Name | Student ID |
|------|-----------|
| Malaika Farooq | 1002311562 |
| Yuanbin Man | 1002296616 |

**GitHub**: https://github.com/malaika-farooq/DistributedSystems_2PC-Raft

---

## How to Compile and Run

### Prerequisites

- Docker Desktop installed and running
- Docker Compose v2+
- Python 3.10+ (for running test scripts on the host)

### Steps

```bash
# 1. Build all images (required first time or after any code change)
docker compose build --no-cache

# 2. Start all containers (2PC nodes + Raft nodes + webapp)
docker compose up

# 3. (Optional) Follow logs in a separate terminal
docker compose logs -f
```

The web application is available at: **http://127.0.0.1:5000**

To stop all containers:

```bash
docker compose down
```

### Running Tests

```bash
# 2PC tests (while docker compose up is running)
pip install requests
python test_2pc.py

# Raft tests — Q5 (while docker compose up is running)
python test_raft.py
```

---

## Project Structure

```
DistributedSystems_2PC-Raft/
├── proto/
│   ├── twopc.proto                # 2PC gRPC definitions (Q1 & Q2)
│   ├── raft.proto                 # Raft gRPC definitions (Q3 & Q4)
│   ├── orders.proto               # Original orders service
│   ├── usercarts.proto            # Original carts service
│   ├── auth.proto                 # Original auth service
│   ├── productlisting.proto       # Original product listing service
│   └── admin.proto                # Original admin service
│
├── microservice-2pc-coordinator/
│   ├── coordinator.py             # 2PC Coordinator — Node 1
│   ├── Dockerfile
│   └── requirements.txt
│
├── microservice-2pc-participant/
│   ├── participant.py             # Generic 2PC Participant — Nodes 3, 4, 5
│   ├── Dockerfile
│   └── requirements.txt
│
├── microservice-orders/
│   ├── order_server.py            # 2PC Participant — Node 2 (saves orders)
│   ├── Dockerfile
│   └── requirements.txt
│
├── microservice-raft/
│   ├── raft_node.py               # Raft node (Q3 election + Q4 log replication)
│   ├── Dockerfile
│   └── requirements.txt
│
├── microservice-usercarts/        # Cart service (original)
├── microservice-userauth/         # Auth service (original)
├── microservice-productlisting/   # Product listing service (original)
├── microservice-admin/            # Admin service (original)
├── python-webapp/                 # Flask web application
│
├── docker-compose.yml             # All services: 2PC (5 nodes) + Raft (5 nodes) + webapp
├── test_2pc.py                    # Automated 2PC test suite
├── test_raft.py                   # Automated Raft test suite (Q5)
├── report.md                      # Implementation evidence & test results for Q1–Q5
└── README.md
```

---

## Unusual Notes for TA

- The `--no-cache` flag is recommended on first build to ensure proto files are compiled fresh in all containers
- All log messages (2PC and Raft) appear in the Docker terminal — run `docker compose logs -f` to follow them
- The web UI shows a modal with the 5-node cluster status after each PlaceOrder attempt
- `productlisting_data/` must be empty (or not exist) on first run so products re-seed with correct image paths
- Raft nodes elect a leader automatically within a few seconds of startup; check logs to see election activity

---

## External References

- [gRPC Python Documentation](https://grpc.io/docs/languages/python/)
- [Protocol Buffers Documentation](https://protobuf.dev/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Two-Phase Commit Protocol (Wikipedia)](https://en.wikipedia.org/wiki/Two-phase_commit_protocol)
- [Raft Consensus Algorithm (Wikipedia)](https://en.wikipedia.org/wiki/Raft_(algorithm))
- [Consensus Algorithms: from 2PC to Raft](https://renjieliu.gitbooks.io/consensus-algorithms-from-2pc-to-raft/content/index.html)

