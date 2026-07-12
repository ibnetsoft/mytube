"""
[AIR-0227B Stage 5/6/7] Local job store + state machine.

docs/AIR_WORKER_JOB_PROTOCOL.md (AIR-0227A) defined a generic
queued|claimed|running|paused|... schema. This Task's own instruction adds a
fuller, render-specific status enum and requires a *local* JSON/SQLite state
store, explicitly replacing remote_drive_worker.py's Supabase-backed
fetch_next_job/claim_job/update_job (which used service_role headers - not
reusable here per docs/AIR_WORKER_SECURITY.md §1's "service_role 사용 금지").

SQLite (not plain JSON) was chosen because multiple OS processes touch this
store concurrently (Local API reads for /jobs, Render Worker claims/updates,
Manager scans for ABANDONED jobs on recovery) - SQLite's file locking makes
concurrent access safe without hand-rolling a lock file, while still being
"a local JSON 또는 SQLite 상태 저장소" per the task's own wording.
"""
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from worker_config import JOB_DB_PATH

# Status enum exactly as specified by the AIR-0227B instruction (Stage 6).
QUEUED = "QUEUED"
CLAIMED = "CLAIMED"
PREPARING = "PREPARING"
RENDERING = "RENDERING"
UPLOADING = "UPLOADING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
CANCELED = "CANCELED"
ABANDONED = "ABANDONED"

TERMINAL_STATUSES = {COMPLETED, CANCELED}
ACTIVE_STATUSES = {CLAIMED, PREPARING, RENDERING, UPLOADING}

# Valid transitions: {from_status: {allowed_to_statuses}}
# docs/AIR_WORKER_JOB_RECOVERY.md documents *why* each edge exists.
TRANSITIONS = {
    QUEUED: {CLAIMED, CANCELED},
    CLAIMED: {PREPARING, FAILED, CANCELED, ABANDONED},
    PREPARING: {RENDERING, FAILED, CANCELED, ABANDONED},
    RENDERING: {UPLOADING, FAILED, CANCELED, ABANDONED},
    UPLOADING: {COMPLETED, FAILED, CANCELED, ABANDONED},
    COMPLETED: set(),
    FAILED: {QUEUED},       # retry re-queues
    CANCELED: set(),
    ABANDONED: {QUEUED, FAILED},  # retry re-queues, or quarantined permanently
}


class InvalidTransitionError(Exception):
    pass


_local = threading.local()


def _conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(JOB_DB_PATH), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        _local.conn = conn
    return conn


def init_db():
    conn = _conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            job_type TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'local_fixture',
            priority INTEGER NOT NULL DEFAULT 0,
            payload TEXT NOT NULL,
            status TEXT NOT NULL,
            worker_pid INTEGER,
            progress INTEGER NOT NULL DEFAULT 0,
            progress_message TEXT,
            created_at REAL NOT NULL,
            started_at REAL,
            completed_at REAL,
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            error_code TEXT,
            error_message TEXT,
            output_path TEXT,
            lease_id TEXT,
            worker_instance_id TEXT,
            lease_expires_at REAL,
            attempt_number INTEGER NOT NULL DEFAULT 1,
            remote_job_id TEXT,
            remote_ack_status TEXT
        )
        """
    )
    # [AIR-0227C Stage 5/7] lease + outbox columns added after the table
    # already existed in AIR-0227B installs - ALTER TABLE ADD COLUMN so
    # existing local worker/state/jobs.db files upgrade in place instead of
    # needing a wipe.
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    for col, ddl in [
        ("lease_id", "ALTER TABLE jobs ADD COLUMN lease_id TEXT"),
        ("worker_instance_id", "ALTER TABLE jobs ADD COLUMN worker_instance_id TEXT"),
        ("lease_expires_at", "ALTER TABLE jobs ADD COLUMN lease_expires_at REAL"),
        ("attempt_number", "ALTER TABLE jobs ADD COLUMN attempt_number INTEGER NOT NULL DEFAULT 1"),
        ("remote_job_id", "ALTER TABLE jobs ADD COLUMN remote_job_id TEXT"),
        ("remote_ack_status", "ALTER TABLE jobs ADD COLUMN remote_ack_status TEXT"),
    ]:
        if col not in existing_cols:
            conn.execute(ddl)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS job_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT NOT NULL,
            at REAL NOT NULL,
            reason TEXT
        )
        """
    )
    conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["payload"] = json.loads(d["payload"]) if d["payload"] else {}
    return d


