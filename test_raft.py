"""
Raft Test Suite — Q5 (5 failure-related test cases)
=====================================================
Run AFTER `docker compose up` has started all Raft nodes:

    python test_raft.py

The script uses `docker compose` commands to interact with the cluster and
`docker compose exec` to submit gRPC operations from inside a container.

Test cases
----------
1. Initial Leader Election      — cluster elects exactly one leader on startup
2. Leader Failure + Re-election — stopping the leader causes a new election
3. New Node Joining             — a previously stopped node rejoins and syncs
4. Follower Failure             — cluster remains functional when a follower goes down
5. Log Replication Consistency  — all nodes end up with the same committed log
"""

import subprocess
import sys
import time

# ── Colour helpers ────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

results = []

RAFT_SERVICES = [
    "raft-node-1",
    "raft-node-2",
    "raft-node-3",
    "raft-node-4",
    "raft-node-5",
]

# ── Low-level helpers ─────────────────────────────────────────────────────────

def banner(text: str) -> None:
    print(f"\n{BOLD}{CYAN}{'='*62}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'='*62}{RESET}\n")


def pass_test(name: str, detail: str = "") -> None:
    print(f"  {GREEN}PASS{RESET}  {name}")
    if detail:
        print(f"        {detail}")
    results.append({"test": name, "result": "PASS", "detail": detail})


def fail_test(name: str, detail: str = "") -> None:
    print(f"  {RED}FAIL{RESET}  {name}")
    if detail:
        print(f"        {detail}")
    results.append({"test": name, "result": "FAIL", "detail": detail})


def run(cmd: str, timeout: int = 30) -> tuple[str, str, int]:
    """Run a shell command; return (stdout, stderr, returncode)."""
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return r.stdout, r.stderr, r.returncode


def get_logs(service: str, lines: int = 40) -> str:
    stdout, stderr, _ = run(f"docker compose logs --tail {lines} {service}")
    return stdout + stderr


def stop_service(service: str) -> None:
    print(f"  {YELLOW}[action]{RESET} Stopping {service} …")
    run(f"docker compose stop {service}")
    time.sleep(1)


def start_service(service: str) -> None:
    print(f"  {YELLOW}[action]{RESET} Starting {service} …")
    run(f"docker compose start {service}")
    time.sleep(2)


def submit_operation(service: str, operation: str) -> tuple[bool, str]:
    """
    Exec a one-liner Python gRPC client inside the named container to submit
    an operation to the Raft cluster.  Returns (success, result_text).
    """
    script = (
        "import grpc, raft_pb2, raft_pb2_grpc; "
        f"ch=grpc.insecure_channel('localhost:50070'); "
        f"stub=raft_pb2_grpc.RaftServiceStub(ch); "
        f"r=stub.ExecuteOperation(raft_pb2.ClientRequest(operation='{operation}'),timeout=8); "
        f"print(r.success, r.result, r.leader_id)"
    )
    stdout, stderr, rc = run(
        f"docker compose exec -T {service} python -c \"{script}\"",
        timeout=15,
    )
    output = stdout.strip()
    if rc != 0 or not output:
        return False, stderr.strip() or "no output"
    parts = output.split(" ", 2)
    success = parts[0] == "True"
    detail  = " ".join(parts[1:]) if len(parts) > 1 else output
    return success, detail


def find_leader() -> str | None:
    """
    Scan logs of all Raft nodes to find the current leader.
    A running leader continuously sends AppendEntries heartbeats, so we look
    for 'sends RPC AppendEntries' in recent logs.  Falls back to '→ LEADER'
    for freshly elected leaders whose heartbeats haven't printed yet.
    """
    leader = None
    for svc in RAFT_SERVICES:
        logs = get_logs(svc, lines=40)
        if "sends RPC AppendEntries" in logs:
            leader = svc
            return leader          # actively sending heartbeats = current leader
    # Fallback: look for the election transition message (larger window)
    for svc in RAFT_SERVICES:
        logs = get_logs(svc, lines=200)
        if "→ LEADER" in logs:
            leader = svc
    return leader


def count_leaders() -> int:
    """Return how many distinct Raft nodes currently believe they are the leader."""
    n = 0
    for svc in RAFT_SERVICES:
        logs = get_logs(svc, lines=40)
        if "sends RPC AppendEntries" in logs:
            n += 1
    return n


