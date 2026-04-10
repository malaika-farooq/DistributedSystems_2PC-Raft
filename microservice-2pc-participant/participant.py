"""
2PC Participant Node (Generic)
================================
Used for Nodes 3, 4, and 5 of the 5-node 2PC cluster.

Each container runs TWO gRPC servers on separate ports:
  Port VOTING_PORT  → Voting Phase Server   (coordinator calls RequestVote/Commit/Abort)
  Port INTRA_PORT   → Decision Phase Server (voting phase calls DoCommit/DoAbort)

The two phases communicate via gRPC over localhost (intra-node gRPC),
satisfying Q2's requirement that both phases use gRPC even if implemented
in different languages on the same node.

NODE_ROLE (env var): "carts", "inventory", "payment" — gives semantic meaning to each node.

Log format:
  Client: "Phase <phase> of Node <id> sends RPC <rpc> to Phase <phase> of Node <id>"
  Server: "Phase <phase> of Node <id> receives RPC <rpc> from Phase <phase> of Node <id>"
"""

import os
from concurrent import futures
import grpc
import twopc_pb2
import twopc_pb2_grpc

NODE_ID    = os.environ.get("NODE_ID",   "participant")
NODE_ROLE  = os.environ.get("NODE_ROLE", "generic")
VOTING_PORT = int(os.environ.get("VOTING_PORT", "50070"))
INTRA_PORT  = int(os.environ.get("INTRA_PORT",  "50071"))

# Store user_id between vote and commit/abort
_pending: dict = {}


# ─────────────────────────────────────────────────────────────
# Logging helpers (exact format from Q2)
# ─────────────────────────────────────────────────────────────
def log_send(phase, rpc, target_phase, target_node):
    print(
        f"Phase {phase} of Node {NODE_ID} sends RPC {rpc} "
        f"to Phase {target_phase} of Node {target_node}",
        flush=True
    )

def log_recv(phase, rpc, from_phase, from_node):
    print(
        f"Phase {phase} of Node {NODE_ID} receives RPC {rpc} "
        f"from Phase {from_phase} of Node {from_node}",
        flush=True
    )


# ─────────────────────────────────────────────────────────────
# DECISION PHASE SERVER  (port INTRA_PORT)
# Called by the voting phase on this same node via intra-node gRPC
# ─────────────────────────────────────────────────────────────
class DecisionPhaseServicer(twopc_pb2_grpc.IntraNodeDecisionServiceServicer):

    def DoCommit(self, request, context):
        # SERVER SIDE: decision phase receives DoCommit from voting phase
        log_recv("decision", "DoCommit", "voting", NODE_ID)
        txn_id = request.transaction_id
        print(
            f"[{NODE_ID}][{NODE_ROLE}][decision] "
            f"Local COMMIT executed for txn {txn_id}",
            flush=True
        )
        return twopc_pb2.IntraCommitResponse(
            transaction_id=txn_id, ok=True,
            message=f"[{NODE_ROLE}] local commit done"
        )

    def DoAbort(self, request, context):
        # SERVER SIDE: decision phase receives DoAbort from voting phase
        log_recv("decision", "DoAbort", "voting", NODE_ID)
        txn_id = request.transaction_id
        print(
            f"[{NODE_ID}][{NODE_ROLE}][decision] "
            f"Local ABORT executed for txn {txn_id}",
            flush=True
        )
        return twopc_pb2.IntraAbortResponse(
            transaction_id=txn_id, ok=True,
            message=f"[{NODE_ROLE}] local abort done"
        )


