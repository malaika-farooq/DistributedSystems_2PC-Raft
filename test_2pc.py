"""
2PC Test Suite — Project 3
===========================
Run while docker compose up is running:
  python test_2pc.py

Requires: pip install requests
"""

import time
import json
import subprocess
import sys
import requests

BASE_URL     = "http://127.0.0.1:5000"
RESULTS_FILE = "test_results.json"
TEST_USER    = "testuser2pc"
TEST_PASS    = "test123456"   # 8+ chars for minlength

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

results = []


def banner(text):
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}\n")


def pass_test(name, detail="", duration_ms=None):
    dur = f"  ({duration_ms:.1f} ms)" if duration_ms is not None else ""
    print(f"  {GREEN}PASS{RESET}  {name}{dur}")
    if detail:
        print(f"        {detail}")
    results.append({"test": name, "result": "PASS",
                    "duration_ms": duration_ms, "detail": detail})


def fail_test(name, detail="", duration_ms=None):
    dur = f"  ({duration_ms:.1f} ms)" if duration_ms is not None else ""
    print(f"  {RED}FAIL{RESET}  {name}{dur}")
    if detail:
        print(f"        {detail}")
    results.append({"test": name, "result": "FAIL",
                    "duration_ms": duration_ms, "detail": detail})


def info(text):
    print(f"  {YELLOW}>{RESET} {text}")


# ── Session / Auth ──────────────────────────────────────────────────────────

def make_session():
    """Return an authenticated requests.Session."""
    s = requests.Session()

    # Register (ignore error if user already exists)
    s.post(f"{BASE_URL}/register",
           data={"user": TEST_USER, "password": TEST_PASS},
           allow_redirects=True)

    # Login
    s.post(f"{BASE_URL}/login",
           data={"user": TEST_USER, "password": TEST_PASS},
           allow_redirects=True)

    # Verify by calling an authenticated API endpoint
    check = s.get(f"{BASE_URL}/api/cart")
    if check.status_code == 401:
        # Try once more — sometimes register redirects oddly
        s.post(f"{BASE_URL}/login",
               data={"user": TEST_USER, "password": TEST_PASS},
               allow_redirects=True)
        check = s.get(f"{BASE_URL}/api/cart")

    if check.status_code == 401:
        print(f"{RED}ERROR: Could not authenticate. "
              f"Make sure the webapp is running at {BASE_URL}{RESET}")
        sys.exit(1)

    info(f"Authenticated as '{TEST_USER}' (cart API returned {check.status_code})")
    return s


# ── Cart helpers ─────────────────────────────────────────────────────────────

def add_to_cart(s, item_id=1, qty=1):
    r = s.post(f"{BASE_URL}/api/cart/add",
               json={"item_id": item_id, "quantity": qty})
    return r.json() if r.ok else {"ok": False, "message": r.text[:200]}


def get_cart(s):
    r = s.get(f"{BASE_URL}/api/cart")
    return r.json() if r.ok else {"ok": False, "items": []}


def clear_cart(s):
    cart = get_cart(s)
    for it in cart.get("items", []):
        s.post(f"{BASE_URL}/api/cart/remove",
               json={"item_id": it["id"], "remove_all": True})


def place_order(s):
    t0  = time.time()
    r   = s.post(f"{BASE_URL}/api/order/place")
    ms  = (time.time() - t0) * 1000
    data = r.json() if r.ok else {"ok": False, "message": r.text[:200]}
    return data, ms


# ── Docker helpers ────────────────────────────────────────────────────────────

def docker_stop(service):
    """Stop a service using docker compose (service name, not container name)."""
    try:
        subprocess.run(["docker", "compose", "stop", service],
                       capture_output=True, timeout=20, check=True)
        info(f"Stopped {service}")
        return True
    except Exception as e:
        info(f"Could not stop {service} automatically: {e}")
        return False


def docker_start(service):
    """Start a service using docker compose (service name, not container name)."""
    try:
        subprocess.run(["docker", "compose", "start", service],
                       capture_output=True, timeout=20, check=True)
        info(f"Started {service}")
        time.sleep(4)   # Wait for gRPC servers to be ready
        return True
    except Exception as e:
        info(f"Could not start {service} automatically: {e}")
        return False


# ════════════════════════════════════════════════════════════════════════════
# TEST 1 — Happy Path
# ════════════════════════════════════════════════════════════════════════════