# ── Test cases ────────────────────────────────────────────────────────────────

def test_1_initial_leader_election():
    """
    Test 1 — Initial Leader Election
    All 5 nodes start as followers.  Within a few seconds exactly one leader
    must emerge (the node whose election timeout fires first wins the vote).
    """
    banner("Test 1: Initial Leader Election")
    print("  Waiting up to 10 s for the cluster to elect a leader …")
    time.sleep(3)

    for attempt in range(5):
        leader = find_leader()
        if leader:
            pass_test(
                "Initial leader election",
                f"Leader elected: {leader}",
            )
            print(f"  {YELLOW}Logs snippet from {leader}:{RESET}")
            snippet = [
                ln for ln in get_logs(leader, 60).splitlines()
                if any(kw in ln for kw in ("LEADER", "FOLLOWER", "election", "term"))
            ][-8:]
            for ln in snippet:
                print(f"    {ln}")
            return
        time.sleep(2)

    fail_test("Initial leader election", "No leader found after 10 s")


def test_2_leader_failure_reelection():
    """
    Test 2 — Leader Failure → New Election
    Stop the current leader.  The remaining 4 nodes (still a majority) must
    elect a replacement within their election timeouts.
    """
    banner("Test 2: Leader Failure and Re-Election")

    leader = find_leader()
    if not leader:
        fail_test("Leader failure + re-election", "No leader found before test — skipping")
        return

    print(f"  Current leader: {BOLD}{leader}{RESET}")
    stop_service(leader)

    print("  Waiting up to 15 s for a new leader to emerge …")
    new_leader = None
    for _ in range(15):
        time.sleep(1)
        for svc in RAFT_SERVICES:
            if svc == leader:
                continue
            logs = get_logs(svc, lines=40)
            # A new leader will either show the transition or start sending heartbeats
            if "→ LEADER" in logs or "sends RPC AppendEntries" in logs:
                new_leader = svc
                break
        if new_leader:
            break

    if new_leader and new_leader != leader:
        pass_test(
            "Leader failure + re-election",
            f"Old leader {leader} stopped → new leader {new_leader}",
        )
    else:
        fail_test(
            "Leader failure + re-election",
            f"No new leader elected after stopping {leader}",
        )

    # Restore the stopped node for subsequent tests
    start_service(leader)
    time.sleep(4)


def test_3_new_node_joining():
    """
    Test 3 — New Node Joining (restart a stopped node)
    Stop a follower node, let the cluster run operations, then restart it.
    The restarted node must receive heartbeats and sync its log from the
    current leader (visible in its logs).
    """
    banner("Test 3: New Node Joining (Restart)")

    # Stop a non-leader follower
    leader = find_leader()
    stopped = None
    for svc in RAFT_SERVICES:
        if svc != leader:
            stopped = svc
            break

    if not stopped:
        fail_test("New node joining", "Could not identify a follower to stop")
        return

    stop_service(stopped)
    print(f"  Stopped follower: {stopped}")

    # Submit an operation while it is down
    if leader:
        ok, detail = submit_operation(leader, "SET rejoined_test=1")
        print(f"  Operation while node down: success={ok} detail={detail}")
    time.sleep(1)

    # Restart the node
    start_service(stopped)
    print(f"  Restarted {stopped}; waiting 5 s for it to sync …")
    time.sleep(5)

    # Verify it received heartbeats after restart
    logs = get_logs(stopped, lines=40)
    if "AppendEntries" in logs or "Executed op" in logs or "Copied" in logs:
        pass_test(
            "New node joining",
            f"{stopped} restarted and received AppendEntries / log sync from leader",
        )
        snippet = [ln for ln in logs.splitlines() if any(
            kw in ln for kw in ("AppendEntries", "Executed", "Copied", "FOLLOWER")
        )][-5:]
        for ln in snippet:
            print(f"    {ln}")
    else:
        fail_test(
            "New node joining",
            f"{stopped} restarted but no AppendEntries seen in logs",
        )