# ─────────────────────────────────────────────────────────────
# VOTING PHASE SERVER  (port VOTING_PORT)
# Called by coordinator for RequestVote, Commit, Abort
# ─────────────────────────────────────────────────────────────
class VotingPhaseServicer(twopc_pb2_grpc.ParticipantServiceServicer):

    def __init__(self):
        # Connect to decision phase on this same node via intra-node gRPC
        self._decision = twopc_pb2_grpc.IntraNodeDecisionServiceStub(
            grpc.insecure_channel(f"localhost:{INTRA_PORT}")
        )

    def RequestVote(self, request, context):
        # SERVER SIDE: voting phase receives RequestVote from coordinator
        log_recv("voting", "RequestVote", "voting", "coordinator")
        txn_id  = request.transaction_id
        user_id = request.user_id
        _pending[txn_id] = user_id

        # Each node performs its role-specific readiness check
        can_commit = bool(user_id)  # Vote abort only if no user_id

        if can_commit:
            print(
                f"[{NODE_ID}][{NODE_ROLE}][voting] Voting COMMIT for txn {txn_id}",
                flush=True
            )
        else:
            print(
                f"[{NODE_ID}][{NODE_ROLE}][voting] Voting ABORT for txn {txn_id}",
                flush=True
            )

        return twopc_pb2.VoteResponse(
            transaction_id=txn_id,
            node_id=NODE_ID,
            vote_commit=can_commit,
            reason="Ready" if can_commit else "No user_id"
        )

    def Commit(self, request, context):
        # SERVER SIDE: voting phase receives Commit from coordinator
        log_recv("decision", "Commit", "decision", "coordinator")
        txn_id  = request.transaction_id
        user_id = _pending.pop(txn_id, "")

        # CLIENT SIDE: voting phase calls decision phase (intra-node gRPC)
        log_send("decision", "DoCommit", "decision", NODE_ID)
        resp = self._decision.DoCommit(
            twopc_pb2.IntraCommitRequest(transaction_id=txn_id, user_id=user_id)
        )
        return twopc_pb2.AckResponse(
            transaction_id=txn_id, node_id=NODE_ID,
            ok=resp.ok, message=resp.message
        )

    def Abort(self, request, context):
        # SERVER SIDE: voting phase receives Abort from coordinator
        log_recv("decision", "Abort", "decision", "coordinator")
        txn_id = request.transaction_id
        _pending.pop(txn_id, None)

        # CLIENT SIDE: voting phase calls decision phase (intra-node gRPC)
        log_send("decision", "DoAbort", "decision", NODE_ID)
        resp = self._decision.DoAbort(
            twopc_pb2.IntraAbortRequest(transaction_id=txn_id, user_id="")
        )
        return twopc_pb2.AckResponse(
            transaction_id=txn_id, node_id=NODE_ID,
            ok=resp.ok, message=resp.message
        )


# ─────────────────────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────────────────────
def serve():
    print(f"\n[{NODE_ID}] Starting 2PC Participant ({NODE_ROLE})", flush=True)
    print(f"[{NODE_ID}]   Voting phase   → port {VOTING_PORT}", flush=True)
    print(f"[{NODE_ID}]   Decision phase → port {INTRA_PORT}", flush=True)

    # Start decision phase server first (voting phase stub connects to it)
    srv_decision = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    twopc_pb2_grpc.add_IntraNodeDecisionServiceServicer_to_server(
        DecisionPhaseServicer(), srv_decision
    )
    srv_decision.add_insecure_port(f"0.0.0.0:{INTRA_PORT}")
    srv_decision.start()
    print(f"[{NODE_ID}] Decision phase server listening on :{INTRA_PORT}", flush=True)

    # Start voting phase server
    srv_voting = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    twopc_pb2_grpc.add_ParticipantServiceServicer_to_server(
        VotingPhaseServicer(), srv_voting
    )
    srv_voting.add_insecure_port(f"0.0.0.0:{VOTING_PORT}")
    srv_voting.start()
    print(f"[{NODE_ID}] Voting phase server listening on :{VOTING_PORT}", flush=True)
    print(f"[{NODE_ID}] Ready.\n", flush=True)

    srv_voting.wait_for_termination()


if __name__ == "__main__":
    serve()
