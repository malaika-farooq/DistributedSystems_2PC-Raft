"""
2PC Participant — Node 2/5 (Orders)
=====================================
Runs TWO gRPC servers inside this one container:

  Port 50054  → Original OrdersService   (webapp calls PlaceOrder here directly)
  Port 50056  → Voting Phase Server      (coordinator calls RequestVote/Commit/Abort)
  Port 50057  → Decision Phase Server    (voting phase calls DoCommit/DoAbort via intra-node gRPC)

The voting phase and decision phase communicate via gRPC over localhost,
satisfying Q2's requirement that both phases on the same node use gRPC even
if they were implemented in different languages.

On COMMIT: saves an order record to SQLite and clears the cart.
On ABORT:  does nothing — no order saved, cart unchanged.

Log format:
  Client: "Phase <phase> of Node <id> sends RPC <rpc> to Phase <phase> of Node <id>"
  Server: "Phase <phase> of Node <id> receives RPC <rpc> from Phase <phase> of Node <id>"
"""

import os
import sqlite3
import uuid
from concurrent import futures
import grpc
import orders_pb2
import orders_pb2_grpc
import usercarts_pb2
import usercarts_pb2_grpc
import twopc_pb2
import twopc_pb2_grpc

CARTS_GRPC_TARGET   = os.environ.get("CARTS_GRPC_TARGET", "microservice-usercarts:50053")
DB_PATH             = os.environ.get("DB_PATH", "/data/orders.db")
NODE_ID             = os.environ.get("NODE_ID", "orders-node")
VOTING_PORT         = int(os.environ.get("VOTING_PORT", "50056"))
INTRA_DECISION_PORT = int(os.environ.get("INTRA_DECISION_PORT", "50057"))

# Pending txns: txn_id → user_id (stored during vote, used during commit/abort)
_pending: dict = {}


# ─────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────
def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL,
            status     TEXT NOT NULL DEFAULT 'completed',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────
# Logging helpers
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
# Original OrdersService (port 50054) — keeps webapp working
# ─────────────────────────────────────────────────────────────
class OrdersService(orders_pb2_grpc.OrdersServiceServicer):
    def __init__(self):
        self._carts = usercarts_pb2_grpc.UserCartsServiceStub(
            grpc.insecure_channel(CARTS_GRPC_TARGET)
        )

    def PlaceOrder(self, request, context):
        user_id = (request.user_id or "").strip()
        if not user_id:
            return orders_pb2.PlaceOrderResponse(ok=False, message="Missing user_id")
        cart = self._carts.GetCart(usercarts_pb2.GetCartRequest(user_id=user_id))
        if not cart.items:
            return orders_pb2.PlaceOrderResponse(ok=False, message="Cart is empty")
        order_id = str(uuid.uuid4())
        conn = get_conn()
        conn.execute("INSERT INTO orders(id,user_id,status) VALUES(?,?,'completed')", (order_id, user_id))
        conn.commit()
        conn.close()
        cleared = self._carts.ClearCart(usercarts_pb2.ClearCartRequest(user_id=user_id))
        if not cleared.ok:
            return orders_pb2.PlaceOrderResponse(ok=False, message=cleared.message)
        return orders_pb2.PlaceOrderResponse(ok=True, message=f"Order {order_id} placed")


# ─────────────────────────────────────────────────────────────
# DECISION PHASE SERVER  (port INTRA_DECISION_PORT)
# Called by the voting phase on this same node via intra-node gRPC
# ─────────────────────────────────────────────────────────────
class DecisionPhaseServicer(twopc_pb2_grpc.IntraNodeDecisionServiceServicer):

    def __init__(self):
        self._carts = usercarts_pb2_grpc.UserCartsServiceStub(
            grpc.insecure_channel(CARTS_GRPC_TARGET)
        )

    def DoCommit(self, request, context):
        # SERVER SIDE: decision phase receives DoCommit from voting phase
        log_recv("decision", "DoCommit", "voting", NODE_ID)
        txn_id  = request.transaction_id
        user_id = request.user_id
        try:
            # Save order record
            order_id = str(uuid.uuid4())
            conn = get_conn()
            conn.execute(
                "INSERT INTO orders(id,user_id,status) VALUES(?,?,'completed')",
                (order_id, user_id)
            )
            conn.commit()
            conn.close()
            # Clear the cart
            self._carts.ClearCart(usercarts_pb2.ClearCartRequest(user_id=user_id))
            print(f"[{NODE_ID}][decision] Committed: order {order_id} saved, cart cleared", flush=True)
            return twopc_pb2.IntraCommitResponse(
                transaction_id=txn_id, ok=True,
                message=f"Order {order_id} saved and cart cleared"
            )
        except Exception as e:
            return twopc_pb2.IntraCommitResponse(
                transaction_id=txn_id, ok=False, message=str(e)
            )

    def DoAbort(self, request, context):
        # SERVER SIDE: decision phase receives DoAbort from voting phase
        log_recv("decision", "DoAbort", "voting", NODE_ID)
        txn_id = request.transaction_id
        print(f"[{NODE_ID}][decision] Aborted txn {txn_id} — no changes made", flush=True)
        return twopc_pb2.IntraAbortResponse(
            transaction_id=txn_id, ok=True, message="Aborted cleanly"
        )