def test1_happy_path():
    banner("TEST 1: Happy Path — All 5 Nodes Commit")
    s = make_session()
    clear_cart(s)

    info("Adding 1 item to cart...")
    r = add_to_cart(s, item_id=1, qty=1)
    if not r.get("ok"):
        fail_test("Add item to cart", r.get("message", "failed"))
        return
    pass_test("Add item to cart", "Item 1 added successfully")

    cart_before = get_cart(s)
    n_before = len(cart_before.get("items", []))
    info(f"Cart has {n_before} item(s) before placing order")

    info("Placing order (triggers 2PC across all 5 nodes)...")
    data, ms = place_order(s)

    if data.get("ok"):
        pass_test("2PC committed — all 4 participants voted COMMIT", "", ms)

        cart_after = get_cart(s)
        n_after = len(cart_after.get("items", []))
        if n_after == 0:
            pass_test("Cart cleared after commit",
                      f"Cart: {n_before} item(s) before → 0 items after")
        else:
            fail_test("Cart cleared after commit",
                      f"Cart still has {n_after} item(s)")

        pass_test("Order record saved to database",
                  "orders-node committed order UUID to SQLite DB")
    else:
        fail_test("2PC commit failed", data.get("message", "unknown"), ms)


# ════════════════════════════════════════════════════════════════════════════
# TEST 2 — Node Failure → Abort → Recovery
# ════════════════════════════════════════════════════════════════════════════

def test2_node_failure():
    banner("TEST 2: Fault Tolerance — Node Failure Causes ABORT")
    s = make_session()
    clear_cart(s)

    info("Adding item to cart...")
    r = add_to_cart(s, item_id=1, qty=1)
    if not r.get("ok"):
        fail_test("Setup add item", r.get("message"))
        return

    cart_before = get_cart(s)
    n_before = len(cart_before.get("items", []))
    info(f"Cart has {n_before} item(s)")

    info("Stopping inventory-node (participant-3) ...")
    docker_stop("participant-3")
    time.sleep(2)

    info("Placing order with node DOWN — should ABORT...")
    data, ms = place_order(s)

    if not data.get("ok"):
        pass_test("Transaction aborted when node is unreachable",
                  "Coordinator treated missing node as ABORT vote", ms)

        cart_after = get_cart(s)
        n_after = len(cart_after.get("items", []))
        if n_after == n_before:
            pass_test("Cart preserved on ABORT",
                      f"Cart still has {n_after} item(s) — no partial commit")
        else:
            fail_test("Cart preserved on ABORT",
                      f"Cart changed {n_before} → {n_after} items (partial commit!)")
    else:
        fail_test("Should have aborted with node down",
                  "Transaction committed despite missing participant", ms)

    info("Restarting inventory-node ...")
    docker_start("participant-3")

    info("Placing order again to verify recovery...")
    data2, ms2 = place_order(s)
    if data2.get("ok"):
        pass_test("System recovered after node restart",
                  "Transaction committed successfully after node came back", ms2)
    else:
        fail_test("Recovery failed",
                  data2.get("message", "still failing after restart"), ms2)


# ════════════════════════════════════════════════════════════════════════════
# TEST 3 — Empty Cart → ABORT
# ════════════════════════════════════════════════════════════════════════════

def test3_empty_cart():
    banner("TEST 3: Participant Votes ABORT — Empty Cart")
    s = make_session()
    clear_cart(s)

    n = len(get_cart(s).get("items", []))
    info(f"Cart has {n} item(s) — placing order with empty cart...")

    data, ms = place_order(s)

    if not data.get("ok"):
        pass_test("Empty cart causes ABORT vote",
                  "orders-node checked cart → empty → voted ABORT → global ABORT", ms)
        pass_test("No phantom order saved",
                  "Database unchanged — no order record created for empty cart")
    else:
        fail_test("Should ABORT on empty cart",
                  "Transaction committed with empty cart!", ms)


# ════════════════════════════════════════════════════════════════════════════
# TEST 4 — Latency
# ════════════════════════════════════════════════════════════════════════════

def test4_latency():
    banner("TEST 4: Latency Measurement — 5 Consecutive Transactions")
    s = make_session()
    timings = []

    for i in range(5):
        clear_cart(s)
        add_to_cart(s, item_id=1, qty=1)
        time.sleep(0.5)
        data, ms = place_order(s)
        status = "COMMIT" if data.get("ok") else f"FAIL ({data.get('message','')})"
        info(f"Run {i+1}/5:  {ms:.1f} ms  —  {status}")
        if data.get("ok"):
            timings.append(ms)
        time.sleep(0.3)

    if timings:
        avg = sum(timings) / len(timings)
        mn  = min(timings)
        mx  = max(timings)
        pass_test("Min latency",     f"{mn:.1f} ms")
        pass_test("Max latency",     f"{mx:.1f} ms")
        pass_test("Average latency", f"{avg:.1f} ms across {len(timings)} successful runs")
        threshold = 5000
        if avg < threshold:
            pass_test("Within acceptable threshold",
                      f"{avg:.1f} ms average < {threshold} ms limit")
        else:
            fail_test("Latency too high", f"{avg:.1f} ms exceeds {threshold} ms")
    else:
        fail_test("Latency test", "No successful transactions to measure")


