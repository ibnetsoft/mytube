"""
[AIR-0227C Stage 2] Live priority/FIFO verification.

Submits jobs with a deliberately invalid source_path and max_retries=0, so
each one fails fast at the PREPARING step (prepare_temp_dir raises
immediately) instead of running a real ~15s render - this still exercises
the REAL claim_next_job()/transition() code path (the thing actually under
test), just without waiting through full renders for every case.

Requires: manager.py already running (Local API reachable) with an EMPTY
job queue. Run from worker/ with the venv python.
"""
import sys
import time

sys.path.insert(0, ".")
import requests

import job_store
from local_api_token import get_or_create_token
from worker_config import LOCAL_API_HOST, LOCAL_API_PORT

BASE_URL = f"http://{LOCAL_API_HOST}:{LOCAL_API_PORT}"
BAD_PAYLOAD = {"source_path": "C:\\does\\not\\exist\\nope"}


def _headers():
    # [AIR-0227D Stage 1 regression fix] this script predates AIR-0227C
    # Stage 3 Local API auth and was never updated to send it - submit()
    # was getting a bare 401 with no 'job_id' key, not the seed job it
    # expected. Local direct job_store reads/writes below are unaffected
    # (no HTTP, no auth boundary).
    return {"Authorization": f"Bearer {get_or_create_token()}"}


def submit(priority, label):
    r = requests.post(f"{BASE_URL}/jobs/submit", json={
        "job_type": "render_video", "priority": priority,
        "payload": BAD_PAYLOAD, "max_retries": 0, "source": f"fifo-test-{label}",
    }, headers=_headers(), timeout=5).json()
    return r["job_id"]


def wait_terminal(job_ids, timeout=30):
    deadline = time.time() + timeout
    pending = set(job_ids)
    while pending and time.time() < deadline:
        for jid in list(pending):
            job = job_store.get_job(jid)
            if job["status"] in ("COMPLETED", "FAILED", "CANCELED"):
                pending.discard(jid)
        if pending:
            time.sleep(0.3)
    return pending


def claim_time(job_id):
    for row in job_store.transition_history(job_id):
        if row["to_status"] == "CLAIMED":
            return row["at"]
    return None


def scenario_priority_preemption():
    print("\n=== Scenario 1: priority preemption (A=20, B=100, C=20, submitted in that order) ===")
    # Occupy the worker first so A/B/C all sit QUEUED together before any is claimed.
    primer = submit(1, "primer")
    deadline = time.time() + 10
    while job_store.get_job(primer)["status"] not in ("PREPARING", "FAILED") and time.time() < deadline:
        time.sleep(0.05)
    time.sleep(0.05)  # let the primer's own claim fully commit before the next batch queues up

    a = submit(20, "A")
    b = submit(100, "B")
    c = submit(20, "C")
    print(f"submitted (in order): A={a} (pri20)  B={b} (pri100)  C={c} (pri20)")

    wait_terminal([primer, a, b, c])
    order = sorted([a, b, c], key=claim_time)
    labels = {a: "A", b: "B", c: "C"}
    result = [labels[j] for j in order]
    print(f"claim order observed: {result}")
    expected = ["B", "A", "C"]
    print(f"expected:             {expected}")
    print("RESULT:", "PASS" if result == expected else "FAIL")
    return result == expected


def scenario_fifo_same_priority():
    print("\n=== Scenario 2: FIFO within same priority (5 jobs, priority=50, sequential submit) ===")
    primer = submit(1, "primer2")
    deadline = time.time() + 10
    while job_store.get_job(primer)["status"] not in ("PREPARING", "FAILED") and time.time() < deadline:
        time.sleep(0.05)
    time.sleep(0.05)

    ids = []
    for i in range(5):
        jid = submit(50, f"fifo{i}")
        ids.append(jid)
        time.sleep(0.05)  # keep submission order unambiguous in created_at
    print(f"submitted in order: {ids}")

    wait_terminal([primer, *ids])
    order = sorted(ids, key=claim_time)
    print(f"claim order observed: {order}")
    print("RESULT:", "PASS" if order == ids else "FAIL")
    return order == ids


def scenario_concurrent_claim():
    print("\n=== Scenario 3: concurrent claim - only one claimer gets the job ===")
    import threading
    jid = job_store.submit_job("render_video", BAD_PAYLOAD, priority=99, max_retries=0, source="concurrent-test")
    results = []
    lock = threading.Lock()

    def try_claim(fake_pid):
        job = job_store.claim_next_job(["render_video"], fake_pid)
        with lock:
            results.append((fake_pid, job["job_id"] if job else None))

    threads = [threading.Thread(target=try_claim, args=(90000 + i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    winners = [r for r in results if r[1] == jid]
    print(f"10 concurrent claim attempts, winners: {winners}")
    print("RESULT:", "PASS" if len(winners) == 1 else f"FAIL ({len(winners)} winners)")
    # cleanup: this claim didn't go through render_worker.py so nothing will ever resolve it -
    # cancel it directly so it doesn't pollute later scenarios/manager state.
    job_store.transition(jid, job_store.CANCELED, reason="concurrent-claim test cleanup")
    return len(winners) == 1


if __name__ == "__main__":
    r1 = scenario_priority_preemption()
    r2 = scenario_fifo_same_priority()
    r3 = scenario_concurrent_claim()
    print(f"\n=== SUMMARY: preemption={r1} fifo={r2} concurrent_claim={r3} ===")
    sys.exit(0 if (r1 and r2 and r3) else 1)
