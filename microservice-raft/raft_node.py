"""
Raft Node — Q3 (Leader Election) + Q4 (Log Replication)
=========================================================
Every node starts as a follower. Role is determined at runtime via the Raft
consensus algorithm.

Environment variables
  NODE_ID    — unique identifier for this node (e.g. "raft-node-1")
  RAFT_PORT  — gRPC port this node listens on (default 50070)
  PEER_ADDRS — comma-separated "host:port" of all OTHER nodes

Timeouts (per spec)
  Heartbeat timeout  : 1 second  (leader → followers)
  Election timeout   : uniform random [1.5 s, 3.0 s] per node

Log format (Q3/Q4 requirement)
  Client side : Node <node_id> sends RPC <rpc_name> to Node <node_id>
  Server side : Node <node_id> runs RPC <rpc_name> called by Node <node_id>
"""

import os
import random
import threading
import time
from concurrent import futures

import grpc
import raft_pb2
import raft_pb2_grpc

# ── Configuration ─────────────────────────────────────────────────────────────

NODE_ID   = os.environ.get("NODE_ID",   "raft-node-1")
RAFT_PORT = int(os.environ.get("RAFT_PORT", "50070"))
_raw      = os.environ.get("PEER_ADDRS", "")
PEER_ADDRS = [a.strip() for a in _raw.split(",") if a.strip()]

HEARTBEAT_INTERVAL   = 1.0   # seconds (leader sends AppendEntries every 1 s)
ELECTION_TIMEOUT_MIN = 1.5   # seconds
ELECTION_TIMEOUT_MAX = 3.0   # seconds


# ── Logging helpers ────────────────────────────────────────────────────────────

def log_send(rpc_name: str, target_node_id: str) -> None:
    """Print the required client-side log line."""
    print(f"Node {NODE_ID} sends RPC {rpc_name} to Node {target_node_id}", flush=True)


def log_run(rpc_name: str, caller_node_id: str) -> None:
    """Print the required server-side log line."""
    print(f"Node {NODE_ID} runs RPC {rpc_name} called by Node {caller_node_id}", flush=True)


# ── Raft Node ─────────────────────────────────────────────────────────────────