def submit_job(job_type: str, payload: dict, priority: int = 0, source: str = "local_fixture",
               max_retries: int = 3, job_id: Optional[str] = None) -> str:
    job_id = job_id or str(uuid.uuid4())
    now = time.time()
    conn = _conn()
    conn.execute(
        """INSERT INTO jobs (job_id, job_type, source, priority, payload, status,
                              created_at, retry_count, max_retries)
           VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)""",
        (job_id, job_type, source, priority, json.dumps(payload, ensure_ascii=False), QUEUED, now, max_retries),
    )
    _log_transition(conn, job_id, None, QUEUED, "submitted")
    conn.commit()
    return job_id


def create_from_remote_claim(remote_job_id: str, job_type: str, payload: dict, priority: int,
                              lease_id: str, worker_instance_id: str, lease_expires_at: float) -> str:
    """[AIR-0227C Stage 5] Mirrors a job just claimed from the central
    server into the local store as CLAIMED (skipping QUEUED entirely - it
    was already claimed server-side before render_worker.py ever saw it).
    From here on it flows through the exact same PREPARING/RENDERING/
    UPLOADING state machine as a local_fixture job; only the lease_id/
    worker_instance_id/remote_job_id columns and the central_client calls
    render_worker.py makes alongside each local transition are different."""
    local_job_id = str(uuid.uuid4())
    now = time.time()
    conn = _conn()
    conn.execute(
        """INSERT INTO jobs (job_id, job_type, source, priority, payload, status, worker_pid,
                              created_at, started_at, retry_count, max_retries,
                              lease_id, worker_instance_id, lease_expires_at, remote_job_id)
           VALUES (?, ?, 'central_server', ?, ?, ?, NULL, ?, ?, 0, 0, ?, ?, ?, ?)""",
        (local_job_id, job_type, priority, json.dumps(payload, ensure_ascii=False), CLAIMED,
         now, now, lease_id, worker_instance_id, lease_expires_at, remote_job_id),
    )
    _log_transition(conn, local_job_id, None, QUEUED, "mirrored from central server claim")
    _log_transition(conn, local_job_id, QUEUED, CLAIMED, f"claimed via central server, lease_id={lease_id}")
    conn.commit()
    return local_job_id


def update_lease(job_id: str, lease_expires_at: float):
    conn = _conn()
    conn.execute("UPDATE jobs SET lease_expires_at = ? WHERE job_id = ?", (lease_expires_at, job_id))
    conn.commit()


def mark_remote_ack_pending(job_id: str):
    """[AIR-0227C Stage 7] The local render finished (COMPLETED/FAILED) but
    reporting that to the central server did not succeed yet (network down,
    5xx, retries exhausted). docs/AIR_WORKER_REMOTE_E2E_QA.md: 'render 완료
    결과는 로컬에 보존' - the local terminal status is authoritative and
    final regardless of this flag; it only tracks whether the *central
    server* still needs to be told."""
    conn = _conn()
    conn.execute("UPDATE jobs SET remote_ack_status = 'pending' WHERE job_id = ?", (job_id,))
    conn.commit()


def mark_remote_acked(job_id: str):
    conn = _conn()
    conn.execute("UPDATE jobs SET remote_ack_status = 'acked' WHERE job_id = ?", (job_id,))
    conn.commit()


