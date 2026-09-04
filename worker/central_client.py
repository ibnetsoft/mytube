"""
[AIR-0227C Stage 4/5/7, path fix AIR-0227D-STAGING-UNBLOCK] HTTP client for
the central server's /api/internal/worker/* contract (docs/AIR_WORKER_AUTH.md,
docs/AIR_WORKER_LEASE_PROTOCOL.md, docs/AIR_WORKER_CENTRAL_API.md).

[AIR-0227D-STAGING-UNBLOCK] Found via staging-unblock research: this module
previously called /api/worker/* (matching only the AIR-0227C-era design
sketch and worker/dev_central_server's mock), but the REAL, actually
implemented and staging-ready auth-web routes live at
auth-web/app/api/internal/worker/** (confirmed by directory listing -
register, heartbeat, jobs/claim, jobs/[jobId]/{progress,complete,fail,renew}).
Pointing AIRWORKER_CENTRAL_SERVER_URL at a real staging/production auth-web
deployment with the old paths would 404 on every call - fixed here, and
worker/dev_central_server/server.py's mock routes were updated to match
(so local E2E continues to exercise the same paths the real deployment
uses, instead of a stale contract). Also note: the real route is
"renew" (auth-web/app/api/internal/worker/jobs/[jobId]/renew/route.ts),
not "renew-lease".

Talks to whatever CENTRAL_SERVER_URL points at - in production/staging that
is a real deployed auth-web instance; for local dev/E2E it points at
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
from pathlib import Path
from json import JSONDecodeError

import requests
from dotenv import dotenv_values, load_dotenv

_env_values = {}
_local_worker_home = Path(
    os.environ.get(
        "AIRWORKER_HOME",
        Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "AIRStudio" / "AIRWorker",
    )
)
for env_path in (
    Path.cwd() / ".env",
    Path(__file__).resolve().parent.parent / ".env",
    _local_worker_home / ".env",
):
    if env_path.exists():
        _env_values.update({k: v for k, v in dotenv_values(env_path).items() if v})
        load_dotenv(env_path, override=False)

CENTRAL_SERVER_URL = (
    _env_values.get("AIRWORKER_CENTRAL_SERVER_URL")
    or _env_values.get("DASHBOARD_URL")
    or os.environ.get("AIRWORKER_CENTRAL_SERVER_URL")
    or os.environ.get("DASHBOARD_URL")
    or "http://127.0.0.1:8799"
).rstrip("/")
WORKER_TOKEN = os.environ.get("AIRWORKER_TOKEN") or _env_values.get("AIRWORKER_TOKEN", "")
VERCEL_PROTECTION_BYPASS_SECRET = os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET", "")

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


class CentralRouteNotFound(CentralServerUnavailable):
    """404 from a deployed central server.

    This usually means the worker is pointed at an older/stale web
    deployment, not that local work should stop.
    """


class LeaseConflict(Exception):
    """[AIR-0227C Stage 7, found via live long-outage QA] 409 - the lease
    this request refers to is no longer the active one (already completed/
    failed by a later attempt, expired and reassigned, etc). Unlike
    CentralServerUnavailable, retrying this exact request will NEVER
    succeed - the caller must stop retrying it, not keep re-queuing it into
    the outbox forever."""


def _headers(idempotency_key: str | None = None) -> dict:
    h = {"Authorization": f"Bearer {WORKER_TOKEN}"}
    if VERCEL_PROTECTION_BYPASS_SECRET:
        h["x-vercel-protection-bypass"] = VERCEL_PROTECTION_BYPASS_SECRET
    if idempotency_key:
        h["Idempotency-Key"] = idempotency_key
    return h


def _request(method: str, path: str, json_body: dict | None = None, idempotency_key: str | None = None) -> dict:
    request_path = path
    url = f"{CENTRAL_SERVER_URL}{request_path}"
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.request(method, url, json=json_body, headers=_headers(idempotency_key), timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            last_exc = e
            delay = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2 ** attempt))
            time.sleep(delay)
            continue

        if resp.status_code == 404 and request_path.startswith("/api/internal/worker/"):
            request_path = request_path.replace("/api/internal/worker/", "/api/worker-central/", 1)
            url = f"{CENTRAL_SERVER_URL}{request_path}"
            try:
                resp = requests.request(method, url, json=json_body, headers=_headers(idempotency_key), timeout=REQUEST_TIMEOUT)
            except requests.RequestException as e:
                last_exc = e
                delay = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2 ** attempt))
                time.sleep(delay)
                continue

        if resp.status_code in (401, 403):
            raise AuthError(f"{method} {request_path} -> {resp.status_code}: {resp.text[:200]}")
        if resp.status_code == 404:
            raise CentralRouteNotFound(f"{method} {request_path} -> 404: {resp.text[:200]}")
        if resp.status_code == 409:
            raise LeaseConflict(f"{method} {request_path} -> 409: {resp.text[:200]}")
        if resp.status_code >= 500:
            last_exc = Exception(f"{resp.status_code}: {resp.text[:200]}")
            delay = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2 ** attempt))
            time.sleep(delay)
            continue
        resp.raise_for_status()
        if not resp.content:
            return {}
        content_type = resp.headers.get("content-type", "")
        if "application/json" not in content_type.lower():
            raise CentralServerUnavailable(
                f"{method} {request_path} returned non-JSON response ({resp.status_code}, {content_type}): {resp.text[:120]}"
            )
        try:
            return resp.json()
        except (ValueError, JSONDecodeError) as e:
            raise CentralServerUnavailable(f"{method} {request_path} returned invalid JSON: {e}")

    raise CentralServerUnavailable(f"{method} {request_path} failed after {MAX_RETRIES} attempts: {last_exc}")


def register(worker_id: str, worker_instance_id: str, allowed_job_types: list[str]) -> dict:
    return _request("POST", "/api/internal/worker/register", {
        "worker_id": worker_id, "worker_instance_id": worker_instance_id,
        "allowed_job_types": allowed_job_types,
    })


def heartbeat(worker_id: str, worker_instance_id: str) -> dict:
    return _request("POST", "/api/internal/worker/heartbeat", {
        "worker_id": worker_id, "worker_instance_id": worker_instance_id,
    })


def claim_job(worker_id: str, worker_instance_id: str, allowed_job_types: list[str]) -> dict | None:
    result = _request("POST", "/api/internal/worker/jobs/claim", {
        "worker_id": worker_id, "worker_instance_id": worker_instance_id,
        "allowed_job_types": allowed_job_types,
    })
    return result if result and result.get("job_id") else None


def report_progress(remote_job_id: str, lease_id: str, worker_instance_id: str, progress: int, message: str,
                    worker_status: str = "RENDERING") -> dict:
    return _request("POST", f"/api/internal/worker/jobs/{remote_job_id}/progress", {
        "lease_id": lease_id, "worker_instance_id": worker_instance_id,
        "worker_status": worker_status,
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
    # [AIR-0227D-STAGING-UNBLOCK] real route is /api/internal/worker/*, not
    # /api/worker/* - see module docstring, this AIR-0230 branch was missing
    # this prefix everywhere until merging that fix.
    return _request("POST", f"/api/internal/worker/jobs/{remote_job_id}/complete", body, idempotency_key=idempotency_key)


def fail_job(remote_job_id: str, lease_id: str, worker_instance_id: str, idempotency_key: str, error_code: str, error_message: str) -> dict:
    return _request("POST", f"/api/internal/worker/jobs/{remote_job_id}/fail", {
        "lease_id": lease_id, "worker_instance_id": worker_instance_id,
        "error_code": error_code, "error_message": error_message,
    }, idempotency_key=idempotency_key)


def renew_lease(remote_job_id: str, lease_id: str, worker_instance_id: str) -> dict:
    # [AIR-0230 + AIR-0227D-STAGING-UNBLOCK, merged fixes] This originally
    # called "/api/worker/jobs/{id}/renew-lease" - wrong on two counts: the
    # missing /internal/ prefix (see module docstring, PR #85) and the
    # "renew-lease" vs "renew" route name (found independently while
    # building the AIR-0230 branch, PR #135) - every renew_lease() call was
    # 404ing on both counts until this merge combined both fixes.
    return _request("POST", f"/api/internal/worker/jobs/{remote_job_id}/renew", {
        "lease_id": lease_id, "worker_instance_id": worker_instance_id,
    })


def new_idempotency_key() -> str:
    return str(uuid.uuid4())
