"""
[AIR-0227C Stage 4/5/7] HTTP client for the central server's /api/worker/*
contract (docs/AIR_WORKER_AUTH.md, docs/AIR_WORKER_LEASE_PROTOCOL.md).

Talks to whatever CENTRAL_SERVER_URL points at - in production that would be
auth-web (docs/AIR_WORKER_AUTH.md documents the real route design there,
not implemented/deployed this Task); for local dev/E2E it points at
worker/dev_central_server (a Python FastAPI stand-in implementing the
identical wire contract, explicitly labeled test-only - same "documented
substitute" pattern AIR-0226 used with Gemini standing in for Hermes).

Failure policy (Stage 7, docs/AIR_WORKER_REMOTE_E2E_QA.md has the live
results):
  - Network errors (connection refused/timeout) -> bounded exponential
    backoff, capped retry count. Rendering itself is NEVER blocked on this -
    callers treat a failed report_progress/renew_lease as non-fatal and
    keep working locally; only claim_job blocks (nothing to claim without
    the server).
  - Auth errors (401/403) -> NO retry. The worker token is either wrong or
    expired; retrying won't fix that and would just hammer the server.
  - complete_job/fail_job always send an Idempotency-Key (the LOCAL job_id)
    so a retried request after a lost response does not double-process.
"""
import os
import time
import uuid

import requests

CENTRAL_SERVER_URL = os.environ.get("AIRWORKER_CENTRAL_SERVER_URL", "http://127.0.0.1:8799")
WORKER_TOKEN = os.environ.get("AIRWORKER_TOKEN", "")

MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_CAP_SECONDS = 16.0
REQUEST_TIMEOUT = 10


class AuthError(Exception):
    """401/403 - never retried automatically."""


class CentralServerUnavailable(Exception):
    """Retries exhausted against a network-level failure - may still
    succeed on a LATER attempt (e.g. the outbox flush), since nothing about
    the request itself was rejected."""


class LeaseConflict(Exception):
    """[AIR-0227C Stage 7, found via live long-outage QA] 409 - the lease
    this request refers to is no longer the active one (already completed/
    failed by a later attempt, expired and reassigned, etc). Unlike
    CentralServerUnavailable, retrying this exact request will NEVER
    succeed - the caller must stop retrying it, not keep re-queuing it into
    the outbox forever."""


def _headers(idempotency_key: str | None = None) -> dict:
    h = {"Authorization": f"Bearer {WORKER_TOKEN}"}
    if idempotency_key:
        h["Idempotency-Key"] = idempotency_key
    return h


def _request(method: str, path: str, json_body: dict | None = None, idempotency_key: str | None = None) -> dict:
    url = f"{CENTRAL_SERVER_URL}{path}"
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.request(method, url, json=json_body, headers=_headers(idempotency_key), timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            last_exc = e
            delay = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2 ** attempt))
            time.sleep(delay)
            continue

        if resp.status_code in (401, 403):
            raise AuthError(f"{method} {path} -> {resp.status_code}: {resp.text[:200]}")
        if resp.status_code == 409:
            raise LeaseConflict(f"{method} {path} -> 409: {resp.text[:200]}")
        if resp.status_code >= 500:
            last_exc = Exception(f"{resp.status_code}: {resp.text[:200]}")
            delay = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2 ** attempt))
            time.sleep(delay)
            continue
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    raise CentralServerUnavailable(f"{method} {path} failed after {MAX_RETRIES} attempts: {last_exc}")


def register(worker_id: str, worker_instance_id: str, allowed_job_types: list[str]) -> dict:
    return _request("POST", "/api/worker/register", {
        "worker_id": worker_id, "worker_instance_id": worker_instance_id,
        "allowed_job_types": allowed_job_types,
    })


def heartbeat(worker_id: str, worker_instance_id: str) -> dict:
    return _request("POST", "/api/worker/heartbeat", {
        "worker_id": worker_id, "worker_instance_id": worker_instance_id,
    })


def claim_job(worker_id: str, worker_instance_id: str, allowed_job_types: list[str]) -> dict | None:
    result = _request("POST", "/api/worker/jobs/claim", {
        "worker_id": worker_id, "worker_instance_id": worker_instance_id,
        "allowed_job_types": allowed_job_types,
    })
    return result if result and result.get("job_id") else None


def report_progress(remote_job_id: str, lease_id: str, worker_instance_id: str, progress: int, message: str) -> dict:
    return _request("POST", f"/api/worker/jobs/{remote_job_id}/progress", {
        "lease_id": lease_id, "worker_instance_id": worker_instance_id,
        "progress": progress, "message": message,
    })


def complete_job(remote_job_id: str, lease_id: str, worker_instance_id: str, idempotency_key: str, output_ref: str,
                  result_payload: dict | None = None) -> dict:
    # [AIR-0230] result_payload is optional and additive - render jobs never
    # pass it (output_ref, a Drive file ref, is their whole "result"), but
    # topic_benchmark_analyze's result is only a few KB of JSON, so it's
    # sent inline instead of requiring a second fetch. The server route only
    # forwards it to report_worker_hermes_job_outcome (the render RPC has no
    # matching param and ignores extra body fields it doesn't read).
    body = {"lease_id": lease_id, "worker_instance_id": worker_instance_id, "output_ref": output_ref}
    if result_payload is not None:
        body["result_payload"] = result_payload
    return _request("POST", f"/api/worker/jobs/{remote_job_id}/complete", body, idempotency_key=idempotency_key)


def fail_job(remote_job_id: str, lease_id: str, worker_instance_id: str, idempotency_key: str, error_code: str, error_message: str) -> dict:
    return _request("POST", f"/api/worker/jobs/{remote_job_id}/fail", {
        "lease_id": lease_id, "worker_instance_id": worker_instance_id,
        "error_code": error_code, "error_message": error_message,
    }, idempotency_key=idempotency_key)


def renew_lease(remote_job_id: str, lease_id: str, worker_instance_id: str) -> dict:
    # [AIR-0230, pre-existing bug fix unrelated to this task's own scope]
    # This called "/renew-lease", but the actual route folder is
    # auth-web/app/api/internal/worker/jobs/[jobId]/renew/route.ts - every
    # renew_lease() call was 404ing. Fixed while touching this file for the
    # topic_benchmark_analyze integration since a broken renew path would
    # have silently broken lease renewal for Hermes jobs too.
    return _request("POST", f"/api/worker/jobs/{remote_job_id}/renew", {
        "lease_id": lease_id, "worker_instance_id": worker_instance_id,
    })


def new_idempotency_key() -> str:
    return str(uuid.uuid4())