def mark_remote_ack_abandoned(job_id: str):
    """[AIR-0227C Stage 7, found via a live long-network-outage test] The
    central server definitively rejected this report (LeaseConflict/409 -
    the lease was already completed/failed/reassigned by the time we could
    reach the server again). Unlike 'pending', this is NOT retried by
    list_pending_remote_acks()/_flush_pending_remote_acks() - retrying a
    409 will never succeed and would just loop forever. See
    docs/AIR_WORKER_REMOTE_E2E_QA.md for the discovered scenario: an outage
    longer than the lease TTL can let the SAME worker both (a) keep this
    now-moot report around and (b) independently re-claim and re-render the
    same job once the expired lease is swept - documented as a known
    limitation, not fully solved by this flag alone."""
    conn = _conn()
    conn.execute("UPDATE jobs SET remote_ack_status = 'abandoned' WHERE job_id = ?", (job_id,))
    conn.commit()


def list_pending_remote_acks() -> list[dict]:
    rows = _conn().execute(
        "SELECT * FROM jobs WHERE remote_ack_status = 'pending' AND status IN ('COMPLETED', 'FAILED')"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _log_transition(conn, job_id: str, from_status: Optional[str], to_status: str, reason: str = ""):
    conn.execute(
        "INSERT INTO job_transitions (job_id, from_status, to_status, at, reason) VALUES (?, ?, ?, ?, ?)",
        (job_id, from_status, to_status, time.time(), reason),
    )


def get_job(job_id: str) -> Optional[dict]:
    row = _conn().execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_jobs(status: Optional[str] = None, limit: int = 100) -> list[dict]:
    conn = _conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY priority DESC, created_at ASC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def transition(job_id: str, to_status: str, *, reason: str = "", worker_pid: Optional[int] = None,
               progress: Optional[int] = None, progress_message: Optional[str] = None,
               error_code: Optional[str] = None, error_message: Optional[str] = None,
               output_path: Optional[str] = None) -> dict:
    """Validate + apply a state transition, logging it to job_transitions.
    Raises InvalidTransitionError if the edge is not allowed (docs/AIR_WORKER_JOB_PROTOCOL.md
    state machine) - callers must treat this as a programming error, not a
    retryable condition."""
    conn = _conn()
    row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    if not row:
        raise KeyError(f"Unknown job_id: {job_id}")
    current = row["status"]
    allowed = TRANSITIONS.get(current, set())
    if to_status not in allowed:
        raise InvalidTransitionError(f"{job_id}: {current} -> {to_status} is not a valid transition (allowed: {sorted(allowed)})")

    fields = ["status = ?"]
    params = [to_status]

    if to_status == CLAIMED:
        fields.append("started_at = ?")
        params.append(time.time())
        if worker_pid is not None:
            fields.append("worker_pid = ?")
            params.append(worker_pid)
    if to_status in (COMPLETED, FAILED, CANCELED):
        fields.append("completed_at = ?")
        params.append(time.time())
    if to_status == QUEUED and current in (FAILED, ABANDONED):
        fields.append("retry_count = retry_count + 1")
        fields.append("worker_pid = NULL")
        fields.append("started_at = NULL")
    if progress is not None:
        fields.append("progress = ?")
        params.append(progress)
    if progress_message is not None:
        fields.append("progress_message = ?")
        params.append(progress_message)
    if error_code is not None:
        fields.append("error_code = ?")
        params.append(error_code)
    if error_message is not None:
        fields.append("error_message = ?")
        params.append(error_message)
    if output_path is not None:
        fields.append("output_path = ?")
        params.append(output_path)

    params.append(job_id)
    conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE job_id = ?", params)
    _log_transition(conn, job_id, current, to_status, reason)
    conn.commit()
    return get_job(job_id)


def update_progress(job_id: str, progress: int, message: str = ""):
    conn = _conn()
    conn.execute(
        "UPDATE jobs SET progress = ?, progress_message = ? WHERE job_id = ?",
        (progress, message, job_id),
    )
    conn.commit()


def claim_next_job(job_types: list[str], worker_pid: int) -> Optional[dict]:
    """Atomically claim the highest-priority QUEUED job of an allowed type,
    oldest-first within the same priority (docs/AIR_WORKER_RESOURCE_POLICY.md
    §1, matching remote_render_queue's existing FIFO convention)."""
    conn = _conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        placeholders = ",".join("?" for _ in job_types)
        row = conn.execute(
            f"""SELECT * FROM jobs WHERE status = ? AND job_type IN ({placeholders})
                ORDER BY priority DESC, created_at ASC LIMIT 1""",
            (QUEUED, *job_types),
        ).fetchone()
        if not row:
            conn.execute("COMMIT")
            return None
        job_id = row["job_id"]
        conn.execute(
            "UPDATE jobs SET status = ?, worker_pid = ?, started_at = ? WHERE job_id = ?",
            (CLAIMED, worker_pid, time.time(), job_id),
        )
        _log_transition(conn, job_id, QUEUED, CLAIMED, f"claimed by pid={worker_pid}")
        conn.commit()
        return get_job(job_id)
    except Exception:
        conn.execute("ROLLBACK")
        raise


def transition_history(job_id: str) -> list[dict]:
    rows = _conn().execute(
        "SELECT from_status, to_status, at, reason FROM job_transitions WHERE job_id = ? ORDER BY id ASC",
        (job_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def find_stale_active_jobs(alive_pid: Optional[int]) -> list[dict]:
    """[AIR-0227B Stage 7 recovery] Jobs left in an ACTIVE_STATUSES status
    whose worker_pid is not the currently-running Render Worker's pid are
    orphaned claims from a process that died mid-job (crash, force-kill) -
    the Manager calls this on startup/health-check to find them."""
    conn = _conn()
    placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
    if alive_pid is None:
        rows = conn.execute(
            f"SELECT * FROM jobs WHERE status IN ({placeholders})", tuple(ACTIVE_STATUSES)
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT * FROM jobs WHERE status IN ({placeholders}) AND (worker_pid IS NULL OR worker_pid != ?)",
            (*ACTIVE_STATUSES, alive_pid),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def mark_abandoned_and_recover(job: dict) -> dict:
    """[AIR-0227B Stage 7] ABANDONED -> retry (QUEUED, retry_count+=1) if
    under max_retries, else quarantine as FAILED with a distinct error_code
    so it's never silently re-tried again. 'avoid needless re-render': if a
    valid output.mp4 already exists at the job's expected output_path (the
    job had reached UPLOADING before its process died), skip straight to
    COMPLETED instead of discarding real work."""
    job_id = job["job_id"]
    conn = _conn()
    current = get_job(job_id)["status"]
    if current not in ACTIVE_STATUSES:
        return get_job(job_id)  # already resolved by the time we got here

    conn.execute("UPDATE jobs SET status = ? WHERE job_id = ?", (ABANDONED, job_id))
    _log_transition(conn, job_id, current, ABANDONED, "owning process not alive (crash/force-kill detected)")
    conn.commit()

    output_path = job.get("output_path")
    if output_path and Path(output_path).exists() and Path(output_path).stat().st_size > 0:
        return transition(job_id, COMPLETED, reason="recovered: valid output already existed, avoided needless re-render")

    if job["retry_count"] < job["max_retries"]:
        return transition(job_id, QUEUED, reason=f"recovery retry {job['retry_count'] + 1}/{job['max_retries']}")

    return transition(
        job_id, FAILED, reason="recovery exhausted max_retries",
        error_code="ABANDONED_MAX_RETRIES_EXCEEDED",
        error_message=f"Job was abandoned {job['max_retries']} times (owning process died mid-job) and quarantined.",
    )


init_db()