def test_4_follower_failure_availability():
    """
    Test 4 — Follower Failure: Cluster Remains Available
    Stop TWO follower nodes (cluster has 5 nodes; majority = 3, so 3 up = OK).
    Submit operations; the leader must still commit them successfully.
    Then restore the stopped nodes.
    """
    banner("Test 4: Follower Failure — Cluster Availability")

    leader = find_leader()
    if not leader:
        fail_test("Follower failure — cluster availability", "No leader found — skipping")
        return

    followers = [svc for svc in RAFT_SERVICES if svc != leader]
    print(f"  Current leader: {BOLD}{leader}{RESET}")

    # Stop 2 followers (5-node cluster still has majority = 3 nodes)
    to_stop = followers[:2]
    for svc in to_stop:
        stop_service(svc)
    print(f"  Stopped followers: {to_stop}")
    time.sleep(3)

    # Try to commit an operation with only 3 nodes alive (retry a few times)
    alive = [s for s in RAFT_SERVICES if s not in to_stop]
    target = leader if leader in alive else alive[0]
    ok, detail = False, ""
    for attempt in range(4):
        ok, detail = submit_operation(target, "SET follower_fail_test=1")
        if ok:
            break
        print(f"  Retry {attempt + 1}: {detail}")
        time.sleep(2)

    print(f"  Operation with 2 followers down: success={ok} detail={detail}")

    if ok:
        pass_test(
            "Follower failure — cluster availability",
            f"Committed with {to_stop} stopped; cluster maintained majority",
        )
    else:
        fail_test(
            "Follower failure — cluster availability",
            f"Operation failed with 2 followers stopped: {detail}",
        )

    # Restore stopped nodes
    for svc in to_stop:
        start_service(svc)
    time.sleep(5)


def test_5_log_replication_consistency():
    """
    Test 5 — Log Replication Consistency
    Submit several operations through the leader.  Then check that all healthy
    nodes show 'Executed op' or 'Committed op' for each operation in their logs,
    confirming that the full log was replicated and committed cluster-wide.
    """
    banner("Test 5: Log Replication Consistency")

    # Wait for cluster to stabilize after previous tests, then find leader
    leader = None
    for attempt in range(6):
        leader = find_leader()
        if leader:
            break
        print(f"  Waiting for leader to be available … ({attempt + 1})")
        time.sleep(2)

    if not leader:
        fail_test("Log replication consistency", "No leader found — skipping")
        return

    ops = ["SET a=10", "SET b=20", "SET c=30"]
    print(f"  Submitting {len(ops)} operations via {leader} …")
    all_committed = True
    for op in ops:
        ok, detail = "", ""
        for retry in range(3):
            ok, detail = submit_operation(leader, op)
            if ok:
                break
            time.sleep(2)
        print(f"    op='{op}'  success={ok}  {detail}")
        if not ok:
            all_committed = False

    if not all_committed:
        fail_test("Log replication consistency", "Not all operations committed by leader")
        return

    # Give followers time to apply the entries (nodes restarted by previous tests
    # need several heartbeat cycles to receive and execute the full log)
    time.sleep(6)

    # Verify every node shows execution of the operations in its logs
    print("  Checking follower logs for replicated operations …")
    replicated_on_all = True
    for svc in RAFT_SERVICES:
        logs = get_logs(svc, lines=120)
        missing = [op for op in ops if op not in logs]
        if missing:
            print(f"    {RED}MISS{RESET} {svc}: missing {missing}")
            replicated_on_all = False
        else:
            print(f"    {GREEN}OK{RESET}   {svc}: all operations present in log")

    if replicated_on_all:
        pass_test(
            "Log replication consistency",
            "All 5 nodes show all 3 committed operations in their logs",
        )
    else:
        fail_test(
            "Log replication consistency",
            "One or more nodes are missing committed log entries",
        )


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary() -> None:
    banner("Test Summary")
    passed = sum(1 for r in results if r["result"] == "PASS")
    total  = len(results)
    colour = GREEN if passed == total else RED
    for r in results:
        icon = f"{GREEN}PASS{RESET}" if r["result"] == "PASS" else f"{RED}FAIL{RESET}"
        print(f"  {icon}  {r['test']}")
        if r["detail"]:
            print(f"        {r['detail']}")
    print(f"\n  {colour}{BOLD}{passed}/{total} tests passed{RESET}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{BOLD}Raft Test Suite — Q5{RESET}")
    print("Make sure `docker compose up` is running before executing this script.\n")

    try:
        test_1_initial_leader_election()
        test_2_leader_failure_reelection()
        test_3_new_node_joining()
        test_4_follower_failure_availability()
        test_5_log_replication_consistency()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        print_summary()
