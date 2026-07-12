"""
[AIR-0227C Stage 4/9 - TEST-ONLY, NOT PRODUCTION] Local stand-in for the
central server's /api/worker/* contract.

This is explicitly NOT auth-web and does NOT touch Supabase or any
production system. It exists so Stage 9's "실제 원격 렌더링 E2E" can be
proven against a real HTTP round-trip (register -> claim -> lease ->
progress -> complete, with real network failure/idempotency/lease-expiry
behavior) without deploying anything or running a production DB migration.
docs/AIR_WORKER_AUTH.md documents where the real implementation belongs
(auth-web, following the desktopSession.ts HMAC pattern) - this mock
implements the identical wire contract (same paths, same request/response
shapes) so central_client.py needs zero code changes to point at the real
thing once it exists (only CENTRAL_SERVER_URL/AIRWORKER_TOKEN change).

Authoritative worker capabilities are hardcoded here (WORKER_REGISTRY) to
prove that a worker's *self-declared* allowed_job_types in a request body
is never trusted - only what the "issuer" (this mock, standing in for the
real Worker Token issuer) actually granted governs what claim_job can hand
out. This is the concrete enforcement of principle #3/#4 ("중앙 서버가
tenant_id/job_id/권한을 결정한다", "Worker는 자신에게 lease된 작업만 처리").
"""
import json
import sqlite3
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException

app = FastAPI(title="AIR Worker Dev Central Server (TEST ONLY)")

DB_PATH = Path(__file__).resolve().parent / "dev_central.db"
LEASE_TTL_SECONDS = 8.0  # short on purpose, for testable expiry - production would use minutes

# worker_token -> authoritative claims. In production this is a verified,
# server-issued HMAC token (docs/AIR_WORKER_AUTH.md); here it's just a
# lookup so the mock can enforce "server decides, not the worker".
WORKER_REGISTRY = {
    "test-worker-token-A": {"worker_id": "worker-A", "allowed_job_types": ["render_video"], "tenant_id": "tenant-test"},
    "test-worker-token-legacy": {"worker_id": "legacy-picadiri-worker", "allowed_job_types": ["render_video"], "tenant_id": "tenant-test"},
}