# ─────────────────────────────────────────────────────────────
# VOTING PHASE SERVER  (port VOTING_PORT)
# Called by coordinator: RequestVote, Commit, Abort
# ─────────────────────────────────────────────────────────────
class VotingPhaseServicer(twopc_pb2_grpc.ParticipantServiceServicer):

    def __init__(self):
        # Connect to decision phase on this same node via intra-node gRPC
        self._decision = twopc_pb2_grpc.IntraNodeDecisionServiceStub(
            grpc.insecure_channel(f"localhost:{INTRA_DECISION_PORT}")
        )
        self._carts = usercarts_pb2_grpc.UserCartsServiceStub(
            grpc.insecure_channel(CARTS_GRPC_TARGET)
        )

    def RequestVote(self, request, context):
        # SERVER SIDE: voting phase receives RequestVote from coordinator
        log_recv("voting", "RequestVote", "voting", "coordinator")
        txn_id  = request.transaction_id
        user_id = request.user_id
        _pending[txn_id] = user_id

        # Check if cart is non-empty (prerequisite for placing order)
        if not user_id:
            return twopc_pb2.VoteResponse(
                transaction_id=txn_id, node_id=NODE_ID,
                vote_commit=False, reason="Empty user_id"
            )
        try:
            cart = self._carts.GetCart(usercarts_pb2.GetCartRequest(user_id=user_id))
            if not cart.items:
                print(f"[{NODE_ID}][voting] Voting ABORT — cart is empty", flush=True)
                return twopc_pb2.VoteResponse(
                    transaction_id=txn_id, node_id=NODE_ID,
                    vote_commit=False, reason="Cart is empty"
                )
        except Exception as e:
            return twopc_pb2.VoteResponse(
                transaction_id=txn_id, node_id=NODE_ID,
                vote_commit=False, reason=f"Error: {e}"
            )

        print(f"[{NODE_ID}][voting] Voting COMMIT for txn {txn_id}", flush=True)
        return twopc_pb2.VoteResponse(
            transaction_id=txn_id, node_id=NODE_ID,
            vote_commit=True, reason="Ready"
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
    init_db()

    # Start decision phase server first
    srv_decision = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    twopc_pb2_grpc.add_IntraNodeDecisionServiceServicer_to_server(
        DecisionPhaseServicer(), srv_decision
    )
    srv_decision.add_insecure_port(f"0.0.0.0:{INTRA_DECISION_PORT}")
    srv_decision.start()
    print(f"[{NODE_ID}] Decision phase server on :{INTRA_DECISION_PORT}", flush=True)

    # Start voting phase server
    srv_voting = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    twopc_pb2_grpc.add_ParticipantServiceServicer_to_server(
        VotingPhaseServicer(), srv_voting
    )
    srv_voting.add_insecure_port(f"0.0.0.0:{VOTING_PORT}")
    srv_voting.start()
    print(f"[{NODE_ID}] Voting phase server on :{VOTING_PORT}", flush=True)

    # Start original orders server
    srv_orders = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    orders_pb2_grpc.add_OrdersServiceServicer_to_server(OrdersService(), srv_orders)
    srv_orders.add_insecure_port("0.0.0.0:50054")
    srv_orders.start()
    print(f"[{NODE_ID}] OrdersService on :50054", flush=True)

    print(f"\n[{NODE_ID}] 2PC Participant Node 2/5 (orders) ready.\n", flush=True)
    srv_orders.wait_for_termination()


if __name__ == "__main__":
    serve()