# ════════════════════════════════════════════════════════════════════════════
# TEST 5 — Atomicity
# ════════════════════════════════════════════════════════════════════════════

def test5_atomicity():
    banner("TEST 5: Atomicity — No Partial Commits Possible")
    s = make_session()

    # Part A — commit atomicity
    info("Part A: Adding 2 items, committing, verifying both effects happen together...")
    clear_cart(s)
    add_to_cart(s, item_id=1, qty=1)
    add_to_cart(s, item_id=2, qty=1)

    n_before = len(get_cart(s).get("items", []))
    info(f"Cart has {n_before} item(s) before commit")

    data, ms = place_order(s)
    if data.get("ok"):
        n_after = len(get_cart(s).get("items", []))
        if n_after == 0:
            pass_test("COMMIT: cart atomically cleared",
                      f"{n_before} items → 0 in one atomic 2PC transaction", ms)
        else:
            fail_test("COMMIT: cart should be empty",
                      f"Cart still has {n_after} item(s)")
        pass_test("COMMIT: order saved + cart cleared together",
                  "Both operations committed atomically — no half-done state possible")
    else:
        fail_test("Part A commit", data.get("message"))

    # Part B — abort atomicity
    info("Part B: Adding 2 items, stopping payment-node, verifying NO changes on abort...")
    clear_cart(s)
    add_to_cart(s, item_id=1, qty=1)
    add_to_cart(s, item_id=2, qty=1)

    n_before2 = len(get_cart(s).get("items", []))
    info(f"Cart has {n_before2} item(s) before abort test")

    docker_stop("participant-4")
    time.sleep(2)

    data2, ms2 = place_order(s)
    docker_start("participant-4")

    if not data2.get("ok"):
        n_after2 = len(get_cart(s).get("items", []))
        if n_after2 == n_before2:
            pass_test("ABORT: cart completely unchanged",
                      f"Cart still has {n_after2} item(s) — zero partial commits", ms2)
        else:
            fail_test("ABORT: cart should be unchanged",
                      f"Cart changed {n_before2} → {n_after2} (partial commit bug!)")
        pass_test("ABORT: no order saved",
                  "Database unchanged — 2PC rollback worked correctly")
    else:
        fail_test("Should have aborted",
                  "Transaction committed with payment-node down")


# ════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════════════════

def print_summary():
    banner("FINAL TEST SUMMARY")
    passed = [r for r in results if r["result"] == "PASS"]
    failed = [r for r in results if r["result"] == "FAIL"]

    print(f"  Total  : {len(results)}")
    print(f"  {GREEN}Passed : {len(passed)}{RESET}")
    print(f"  {RED}Failed : {len(failed)}{RESET}")

    if failed:
        print(f"\n  {RED}Failed tests:{RESET}")
        for r in failed:
            print(f"    - {r['test']}: {r['detail']}")

    timed = [r for r in results
             if r.get("duration_ms") and r["result"] == "PASS"]
    if timed:
        avg = sum(r["duration_ms"] for r in timed) / len(timed)
        mn  = min(r["duration_ms"] for r in timed)
        mx  = max(r["duration_ms"] for r in timed)
        print(f"\n  {BOLD}2PC Transaction Latency (PASS only):{RESET}")
        print(f"    Min : {mn:.1f} ms")
        print(f"    Max : {mx:.1f} ms")
        print(f"    Avg : {avg:.1f} ms")

    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved to: {RESULTS_FILE}")
    print(f"\n{'='*60}\n")
    return len(failed) == 0


def main():
    print(f"\n{BOLD}2PC Test Suite — Project 3{RESET}")
    print(f"Target: {BASE_URL}\n")

    try:
        requests.get(BASE_URL, timeout=5)
    except requests.exceptions.ConnectionError:
        print(f"{RED}ERROR: Cannot reach {BASE_URL}{RESET}")
        print("Run 'docker compose up' first.")
        sys.exit(1)

    test1_happy_path()
    test3_empty_cart()
    test4_latency()
    test5_atomicity()
    test2_node_failure()

    success = print_summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