def _conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init():
    conn = _conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS remote_jobs (
            job_id TEXT PRIMARY KEY,
            job_type TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 0,
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            lease_id TEXT,
            worker_instance_id TEXT,
            lease_expires_at REAL,
            attempt_number INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            output_ref TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS idempotency_seen (
            idempotency_key TEXT PRIMARY KEY,
            response TEXT NOT NULL,
            at REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()


_init()


def _authorize(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing worker token")
    token = authorization[len("Bearer "):]
    claims = WORKER_REGISTRY.get(token)
    if not claims:
        raise HTTPException(401, "Invalid or expired worker token")
    return claims


@app.post("/api/worker/register")
async def register(body: dict, authorization: str | None = Header(default=None)):
    claims = _authorize(authorization)
    return {"worker_id": claims["worker_id"], "allowed_job_types": claims["allowed_job_types"], "registered_at": time.time()}


@app.post("/api/worker/heartbeat")
async def heartbeat(body: dict, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    return {"ok": True, "server_time": time.time()}


def _expire_stale_leases(conn):
    now = time.time()
    conn.execute(
        "UPDATE remote_jobs SET status='queued', lease_id=NULL, worker_instance_id=NULL, lease_expires_at=NULL "
        "WHERE status='leased' AND lease_expires_at < ?",
        (now,),
    )


@app.post("/api/worker/jobs/claim")
async def claim(body: dict, authorization: str | None = Header(default=None)):
    claims = _authorize(authorization)
    # [enforcement] intersect the request's self-declared types with the
    # AUTHORITATIVE list from the token - the worker cannot expand its own
    # scope by just asking for more.
    requested = set(body.get("allowed_job_types", []))
    authoritative = set(claims["allowed_job_types"])
    allowed = list(requested & authoritative) or list(authoritative)

    conn = _conn()
    try:
        _expire_stale_leases(conn)
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        placeholders = ",".join("?" for _ in allowed)
        row = conn.execute(
            f"SELECT * FROM remote_jobs WHERE status='queued' AND job_type IN ({placeholders}) "
            f"AND tenant_id = ? ORDER BY priority DESC, created_at ASC LIMIT 1",
            (*allowed, claims["tenant_id"]),
        ).fetchone()
        if not row:
            conn.execute("COMMIT")
            return {"job_id": None}
        lease_id = str(uuid.uuid4())
        expires_at = time.time() + LEASE_TTL_SECONDS
        conn.execute(
            "UPDATE remote_jobs SET status='leased', lease_id=?, worker_instance_id=?, lease_expires_at=?, attempt_number=attempt_number+1 WHERE job_id=?",
            (lease_id, body.get("worker_instance_id"), expires_at, row["job_id"]),
        )
        conn.commit()
        return {
            "job_id": row["job_id"], "job_type": row["job_type"], "priority": row["priority"],
            "payload": json.loads(row["payload"]), "lease_id": lease_id, "lease_expires_at": expires_at,
            "tenant_id": row["tenant_id"],
        }
    finally:
        conn.close()


def _check_lease(conn, job_id, lease_id, worker_instance_id):
    row = conn.execute("SELECT * FROM remote_jobs WHERE job_id=?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, "job not found")
    if row["status"] != "leased":
        raise HTTPException(409, f"job is not in leased state (status={row['status']})")
    if row["lease_id"] != lease_id:
        raise HTTPException(403, "stale or invalid lease_id - lease was reassigned")
    if row["worker_instance_id"] != worker_instance_id:
        raise HTTPException(403, "worker_instance_id does not match lease holder")
    if row["lease_expires_at"] < time.time():
        raise HTTPException(403, "lease has expired")
    return row


@app.post("/api/worker/jobs/{job_id}/progress")
async def progress(job_id: str, body: dict, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    conn = _conn()
    try:
        _check_lease(conn, job_id, body.get("lease_id"), body.get("worker_instance_id"))
        return {"ok": True, "progress": body.get("progress")}
    finally:
        conn.close()


def _idempotent(conn, key, compute):
    if key:
        existing = conn.execute("SELECT response FROM idempotency_seen WHERE idempotency_key=?", (key,)).fetchone()
        if existing:
            return json.loads(existing["response"]), True
    result = compute()
    if key:
        conn.execute("INSERT OR REPLACE INTO idempotency_seen (idempotency_key, response, at) VALUES (?, ?, ?)",
                     (key, json.dumps(result), time.time()))
        conn.commit()
    return result, False


@app.post("/api/worker/jobs/{job_id}/complete")
async def complete(job_id: str, body: dict, authorization: str | None = Header(default=None), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    _authorize(authorization)
    conn = _conn()
    try:
        def _do():
            row = _check_lease(conn, job_id, body.get("lease_id"), body.get("worker_instance_id"))
            conn.execute("UPDATE remote_jobs SET status='completed', output_ref=? WHERE job_id=?", (body.get("output_ref"), job_id))
            conn.commit()
            return {"ok": True, "job_id": job_id, "status": "completed"}
        result, replayed = _idempotent(conn, idempotency_key, _do)
        result["idempotent_replay"] = replayed
        return result
    finally:
        conn.close()


@app.post("/api/worker/jobs/{job_id}/fail")
async def fail(job_id: str, body: dict, authorization: str | None = Header(default=None), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    _authorize(authorization)
    conn = _conn()
    try:
        def _do():
            row = _check_lease(conn, job_id, body.get("lease_id"), body.get("worker_instance_id"))
            conn.execute("UPDATE remote_jobs SET status='failed', output_ref=? WHERE job_id=?", (body.get("error_message"), job_id))
            conn.commit()
            return {"ok": True, "job_id": job_id, "status": "failed"}
        result, replayed = _idempotent(conn, idempotency_key, _do)
        result["idempotent_replay"] = replayed
        return result
    finally:
        conn.close()


@app.post("/api/worker/jobs/{job_id}/renew-lease")
async def renew_lease(job_id: str, body: dict, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    conn = _conn()
    try:
        row = _check_lease(conn, job_id, body.get("lease_id"), body.get("worker_instance_id"))
        new_expiry = time.time() + LEASE_TTL_SECONDS
        conn.execute("UPDATE remote_jobs SET lease_expires_at=? WHERE job_id=?", (new_expiry, job_id))
        conn.commit()
        return {"ok": True, "lease_expires_at": new_expiry}
    finally:
        conn.close()


# --- test-only helper endpoints (not part of the real contract) ---

@app.post("/_test/seed-job")
async def seed_job(body: dict):
    """Not part of the real /api/worker/* contract - lets the E2E test
    script create a queued job on the mock server without needing a
    separate 'admin creates job' surface."""
    conn = _conn()
    job_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO remote_jobs (job_id, job_type, tenant_id, priority, payload, status, created_at) VALUES (?, ?, ?, ?, ?, 'queued', ?)",
        (job_id, body.get("job_type", "render_video"), body.get("tenant_id", "tenant-test"),
         body.get("priority", 100), json.dumps(body.get("payload", {})), time.time()),
    )
    conn.commit()
    conn.close()
    return {"job_id": job_id}


@app.get("/_test/job/{job_id}")
async def test_job_status(job_id: str):
    conn = _conn()
    row = conn.execute("SELECT * FROM remote_jobs WHERE job_id=?", (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else {"error": "not found"}