class RaftNode(raft_pb2_grpc.RaftServiceServicer):

    def __init__(self):
        # ── Persistent state ──────────────────────────────────────────────────
        self.current_term: int = 0
        self.voted_for: str | None = None

        # Q4: Log entries, each a dict {term, index, operation}
        # 'index' is 1-based (k+1 in the spec's <o, t, k+1> notation)
        self.log: list[dict] = []

        # Q4: Index of most recently committed operation (c in the spec); 0 = none
        self.commit_index: int = 0

        # ── Volatile state ────────────────────────────────────────────────────
        self.state: str = "follower"   # "follower" | "candidate" | "leader"
        self.leader_id: str | None = None

        # ── Synchronisation ───────────────────────────────────────────────────
        self._lock = threading.Lock()
        self._election_timer: threading.Timer | None = None
        self._heartbeat_timer: threading.Timer | None = None

        # ── Peer gRPC stubs ───────────────────────────────────────────────────
        # peer_id is the hostname portion of the address (= Docker service name = NODE_ID)
        self._peer_stubs: dict[str, raft_pb2_grpc.RaftServiceStub] = {}
        for addr in PEER_ADDRS:
            peer_id = addr.split(":")[0]
            channel = grpc.insecure_channel(addr)
            self._peer_stubs[peer_id] = raft_pb2_grpc.RaftServiceStub(channel)

        print(
            f"[{NODE_ID}] Starting as FOLLOWER (term 0) | peers: {PEER_ADDRS}",
            flush=True,
        )
        self._reset_election_timer()

    # ── Timer management ──────────────────────────────────────────────────────

    def _random_election_timeout(self) -> float:
        return random.uniform(ELECTION_TIMEOUT_MIN, ELECTION_TIMEOUT_MAX)

    def _reset_election_timer(self) -> None:
        """Cancel the existing election timer and start a new randomised one."""
        if self._election_timer is not None:
            self._election_timer.cancel()
        timeout = self._random_election_timeout()
        self._election_timer = threading.Timer(timeout, self._start_election)
        self._election_timer.daemon = True
        self._election_timer.start()

    def _cancel_election_timer(self) -> None:
        if self._election_timer is not None:
            self._election_timer.cancel()
            self._election_timer = None

    def _start_heartbeat_timer(self) -> None:
        """Schedule the next heartbeat; cancels any pending one first."""
        self._cancel_heartbeat_timer()
        self._heartbeat_timer = threading.Timer(HEARTBEAT_INTERVAL, self._send_heartbeats)
        self._heartbeat_timer.daemon = True
        self._heartbeat_timer.start()

    def _cancel_heartbeat_timer(self) -> None:
        if self._heartbeat_timer is not None:
            self._heartbeat_timer.cancel()
            self._heartbeat_timer = None

    # ── State transitions ─────────────────────────────────────────────────────

    def _become_follower(self, term: int) -> None:
        """Transition to follower. MUST be called with self._lock held."""
        self.current_term = term
        self.state        = "follower"
        self.voted_for    = None
        self._cancel_heartbeat_timer()
        self._reset_election_timer()
        print(f"[{NODE_ID}] → FOLLOWER (term {term})", flush=True)

    def _become_leader(self) -> None:
        """Transition to leader. MUST be called with self._lock held."""
        self.state     = "leader"
        self.leader_id = NODE_ID
        self._cancel_election_timer()
        print(f"[{NODE_ID}] → LEADER (term {self.current_term})", flush=True)
        self._start_heartbeat_timer()

    # ── Election ──────────────────────────────────────────────────────────────

    def _start_election(self) -> None:
        """Fired by the election timer when no heartbeat arrives in time."""
        with self._lock:
            if self.state == "leader":
                return
            self.state        = "candidate"
            self.current_term += 1
            self.voted_for    = NODE_ID   # vote for self
            term              = self.current_term
            last_log_index    = len(self.log)
            last_log_term     = self.log[-1]["term"] if self.log else 0

        print(f"[{NODE_ID}] Starting election — term {term}", flush=True)

        votes           = 1   # self-vote
        total_nodes     = len(self._peer_stubs) + 1
        majority        = total_nodes // 2 + 1
        votes_lock      = threading.Lock()
        stepped_down    = threading.Event()

        def request_vote_from(peer_id: str, stub) -> None:
            nonlocal votes
            try:
                log_send("RequestVote", peer_id)
                resp = stub.RequestVote(
                    raft_pb2.RequestVoteRequest(
                        term=term,
                        candidate_id=NODE_ID,
                        last_log_index=last_log_index,
                        last_log_term=last_log_term,
                    ),
                    timeout=1.0,
                )
                with self._lock:
                    if resp.term > self.current_term:
                        self._become_follower(resp.term)
                        stepped_down.set()
                        return
                if resp.vote_granted:
                    with votes_lock:
                        votes += 1
                    print(
                        f"[{NODE_ID}] Vote granted by {peer_id} — total {votes}/{majority} needed",
                        flush=True,
                    )
            except Exception as exc:
                print(f"[{NODE_ID}] RequestVote → {peer_id} failed: {exc}", flush=True)

        threads = [
            threading.Thread(target=request_vote_from, args=(pid, stub), daemon=True)
            for pid, stub in self._peer_stubs.items()
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=1.5)

        if stepped_down.is_set():
            return

        with self._lock:
            # Stale: another election already started
            if self.state != "candidate" or self.current_term != term:
                return
            if votes >= majority:
                self._become_leader()
            else:
                print(
                    f"[{NODE_ID}] Election failed (got {votes}/{majority}), back to follower",
                    flush=True,
                )
                self.state     = "follower"
                self.voted_for = None
                self._reset_election_timer()

    # ── Heartbeat / Log replication ───────────────────────────────────────────

    def _send_heartbeats(self) -> None:
        """
        Q3: Fires every HEARTBEAT_INTERVAL while leader.
        Q4: Carries the full log and leader_commit so followers replicate state.
        """
        with self._lock:
            if self.state != "leader":
                return
            term         = self.current_term
            commit_index = self.commit_index
            log_snapshot = list(self.log)

        entries = [
            raft_pb2.LogEntry(term=e["term"], index=e["index"], operation=e["operation"])
            for e in log_snapshot
        ]

        acks      = 0
        ack_lock  = threading.Lock()

        def append_to(peer_id: str, stub) -> None:
            nonlocal acks
            try:
                log_send("AppendEntries", peer_id)
                resp = stub.AppendEntries(
                    raft_pb2.AppendEntriesRequest(
                        term=term,
                        leader_id=NODE_ID,
                        entries=entries,
                        leader_commit=commit_index,
                    ),
                    timeout=0.8,
                )
                with self._lock:
                    if resp.term > self.current_term:
                        self._become_follower(resp.term)
                        return
                if resp.success:
                    with ack_lock:
                        acks += 1
            except Exception as exc:
                print(f"[{NODE_ID}] AppendEntries → {peer_id} failed: {exc}", flush=True)

        threads = [
            threading.Thread(target=append_to, args=(pid, stub), daemon=True)
            for pid, stub in self._peer_stubs.items()
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=0.9)

        # Q4: Commit pending entries once a majority has ACKed
        with self._lock:
            if self.state != "leader":
                return
            total_nodes = len(self._peer_stubs) + 1
            majority    = total_nodes // 2 + 1
            if (acks + 1) >= majority and len(self.log) > self.commit_index:
                while self.commit_index < len(self.log):
                    self.commit_index += 1
                    entry = self.log[self.commit_index - 1]
                    print(
                        f"[{NODE_ID}] Committed op '{entry['operation']}' at index {self.commit_index}",
                        flush=True,
                    )
            # Re-arm the heartbeat timer if still leader
            if self.state == "leader":
                self._start_heartbeat_timer()

    # ── gRPC handlers ─────────────────────────────────────────────────────────

    def RequestVote(self, request, context):
        """Q3: Handle vote request from a candidate."""
        log_run("RequestVote", request.candidate_id)
        with self._lock:
            # Step down if we see a higher term
            if request.term > self.current_term:
                self._become_follower(request.term)

            grant = False
            if request.term >= self.current_term:
                already_voted = self.voted_for not in (None, request.candidate_id)
                my_last_term  = self.log[-1]["term"] if self.log else 0
                my_last_index = len(self.log)
                # Candidate log must be at least as up-to-date as ours
                candidate_ok = (
                    request.last_log_term > my_last_term
                    or (request.last_log_term == my_last_term
                        and request.last_log_index >= my_last_index)
                )
                if not already_voted and candidate_ok:
                    grant = True
                    self.voted_for = request.candidate_id
                    self._reset_election_timer()   # reset on granting vote
                    print(
                        f"[{NODE_ID}] Voted for {request.candidate_id} in term {request.term}",
                        flush=True,
                    )
            return raft_pb2.RequestVoteResponse(
                term=self.current_term,
                vote_granted=grant,
            )

    def AppendEntries(self, request, context):
        """Q3/Q4: Handle heartbeat + log from the leader."""
        log_run("AppendEntries", request.leader_id)
        with self._lock:
            # Reject stale leaders
            if request.term < self.current_term:
                return raft_pb2.AppendEntriesResponse(
                    term=self.current_term, success=False
                )

            # Recognise valid leader
            if request.term > self.current_term or self.state != "follower":
                self._become_follower(request.term)
            else:
                # Same term, already follower — just reset election timer
                self._reset_election_timer()

            self.current_term = request.term
            self.leader_id    = request.leader_id

            # Q4: Replace our log with the leader's full log
            if request.entries:
                self.log = [
                    {
                        "term":      e.term,
                        "index":     e.index,
                        "operation": e.operation,
                    }
                    for e in request.entries
                ]
                print(
                    f"[{NODE_ID}] Copied {len(self.log)}-entry log from leader {request.leader_id}",
                    flush=True,
                )

            # Q4: Execute all operations up to leader's commit index
            new_commit = min(request.leader_commit, len(self.log))
            while self.commit_index < new_commit:
                self.commit_index += 1
                entry = self.log[self.commit_index - 1]
                print(
                    f"[{NODE_ID}] Executed op '{entry['operation']}' at index {self.commit_index}",
                    flush=True,
                )

            return raft_pb2.AppendEntriesResponse(term=self.current_term, success=True)

    def ExecuteOperation(self, request, context):
        """
        Q4: Client submits an operation.
        - If this node is the leader, append to log and wait for commit.
        - Otherwise, forward the request to the known leader.
        """
        with self._lock:
            my_state  = self.state
            my_leader = self.leader_id

        if my_state != "leader":
            if my_leader and my_leader != NODE_ID:
                leader_addr = f"{my_leader}:{RAFT_PORT}"
                try:
                    log_send("ExecuteOperation", my_leader)
                    fwd_channel = grpc.insecure_channel(leader_addr)
                    fwd_stub    = raft_pb2_grpc.RaftServiceStub(fwd_channel)
                    resp        = fwd_stub.ExecuteOperation(request, timeout=6.0)
                    return resp
                except Exception as exc:
                    return raft_pb2.ClientResponse(
                        success=False,
                        result=f"Forward to leader {my_leader} failed: {exc}",
                        leader_id=my_leader,
                    )
            else:
                return raft_pb2.ClientResponse(
                    success=False,
                    result="No leader known yet — retry in a moment",
                    leader_id="",
                )

        # This node is the leader — append the entry
        with self._lock:
            index = len(self.log) + 1
            entry = {
                "term":      self.current_term,
                "index":     index,
                "operation": request.operation,
            }
            self.log.append(entry)
            print(
                f"[{NODE_ID}] Leader appended op '{request.operation}' at index {index}",
                flush=True,
            )

        # Wait for the next heartbeat round to commit this entry
        deadline = time.time() + 6.0
        while time.time() < deadline:
            with self._lock:
                if self.commit_index >= index:
                    return raft_pb2.ClientResponse(
                        success=True,
                        result=f"Committed '{request.operation}' at index {index}",
                        leader_id=NODE_ID,
                    )
            time.sleep(0.1)

        return raft_pb2.ClientResponse(
            success=False,
            result="Timeout waiting for majority commit",
            leader_id=NODE_ID,
        )


# ── Entry point ───────────────────────────────────────────────────────────────

def serve():
    node   = RaftNode()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=20))
    raft_pb2_grpc.add_RaftServiceServicer_to_server(node, server)
    server.add_insecure_port(f"0.0.0.0:{RAFT_PORT}")
    server.start()
    print(f"[{NODE_ID}] Raft gRPC server listening on :{RAFT_PORT}", flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
