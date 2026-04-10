"""
2PC Coordinator  —  Node 1 of 5
================================
Drives the two-phase commit protocol for PlaceOrder transactions.

VOTING PHASE:
  Coordinator sends RequestVote to all 4 participant nodes.
  Each participant replies with vote-commit or vote-abort.

DECISION PHASE:
  If ALL voted commit → send Commit to all participants.
  If ANY voted abort  → send Abort to all participants.

Log format (Q2 requirement):
  Client side: "Phase <phase> of Node <id> sends RPC <rpc> to Phase <phase> of Node <id>"
  Server side: "Phase <phase> of Node <id> receives RPC <rpc> from Phase <phase> of Node <id>"
"""

import os
import uuid
from concurrent import futures
import grpc
import twopc_pb2
import twopc_pb2_grpc

NODE_ID = os.environ.get("NODE_ID", "coordinator")

_raw = os.environ.get(
    "PARTICIPANT_ADDRS",
    "microservice-orders:50056,participant-carts:50062,participant-3:50064,participant-4:50066"
)
PARTICIPANT_ADDRS = [a.strip() for a in _raw.split(",") if a.strip()]


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


def _make_stub(addr):
    channel = grpc.insecure_channel(addr)
    stub    = twopc_pb2_grpc.ParticipantServiceStub(channel)
    label   = addr.split(":")[0]
    return stub, label


class CoordinatorServicer(twopc_pb2_grpc.CoordinatorServiceServicer):

    def PlaceOrderTransaction(self, request, context):
        txn_id  = request.transaction_id or str(uuid.uuid4())
        user_id = request.user_id

        print(f"\n{'='*60}", flush=True)
        print(f"[{NODE_ID}] 2PC txn={txn_id}  user={user_id}", flush=True)
        print(f"{'='*60}", flush=True)

        stubs = [_make_stub(addr) for addr in PARTICIPANT_ADDRS]

        # ── PHASE 1: VOTING ───────────────────────────────────────
        print("\n--- VOTING PHASE ---", flush=True)
        votes = {}

        for stub, label in stubs:
            # Client side log
            log_send("voting", "RequestVote", "voting", label)
            try:
                resp = stub.RequestVote(
                    twopc_pb2.VoteRequest(
                        transaction_id=txn_id,
                        user_id=user_id
                    )
                )
                # Client side receives response — log it
                log_recv("voting", "RequestVote", "voting", resp.node_id)
                votes[label] = resp.vote_commit
                verdict = "COMMIT" if resp.vote_commit else f"ABORT ({resp.reason})"
                print(f"[{NODE_ID}][voting] {resp.node_id} voted: {verdict}", flush=True)
            except grpc.RpcError as e:
                print(f"[{NODE_ID}][voting] ERROR from {label}: {e.details()} → treating as ABORT", flush=True)
                votes[label] = False

        global_commit = all(votes.values())

        # ── PHASE 2: DECISION ─────────────────────────────────────
        decision_str = "COMMIT" if global_commit else "ABORT"
        print(f"\n--- DECISION PHASE ({decision_str}) ---", flush=True)

        decision = twopc_pb2.GlobalDecision(
            transaction_id=txn_id,
            commit=global_commit
        )
        all_ok = True

        for stub, label in stubs:
            rpc_name = "Commit" if global_commit else "Abort"
            # Client side log
            log_send("decision", rpc_name, "decision", label)
            try:
                ack = stub.Commit(decision) if global_commit else stub.Abort(decision)
                # Client side receives ack
                log_recv("decision", rpc_name, "decision", ack.node_id)
                status = "OK" if ack.ok else f"FAILED ({ack.message})"
                print(f"[{NODE_ID}][decision] Ack from {ack.node_id}: {status}", flush=True)
                if not ack.ok:
                    all_ok = False
            except grpc.RpcError as e:
                print(f"[{NODE_ID}][decision] ERROR from {label}: {e.details()}", flush=True)
                all_ok = False

        success = global_commit and all_ok
        msg = "Transaction committed successfully." if success else "Transaction aborted."
        print(f"\n[{NODE_ID}] {msg}", flush=True)
        print(f"{'='*60}\n", flush=True)

        return twopc_pb2.AckResponse(
            transaction_id=txn_id,
            node_id=NODE_ID,
            ok=success,
            message=msg,
        )


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    twopc_pb2_grpc.add_CoordinatorServiceServicer_to_server(CoordinatorServicer(), server)
    server.add_insecure_port("0.0.0.0:50060")
    server.start()
    print(f"\n[{NODE_ID}] 2PC Coordinator (Node 1/5) listening on :50060", flush=True)
    print(f"[{NODE_ID}] Participants: {PARTICIPANT_ADDRS}\n", flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
