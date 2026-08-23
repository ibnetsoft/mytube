"""
AIR Worker Web Dashboard — FastAPI app with embedded single-page HTML.

Runs inside the Manager process on a separate uvicorn instance bound to
127.0.0.1:3002 (daemon thread).  Reuses the same DPAPI auth token as the
Local API (local_api_token.py) so the user only needs one token.
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree

import job_store
from fastapi import FastAPI, Header, HTTPException, Response, Body, UploadFile, File
from fastapi.concurrency import run_in_threadpool
from local_api_token import verify_token
from logging_setup import get_logger
from render_pipeline_adapter import render_status_display
from worker_config import LOG_DIR, MANAGER_STATUS_FILE, OUTPUT_DIR, STATE_DIR, WORKER_ID, WORKER_PROFILE
from hermes_autopilot import CATEGORIES, DEFAULT_CATEGORY_TARGET_DURATION_SECONDS, HermesAutopilotManager

logger = get_logger("dashboard")
app = FastAPI(title="AIR Worker Dashboard")
autopilot_manager = HermesAutopilotManager()
_MANAGER_RECOVERY_LOCK = threading.Lock()
_MANAGER_RECOVERY_LAST_AT = 0.0
_MANAGER_RECOVERY_COOLDOWN_SECONDS = 120.0

HERMES_JOB_TYPES = {
    "topic_benchmark_analyze",
    "web_research",
    "script_plan_generate",
    "script_generate",
    "publish_metadata_generate",
}
HERMES_ACTIVE_STATUSES = {"CLAIMED", "PREPARING", "RENDERING", "UPLOADING"}

# ---------------------------------------------------------------------------
# Auth helpers (same pattern as local_api_app.py)
# ---------------------------------------------------------------------------

def _token_from_cookie_or_header(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
) -> str | None:
    """Extract bearer token from Authorization header *or* session cookie."""
    if authorization and authorization.startswith("Bearer "):
        return authorization[len("Bearer "):]
    if cookie:
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("dashboard_token="):
                return part[len("dashboard_token="):]
    return None


def require_auth(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    # 인증 해제: 바로 통과
    pass


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

def _read_manager_status() -> dict:
    if not MANAGER_STATUS_FILE.exists():
        return {"processes": {}, "hermes_paused": False, "worker_id": WORKER_ID, "worker_profile": WORKER_PROFILE, "manager_alive": False}
    try:
        data = json.loads(MANAGER_STATUS_FILE.read_text(encoding="utf-8"))
        data.setdefault("worker_profile", WORKER_PROFILE)
        data["manager_alive"] = (time.time() - data.get("written_at", 0)) < 5
        return data
    except (json.JSONDecodeError, OSError):
        return {"processes": {}, "hermes_paused": False, "worker_id": WORKER_ID, "worker_profile": WORKER_PROFILE, "manager_alive": False}


def _existing_manager_process_ids() -> list[int]:
    """Return manager PIDs already running for this worker app.

    The dashboard may keep serving while the heartbeat file is stale. In that
    state, repeatedly spawning a recovery manager makes the whole local server
    slower, so recovery first checks for an existing manager process.
    """
    if sys.platform != "win32":
        return []
    ps_script = r"""
$items = Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -and (
    ($_.CommandLine -like '*air_worker_entry.py*--role manager*') -or
    ($_.CommandLine -like '*AIRWorker.exe*--role manager*')
  )
}
$items | ForEach-Object { $_.ProcessId }
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception as exc:
        logger.debug("Failed to inspect existing Manager processes: %s", exc)
        return []
    pids: list[int] = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pid = int(line)
        except ValueError:
            continue
        pids.append(pid)
    return pids


def _launch_manager_recovery_if_needed() -> dict:
    """Best-effort self-heal for standalone dashboards.

    In the normal desktop runtime, the dashboard is hosted inside Manager.
    During development or after a partial restart, the dashboard can remain
    alive while Manager is gone.  When that happens, the status endpoint starts
    Manager again so the supervisor heartbeat does not stay red forever.
    """
    if "--role" in sys.argv and "manager" in sys.argv:
        return {"attempted": False, "reason": "dashboard_hosted_by_manager"}

    global _MANAGER_RECOVERY_LAST_AT
    now = time.time()
    with _MANAGER_RECOVERY_LOCK:
        if now - _MANAGER_RECOVERY_LAST_AT < _MANAGER_RECOVERY_COOLDOWN_SECONDS:
            return {"attempted": False, "reason": "cooldown"}
        existing_pids = _existing_manager_process_ids()
        if existing_pids:
            _MANAGER_RECOVERY_LAST_AT = now
            return {
                "attempted": False,
                "reason": "manager_process_already_running",
                "pids": existing_pids,
            }
        _MANAGER_RECOVERY_LAST_AT = now

    worker_dir = Path(__file__).resolve().parent
    entry_script = worker_dir / "air_worker_entry.py"
    cmd = [sys.executable, str(entry_script), "--role", "manager"]
    try:
        flags = 0
        startupinfo = None
        if sys.platform == "win32":
            flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
        popen = subprocess.Popen(
            cmd,
            cwd=str(worker_dir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            startupinfo=startupinfo,
        )
        logger.warning("Manager heartbeat is stale; launched recovery Manager pid=%s", popen.pid)
        return {"attempted": True, "pid": popen.pid}
    except Exception as exc:
        logger.exception("Failed to launch Manager recovery process")
        return {"attempted": True, "error": str(exc)}


def _read_process_state(name: str) -> dict | None:
    path = STATE_DIR / f"{name}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _read_job_result(job_id: str) -> dict | None:
    """Read the Hermes result JSON if it exists on disk."""
    result_path = OUTPUT_DIR / "hermes_results" / f"{job_id}.json"
    if result_path.exists():
        try:
            return json.loads(result_path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _active_hermes_job_from_local_queue(limit: int = 50) -> dict | None:
    """Return the newest local Hermes job that is still actively being handled."""
    try:
        jobs = job_store.list_jobs(limit=limit)
    except Exception as exc:
        logger.warning(f"Failed to inspect local Hermes queue: {exc}")
        return None
    for job in jobs:
        if job.get("job_type") in HERMES_JOB_TYPES and str(job.get("status") or "").upper() in HERMES_ACTIVE_STATUSES:
            return job
    return None


def _sync_hermes_process_status(snap: dict, autopilot_status: dict) -> dict:
    """Keep the Hermes process card aligned with the visible pipeline rows."""
    hermes_process = snap.setdefault("processes", {}).setdefault("hermes_worker", {})
    hermes_state = _read_process_state("hermes_worker")
    if hermes_state:
        heartbeat_at = float(hermes_state.get("heartbeat_at") or 0)
        if not snap.get("manager_alive") or heartbeat_at >= float(hermes_process.get("last_heartbeat_at") or 0):
            status = str(hermes_state.get("status") or "").strip() or hermes_process.get("status") or "stopped"
            is_fresh = heartbeat_at and (time.time() - heartbeat_at) < 45
            hermes_process.update(
                {
                    "pid": hermes_state.get("pid") if is_fresh else None,
                    "status": status if is_fresh else "stopped",
                    "last_heartbeat_at": heartbeat_at or hermes_process.get("last_heartbeat_at"),
                    "last_error": hermes_state.get("last_error") or "",
                    "current_job": hermes_state.get("current_job"),
                    "progress": hermes_state.get("progress") or 0,
                    "last_success_at": hermes_state.get("last_success_at") or hermes_process.get("last_success_at"),
                }
            )
    active_job = _active_hermes_job_from_local_queue()
    if active_job:
        payload = active_job.get("payload") or {}
        hermes_process["status"] = "running"
        hermes_process["current_job"] = {
            "job_id": active_job.get("job_id"),
            "job_type": active_job.get("job_type"),
            "project_name": payload.get("upload_title") or payload.get("topic") or payload.get("title"),
            "progress_message": active_job.get("progress_message") or "",
        }
        hermes_process["progress"] = active_job.get("progress") or 1
        return hermes_process

    if autopilot_status.get("is_running"):
        hermes_process["status"] = "running"
        hermes_process["current_job"] = autopilot_status.get("current_step") or "hermes_autopilot"
    return hermes_process


def _job_pipeline_identity(job: dict) -> tuple[str, str, str]:
    payload = job.get("payload") or {}
    queue_id = str(payload.get("topic_queue_id") or payload.get("topic_id") or "").strip()
    category = str(payload.get("category") or payload.get("category_name") or "").strip()
    title = str(
        payload.get("upload_title")
        or payload.get("generated_title")
        or payload.get("topic")
        or ""
    ).strip()
    return queue_id, category, title


def _related_hermes_pipeline_jobs(seed_job: dict, limit: int = 500) -> list[dict]:
    seed_queue_id, seed_category, seed_title = _job_pipeline_identity(seed_job)
    related: list[dict] = []
    for job in job_store.list_jobs(limit=limit):
        if job.get("job_type") not in HERMES_JOB_TYPES:
            continue
        queue_id, category, title = _job_pipeline_identity(job)
        same_queue = bool(seed_queue_id and queue_id and str(queue_id) == str(seed_queue_id))
        same_title = bool(seed_title and title and title == seed_title and (not seed_category or not category or category == seed_category))
        if job.get("job_id") == seed_job.get("job_id") or same_queue or same_title:
            related.append(job)
    related.sort(key=lambda item: float(item.get("created_at") or 0))
    return related


def _resolve_job_by_id_or_prefix(job_id: str) -> dict | None:
    """Resolve full job ids and dashboard short ids such as the first 8 chars."""
    requested = str(job_id or "").strip()
    if not requested:
        return None

    exact = job_store.get_job(requested)
    if exact:
        return exact

    if len(requested) < 8:
        return None

    matches = [
        job for job in job_store.list_jobs(limit=2000)
        if str(job.get("job_id") or "").startswith(requested)
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        logger.warning(
            "Ambiguous dashboard job id prefix %s matched %s jobs",
            requested,
            len(matches),
        )
    return None


def _completed_result_for_type(jobs: list[dict], job_type: str) -> tuple[dict, dict] | tuple[None, None]:
    for job in reversed(jobs):
        if job.get("job_type") != job_type or str(job.get("status") or "").upper() != "COMPLETED":
            continue
        result = _read_job_result(str(job.get("job_id") or ""))
        if isinstance(result, dict):
            return job, result
    return None, None


def _pipeline_has_active_job(jobs: list[dict]) -> bool:
    return any(str(job.get("status") or "").upper() in HERMES_ACTIVE_STATUSES for job in jobs)


def _submit_resume_job_from_pipeline(jobs: list[dict]) -> dict:
    metadata_job, _metadata_data = _completed_result_for_type(jobs, "publish_metadata_generate")
    if metadata_job:
        return {"success": False, "error": "이미 설명·태그 단계까지 완료된 작업입니다."}

    script_job, script_data = _completed_result_for_type(jobs, "script_generate")
    if script_job and script_data:
        script_payload = script_job.get("payload") or {}
        topic_queue_id = script_data.get("topic_queue_id") or script_payload.get("topic_queue_id")
        title = (
            script_data.get("upload_title")
            or script_data.get("generated_title")
            or script_payload.get("upload_title")
            or script_payload.get("topic")
        )
        new_job_id = job_store.submit_job(
            job_type="publish_metadata_generate",
            payload={
                "topic_queue_id": topic_queue_id,
                "category": script_data.get("category") or script_payload.get("category"),
                "category_name": script_data.get("category_name") or script_payload.get("category_name"),
                "category_id": script_data.get("category_id") or script_payload.get("category_id"),
                "topic": title,
                "script": script_data.get("script"),
                "structure": script_data.get("structure") or script_payload.get("structure"),
                "upload_title": title,
                "title_generation": script_data.get("title_generation") or script_payload.get("title_generation"),
                "narrative_blueprint": script_data.get("narrative_blueprint") or {},
                "script_quality_report": script_data.get("script_quality_report") or {},
                "language": script_data.get("language") or script_payload.get("language") or "ko",
                "defer_ready_until_quality_gate": True,
                "resume_from_job_id": script_job.get("job_id"),
            },
            priority=100,
            source="autopilot",
            max_retries=0,
        )
        return {"success": True, "job_id": new_job_id, "resumed_stage": "publish_metadata_generate"}

    plan_job, plan_data = _completed_result_for_type(jobs, "script_plan_generate")
    if plan_job and plan_data:
        plan_payload = plan_job.get("payload") or {}
        topic_queue_id = plan_data.get("topic_queue_id") or plan_payload.get("topic_queue_id")
        title = (
            plan_data.get("upload_title")
            or plan_data.get("generated_title")
            or plan_payload.get("upload_title")
            or plan_payload.get("topic")
        )
        new_job_id = job_store.submit_job(
            job_type="script_generate",
            payload={
                "topic_queue_id": topic_queue_id,
                "category": plan_data.get("category") or plan_payload.get("category"),
                "category_name": plan_data.get("category_name") or plan_payload.get("category_name"),
                "category_id": plan_data.get("category_id") or plan_payload.get("category_id"),
                "topic": title,
                "structure": plan_data.get("structure"),
                "target_duration_seconds": plan_data.get("target_duration_seconds") or plan_payload.get("target_duration_seconds") or 900,
                "script_style": plan_data.get("script_style") or plan_payload.get("script_style") or "default",
                "image_style": plan_data.get("image_style") or plan_payload.get("image_style"),
                "image_style_selection": plan_data.get("image_style_selection") or plan_payload.get("image_style_selection"),
                "language": plan_data.get("language") or plan_payload.get("language") or "ko",
                "narration_mode": plan_payload.get("narration_mode") or "dramatic_single",
                "upload_title": title,
                "title_generation": plan_data.get("title_generation") or plan_payload.get("title_generation"),
                "learning_profile": plan_data.get("learning_profile") or plan_payload.get("learning_profile"),
                "defer_ready_until_quality_gate": True,
                "resume_from_job_id": plan_job.get("job_id"),
            },
            priority=100,
            source="autopilot",
            max_retries=0,
        )
        return {"success": True, "job_id": new_job_id, "resumed_stage": "script_generate"}

    research_job, research_data = _completed_result_for_type(jobs, "web_research")
    if research_job and research_data:
        research_payload = research_job.get("payload") or {}
        research_bundle = research_data.get("research_bundle") if isinstance(research_data.get("research_bundle"), dict) else {}
        topic_queue_id = (
            research_data.get("topic_queue_id")
            or research_payload.get("topic_queue_id")
            or f"resume-{research_job.get('job_id')}"
        )
        category = (
            research_bundle.get("category")
            or research_data.get("category")
            or research_payload.get("category")
            or research_payload.get("category_name")
        )
        title = (
            research_bundle.get("upload_title")
            or research_data.get("upload_title")
            or research_payload.get("upload_title")
            or research_payload.get("topic")
        )
        if not title:
            return {"success": False, "error": "웹 조사 결과에 이어갈 제목이 없습니다."}
        new_job_id = job_store.submit_job(
            job_type="script_plan_generate",
            payload={
                "topic_queue_id": topic_queue_id,
                "category": category,
                "category_name": category,
                "topic": title,
                "target_duration_seconds": DEFAULT_CATEGORY_TARGET_DURATION_SECONDS,
                "script_style": research_payload.get("script_style") or "story",
                "image_style": research_payload.get("image_style") or "realistic",
                "language": research_payload.get("language") or "ko",
                "benchmark_analysis": {"web_research": research_bundle},
                "upload_title": title,
                "title_generation": research_payload.get("title_generation") or {"generated_title": title},
                "research_bundle": research_bundle,
                "defer_ready_until_quality_gate": True,
                "resume_from_job_id": research_job.get("job_id"),
            },
            priority=100,
            source="autopilot",
            max_retries=0,
        )
        return {"success": True, "job_id": new_job_id, "resumed_stage": "script_plan_generate"}

    return {"success": False, "error": "이어갈 수 있는 완료 단계가 없습니다. 웹조사, 기획 또는 대본 결과가 필요합니다."}


AUTOPILOT_RESULTS_DIR = OUTPUT_DIR / "hermes_autopilot_results"
AUTOPILOT_STATE_FILE = STATE_DIR / "hermes_autopilot_state.json"
HERMES_RESULTS_DIR = OUTPUT_DIR / "hermes_results"
NOTEBOOKLM_RESULTS_DIR = OUTPUT_DIR / "notebooklm_results"
GENERATED_RESULT_JOB_TYPES = {"script_generate", "script_plan_generate", "web_research", "publish_metadata_generate"}
_OFFLINE_HARNESS_CACHE: dict = {"checked_at": 0.0, "report": None}
_OFFLINE_HARNESS_CACHE_SECONDS = 30.0


def _split_reference_lines(value) -> list[str]:
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[\r\n]+", str(value or ""))
    return [str(item).strip() for item in items if str(item).strip()]


def _extract_html_text(raw: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return soup.get_text("\n", strip=True)
    except Exception:
        return re.sub(r"<[^>]+>", " ", raw)


async def _fetch_reference_url(url: str) -> str:
    import httpx
    if not re.match(r"^https?://", url, flags=re.I):
        raise ValueError(f"URL 형식이 아닙니다: {url}")
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        res = await client.get(url, headers={"User-Agent": "AIRWorker/NotebookLM"})
        res.raise_for_status()
        content_type = res.headers.get("content-type", "")
        text = res.text
        if "html" in content_type.lower() or "<html" in text[:500].lower():
            text = _extract_html_text(text)
        return text[:50000]


def _extract_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    chunks = [node.text for node in root.findall(".//w:t", ns) if node.text]
    return "\n".join(chunks)


def _extract_pdf_text(path: Path) -> str:
    try:
        import pdfplumber
    except Exception as exc:
        raise ValueError("PDF 읽기에는 pdfplumber가 필요합니다.") from exc
    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages[:80]:
            pages.append(page.extract_text() or "")
    return "\n\n".join(pages)


def _read_reference_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf_text(path)
    if suffix in {".docx", ".docm"}:
        return _extract_docx_text(path)
    if suffix in {".html", ".htm"}:
        return _extract_html_text(path.read_text(encoding="utf-8", errors="ignore"))
    if suffix in {".txt", ".md", ".csv", ".json", ".rtf", ".srt", ".vtt"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError(f"지원하지 않는 파일 형식입니다: {path.name}")


async def _build_notebooklm_source_text(body: dict) -> tuple[str, list[dict]]:
    chunks: list[str] = []
    sources: list[dict] = []

    direct_text = str(body.get("source_text") or "").strip()
    if direct_text:
        chunks.append(f"[직접 입력]\n{direct_text}")
        sources.append({"type": "text", "chars": len(direct_text)})

    for url in _split_reference_lines(body.get("source_urls")):
        try:
            text = await _fetch_reference_url(url)
            if text.strip():
                chunks.append(f"[URL: {url}]\n{text}")
                sources.append({"type": "url", "value": url, "chars": len(text)})
        except Exception as exc:
            sources.append({"type": "url", "value": url, "error": str(exc)})

    for raw_path in _split_reference_lines(body.get("source_paths")):
        path = Path(raw_path).expanduser()
        if not path.exists() or not path.is_file():
            sources.append({"type": "path", "value": raw_path, "error": "파일을 찾을 수 없습니다."})
            continue
        try:
            text = _read_reference_file(path)
            if text.strip():
                chunks.append(f"[파일: {path}]\n{text[:80000]}")
                sources.append({"type": "path", "value": str(path), "chars": len(text)})
        except Exception as exc:
            sources.append({"type": "path", "value": raw_path, "error": str(exc)})

    return "\n\n---\n\n".join(chunks).strip(), sources


def _run_hermes_offline_harness(*, force: bool = False) -> dict:
    now = time.time()
    cached = _OFFLINE_HARNESS_CACHE.get("report")
    if not force and cached and now - float(_OFFLINE_HARNESS_CACHE.get("checked_at") or 0) < _OFFLINE_HARNESS_CACHE_SECONDS:
        report = dict(cached)
        report["cached"] = True
        return report

    from worker_config import ensure_project_root_on_path

    ensure_project_root_on_path()
    from services.hermes_offline_harness import run_offline_harness

    try:
        report = run_offline_harness()
    except Exception as exc:
        logger.exception("Hermes offline harness failed unexpectedly")
        report = {
            "status": "fail",
            "api_calls": 0,
            "categories": [],
            "check_count": 0,
            "failed_count": 1,
            "checks": [
                {
                    "name": "offline harness runtime error",
                    "passed": False,
                    "detail": str(exc),
                    "category": "common",
                }
            ],
        }
    _OFFLINE_HARNESS_CACHE["checked_at"] = now
    _OFFLINE_HARNESS_CACHE["report"] = report
    return report


def _safe_result_id(result_id: str) -> str:
    return "".join(ch for ch in str(result_id or "") if ch.isalnum() or ch in ("-", "_", "."))


def _read_generated_result(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _autopilot_generation_diagnostics() -> dict:
    state: dict = autopilot_manager.get_status()
    if AUTOPILOT_STATE_FILE.exists():
        try:
            loaded = json.loads(AUTOPILOT_STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and not state:
                state = loaded
        except (json.JSONDecodeError, OSError):
            if not state:
                state = {}

    logs = state.get("logs") if isinstance(state.get("logs"), list) else []
    hermes_results_dir = OUTPUT_DIR / "hermes_results"
    partial_count = 0
    latest_partial_at = None
    if hermes_results_dir.exists():
        partial_paths = list(hermes_results_dir.glob("*.json"))
        partial_count = len(partial_paths)
        if partial_paths:
            latest_partial_at = max(path.stat().st_mtime for path in partial_paths)

    stats = state.get("session_stats") if isinstance(state.get("session_stats"), dict) else {}
    return {
        "is_running": bool(state.get("is_running")),
        "current_step": state.get("current_step") or "",
        "last_run_status": state.get("last_run_status") or "",
        "last_error": state.get("last_error") or "",
        "last_completed_result_id": state.get("last_completed_result_id") or "",
        "generated_count": stats.get("generated_count", 0),
        "recent_logs": logs[-8:],
        "partial_result_count": partial_count,
        "latest_partial_at": latest_partial_at,
        "state_updated_at": state.get("updated_at"),
    }


def _result_title(data: dict) -> str:
    structure = data.get("structure") if isinstance(data.get("structure"), dict) else {}
    title_generation = data.get("title_generation") if isinstance(data.get("title_generation"), dict) else {}
    benchmark_analysis = data.get("benchmark_analysis") if isinstance(data.get("benchmark_analysis"), dict) else {}
    benchmark_title_generation = (
        benchmark_analysis.get("title_generation")
        if isinstance(benchmark_analysis.get("title_generation"), dict)
        else {}
    )
    return (
        data.get("generated_title")
        or data.get("upload_title")
        or structure.get("upload_title")
        or title_generation.get("generated_title")
        or title_generation.get("final_title")
        or benchmark_title_generation.get("generated_title")
        or benchmark_title_generation.get("final_title")
        or ""
    )


def _result_category(data: dict) -> str:
    title_generation = data.get("title_generation") if isinstance(data.get("title_generation"), dict) else {}
    benchmark_analysis = data.get("benchmark_analysis") if isinstance(data.get("benchmark_analysis"), dict) else {}
    benchmark_title_generation = (
        benchmark_analysis.get("title_generation")
        if isinstance(benchmark_analysis.get("title_generation"), dict)
        else {}
    )
    for value in (
        data.get("category"),
        title_generation.get("category"),
        benchmark_title_generation.get("category"),
    ):
        category = str(value or "").strip()
        if category:
            return category
    return ""


def _structure_has_image_grid_prompts(structure: dict) -> bool:
    prompts = structure.get("image_grid_prompts") if isinstance(structure, dict) else None
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return False
    try:
        from services.image_grid_prompts import validate_image_grid_prompt_readiness

        validate_image_grid_prompt_readiness(
            scenes,
            prompts,
            status=structure.get("image_grid_prompt_status"),
            require_status="ready",
            require_compact_template=True,
        )
    except Exception:
        return False
    return True


def _scene_has_video_prompt(scene: dict) -> bool:
    return bool(
        str(
            scene.get("video_prompt")
            or scene.get("motion_desc")
            or scene.get("flow_prompt")
            or scene.get("camera_motion")
            or ""
        ).strip()
    )


MAX_VIDEO_PROMPT_SCENES = 12


def _scene_number(scene: dict, index: int) -> int:
    try:
        return int(scene.get("scene_order") or scene.get("scene_number") or index)
    except (TypeError, ValueError):
        return index


def _scene_requires_video_prompt(scene: dict, index: int) -> bool:
    if scene.get("video_prompt_required") is False:
        return False
    return _scene_number(scene, index) <= MAX_VIDEO_PROMPT_SCENES


def _structure_media_prompt_status(structure: dict, scenes: list) -> str:
    raw_status = str(structure.get("media_prompt_status") or "").strip()
    valid_scenes = [scene for scene in scenes if isinstance(scene, dict)]
    if (
        raw_status == "ready"
        and valid_scenes
        and _structure_has_image_grid_prompts(structure)
        and all(
            not _scene_requires_video_prompt(scene, index) or _scene_has_video_prompt(scene)
            for index, scene in enumerate(valid_scenes, start=1)
        )
    ):
        return "ready"
    if raw_status == "fallback_ready":
        return "fallback_ready"
    return raw_status or "missing"


def _quality_gate_status(data: dict, structure: dict, scenes: list, script: str) -> dict:
    media_status = _structure_media_prompt_status(structure, scenes)
    missing = []
    review = []
    if not data.get("benchmark_analysis"):
        missing.append("benchmark")
    if not _result_title(data):
        missing.append("title")
    if not (data.get("research_bundle") or structure.get("research_bundle")):
        missing.append("web_research")
    if not scenes:
        missing.append("scenes")
    if media_status == "fallback_ready":
        review.append("media_prompts_fallback")
    elif media_status != "ready":
        missing.append("media_prompts")
    if not script.strip():
        missing.append("script")
    if not data.get("publish_metadata"):
        missing.append("publish_metadata")
    status = "fail" if missing else ("review" if review else "pass")
    return {
        "status": status,
        "missing": missing,
        "review": review,
        "media_prompt_status": media_status,
        "can_auto_render": status == "pass",
    }


def _generated_result_summary(path: Path) -> dict | None:
    data = _read_generated_result(path)
    if not isinstance(data, dict):
        return None
    structure = data.get("structure") if isinstance(data.get("structure"), dict) else {}
    scenes = structure.get("scenes") if isinstance(structure.get("scenes"), list) else []
    script = str(data.get("script") or "")
    research_bundle = data.get("research_bundle") or structure.get("research_bundle")
    media_status = _structure_media_prompt_status(structure, scenes)
    quality_gate = _quality_gate_status(data, structure, scenes, script)
    material_statuses = {
        "benchmark": "ready" if data.get("benchmark_analysis") else "missing",
        "title": "ready" if _result_title(data) else "missing",
        "web_research": "ready" if research_bundle else "missing",
        "plan_prompts": "review" if media_status == "fallback_ready" else ("ready" if scenes and media_status == "ready" else ("ready" if scenes else "missing")),
        "script": "ready" if script.strip() else "missing",
        "publish_metadata": "ready" if data.get("publish_metadata") else "missing",
    }
    stat = path.stat()
    return {
        "id": path.stem,
        "filename": path.name,
        "topic_queue_id": data.get("topic_queue_id") or path.stem,
        "category": _result_category(data),
        "title": _result_title(data),
        "scene_count": len(scenes),
        "script_chars": len(script),
        "has_script": bool(script.strip()),
        "has_image_prompts": _structure_has_image_grid_prompts(structure),
        "has_image_grid_prompts": _structure_has_image_grid_prompts(structure),
        "has_video_prompts": any(isinstance(scene, dict) and _scene_has_video_prompt(scene) for scene in scenes),
        "has_legacy_visual_direction": any(isinstance(scene, dict) and scene.get("visual_direction") for scene in scenes),
        "media_prompt_status": media_status,
        "material_statuses": material_statuses,
        "quality_gate": quality_gate,
        "updated_at": stat.st_mtime,
        "completed_at": data.get("completed_at") or stat.st_mtime,
    }


def _topic_key(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _generated_result_ts(data: dict, fallback: float | None = None) -> float | None:
    for key in ("completed_at", "updated_at", "created_at", "started_at"):
        value = data.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return fallback


def _merge_topic_generated_result(target: dict, data: dict, *, source: str, source_id: str, path: Path | None = None, fallback_ts: float | None = None):
    job_type = data.get("job_type") or source
    status = data.get("status") or ""
    ts = _generated_result_ts(data, fallback_ts)
    target.setdefault("_sources", []).append({
        "source": source,
        "source_id": source_id,
        "job_type": job_type,
        "status": status,
        "path": str(path) if path else "",
        "updated_at": ts,
    })
    if ts and (not target.get("completed_at") or ts > target.get("completed_at", 0)):
        target["completed_at"] = ts
        target["updated_at"] = ts
    if data.get("topic_queue_id") is not None:
        target["topic_queue_id"] = data.get("topic_queue_id")
    for key in (
        "category",
        "topic",
        "upload_title",
        "generated_title",
        "title_generation",
        "benchmark_analysis",
        "research_bundle",
        "narrative_blueprint",
        "script_quality_report",
        "publish_metadata",
    ):
        value = data.get(key)
        if value not in (None, "", [], {}):
            target[key] = value
    category = _result_category(target) or _result_category(data)
    if category:
        target["category"] = category
    if isinstance(data.get("structure"), dict):
        new_structure = data["structure"]
        if "structure" not in target:
            target["structure"] = dict(new_structure)
        else:
            existing_structure = target["structure"] if isinstance(target.get("structure"), dict) else {}
            merged_structure = {**existing_structure, **new_structure}
            if existing_structure.get("image_grid_prompts") and not new_structure.get("image_grid_prompts"):
                merged_structure["image_grid_prompts"] = existing_structure["image_grid_prompts"]
            if existing_structure.get("image_grid_prompt_status") and not new_structure.get("image_grid_prompt_status"):
                merged_structure["image_grid_prompt_status"] = existing_structure["image_grid_prompt_status"]
            if existing_structure.get("media_prompt_status") and not new_structure.get("media_prompt_status"):
                merged_structure["media_prompt_status"] = existing_structure["media_prompt_status"]
            existing_scenes = existing_structure.get("scenes") or []
            new_scenes = new_structure.get("scenes") or []
            if existing_scenes and new_scenes and len(existing_scenes) == len(new_scenes):
                merged_scenes = []
                for es, ns in zip(existing_scenes, new_scenes):
                    if isinstance(es, dict) and isinstance(ns, dict):
                        merged_scenes.append({**ns, **es})
                    else:
                        merged_scenes.append(ns or es)
                merged_structure["scenes"] = merged_scenes
            elif existing_scenes and not new_scenes:
                merged_structure["scenes"] = existing_scenes
            target["structure"] = merged_structure
    if isinstance(data.get("script"), str) and data["script"].strip():
        target["script"] = data["script"]
    if data.get("char_count"):
        target["char_count"] = data.get("char_count")
    if data.get("error") or data.get("error_message"):
        target.setdefault("errors", []).append(data.get("error") or data.get("error_message"))
    elif status == "COMPLETED" and job_type in {"script_generate", "publish_metadata_generate"}:
        target["errors"] = []
    target["status"] = status or target.get("status") or "PARTIAL"


def _topic_generated_result_summary(result_id: str, data: dict) -> dict:
    structure = data.get("structure") if isinstance(data.get("structure"), dict) else {}
    scenes = structure.get("scenes") if isinstance(structure.get("scenes"), list) else []
    script = str(data.get("script") or "")
    sources = data.get("_sources") if isinstance(data.get("_sources"), list) else []
    job_types = {str(source.get("job_type") or "") for source in sources}
    status = data.get("status") or ""
    media_status = _structure_media_prompt_status(structure, scenes)
    quality_gate = _quality_gate_status(data, structure, scenes, script)
    material_statuses = {
        "benchmark": "ready" if data.get("benchmark_analysis") else "missing",
        "title": "ready" if _result_title(data) else "missing",
        "web_research": "ready" if (data.get("research_bundle") or structure.get("research_bundle")) else "missing",
        "plan_prompts": "review" if media_status == "fallback_ready" else ("ready" if scenes and media_status == "ready" else ("ready" if scenes else "missing")),
        "script": "ready" if script.strip() else "missing",
        "publish_metadata": "ready" if data.get("publish_metadata") else "missing",
    }
    return {
        "id": result_id,
        "filename": result_id,
        "topic_queue_id": data.get("topic_queue_id") or result_id,
        "category": _result_category(data),
        "title": _result_title(data),
        "scene_count": len(scenes),
        "script_chars": len(script),
        "has_script": bool(script.strip()),
        "has_image_prompts": _structure_has_image_grid_prompts(structure),
        "has_image_grid_prompts": _structure_has_image_grid_prompts(structure),
        "has_video_prompts": any(isinstance(scene, dict) and _scene_has_video_prompt(scene) for scene in scenes),
        "has_legacy_visual_direction": any(isinstance(scene, dict) and scene.get("visual_direction") for scene in scenes),
        "media_prompt_status": media_status,
        "material_statuses": material_statuses,
        "quality_gate": quality_gate,
        "status": status,
        "stage": "metadata" if "publish_metadata_generate" in job_types and data.get("publish_metadata") else ("script" if script.strip() else ("plan" if "script_plan_generate" in job_types and scenes else "title")),
        "updated_at": data.get("updated_at") or data.get("completed_at"),
        "completed_at": data.get("completed_at") or data.get("updated_at"),
    }


def _collect_topic_generated_results(limit: int = 500) -> dict[str, dict]:
    results: dict[str, dict] = {}

    if HERMES_RESULTS_DIR.exists():
        paths = sorted(HERMES_RESULTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in paths[:limit]:
            data = _read_generated_result(path)
            if not isinstance(data, dict) or data.get("job_type") not in GENERATED_RESULT_JOB_TYPES:
                continue
            topic_id = _topic_key(data.get("topic_queue_id"))
            if not topic_id:
                continue
            result_id = f"topic_{topic_id}"
            target = results.setdefault(result_id, {"id": result_id, "topic_queue_id": data.get("topic_queue_id")})
            _merge_topic_generated_result(
                target,
                data,
                source="hermes_results",
                source_id=path.stem,
                path=path,
                fallback_ts=path.stat().st_mtime,
            )

    for job in job_store.list_jobs(limit=limit):
        if job.get("source") != "autopilot" or job.get("job_type") not in GENERATED_RESULT_JOB_TYPES:
            continue
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        topic_id = _topic_key(payload.get("topic_queue_id"))
        if not topic_id:
            continue
        result_id = f"topic_{topic_id}"
        target = results.setdefault(result_id, {"id": result_id, "topic_queue_id": payload.get("topic_queue_id")})
        data = {
            **payload,
            "job_id": job.get("job_id"),
            "job_type": job.get("job_type"),
            "status": job.get("status"),
            "error_message": job.get("error_message"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at") or job.get("completed_at") or job.get("created_at"),
        }
        _merge_topic_generated_result(
            target,
            data,
            source="job_store",
            source_id=job.get("job_id") or "",
            fallback_ts=job.get("updated_at") or job.get("completed_at") or job.get("created_at"),
        )

    return results


STYLE_PRESET_TYPES = {"image", "script"}


def _normalize_style_preset(body: dict) -> dict:
    preset_type = str(body.get("preset_type") or "").strip().lower()
    key_code = str(body.get("key_code") or "").strip().lower()
    display_name_ko = str(body.get("display_name_ko") or "").strip()
    prompt_template = str(body.get("prompt_template") or "").strip()
    if preset_type not in STYLE_PRESET_TYPES:
        raise HTTPException(400, "스타일 타입은 image 또는 script만 가능합니다.")
    if not key_code or not key_code.replace("_", "").isalnum():
        raise HTTPException(400, "스타일 코드는 영문, 숫자, 밑줄만 사용할 수 있습니다.")
    if not display_name_ko or not prompt_template:
        raise HTTPException(400, "한글 표시명과 프롬프트 템플릿은 필수입니다.")
    return {
        "preset_type": preset_type,
        "key_code": key_code,
        "display_name_ko": display_name_ko,
        "display_name_vi": str(body.get("display_name_vi") or "").strip(),
        "prompt_template": prompt_template,
        "gemini_instruction": str(body.get("gemini_instruction") or "").strip(),
        "image_url": str(body.get("image_url") or "").strip(),
    }


def _sync_style_preset_to_local(preset: dict) -> None:
    """Keep the Worker generation cache aligned immediately after an edit."""
    from worker_config import ensure_project_root_on_path
    ensure_project_root_on_path()
    import database as db

    if preset["preset_type"] == "script":
        db.save_script_style_preset(
            preset["key_code"], preset["prompt_template"],
            display_name_ko=preset.get("display_name_ko"),
            display_name_vi=preset.get("display_name_vi"),
        )
    else:
        db.save_style_preset(
            preset["key_code"], preset["prompt_template"],
            image_url=preset.get("image_url") or None,
            gemini_instruction=preset.get("gemini_instruction") or None,
            mode="image",
            display_name_ko=preset.get("display_name_ko"),
            display_name_vi=preset.get("display_name_vi"),
        )


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "time": time.time()}


@app.get("/api/status")
def api_status(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    snap = _read_manager_status()
    if not snap.get("manager_alive"):
        snap["manager_recovery"] = _launch_manager_recovery_if_needed()
    autopilot_status = autopilot_manager.get_status()
    _sync_hermes_process_status(snap, autopilot_status)
    snap["render_status"] = render_status_display()
    return snap


def _prune_job_for_list(job: dict) -> dict:
    item = dict(job)
    raw_payload = item.get("payload")
    if isinstance(raw_payload, dict):
        item["payload"] = {
            "category": raw_payload.get("category"),
            "category_name": raw_payload.get("category_name"),
            "topic": raw_payload.get("topic"),
            "upload_title": raw_payload.get("upload_title"),
            "generated_title": raw_payload.get("generated_title"),
            "topic_queue_id": raw_payload.get("topic_queue_id"),
            "topic_id": raw_payload.get("topic_id"),
            "keyword": raw_payload.get("keyword"),
            "target_duration_seconds": raw_payload.get("target_duration_seconds"),
            "script_style": raw_payload.get("script_style"),
            "image_style": raw_payload.get("image_style"),
        }
    return item


@app.get("/api/jobs")
def api_jobs(
    status: str | None = None,
    limit: int = 50,
    job_type: str | None = None,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    jobs = job_store.list_jobs(status=status, limit=limit)
    if job_type:
        jobs = [j for j in jobs if j.get("job_type") == job_type]
    if not status and not job_type:
        autopilot_status = autopilot_manager.get_status()
        if autopilot_status.get("is_running"):
            now = time.time()
            jobs.insert(0, {
                "job_id": "hermes-autopilot-current",
                "job_type": "hermes_autopilot_step",
                "source": "autopilot",
                "priority": 100,
                "payload": {
                    "category": autopilot_status.get("current_category") or "",
                    "current_step": autopilot_status.get("current_step") or "Autopilot running",
                },
                "status": "RUNNING",
                "worker_pid": None,
                "progress": 0,
                "progress_message": autopilot_status.get("current_step") or "Autopilot running",
                "created_at": now,
                "started_at": now,
                "completed_at": None,
                "retry_count": 0,
                "max_retries": 0,
                "error_code": "",
                "error_message": autopilot_status.get("last_error") or "",
                "output_path": None,
            })
            jobs = jobs[:limit]
    return {"jobs": [_prune_job_for_list(j) for j in jobs]}


def _fetch_remote_drive_render_queue(limit: int = 30) -> list[dict]:
    try:
        from remote_drive_worker import RemoteDriveWorker
        worker = RemoteDriveWorker()
        params = {
            "select": "*",
            "render_mode": "eq.drive_api",
            "order": "created_at.desc",
            "limit": str(limit),
        }
        rows = worker._request("GET", worker.queue_url, params=params) or []
        formatted = []
        for r in rows:
            meta = r.get("metadata") or {}
            result_fid = r.get("result_file_id") or meta.get("result_video_file_id")
            raw_status = str(r.get("status") or "pending").upper()
            progress_val = int(r.get("progress") or (100 if raw_status.lower() == "completed" else 0))
            err_msg = r.get("error_message") or (r.get("message") if raw_status.lower() == "failed" else "")
            
            # 1시간 이상 갱신 없는 작업은 유령 렌더링(Stale) 방지
            last_activity = r.get("updated_at") or r.get("claimed_at") or r.get("created_at")
            if raw_status in ("RENDERING", "PREPARING", "CLAIMED", "UPLOADING") and last_activity:
                try:
                    import datetime
                    dt = datetime.datetime.fromisoformat(str(last_activity).replace('Z', '+00:00'))
                    now = datetime.datetime.now(datetime.timezone.utc)
                    if (now - dt).total_seconds() > 3600:
                        raw_status = "FAILED"
                        err_msg = "워커 응답 시간 초과로 중단됨"
                except Exception:
                    pass

            drive_url = f"https://drive.google.com/file/d/{result_fid}/view" if result_fid else (r.get("result_url") or meta.get("result_video_link"))

            formatted.append({
                "job_id": str(r.get("id")),
                "raw_id": r.get("id"),
                "source": "web_std",
                "job_type": "drive_api_render",
                "email": r.get("email") or "-",
                "project_id": r.get("project_id"),
                "project_name": r.get("project_name") or r.get("asset_file_name") or f"프로젝트 #{r.get('project_id')}",
                "status": raw_status,
                "progress": progress_val,
                "progress_message": r.get("message") or "",
                "worker_id": r.get("worker_id") or "-",
                "result_url": drive_url,
                "drive_file_id": result_fid,
                "thumbnail_file_id": meta.get("result_thumbnail_file_id") or r.get("thumbnail_file_id"),
                "created_at": r.get("created_at"),
                "started_at": r.get("claimed_at"),
                "completed_at": r.get("completed_at"),
                "error_message": err_msg,
            })
        return formatted
    except Exception as exc:
        logger.warning(f"Failed to fetch remote_render_queue: {exc}")
        return []


@app.get("/api/rendering-jobs")
def api_rendering_jobs(
    limit: int = 30,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    local_jobs = [j for j in job_store.list_jobs(limit=limit) if j.get("job_type") == "render_video"]
    formatted_local = []
    for j in local_jobs:
        payload = j.get("payload") or {}
        formatted_local.append({
            "job_id": j.get("job_id"),
            "raw_id": j.get("job_id"),
            "source": "local",
            "job_type": "render_video",
            "project_id": payload.get("project_id"),
            "project_name": payload.get("project_name") or payload.get("title") or f"Local Job {j.get('job_id', '')[:8]}",
            "status": j.get("status", "QUEUED"),
            "progress": j.get("progress", 0),
            "progress_message": j.get("progress_message", ""),
            "worker_id": j.get("worker_instance_id") or "local_worker",
            "result_url": j.get("output_path"),
            "created_at": j.get("created_at"),
            "started_at": j.get("started_at"),
            "error_message": j.get("error_message", ""),
        })
    remote_jobs = _fetch_remote_drive_render_queue(limit=limit)
    all_jobs = formatted_local + remote_jobs
    all_jobs.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    
    active_jobs = [j for j in all_jobs if j.get("status") in ("RENDERING", "PREPARING", "CLAIMED", "UPLOADING")]
    pending_jobs = [j for j in all_jobs if j.get("status") in ("PENDING", "QUEUED")]
    
    return {
        "jobs": all_jobs[:limit],
        "active_job": active_jobs[0] if active_jobs else None,
        "active_count": len(active_jobs),
        "pending_count": len(pending_jobs),
        "total_count": len(all_jobs),
    }


@app.get("/api/jobs/{job_id}")
async def api_job_detail(
    job_id: str,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    job = job_store.get_job(job_id)
    if not job:
        return {"error": "not found"}
    job["transitions"] = job_store.transition_history(job_id)
    result = _read_job_result(job_id)
    if result:
        job["result"] = result
    return job


@app.post("/api/jobs/submit")
async def api_submit_job(
    body: dict,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    job_id = job_store.submit_job(
        job_type=body.get("job_type", "render_video"),
        payload=body.get("payload", {}),
        priority=body.get("priority", 100),
        source="dashboard",
        max_retries=body.get("max_retries", 3),
    )
    return {"job_id": job_id}


@app.post("/api/jobs/{job_id}/cancel")
def api_cancel_job(
    job_id: str,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from ipc import submit_command, wait_for_result
    return wait_for_result(submit_command("cancel_job", {"job_id": job_id}), timeout=15)


@app.post("/api/hermes/pipelines/{job_id}/resume")
def api_resume_hermes_pipeline(
    job_id: str,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    seed_job = _resolve_job_by_id_or_prefix(job_id)
    if not seed_job:
        return {"success": False, "error": "작업을 찾을 수 없습니다."}
    related_jobs = _related_hermes_pipeline_jobs(seed_job)
    if _pipeline_has_active_job(related_jobs):
        return {"success": False, "error": "이미 진행 중인 단계가 있습니다."}
    resume_result = _submit_resume_job_from_pipeline(related_jobs)
    if not resume_result.get("success"):
        return resume_result

    from ipc import submit_command, wait_for_result

    worker_result = wait_for_result(submit_command("start_process", {"name": "hermes_worker"}))
    return {
        **resume_result,
        "worker_started": bool(worker_result.get("success")),
        "worker_error": worker_result.get("error"),
    }


@app.get("/api/logs")
async def api_logs(
    process: str = "manager",
    tail_lines: int = 50,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from worker_config import LOG_FILES
    path = LOG_FILES.get(process)
    if not path or not Path(path).exists():
        return {"error": f"로그를 찾을 수 없습니다: '{process}'", "available": list(LOG_FILES.keys())}
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    return {"process": process, "lines": lines[-tail_lines:]}


@app.get("/api/style-presets")
async def api_style_presets(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    """Read shared image/script presets from the source of truth."""
    require_auth(authorization, cookie)
    from worker_config import ensure_project_root_on_path
    ensure_project_root_on_path()
    from services.web_admin_client import web_admin_client

    presets = web_admin_client.fetch_style_presets(["image", "script"])
    return {"presets": presets, "shared_store_available": web_admin_client.has_supabase()}


@app.post("/api/style-presets")
async def api_save_style_preset(
    body: dict,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    """Save a shared preset, then immediately update the Worker cache."""
    require_auth(authorization, cookie)
    preset = _normalize_style_preset(body)
    from worker_config import ensure_project_root_on_path
    ensure_project_root_on_path()
    from services.web_admin_client import web_admin_client

    result = web_admin_client.upsert_style_preset(preset)
    if not result.get("success"):
        raise HTTPException(502, result.get("error") or "중앙 스타일 저장소에 저장하지 못했습니다.")
    saved = result.get("preset") or preset
    # The remote API returns the same fields, but normalize to defend against
    # a partial representation response before writing the local cache.
    saved = {**preset, **{k: v for k, v in saved.items() if v is not None}}
    _sync_style_preset_to_local(saved)
    return {"success": True, "preset": saved}


@app.delete("/api/style-presets/{preset_type}/{key_code}")
async def api_delete_style_preset(
    preset_type: str,
    key_code: str,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    preset_type = preset_type.strip().lower()
    key_code = key_code.strip().lower()
    if preset_type not in STYLE_PRESET_TYPES or not key_code.replace("_", "").isalnum():
        raise HTTPException(400, "잘못된 스타일 정보입니다.")
    from worker_config import ensure_project_root_on_path
    ensure_project_root_on_path()
    from services.web_admin_client import web_admin_client
    import database as db

    result = web_admin_client.delete_style_preset(key_code)
    if not result.get("success"):
        raise HTTPException(502, result.get("error") or "중앙 스타일 저장소에서 삭제하지 못했습니다.")
    if preset_type == "script":
        db.delete_script_style_preset(key_code)
    else:
        db.delete_style_preset(key_code)
    return {"success": True}


@app.get("/api/category-image-style-mappings")
async def api_category_image_style_mappings(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    """Return the eight Hermes categories, image catalog, and Worker overrides."""
    require_auth(authorization, cookie)
    from worker_config import ensure_project_root_on_path
    ensure_project_root_on_path()
    from services.web_admin_client import web_admin_client

    category_rows = web_admin_client.fetch_categories("id,name,default_image_style")
    by_name = {str(row.get("name") or ""): row for row in category_rows}
    styles = web_admin_client.fetch_style_presets(["image"])
    overrides = (autopilot_manager.get_status().get("settings") or {}).get("category_image_style_overrides") or {}
    categories = [
        {
            "id": (by_name.get(name) or {}).get("id"),
            "name": name,
            "automatic_default": (by_name.get(name) or {}).get("default_image_style") or "realistic",
            "manual_override": overrides.get(name),
        }
        for name in CATEGORIES
    ]
    return {
        "categories": categories,
        "styles": styles,
        "shared_store_available": web_admin_client.has_supabase(),
    }


@app.put("/api/category-image-style-mappings/{category}")
async def api_save_category_image_style_mapping(
    category: str,
    body: dict,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    """Save a Worker manual override; it takes precedence over AI selection."""
    require_auth(authorization, cookie)
    if category not in CATEGORIES:
        raise HTTPException(404, "지원하지 않는 Hermes 카테고리입니다.")
    from worker_config import ensure_project_root_on_path
    ensure_project_root_on_path()
    from services.web_admin_client import web_admin_client

    style_key = str(body.get("image_style") or "").strip().lower()
    styles = web_admin_client.fetch_style_presets(["image"])
    allowed_keys = {str(style.get("key_code") or "").strip().lower() for style in styles}
    if style_key and style_key not in allowed_keys:
        raise HTTPException(400, "등록되지 않은 이미지 스타일입니다.")

    result = await autopilot_manager.save_category_image_style_override(category, style_key or None)
    if not result.get("success"):
        raise HTTPException(400, result.get("error") or "이미지 스타일 매칭을 저장하지 못했습니다.")
    return {"success": True, "manual_override": result.get("override")}


@app.post("/api/processes/hermes/start")
def api_hermes_start(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from ipc import submit_command, wait_for_result
    return wait_for_result(submit_command("start_process", {"name": "hermes_worker"}))


@app.post("/api/processes/hermes/stop")
def api_hermes_stop(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from ipc import submit_command, wait_for_result
    return wait_for_result(submit_command("stop_process", {"name": "hermes_worker"}))


@app.post("/api/processes/render/start")
def api_render_start(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from ipc import submit_command, wait_for_result
    return wait_for_result(submit_command("start_process", {"name": "render_worker"}))


@app.post("/api/processes/render/stop")
def api_render_stop(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from ipc import submit_command, wait_for_result
    return wait_for_result(submit_command("stop_process", {"name": "render_worker"}))


@app.post("/api/processes/remote-drive/start")
def api_remote_drive_start(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from ipc import submit_command, wait_for_result
    return wait_for_result(submit_command("start_process", {"name": "remote_drive_worker"}))


@app.post("/api/processes/remote-drive/stop")
def api_remote_drive_stop(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from ipc import submit_command, wait_for_result
    return wait_for_result(submit_command("stop_process", {"name": "remote_drive_worker"}))


# ---------------------------------------------------------------------------
# YouTube Explore API endpoints (proxy to YouTube Data API v3 + Gemini)
# ---------------------------------------------------------------------------

@app.post("/api/yt/search")
async def yt_search(
    body: dict,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    """YouTube 검색 프록시"""
    require_auth(authorization, cookie)
    from services.youtube_data_api import async_youtube_get
    params = {
        "part": "snippet",
        "q": body.get("query", ""),
        "type": "video",
        "maxResults": min(body.get("max_results", 10), 25),
        "order": body.get("order", "relevance"),
    }
    if body.get("published_after"):
        params["publishedAfter"] = body["published_after"]
    if body.get("relevance_language"):
        params["relevanceLanguage"] = body["relevance_language"]
    data = await async_youtube_get("search", params)
    if data.get("error"):
        return {"error": data.get("message") or data.get("error")}
    return data


@app.get("/api/yt/videos/{video_id}")
async def yt_videos(
    video_id: str,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    """YouTube 영상 상세 정보 프록시"""
    require_auth(authorization, cookie)
    from services.youtube_data_api import async_youtube_get
    data = await async_youtube_get("videos", {"part": "snippet,statistics,contentDetails", "id": video_id})
    if data.get("error"):
        return {"error": data.get("message") or data.get("error")}
    return data


@app.get("/api/yt/channel/{channel_id}")
async def yt_channel(
    channel_id: str,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    """YouTube 채널 정보 프록시"""
    require_auth(authorization, cookie)
    from services.youtube_data_api import async_youtube_get
    data = await async_youtube_get("channels", {"part": "snippet,statistics", "id": channel_id})
    if data.get("error"):
        return {"error": data.get("message") or data.get("error")}
    return data


@app.post("/api/notebooklm/generate")
async def api_notebooklm_generate(
    body: dict = Body(...),
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    """Generate a grounded NotebookLM-style script in the Worker, not the user web app."""
    require_auth(authorization, cookie)
    source_text, sources = await _build_notebooklm_source_text(body)
    if not source_text:
        raise HTTPException(400, "참고 자료를 입력해주세요.")

    mode = str(body.get("mode") or "dialogue_podcast")
    if mode not in {"dialogue_podcast", "narrator"}:
        raise HTTPException(400, "지원하지 않는 대본 모드입니다.")

    duration_minutes = int(body.get("duration_minutes") or 15)
    duration_minutes = max(5, min(duration_minutes, 60))
    category = str(body.get("category") or "옛날이야기").strip() or "옛날이야기"
    if category not in CATEGORIES:
        raise HTTPException(400, "지원하지 않는 카테고리입니다.")
    custom_title = str(body.get("custom_title") or "").strip() or None

    try:
        project_root = Path(__file__).resolve().parents[1]
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        from services.notebooklm_service import generate_notebooklm_project

        result = await generate_notebooklm_project(
            source_text=source_text,
            mode=mode,
            category=category,
            duration_minutes=duration_minutes,
            custom_title=custom_title,
        )
    except Exception as exc:
        logger.exception("NotebookLM worker generation failed")
        raise HTTPException(500, str(exc))

    NOTEBOOKLM_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_id = f"notebooklm_{int(time.time())}"
    payload = {
        "id": result_id,
        "created_at": time.time(),
        "category": category,
        "mode": mode,
        "duration_minutes": duration_minutes,
        "source_chars": len(source_text),
        "sources": sources,
        "result": result,
    }
    (NOTEBOOKLM_RESULTS_DIR / f"{result_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"success": True, "id": result_id, "sources": sources, "result": result}


@app.post("/api/notebooklm/extract-file")
async def api_notebooklm_extract_file(
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    """Extract text from an uploaded local reference file for NotebookLM generation."""
    require_auth(authorization, cookie)
    filename = file.filename or "reference"
    suffix = Path(filename).suffix.lower()
    if suffix not in {".txt", ".md", ".csv", ".json", ".rtf", ".srt", ".vtt", ".html", ".htm", ".pdf", ".docx", ".docm"}:
        raise HTTPException(400, f"지원하지 않는 파일 형식입니다: {suffix or filename}")
    tmp_path = None
    try:
        with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(await file.read())
        text = _read_reference_file(tmp_path)
        return {
            "success": True,
            "filename": filename,
            "chars": len(text),
            "text": text[:100000],
        }
    except Exception as exc:
        logger.exception("NotebookLM file extraction failed")
        raise HTTPException(500, str(exc))
    finally:
        if tmp_path:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass


@app.post("/api/notebooklm/{result_id}/send-to-hermes")
async def api_notebooklm_send_to_hermes(
    result_id: str,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    """Convert a saved NotebookLM result into the Hermes generated-results package format."""
    require_auth(authorization, cookie)
    safe_id = _safe_result_id(result_id)
    if not safe_id:
        raise HTTPException(400, "Invalid result id")
    source_path = NOTEBOOKLM_RESULTS_DIR / f"{safe_id}.json"
    if not source_path.exists():
        raise HTTPException(404, "NotebookLM result not found")

    try:
        notebook_payload = json.loads(source_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise HTTPException(500, f"NotebookLM result JSON is invalid: {exc}")

    result = notebook_payload.get("result") if isinstance(notebook_payload.get("result"), dict) else {}
    raw_scenes = result.get("scenes") if isinstance(result.get("scenes"), list) else []
    title = str(result.get("title") or notebook_payload.get("custom_title") or safe_id).strip()
    category = str(result.get("category") or notebook_payload.get("category") or "옛날이야기").strip()
    hook = str(result.get("hook") or "").strip()
    script = str(result.get("full_script") or result.get("script") or "").strip()

    scenes = []
    scene_script_lines = []
    for index, raw_scene in enumerate(raw_scenes, start=1):
        if not isinstance(raw_scene, dict):
            continue
        scene_text = str(
            raw_scene.get("scene_text")
            or raw_scene.get("narration")
            or raw_scene.get("script")
            or raw_scene.get("text")
            or ""
        ).strip()
        speaker = str(raw_scene.get("speaker") or "").strip()
        image_prompt = str(raw_scene.get("image_prompt") or raw_scene.get("visual_prompt") or "").strip()
        scene_number = raw_scene.get("scene_number") or raw_scene.get("scene_order") or index
        if scene_text:
            scene_script_lines.append(f"{speaker}: {scene_text}" if speaker else scene_text)
        scenes.append({
            "scene_number": scene_number,
            "scene_order": scene_number,
            "speaker": speaker,
            "scene_summary": scene_text[:120] or f"Scene {index}",
            "scene_situation": scene_text,
            "narration": scene_text,
            "visual_direction": image_prompt,
            "image_prompt": image_prompt,
            "visual_type": raw_scene.get("visual_type") or ("video" if index <= MAX_VIDEO_PROMPT_SCENES else "image"),
            "video_prompt_required": index <= MAX_VIDEO_PROMPT_SCENES,
        })
    if not script and scene_script_lines:
        script = "\n\n".join(scene_script_lines)

    now = time.time()
    hermes_id = f"{safe_id}_hermes"
    hermes_payload = {
        "id": hermes_id,
        "source": "notebooklm",
        "source_notebooklm_id": safe_id,
        "topic_queue_id": hermes_id,
        "status": "COMPLETED",
        "category": category,
        "topic": title,
        "generated_title": title,
        "upload_title": title,
        "title_generation": {
            "generated_title": title,
            "final_title": title,
            "category": category,
            "source": "notebooklm",
        },
        "benchmark_analysis": {
            "source": "notebooklm",
            "summary": hook or "NotebookLM 자료 기반 생성 결과",
        },
        "research_bundle": {
            "source": "notebooklm",
            "sources": notebook_payload.get("sources") or [],
            "source_chars": notebook_payload.get("source_chars"),
        },
        "narrative_blueprint": {
            "hook": hook,
            "mode": result.get("mode") or notebook_payload.get("mode"),
            "speakers": result.get("speakers") or [],
        },
        "script": script,
        "char_count": len(script),
        "structure": {
            "upload_title": title,
            "title_promise": hook,
            "opening_hook": hook,
            "global_mood": "NotebookLM grounded script",
            "scenes": scenes,
            "media_prompt_status": "fallback_ready" if any(scene.get("visual_direction") for scene in scenes) else "missing",
            "research_bundle": {
                "source": "notebooklm",
                "sources": notebook_payload.get("sources") or [],
            },
        },
        "publish_metadata": {
            "title": title,
            "titles": [title],
            "description": hook or script[:500],
            "tags": [category, "NotebookLM", "자료기반대본"],
            "hashtags": [f"#{category}", "#NotebookLM"],
        },
"material_statuses": {
            "benchmark": "ready",
            "title": "ready",
            "web_research": "ready",
            "plan_prompts": "review" if scenes else "missing",
            "script": "ready" if script else "missing",
            "publish_metadata": "ready",
        },
        "quality_gate": {
            "status": "review",
            "missing": ["media_prompts"],
            "review": ["notebooklm_import_needs_media_prompt_upgrade"],
            "media_prompt_status": "fallback_ready" if scenes else "missing",
            "can_auto_render": False,
        },
        "created_at": now,
        "updated_at": now,
        "completed_at": now,
    }

    AUTOPILOT_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    target_path = AUTOPILOT_RESULTS_DIR / f"{hermes_id}.json"
    target_path.write_text(json.dumps(hermes_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "success": True,
        "id": hermes_id,
        "path": str(target_path),
        "scene_count": len(scenes),
        "script_chars": len(script),
    }

@app.get("/api/yt/trending-keywords")
async def yt_trending_keywords(
    language: str = "ko",
    period: str = "now",
    age: str = "all",
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    """Gemini 기반 트렌드 키워드 생성 (버블 차트용)"""
    require_auth(authorization, cookie)
    from config import Config
    import asyncio
    import re as _re
    from services.ai_router import generate_text
    fallback_keywords = [
        {"keyword": "AI 영상", "translation": "AI 영상", "volume": 96, "category": "Technology"},
        {"keyword": "경제 전망", "translation": "경제 전망", "volume": 88, "category": "Finance"},
        {"keyword": "부동산 이슈", "translation": "부동산 이슈", "volume": 82, "category": "Finance"},
        {"keyword": "건강 루틴", "translation": "건강 루틴", "volume": 76, "category": "Health"},
        {"keyword": "여행 브이로그", "translation": "여행 브이로그", "volume": 70, "category": "Travel"},
        {"keyword": "요리 레시피", "translation": "요리 레시피", "volume": 64, "category": "Cooking"},
        {"keyword": "영화 리뷰", "translation": "영화 리뷰", "volume": 58, "category": "Film"},
        {"keyword": "게임 공략", "translation": "게임 공략", "volume": 52, "category": "Gaming"},
    ]
    if (
        not Config.GEMINI_API_KEY
        and not getattr(Config, "DEEPSEEK_API_KEY", "")
        and not getattr(Config, "GLM_API_KEY", "")
    ):
        return {"status": "ok", "keywords": fallback_keywords, "source": "fallback"}
    lang_map = {"ko": "South Korea (Korean)", "ja": "Japan (Japanese)", "en": "USA/International (English)"}
    period_map = {"now": "REAL-TIME / NOW", "week": "THIS WEEK (Last 7 days)", "month": "THIS MONTH (Last 30 days)"}
    age_map = {"all": "ALL Ages", "10s": "Teenagers (10-19)", "20s": "Young Adults (20-29)", "30s": "Adults (30-39)", "40s": "Middle-aged (40+)"}
    lang_name = lang_map.get(language, "South Korea (Korean)")
    period_text = period_map.get(period, "REAL-TIME / NOW")
    age_text = age_map.get(age, "ALL Ages")
    prompt = (
        f"Act as a Local Trend Analyst and YouTube SEO Expert for the specific region: {lang_name}.\n\n"
        f"Generate a list of 20-30 CURRENT trending search keywords/topics on YouTube specifically for:\n"
        f"- Region/Language: {lang_name}\n"
        f"- Time Period: {period_text}\n"
        f"- Target Age Group: {age_text}\n\n"
        f'STRICT LANGUAGE RULES:\n'
        f'1. "keyword": MUST be in the target language ({language}). NOT English (unless English region).\n'
        f'2. "translation": MUST be the meaning in KOREAN (Hangul).\n\n'
        f"DISTRIBUTION RULES:\n"
        f"- Assign a 'volume' score (1-100) using a Power Law distribution.\n"
        f"- 1-2 keywords: 95-100 (Viral)\n"
        f"- 3-5 keywords: 70-90 (High)\n"
        f"- Rest: 20-60 (Moderate)\n\n"
        f'OUTPUT FORMAT (JSON List):\n'
        f'[{{"keyword": "Keyword in Target Language", "translation": "한국어 뜻 설명", "volume": 98, "category": "Gaming"}}, ...]\n\n'
        f"RETURN ONLY THE JSON LIST. NO MARKDOWN."
    )
    try:
        text = await asyncio.wait_for(
            generate_text(
                prompt,
                model=Config.TOPIC_GENERATION_MODEL,
                temperature=0.9,
                max_tokens=4096,
                task_type="yt_trending_keywords",
                json_mode=True,
            ),
            timeout=5,
        )
        match = _re.search(r'\[[\s\S]*\]', text or "")
        keywords = json.loads(match.group(0) if match else text)
        if isinstance(keywords, list):
            return {"status": "ok", "keywords": keywords}
        return {"status": "ok", "keywords": fallback_keywords, "source": "fallback"}
    except Exception as e:
        logger.error(f"trending-keywords error: {e}")
        return {"status": "ok", "keywords": fallback_keywords, "source": "fallback"}


# ---------------------------------------------------------------------------
# Settings endpoints (Hermes / AI API keys & Worker Profile)
# ---------------------------------------------------------------------------

_MASKED = "••••••••"


def _mask_value(v: str) -> str:
    if not v:
        return ""
    if len(v) <= 8:
        return _MASKED
    return v[:4] + _MASKED


@app.get("/api/settings")
async def api_get_settings(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from config import Config
    keys = [
        ("GEMINI_API_KEY", "Gemini API 키"),
        ("CLAUDE_API_KEY", "Claude API 키"),
        ("DEEPSEEK_API_KEY", "DeepSeek API 키"),
        ("DEEPSEEK_BASE_URL", "DeepSeek Base URL"),
        ("GLM_API_KEY", "GLM API 키"),
        ("GLM_BASE_URL", "GLM Base URL"),
        ("YOUTUBE_API_KEY", "YouTube Data API 키"),
        ("YOUTUBE_API_KEYS", "YouTube Data API 백업 키"),
        ("ELEVENLABS_API_KEY", "ElevenLabs API 키"),
        ("SUNO_API_KEY", "Suno API 키"),
        ("TOPIC_GENERATION_MODEL", "제목 생성 모델"),
        ("TITLE_GENERATION_MODEL", "제목 후보 모델"),
        ("SCRIPT_GENERATION_MODEL", "대본 생성 모델"),
        ("SCRIPT_PLANNING_MODEL", "대본 구조 모델"),
        ("IMAGE_PROMPT_MODEL", "이미지/영상 프롬프트 모델"),
    ]
    result = []
    for attr, label in keys:
        val = getattr(Config, attr, "")
        result.append({"key": attr, "label": label, "value": _mask_value(val), "set": bool(val)})
    return {"settings": result}


@app.post("/api/settings")
async def api_set_setting(
    body: dict,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    key = (body.get("key") or "").strip()
    value = (body.get("value") or "").strip()
    if not key:
        return {"error": "key가 필요합니다"}

    is_key = "KEY" in key
    if is_key and (value == _MASKED or value.startswith(_MASKED)):
        return {"ok": True, "message": "변경 없음 (마스킹된 값)"}

    allowed = {
        "GEMINI_API_KEY", "CLAUDE_API_KEY", "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL",
        "GLM_API_KEY", "GLM_BASE_URL", "YOUTUBE_API_KEY", "YOUTUBE_API_KEYS",
        "ELEVENLABS_API_KEY", "SUNO_API_KEY",
        "TOPIC_GENERATION_MODEL", "TITLE_GENERATION_MODEL", "SCRIPT_GENERATION_MODEL", "SCRIPT_PLANNING_MODEL", "IMAGE_PROMPT_MODEL",
    }
    if key not in allowed:
        return {"error": f"허용되지 않은 설정 키: {key}"}
    try:
        from config import Config
        Config.update_api_key(key, value)
        logger.info(f"설정 변경 (대시보드): {key} = {value if 'KEY' not in key else '••••'}")

        try:
            from services.web_admin_client import web_admin_client
            sb_key = None
            for k, v in web_admin_client.KEY_MAP.items():
                if v == key:
                    sb_key = k
                    break

            if sb_key and web_admin_client.has_supabase():
                str_val = str(value).lower() if isinstance(value, bool) else str(value)
                ok = web_admin_client.save_global_setting(sb_key, str_val)
                if ok:
                    logger.info(f"Supabase 원격 동기화 완료: {sb_key} = {str_val}")
                else:
                    logger.warning(f"Supabase 원격 동기화 실패 (응답 에러): {sb_key}")
        except Exception as sb_err:
            logger.warning(f"Supabase 원격 저장 실패 (로컬 저장은 유지됨): {sb_err}")

        return {"ok": True, "success": True, "message": f"{key} 저장 완료 (원격 동기화 시도 완료)"}
    except Exception as e:
        logger.error(f"설정 저장 실패: {key} — {e}")
        return {"error": f"저장 실패: {e}"}


@app.get("/api/worker-profile-settings")
async def api_get_worker_profile_settings(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    import worker_config
    token_val = os.environ.get("AIRWORKER_TOKEN") or worker_config.WORKER_TOKEN or ""
    masked_token = (token_val[:4] + "••••••••") if len(token_val) > 4 else ("••••••••" if token_val else "")
    return {
        "worker_profile": worker_config.WORKER_PROFILE,
        "worker_id": os.environ.get("AIRWORKER_ID") or worker_config.WORKER_ID,
        "central_server_url": os.environ.get("AIRWORKER_CENTRAL_SERVER_URL", ""),
        "worker_token": masked_token,
        "worker_token_set": bool(token_val),
        "remote_worker_id": os.environ.get("REMOTE_RENDER_WORKER_ID", ""),
        "use_gpu_render": os.environ.get("USE_GPU_RENDER", "false").lower() in ("true", "1", "yes"),
    }


@app.post("/api/worker-profile-settings")
async def api_save_worker_profile_settings(
    body: dict,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    import worker_config
    result = worker_config.save_worker_settings(body)
    return result


# ---------------------------------------------------------------------------
# Hermes Autopilot endpoints
# ---------------------------------------------------------------------------

@app.get("/api/autopilot/hermes/status")
def api_autopilot_status(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    return autopilot_manager.get_status()


@app.get("/api/autopilot/hermes/offline-harness")
def api_autopilot_offline_harness(
    force: bool = False,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    return _run_hermes_offline_harness(force=force)


@app.post("/api/autopilot/hermes/start")
async def api_autopilot_start(
    body: dict = None,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    custom_settings = body.get("settings") if body else None
    harness_report = await run_in_threadpool(_run_hermes_offline_harness, force=True)
    if harness_report.get("status") != "pass":
        failed_checks = [
            check
            for check in harness_report.get("checks", [])
            if isinstance(check, dict) and not check.get("passed")
        ]
        summary = "; ".join(
            str(check.get("name") or "unknown check") + (f": {check.get('detail')}" if check.get("detail") else "")
            for check in failed_checks[:5]
        )
        return {
            "success": False,
            "error": "Hermes offline preflight failed. 자동 생성 시작이 차단되었습니다.",
            "detail": summary,
            "offline_harness": harness_report,
        }
    from ipc import submit_command, wait_for_result

    worker_result = await run_in_threadpool(
        wait_for_result,
        submit_command("start_process", {"name": "hermes_worker"}),
    )
    if not worker_result.get("success"):
        return {
            "success": False,
            "error": worker_result.get("error") or "Hermes Worker start failed",
        }

    autopilot_result = await autopilot_manager.start(custom_settings)
    return {**autopilot_result, "worker_started": True, "offline_harness": harness_report}


@app.post("/api/autopilot/hermes/save_settings")
async def api_autopilot_save_settings(
    body: dict,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    new_settings = body.get("settings")
    if not new_settings:
        return {"error": "settings가 필요합니다"}
    return await autopilot_manager.save_settings(new_settings)


@app.post("/api/autopilot/hermes/stop")
async def api_autopilot_stop(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    autopilot_result = await autopilot_manager.stop()
    from ipc import submit_command, wait_for_result
    worker_result = await run_in_threadpool(
        wait_for_result,
        submit_command("stop_process", {"name": "hermes_worker"}),
    )
    cancelled_jobs = job_store.cancel_nonterminal_jobs_by_source(
        "autopilot",
        reason="autopilot stopped by administrator",
    )
    return {
        "success": bool(worker_result.get("success")),
        "autopilot_was_running": bool(autopilot_result.get("success")),
        "cancelled_job_count": len(cancelled_jobs),
    }


def _delayed_restart():
    _launch_worker_server_lifecycle_helper(restart=True)


def _delayed_shutdown():
    _launch_worker_server_lifecycle_helper(restart=False)


def _launch_worker_server_lifecycle_helper(*, restart: bool) -> None:
    """Stop every AIR Worker server/process, optionally starting a clean set.

    The dashboard server is one of the processes being stopped, so the actual
    lifecycle work must happen in a detached helper after this HTTP response is
    returned. On this desktop target Windows PowerShell is available and gives
    us reliable command-line process filtering without adding a runtime dep.
    """
    worker_dir = Path(__file__).resolve().parent
    python_exe = Path(sys.executable)
    dashboard_args = "-m uvicorn dashboard_app:app --host 127.0.0.1 --port 3002"
    roles_to_start = ["manager"] if restart else []
    helper_script = STATE_DIR / ("restart_worker_server.ps1" if restart else "shutdown_worker_server.ps1")
    lifecycle_log = LOG_DIR / "server_lifecycle.log"

    ps_lines = [
        "$ErrorActionPreference = 'SilentlyContinue'",
        f"$log = {json.dumps(str(lifecycle_log))}",
        "function Write-LifeLog([string]$message) {",
        "  $line = ('{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'), $message)",
        "  Add-Content -LiteralPath $log -Value $line -Encoding UTF8",
        "}",
        "Write-LifeLog 'helper started'",
        "Start-Sleep -Milliseconds 900",
        f"$worker = {json.dumps(str(worker_dir))}",
        f"$python = {json.dumps(str(python_exe))}",
        "$patterns = @(",
        "  'dashboard_app:app',",
        "  'air_worker_entry.py',",
        "  'worker\\manager.py',",
        "  'worker\\render_worker.py',",
        "  'worker\\remote_drive_worker_process.py',",
        "  'worker\\hermes_worker.py',",
        "  'worker\\local_api_process.py'",
        ")",
        "function Get-AirWorkerProcesses {",
        "  Get-CimInstance Win32_Process | Where-Object {",
        "    $cmd = $_.CommandLine",
        "    $_.ProcessId -ne $PID -and $cmd -and $cmd -like '*LongformGenerator*' -and",
        "    (($patterns | Where-Object { $cmd -like \"*$_*\" }).Count -gt 0)",
        "  }",
        "}",
        "$procs = @(Get-AirWorkerProcesses | Sort-Object ProcessId -Unique)",
        "Write-LifeLog ('matched processes: ' + (($procs | ForEach-Object { \"$($_.ProcessId):$($_.Name)\" }) -join ', '))",
        "foreach ($proc in $procs) {",
        "  Write-LifeLog ('killing pid=' + $proc.ProcessId + ' cmd=' + $proc.CommandLine)",
        "  Start-Process -FilePath 'taskkill.exe' -ArgumentList @('/PID', [string]$proc.ProcessId, '/T', '/F') -WindowStyle Hidden -Wait",
        "}",
        "$deadline = (Get-Date).AddSeconds(12)",
        "do {",
        "  Start-Sleep -Milliseconds 500",
        "  $remaining = @(Get-AirWorkerProcesses | Sort-Object ProcessId -Unique)",
        "} while ($remaining.Count -gt 0 -and (Get-Date) -lt $deadline)",
        "if ($remaining.Count -gt 0) {",
        "  Write-LifeLog ('remaining after kill: ' + (($remaining | ForEach-Object { \"$($_.ProcessId):$($_.Name)\" }) -join ', '))",
        "} else {",
        "  Write-LifeLog 'all matched processes stopped'",
        "}",
    ]
    if restart:
        ps_lines.append(
            "Write-LifeLog 'starting dashboard'"
        )
        ps_lines.append(
            "Start-Process -FilePath $python "
            f"-ArgumentList {json.dumps(dashboard_args)} "
            "-WorkingDirectory $worker -WindowStyle Hidden"
        )
        ps_lines.append("Start-Sleep -Milliseconds 1200")
        for role in roles_to_start:
            ps_lines.append(f"Write-LifeLog 'starting role {role}'")
            ps_lines.append(
                "Start-Process -FilePath $python "
                f"-ArgumentList {json.dumps(str(worker_dir / 'air_worker_entry.py') + ' --role ' + role)} "
                "-WorkingDirectory $worker -WindowStyle Hidden"
            )
    ps_lines.append("Write-LifeLog 'helper completed'")
    helper_script.write_text("\n".join(ps_lines) + "\n", encoding="utf-8")
    logger.info(
        "Launching full worker lifecycle helper "
        f"restart={restart}, python={python_exe}, worker_dir={worker_dir}"
    )
    flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(helper_script)],
        cwd=str(worker_dir),
        creationflags=flags if sys.platform == "win32" else 0,
    )


@app.post("/api/server/restart")
async def api_server_restart(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    threading.Thread(target=_delayed_restart, daemon=True).start()
    return {"success": True, "message": "워커 서버 재시작을 진행합니다."}


@app.post("/api/server/shutdown")
async def api_server_shutdown(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    threading.Thread(target=_delayed_shutdown, daemon=True).start()
    return {"success": True, "message": "워커 서버가 완전히 종료됩니다."}


# ---------------------------------------------------------------------------
# Login page (serves HTML — no auth required)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Voicebox GPU TTS API Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/voicebox/history")
async def api_voicebox_history(
    topic_id: str | None = None,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from pathlib import Path
    output_dir = Path(__file__).resolve().parent / "voicebox_outputs"
    if not output_dir.exists():
        return {"history": []}
        
    files = list(output_dir.glob("*.mp3")) + list(output_dir.glob("*.wav"))
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    
    history = []
    for f in files[:30]:
        stat = f.stat()
        mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
        history.append({
            "filename": f.name,
            "url": f"/api/voicebox/audio/{f.name}",
            "size_kb": round(stat.st_size / 1024, 1),
            "created_at": mtime,
            "timestamp": stat.st_mtime,
        })
        
    return {"history": history}


@app.get("/api/voicebox/topics")
async def api_voicebox_topics(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    
    combined_topics = []
    
    # 1. Supabase topics_queue (Fetch all topics, prioritizing ones with scripts)
    try:
        from remote_drive_worker import RemoteDriveWorker
        worker = RemoteDriveWorker()
        topics_url = f"{worker.supabase_url}/rest/v1/topics_queue"
        
        # 1-1. Fetch topics with pregenerated scripts first
        params_with_script = {
            "select": "*",
            "pregenerated_script": "not.is.null",
            "order": "created_at.desc",
            "limit": "50",
        }
        script_rows = worker._request("GET", topics_url, params=params_with_script) or []
        
        # 1-2. Fetch latest topics
        params_latest = {
            "select": "*",
            "order": "created_at.desc",
            "limit": "30",
        }
        latest_rows = worker._request("GET", topics_url, params=params_latest) or []
        
        # Combine unique rows (script-ready topics first)
        seen_ids = set()
        rows = []
        for r in script_rows + latest_rows:
            if r.get("id") not in seen_ids:
                seen_ids.add(r.get("id"))
                rows.append(r)
        for r in rows:
            script_raw = r.get("pregenerated_script") or ""
            script_text = ""
            if isinstance(script_raw, str):
                script_text = script_raw
            elif isinstance(script_raw, dict):
                script_text = script_raw.get("script") or script_raw.get("full_script") or str(script_raw)
            
            # Check progress_payload script
            if not script_text.strip():
                pp = r.get("progress_payload") or {}
                if isinstance(pp, dict) and pp.get("script"):
                    script_text = str(pp.get("script"))
                    
            # If script column is empty, check structure scenes narration
            if not script_text.strip():
                structure = r.get("pregenerated_structure") or {}
                if isinstance(structure, dict) and "scenes" in structure:
                    scene_texts = []
                    for sc in structure["scenes"]:
                        narr = sc.get("narration") or sc.get("script") or sc.get("text") or ""
                        if narr:
                            scene_texts.append(narr)
                    if scene_texts:
                        script_text = "\n\n".join(scene_texts)
            
            combined_topics.append({
                "id": f"queue-{r.get('id')}",
                "type": "supabase",
                "topic_id": r.get("id"),
                "title": r.get("generated_title") or r.get("topic") or f"주제 #{r.get('id')}",
                "category": r.get("category_name") or "옛날이야기/사연",
                "script": script_text,
                "has_audio": bool(r.get("pregenerated_audio_url")),
                "created_at": r.get("created_at"),
            })
    except Exception as e:
        logger.warning(f"Failed to fetch supabase topics: {e}")
    
    # 1. Local generated results
    try:
        from hermes_autopilot import hermes_autopilot
        local_results = hermes_autopilot.list_generated_results(limit=50)
        for r in local_results:
            combined_topics.append({
                "id": str(r.get("id")),
                "type": "local",
                "topic_id": r.get("topic_id"),
                "title": r.get("title") or r.get("topic") or f"결과 #{r.get('id')}",
                "category": r.get("category") or "일반",
                "script": r.get("script") or "",
                "created_at": r.get("created_at"),
            })
    except Exception as e:
        logger.warning(f"Failed to fetch local generated results: {e}")

    # 2. Supabase topics_queue
    try:
        from remote_drive_worker import RemoteDriveWorker
        worker = RemoteDriveWorker()
        topics_url = f"{worker.supabase_url}/rest/v1/topics_queue"
        params = {
            "select": "id,topic,generated_title,category_name,pregenerated_script,pregenerated_audio_url,status,created_at",
            "order": "created_at.desc",
            "limit": "30",
        }
        rows = worker._request("GET", topics_url, params=params) or []
        for r in rows:
            script_text = r.get("pregenerated_script") or ""
            if isinstance(script_text, dict):
                script_text = script_text.get("script") or str(script_text)
            
            if not script_text:
                script_text = f"국민연금을 30년 동안 성실히 납부해온 부부가 있습니다.\n\n할머니: \"그 집은 말이야, 대대로 내려오는 비밀이 있어.\"\n\n여인) \"정말 그게 사실인가요? 믿기지가 않아요.\"\n\n나레이터: 두 사람의 이야기는 그렇게 시작되었습니다."

            combined_topics.append({
                "id": f"queue-{r.get('id')}",
                "type": "supabase",
                "topic_id": r.get("id"),
                "title": r.get("generated_title") or r.get("topic") or f"주제 #{r.get('id')}",
                "category": r.get("category_name") or "경제/사연",
                "script": str(script_text),
                "has_audio": bool(r.get("pregenerated_audio_url")),
                "created_at": r.get("created_at"),
            })
    except Exception as e:
        logger.warning(f"Failed to fetch supabase topics: {e}")

    # 3. If empty, provide default rich topics
    if not combined_topics:
        combined_topics.append({
            "id": "sample-1",
            "type": "sample",
            "topic_id": 101,
            "title": "국민연금 30년 냈는데 월 80만 원? 30년 차 부부가 공개한 실제 수령액",
            "category": "경제/재테크",
            "script": "서른 해 동안 한 번도 거르지 않고 국민연금을 납입해온 평범한 부부가 있습니다.\n\n오늘 통장을 마주한 부부는 말을 잇지 못했습니다.\n\n할머니: \"30년을 일해서 넣었는데, 겨우 이 정도라니...\"\n\n여인) \"앞으로 은퇴 생활비는 어떻게 감당해야 할지 막막해요.\"\n\n나레이터: 국민연금 30년 납입의 충격적인 진실과 노후 대비의 핵심 포인트를 지금 공개합니다.",
            "has_audio": False,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        combined_topics.append({
            "id": "sample-2",
            "type": "sample",
            "topic_id": 102,
            "title": "아내의 장례식 날, 30년 숨긴 첫사랑의 편지가 열렸다",
            "category": "사연/감동",
            "script": "글쎄, 장례식이 끝나고 조문객들이 하나둘 돌아간 뒤였어요.\n\n여인이 품에 안고 있던 오래된 나무 상자를 열자 빛바랜 편지 봉투가 모습을 드러냈습니다.\n\n할머니: \"그 사람과 나눈 마지막 약속이었어. 절대 열어보지 않겠다고.\"\n\n나레이터: 30년 세월 속에 감춰진 가슴 아픈 첫사랑의 비밀이 마침내 밝혀집니다.",
            "has_audio": False,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        
    return {"topics": combined_topics}


@app.get("/api/voicebox/presets")
async def api_voicebox_presets(
    provider: str = "all",
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from voicebox_engine import voicebox_engine
    return {"presets": voicebox_engine.list_presets(provider), "device": voicebox_engine.device}

@app.post("/api/voicebox/generate")
async def api_voicebox_generate(
    payload: dict = Body(...),
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from voicebox_engine import voicebox_engine
    script_text = str(payload.get("script") or "").strip()
    provider = str(payload.get("provider") or "voicebox").strip()
    voice_id = str(payload.get("voice_id") or ("google_kr_standard" if provider == "google" else "narrator_calm_kr")).strip()
    speed = float(payload.get("speed") or 1.0)
    topic_id = payload.get("topic_id")
    
    if not script_text:
        raise HTTPException(status_code=400, detail="대본 내용이 비어 있습니다.")
        
    try:
        res = await voicebox_engine.generate_tts(
            script_text=script_text,
            provider=provider,
            voice_id=voice_id,
            speed=speed,
        )
        return {"success": True, **res}
    except Exception as e:
        logger.error(f"TTS generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"TTS 생성 실패: {str(e)}")

@app.get("/api/voicebox/audio/{filename}")
async def api_voicebox_audio(filename: str):
    from pathlib import Path
    output_dir = Path(__file__).resolve().parent / "voicebox_outputs"
    file_path = output_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    from fastapi.responses import FileResponse
    return FileResponse(str(file_path), media_type="audio/mpeg")

@app.post("/api/voicebox/save-to-supabase")
async def api_voicebox_save_to_supabase(
    payload: dict = Body(...),
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    topic_id = payload.get("topic_id")
    audio_filename = payload.get("audio_filename")
    voice_id = payload.get("voice_id") or "voicebox"
    
    if not topic_id:
        raise HTTPException(status_code=400, detail="topic_id가 필요합니다.")
        
    try:
        from remote_drive_worker import RemoteDriveWorker
        worker = RemoteDriveWorker()
        
        # Audio URL constructing
        # If hosting locally or via worker dashboard audio API:
        audio_url = f"/api/voicebox/audio/{audio_filename}"
        
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        topics_url = f"{worker.supabase_url}/rest/v1/topics_queue"
        
        # 1. Fetch existing progress_payload to preserve existing properties
        existing_rows = worker._request("GET", topics_url, params={"select": "id,progress_payload", "id": f"eq.{topic_id}"}) or []
        existing_payload = {}
        if existing_rows and isinstance(existing_rows[0].get("progress_payload"), dict):
            existing_payload = existing_rows[0]["progress_payload"]
            
        merged_payload = {
            **existing_payload,
            "has_pregenerated_audio": True,
            "pregenerated_audio_url": audio_url,
            "pregenerated_audio_filename": audio_filename,
            "pregenerated_voice_id": voice_id,
            "tts_provider": "voicebox",
            "tts_completed": True,
            "tts_completed_at": now,
        }
        
        update_payload = {
            "progress_updated_at": now,
            "progress_payload": merged_payload,
        }
        
        url = f"{topics_url}?id=eq.{topic_id}"
        patch_res = worker._request("PATCH", url, json=update_payload)
        return {
            "success": True,
            "message": f"주제 #{topic_id}에 Voicebox 음성이 Supabase로 저장되었습니다. 유저 작업 시 TTS가 즉시 완료 상태가 됩니다!",
            "audio_url": audio_url,
        }
    except Exception as e:
        logger.error(f"Failed to save voicebox audio to supabase: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Supabase 저장 실패: {str(e)}")


@app.get("/api/generated-results")
async def api_generated_results(
    limit: int = 100,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    AUTOPILOT_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    seen_ids = set()
    seen_topic_ids = set()
    for path in sorted(AUTOPILOT_RESULTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        summary = _generated_result_summary(path)
        if summary:
            seen_ids.add(summary["id"])
            if summary.get("topic_queue_id") is not None:
                seen_topic_ids.add(_topic_key(summary.get("topic_queue_id")))
            rows.append(summary)
    for result_id, data in _collect_topic_generated_results(limit=max(100, min(limit * 10, 1000))).items():
        if result_id in seen_ids:
            continue
        topic_id = _topic_key(data.get("topic_queue_id"))
        if topic_id and topic_id in seen_topic_ids:
            continue
        summary = _topic_generated_result_summary(result_id, data)
        if summary.get("has_script") or summary.get("scene_count"):
            rows.append(summary)
    rows.sort(key=lambda row: row.get("completed_at") or row.get("updated_at") or 0, reverse=True)
    rows = rows[:max(1, min(limit, 500))]
    return {
        "results": rows,
        "dir": f"{AUTOPILOT_RESULTS_DIR} + {HERMES_RESULTS_DIR}",
        "diagnostics": _autopilot_generation_diagnostics(),
    }


@app.get("/api/generated-results/{result_id}")
async def api_generated_result_detail(
    result_id: str,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    safe_id = _safe_result_id(result_id)
    if not safe_id:
        raise HTTPException(400, "Invalid result id")
    if safe_id.startswith("topic_"):
        topic_results = _collect_topic_generated_results(limit=1000)
        data = topic_results.get(safe_id)
        if not isinstance(data, dict):
            raise HTTPException(404, "Generated result not found")
        data["_file"] = {"id": safe_id, "path": "job_store/hermes_results", "updated_at": data.get("updated_at") or data.get("completed_at")}
        return data
    path = AUTOPILOT_RESULTS_DIR / f"{safe_id}.json"
    if not path.exists():
        raise HTTPException(404, "Generated result not found")
    data = _read_generated_result(path)
    if not isinstance(data, dict):
        raise HTTPException(500, "Generated result JSON is invalid")
    data["_file"] = {"id": safe_id, "path": str(path), "updated_at": path.stat().st_mtime}
    return data


@app.get("/login")
async def login_page():
    return Response(content=LOGIN_HTML, media_type="text/html; charset=utf-8")


@app.post("/auth/login")
async def auth_login(body: dict, response: Response):
    token = (body.get("token") or "").strip()
    if not verify_token(token):
        return {"error": "토큰이 올바르지 않습니다"}
    response = Response(
        content='{"ok":true}',
        media_type="application/json",
        headers={"Set-Cookie": f"dashboard_token={token}; Path=/; SameSite=Strict; Max-Age=604800"},
    )
    return response


@app.post("/auth/logout")
async def auth_logout(response: Response):
    return Response(
        content='{"ok":true}',
        media_type="application/json",
        headers={"Set-Cookie": "dashboard_token=; Path=/; SameSite=Strict; Max-Age=0"},
    )


# ---------------------------------------------------------------------------
# Dashboard single-page HTML (embedded as a Python string)
# ---------------------------------------------------------------------------

@app.get("/")
async def dashboard_page():
    return Response(
        content=DASHBOARD_HTML,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# =========================================================================
# HTML templates (login + dashboard)
# =========================================================================

LOGIN_HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AIR Worker — 로그인</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, 'Segoe UI', sans-serif; background: #0f1117; color: #e1e4e8; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
.login-box { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 40px; width: 400px; max-width: 90vw; }
.login-box h1 { font-size: 24px; margin-bottom: 8px; }
.login-box p { color: #8b949e; margin-bottom: 24px; font-size: 14px; }
input { width: 100%; padding: 10px 14px; border: 1px solid #30363d; border-radius: 6px; background: #0d1117; color: #e1e4e8; font-size: 14px; outline: none; }
input:focus { border-color: #58a6ff; }
button { width: 100%; padding: 10px; border: none; border-radius: 6px; background: #238636; color: #fff; font-size: 14px; font-weight: 600; cursor: pointer; margin-top: 16px; }
button:hover { background: #2ea043; }
.error { color: #f85149; font-size: 13px; margin-top: 12px; display: none; }
</style>
</head>
<body>
<div class="login-box">
  <h1>AIR Worker</h1>
  <p>대시보드에 접근하려면 인증 토큰을 입력하세요.</p>
  <input type="password" id="token-input" placeholder="인증 토큰" autocomplete="off">
  <button onclick="login()">로그인</button>
  <div class="error" id="error-msg"></div>
</div>
<script>
async function login() {
  const token = document.getElementById('token-input').value.trim();
  const errEl = document.getElementById('error-msg');
  errEl.style.display = 'none';
  try {
    const res = await fetch('/auth/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token})
    });
    const data = await res.json();
    if (data.error) { errEl.textContent = data.error; errEl.style.display = 'block'; return; }
    window.location.href = '/';
  } catch(e) { errEl.textContent = '서버 오류'; errEl.style.display = 'block'; }
}
document.getElementById('token-input').addEventListener('keydown', e => { if(e.key==='Enter') login(); });
</script>
</body>
</html>"""


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AIR Worker — 대시보드</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
/* ── Reset & Base ── */
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; font-size: 14px; line-height: 1.5; }
a { color: #58a6ff; text-decoration: none; }
a:hover { text-decoration: underline; }
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: #161b22; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 4px; }

/* ── Layout ── */
.app { display: flex; height: 100vh; }
.sidebar { width: 220px; background: #161b22; border-right: 1px solid #21262d; display: flex; flex-direction: column; flex-shrink: 0; }
.sidebar-brand { padding: 20px 16px; border-bottom: 1px solid #21262d; }
.sidebar-brand h1 { font-size: 18px; font-weight: 700; }
.sidebar-brand span { font-size: 12px; color: #8b949e; }
.nav { flex: 1; padding: 12px 8px; }
.nav-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 6px; cursor: pointer; color: #8b949e; transition: all 0.15s; }
.nav-item:hover { background: #21262d; color: #c9d1d9; }
.nav-item.active { background: #1f6feb22; color: #58a6ff; font-weight: 600; }
.nav-item .icon { font-size: 18px; width: 24px; text-align: center; }
.main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.topbar { padding: 12px 24px; border-bottom: 1px solid #21262d; display: flex; align-items: center; justify-content: space-between; background: #161b22; }
.topbar h2 { font-size: 16px; font-weight: 600; }
.topbar-actions { display: flex; align-items: center; gap: 12px; }
.refresh-indicator { font-size: 12px; color: #8b949e; }
.content { flex: 1; overflow-y: auto; padding: 24px; }

/* ── Cards ── */
.card { background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 20px; margin-bottom: 16px; }
.card-title { font-size: 13px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }

/* ── Status Cards Grid ── */
.status-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; margin-bottom: 24px; }
.status-card { background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 16px; }
.status-card .name { font-size: 16px; font-weight: 600; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
.status-card .info { font-size: 12px; color: #8b949e; }
.status-card .progress-bar { height: 4px; background: #21262d; border-radius: 2px; margin-top: 10px; overflow: hidden; }
.status-card .progress-fill { height: 100%; background: #238636; border-radius: 2px; transition: width 0.3s; }

/* ── Badges ── */
.badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }
.badge-running { background: #23863622; color: #3fb950; }
.badge-idle { background: #8b949e22; color: #8b949e; }
.badge-stopped { background: #f8514922; color: #f85149; }
.badge-paused { background: #d2992222; color: #d29922; }
.badge-starting { background: #d2992222; color: #d29922; }
.badge-disabled { background: #f8514922; color: #f85149; }
.badge-queued { background: #8b949e22; color: #8b949e; }
.badge-claimed { background: #d2992222; color: #d29922; }
.badge-preparing { background: #1f6feb22; color: #58a6ff; }
.badge-rendering { background: #23863622; color: #3fb950; }
.badge-uploading { background: #a371f722; color: #a371f7; }
.badge-completed { background: #23863622; color: #3fb950; }
.badge-review { background: #d2992222; color: #d29922; }
.badge-failed { background: #f0883e22; color: #f0883e; }
.prompt-box-error { border-color: #f0883e66; color: #f0883e; }
.badge-canceled { background: #f8514922; color: #f85149; }
.badge-abandoned { background: #f8514922; color: #f85149; }
.generated-results-section { margin-top: 14px; }
.generated-results-section:first-of-type { margin-top: 0; }
.generated-results-heading { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin: 0 0 8px; font-size: 12px; font-weight: 700; color: #c9d1d9; }
.generated-results-heading .info { font-weight: 500; }
.generated-progress { display: inline-flex; align-items: center; min-width: 42px; justify-content: center; }

/* ── Tables ── */
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #21262d; }
th { color: #8b949e; font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
td { font-size: 13px; }
tr:hover { background: #161b22; }

/* ── Buttons ── */
.btn { display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px; border: 1px solid #30363d; border-radius: 6px; background: #21262d; color: #c9d1d9; font-size: 13px; cursor: pointer; transition: all 0.15s; }
.btn:hover { background: #30363d; }
.btn-primary { background: #238636; border-color: #238636; color: #fff; }
.btn-primary:hover { background: #2ea043; }
.btn-danger { background: #da3633; border-color: #da3633; color: #fff; }
.btn-danger:hover { background: #f85149; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn-start { border-color: #238636; color: #3fb950; }
.btn-start:hover:not(:disabled) { background: #23863622; }
.btn-stop { border-color: #da3633; color: #f85149; }
.btn-stop:hover:not(:disabled) { background: #da363322; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── Forms ── */
.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 13px; color: #8b949e; margin-bottom: 6px; font-weight: 500; }
.form-group input, .form-group select, .form-group textarea {
  width: 100%; padding: 8px 12px; border: 1px solid #30363d; border-radius: 6px;
  background: #0d1117; color: #c9d1d9; font-size: 14px; outline: none;
}
.form-group input:focus, .form-group select:focus, .form-group textarea:focus { border-color: #58a6ff; }
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

/* ── Log viewer ── */
.log-viewer { background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 12px; font-family: 'Cascadia Code', 'Fira Code', monospace; font-size: 12px; max-height: 400px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; color: #8b949e; }

/* ── Tab content ── */
.tab-content { display: none; }
.tab-content.active { display: block; }

/* ── Job detail modal ── */
.modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 100; justify-content: center; align-items: center; }
.modal-overlay.active { display: flex; }
.modal { background: #161b22; border: 1px solid #21262d; border-radius: 12px; width: 700px; max-width: 90vw; max-height: 80vh; overflow-y: auto; padding: 24px; }
.modal h3 { margin-bottom: 16px; }
.modal .close { float: right; cursor: pointer; color: #8b949e; font-size: 20px; }

/* ── YouTube Explore Tab ── */
.yt-filter-row { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.yt-lang-btn.active { background: #1f6feb22; border-color: #58a6ff; color: #58a6ff; }
.yt-search-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.yt-search-row input { flex: 1; min-width: 200px; padding: 8px 12px; border: 1px solid #30363d; border-radius: 6px; background: #0d1117; color: #c9d1d9; font-size: 14px; outline: none; }
.yt-search-row input:focus { border-color: #58a6ff; }
.yt-search-row select { padding: 8px 12px; border: 1px solid #30363d; border-radius: 6px; background: #0d1117; color: #c9d1d9; font-size: 13px; outline: none; }
.yt-tag { display: inline-block; padding: 4px 10px; border-radius: 14px; font-size: 12px; cursor: pointer; background: #21262d; color: #8b949e; border: 1px solid #30363d; transition: all 0.15s; }
.yt-tag:hover { background: #1f6feb22; border-color: #58a6ff; color: #58a6ff; }
.bubble-loading { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: #161b22cc; color: #8b949e; font-size: 14px; z-index: 5; border-radius: 8px; }
.yt-thumb { width: 120px; height: 68px; border-radius: 4px; object-fit: cover; background: #21262d; }
.yt-channel-avatar { width: 32px; height: 32px; border-radius: 50%; object-fit: cover; margin-right: 6px; vertical-align: middle; }
.yt-title-cell { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.yt-viral-score { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.yt-viral-high { background: #23863622; color: #3fb950; }
.yt-viral-mid { background: #d2992222; color: #d29922; }
.yt-viral-low { background: #8b949e22; color: #8b949e; }
.yt-analysis-text { background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 16px; font-size: 13px; line-height: 1.8; color: #c9d1d9; white-space: pre-wrap; max-height: 400px; overflow-y: auto; margin-top: 12px; }
.yt-stat { font-size: 11px; color: #8b949e; margin-top: 2px; }

/* ── Timeline ── */
.timeline { border-left: 2px solid #21262d; padding-left: 20px; margin: 16px 0; }
.timeline-item { position: relative; padding: 8px 0; font-size: 13px; }
.timeline-item::before { content: ''; position: absolute; left: -26px; top: 14px; width: 10px; height: 10px; border-radius: 50%; background: #58a6ff; border: 2px solid #0d1117; }
.timeline-item .time { color: #8b949e; font-size: 11px; }

/* ── Notification toast ── */
.toast-container { position: fixed; top: 20px; right: 20px; z-index: 200; display: flex; flex-direction: column; gap: 8px; }
.toast { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 12px 16px; font-size: 13px; animation: slideIn 0.3s ease; }
.toast.success { border-left: 3px solid #3fb950; }
.toast.error { border-left: 3px solid #f85149; }
.toast.warning { border-left: 3px solid #d29922; }
.toast.info { border-left: 3px solid #58a6ff; }
@keyframes slideIn { from { opacity: 0; transform: translateX(40px); } to { opacity: 1; transform: translateX(0); } }

/* ── Empty state ── */
.empty { text-align: center; padding: 40px; color: #8b949e; }
.empty .icon { font-size: 48px; margin-bottom: 12px; }

/* ── Settings tab ── */
.settings-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; align-items: start; }
.settings-panel { border: 1px solid #21262d; border-radius: 8px; background: rgba(13,17,23,0.35); padding: 16px; min-width: 0; }
.settings-panel-title { color: #c9d1d9; font-size: 13px; font-weight: 700; margin-bottom: 8px; }
.settings-panel-note { color: #8b949e; font-size: 12px; margin-bottom: 12px; line-height: 1.5; }
.setting-row { display: flex; align-items: flex-start; gap: 12px; padding: 12px 0; border-bottom: 1px solid #21262d; }
.setting-row:last-child { border-bottom: none !important; }
.setting-input:focus { border-color: #58a6ff !important; box-shadow: 0 0 0 2px rgba(88,166,255,0.15); }
.setting-input::placeholder { color: #484f58; }
@media (max-width: 1100px) { .settings-grid { grid-template-columns: 1fr; } }

/* ── Result viewer ── */
.result-viewer { background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 12px; font-size: 13px; max-height: 300px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; }
.generated-result-layout { display: grid; grid-template-columns: minmax(360px, 0.9fr) minmax(420px, 1.1fr); gap: 16px; }
.generated-result-detail { display: flex; flex-direction: column; gap: 14px; }
.generated-section { border: 1px solid #21262d; border-radius: 8px; padding: 14px; background: rgba(13,17,23,0.45); }
.generated-section h4 { margin: 0 0 10px; font-size: 14px; color: #e6edf3; }
.generated-meta { display: grid; grid-template-columns: 120px 1fr; gap: 8px 12px; font-size: 13px; }
.generated-meta .label { color: #8b949e; }
.scene-card { border: 1px solid #30363d; border-radius: 8px; padding: 12px; margin-top: 10px; background: #0d1117; }
.scene-card .scene-title { font-weight: 700; color: #58a6ff; margin-bottom: 8px; }
/* ── Video Production Pipeline Cards ── */
.pipeline-list { display: flex; flex-direction: column; gap: 12px; }
.pipeline-card { background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 14px 16px; transition: border-color 0.2s, box-shadow 0.2s; }
.pipeline-card:hover { border-color: rgba(88, 166, 255, 0.4); }
.pipeline-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.pipeline-title-group { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 260px; }
.pipeline-badge-category { background: rgba(163, 113, 247, 0.15); border: 1px solid rgba(163, 113, 247, 0.4); color: #d2a8ff; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 12px; white-space: nowrap; }
.pipeline-title { font-size: 14px; font-weight: 600; color: #e6edf3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 520px; }
.pipeline-meta-group { display: flex; align-items: center; gap: 10px; }
.pipeline-time { font-size: 11px; color: #8b949e; font-family: monospace; }
.pipeline-toggle-btn { background: #21262d; border: 1px solid #30363d; color: #8b949e; font-size: 11px; padding: 3px 8px; border-radius: 6px; cursor: pointer; transition: all 0.15s; }
.pipeline-toggle-btn:hover { color: #c9d1d9; background: #30363d; }

.pipeline-steps-container { display: flex; align-items: center; gap: 6px; background: #0d1117; padding: 8px 12px; border-radius: 8px; border: 1px solid #21262d; overflow-x: auto; }
.pipeline-step-item { display: flex; align-items: center; gap: 6px; padding: 5px 10px; border-radius: 6px; font-size: 11px; font-weight: 600; white-space: nowrap; border: 1px solid transparent; transition: all 0.2s; flex-shrink: 0; }
.pipeline-step-arrow { color: #484f58; font-size: 10px; flex-shrink: 0; }

.step-done { background: rgba(35, 134, 54, 0.15); border-color: rgba(35, 134, 54, 0.4); color: #3fb950; }
.step-running { background: rgba(56, 139, 253, 0.15); border-color: rgba(56, 139, 253, 0.5); color: #58a6ff; animation: pulseGlow 1.5s infinite; }
.step-failed { background: rgba(240, 136, 62, 0.15); border-color: rgba(240, 136, 62, 0.45); color: #f0883e; }
.step-pending { background: rgba(110, 118, 129, 0.08); border-color: rgba(110, 118, 129, 0.2); color: #8b949e; opacity: 0.7; }

@keyframes pulseGlow {
  0% { box-shadow: 0 0 0 0 rgba(56, 139, 253, 0.4); }
  70% { box-shadow: 0 0 0 5px rgba(56, 139, 253, 0); }
  100% { box-shadow: 0 0 0 0 rgba(56, 139, 253, 0); }
}

.pipeline-details-accordion { display: none; margin-top: 12px; padding-top: 12px; border-top: 1px solid #21262d; }
.pipeline-details-accordion.open { display: block; }
.pipeline-subjob-row { display: flex; align-items: center; justify-content: space-between; padding: 6px 8px; border-radius: 6px; font-size: 12px; background: rgba(13, 17, 23, 0.5); margin-bottom: 4px; border: 1px solid rgba(255,255,255,0.03); }
.pipeline-subjob-row:hover { background: rgba(13, 17, 23, 0.8); }
.pipeline-actions-footer { display: flex; gap: 8px; justify-content: flex-end; margin-top: 10px; }
.pipeline-error-summary { margin-top: 10px; color: #f0883e; font-size: 12px; word-break: break-word; background: rgba(240,136,62,0.12); padding: 8px 10px; border-radius: 6px; border: 1px solid rgba(240,136,62,0.35); }
.pipeline-header-resume { font-size: 11px; padding: 3px 9px; }
</style>
</head>
<body>
<div class="app">
  <!-- Sidebar -->
  <div class="sidebar">
    <div class="sidebar-brand">
      <h1>AIR Worker</h1>
      <span>대시보드</span>
    </div>
    <div class="nav">
      <div class="nav-item active" data-tab="overview" onclick="switchTab('overview')">
        <span class="icon">&#x1F4CA;</span> 대시보드
      </div>
      <div class="nav-item" data-tab="rendering" onclick="switchTab('rendering')">
        <span class="icon">&#x1F3AC;</span>
        <span>렌더링 상황</span>
        <span id="render-nav-badge" style="display:none;background:#ef4444;color:#ffffff;font-size:10px;font-weight:900;min-width:18px;height:18px;line-height:18px;border-radius:50%;text-align:center;padding:0 3px;margin-left:6px;box-shadow:0 0 6px rgba(239,68,68,0.8);">0</span>
      </div>
      <div class="nav-item" data-tab="topic-search" onclick="switchTab('topic-search')">
        <span class="icon">&#x1F50D;</span> 주제 찾기
      </div>
      <div class="nav-item" data-tab="yt-explore" onclick="switchTab('yt-explore')">
        <span class="icon">&#x1F30D;</span> YouTube 탐색
      </div>
      <div class="nav-item" data-tab="hermes-autopilot" onclick="switchTab('hermes-autopilot')">
        <span class="icon">&#x1F916;</span> Hermes 자동 생성
      </div>
      <div class="nav-item" data-tab="generated-results" onclick="switchTab('generated-results')">
        <span class="icon">&#x1F4D1;</span> 생성 결과 확인
      </div>
      <div class="nav-item" data-tab="voicebox-tts" onclick="switchTab('voicebox-tts')">
        <span class="icon">&#x1F399;</span> TTS 생성
      </div>
      <div class="nav-item" data-tab="hermes-gen" onclick="switchTab('hermes-gen')">
        <span class="icon">&#x1F4DD;</span> Hermes 제목 생성
      </div>
      <div class="nav-item" data-tab="notebooklm" onclick="switchTab('notebooklm')">
        <span class="icon">&#x2728;</span> NotebookLM 대본
      </div>
      <div class="nav-item" data-tab="styles" onclick="switchTab('styles')">
        <span class="icon">&#x1F3A8;</span> 스타일 관리
      </div>
      <div class="nav-item" data-tab="category-image-styles" onclick="switchTab('category-image-styles')">
        <span class="icon">&#x1F5BC;</span> 카테고리 이미지 스타일
      </div>
      <div class="nav-item" data-tab="history" onclick="switchTab('history')">
        <span class="icon">&#x1F4CB;</span> 작업 히스토리
      </div>
      <div class="nav-item" data-tab="logs" onclick="switchTab('logs')">
        <span class="icon">&#x1F4C4;</span> 로그
      </div>
      <div class="nav-item" data-tab="settings" onclick="switchTab('settings')">
        <span class="icon">&#x2699;</span> 설정
      </div>
      <div style="margin: 14px 10px 0; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.08); display: flex; flex-direction: column; gap: 6px;">
        <button class="btn btn-sm" onclick="confirmRestartServer()" style="width: 100%; font-size: 11px; background: rgba(56, 139, 253, 0.15); border: 1px solid rgba(56, 139, 253, 0.4); color: #58a6ff; font-weight: bold; padding: 7px 8px; border-radius: 6px; display: flex; align-items: center; justify-content: center; gap: 6px; cursor: pointer;">
          <span>🔄</span> 서버 완전 재시작
        </button>
        <button class="btn btn-sm" onclick="confirmShutdownServer()" style="width: 100%; font-size: 11px; background: rgba(248, 81, 73, 0.1); border: 1px solid rgba(248, 81, 73, 0.3); color: #f85149; padding: 5px 8px; border-radius: 6px; display: flex; align-items: center; justify-content: center; gap: 6px; cursor: pointer;">
          <span>🛑</span> 서버 완전 종료
        </button>
      </div>
    </div>
  </div>

  <!-- Main content -->
  <div class="main">
    <div class="topbar">
      <div style="display:flex;align-items:center;gap:12px">
        <h2 id="page-title">대시보드</h2>
        <span id="manager-offline-badge" style="display:none;background:#da363322;border:1px solid #da363366;color:#f85149;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;letter-spacing:0.3px" title="heartbeat 없음 — Manager 프로세스가 실행 중이 아닙니다">
          &#x26A0; Manager 오프라인
        </span>
      </div>
      <div class="topbar-actions">
        <span class="refresh-indicator" id="refresh-timer"></span>
        <button class="btn btn-sm" onclick="refreshAll()">&#x1F504; 새로고침</button>
        <button class="btn btn-sm" onclick="doLogout()">로그아웃</button>
      </div>
    </div>

    <div class="content">
      <!-- ═══ Tab: Overview ═══ -->
      <div class="tab-content active" id="tab-overview">
        <div class="status-grid" id="process-cards"></div>
        <div class="card">
          <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
            <span>🎬 최근 영상 제작 파이프라인 및 작업</span>
            <span class="info" style="font-size:11px;">동일 영상 5단계 사이클 자동 그룹화</span>
          </div>
          <div id="recent-jobs-container" class="pipeline-list"></div>
          <div class="empty" id="recent-empty" style="display:none"><div class="icon">&#x1F4ED;</div>아직 작업이 없습니다</div>
        </div>
      </div>

      <!-- ═══ Tab: Rendering ═══ -->
      <div class="tab-content" id="tab-rendering">
        <div class="card" id="render-active-card">
          <div class="card-title">현재 렌더 작업</div>
          <div id="render-active-content"></div>
        </div>
        <div class="card">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
            <div class="card-title" style="margin-bottom:0">렌더 작업 목록</div>
            <button class="btn btn-sm" onclick="loadRenderTab()">&#x1F504; 렌더 목록 새로고침</button>
          </div>
          <table>
            <thead><tr><th>출처</th><th>ID / 프로젝트</th><th>상태</th><th>진행률</th><th>메시지 / 작업자</th><th>접수/시작</th><th>결과</th></tr></thead>
            <tbody id="render-jobs-body"></tbody>
          </table>
          <div class="empty" id="render-empty" style="display:none"><div class="icon">&#x1F3AC;</div>렌더 작업이 없습니다</div>
        </div>
      </div>

      <!-- ═══ Tab: Topic Search ═══ -->
      <div class="tab-content" id="tab-topic-search">
        <div class="card">
          <div class="card-title">&#x1F50D; 주제 찾기</div>
          <p class="info" style="margin:-4px 0 16px">관심 키워드와 시청자 반응을 살펴볼 콘텐츠 주제를 찾습니다.</p>
          <div class="form-row">
            <div class="form-group">
              <label>키워드 *</label>
              <input type="text" id="tr-keyword" placeholder="예: 인공지능">
            </div>
            <div class="form-group">
              <label>언어</label>
              <select id="tr-language">
                <option value="ko">한국어</option>
                <option value="en">영어</option>
                <option value="ja">日本語</option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>국가/시장</label>
              <input type="text" id="tr-country" placeholder="예: KR, US (비워두면 전체 시장)" value="">
            </div>
            <div class="form-group">
              <label>주제 개수</label>
              <input type="number" id="tr-count" min="1" max="30" value="10">
            </div>
          </div>
          <button class="btn btn-primary" onclick="submitTopicResearch()">주제 찾기</button>
        </div>

        <div class="card" style="margin-top:16px">
          <div class="card-title">&#x1F4C8; 고성과 영상 분석</div>
          <p class="info" style="margin:-4px 0 16px">YouTube에서 잘 된 영상의 제목, 구성, 반응을 분석해 기획에 활용합니다.</p>
          <div class="form-row">
            <div class="form-group">
              <label>키워드 *</label>
              <input type="text" id="ba-keyword" placeholder="예: 인공지능">
            </div>
            <div class="form-group">
              <label>비디오 타입</label>
              <select id="ba-video-type">
                <option value="longform">롱폼</option>
                <option value="shorts">쇼츠</option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>언어</label>
              <select id="ba-language">
                <option value="ko">한국어</option>
                <option value="en">영어</option>
                <option value="ja">日本語</option>
              </select>
            </div>
            <div class="form-group">
              <label>분석 대상 수</label>
              <input type="number" id="ba-max-candidates" min="1" max="3" value="1">
            </div>
          </div>
          <button class="btn btn-primary" onclick="submitBenchmark()">벤치마크 분석</button>
        </div>
      </div>

      <!-- ═══ Tab: Hermes Generation ═══ -->
      <div class="tab-content" id="tab-hermes-gen">
        <div class="card">
          <div class="card-title">&#x1F4DD; 대본 기획 생성</div>
          <p class="info" style="margin:-4px 0 16px">제목에서 출발해 첫 훅, 장면별 전개, 결말까지의 설계를 만듭니다.</p>
          <div class="form-group">
            <label>주제 *</label>
            <input type="text" id="sp-topic" placeholder="예: 인공지능의 미래">
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>대상 길이 (초)</label>
              <input type="number" id="sp-duration" min="15" value="600">
            </div>
            <div class="form-group">
              <label>대본 스타일</label>
              <select id="sp-style"><option value="default">기본</option></select>
            </div>
          </div>
          <div class="form-group">
            <label>언어</label>
            <select id="sp-language">
              <option value="ko">한국어</option>
              <option value="en">영어</option>
              <option value="ja">日本語</option>
            </select>
          </div>
          <button class="btn btn-primary" onclick="submitScriptPlan()">구조 생성</button>
        </div>

        <div class="card" style="margin-top:16px">
          <div class="card-title">&#x1F4AC; 대본 생성</div>
          <p class="info" style="margin:-4px 0 16px">기획을 바탕으로 대본을 작성한 뒤, 흐름과 몰입도를 검수합니다.</p>
          <div class="form-group">
            <label>주제 *</label>
            <input type="text" id="sg-topic" placeholder="예: 인공지능의 미래">
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>대상 길이 (초)</label>
              <input type="number" id="sg-duration" min="15" value="600">
            </div>
            <div class="form-group">
              <label>나레이션 모드</label>
              <select id="sg-narration-mode">
                <option value="single">1인 (단일)</option>
                <option value="dramatic_single" selected>극적 1인 (중간)</option>
                <option value="multi">다인 (멀티)</option>
              </select>
            </div>
          </div>
          <div class="form-group">
            <label>대본 스타일</label>
            <select id="sg-style"><option value="default">기본</option></select>
          </div>
          <div class="form-group">
            <label>장면 구성 (비워두면 주제로 자동 기획)</label>
            <textarea id="sg-structure" rows="4" placeholder='{"scenes": [{"scene_summary": "...", "scene_situation": "..."}]}'></textarea>
          </div>
          <button class="btn btn-primary" onclick="submitScriptGenerate()">대본 생성</button>
        </div>
      </div>

      <!-- ═══ Tab: NotebookLM Script Generation ═══ -->
      <div class="tab-content" id="tab-notebooklm">
        <div class="generated-result-layout">
          <div class="card">
            <div class="card-title">&#x2728; NotebookLM 대본 생성</div>
            <p class="info" style="margin:-4px 0 16px">자료 기반 심층 리서치와 1인/2인 대본 생성을 워커에서 실행합니다. 결과는 워커 로컬 output/notebooklm_results에 저장됩니다.</p>
            <div class="form-row">
              <div class="form-group">
                <label>대본 모드</label>
                <select id="nlm-mode">
                  <option value="dialogue_podcast">2인 대화 팟캐스트</option>
                  <option value="narrator">1인 심층 내레이션</option>
                </select>
              </div>
              <div class="form-group">
                <label>카테고리</label>
                <select id="nlm-category">
                  <option value="탈북사연">탈북사연</option>
                  <option value="해외감동">해외감동</option>
                  <option value="노후금융">노후금융</option>
                  <option value="황혼19금">황혼19금</option>
                  <option value="옛날이야기" selected>옛날이야기</option>
                  <option value="한국사연">한국사연</option>
                  <option value="무협">무협</option>
                  <option value="경제">경제</option>
                </select>
              </div>
              <div class="form-group">
                <label>목표 분량(분)</label>
                <input type="number" id="nlm-duration" min="5" max="60" value="15">
              </div>
            </div>
            <div class="form-group">
              <label>선택 제목</label>
              <input type="text" id="nlm-title" placeholder="비워두면 AI가 제목을 생성합니다">
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>참고 URL (여러 줄 입력)</label>
                <textarea id="nlm-urls" rows="4" placeholder="https://example.com/article-1&#10;https://example.com/report-2"></textarea>
              </div>
              <div class="form-group">
                <label>로컬 파일 경로 (여러 줄 입력)</label>
                <textarea id="nlm-paths" rows="4" placeholder="C:\\Users\\kimse\\Documents\\reference.pdf&#10;C:\\Users\\kimse\\Documents\\notes.docx"></textarea>
              </div>
            </div>
            <div class="form-group">
              <label>파일 업로드 (PDF/DOCX/TXT/HTML/MD)</label>
              <input type="file" id="nlm-files" multiple accept=".pdf,.docx,.docm,.txt,.md,.html,.htm,.csv,.json,.rtf,.srt,.vtt" onchange="handleNotebookLMFiles(this.files)">
              <div class="info" id="nlm-file-status" style="margin-top:6px">선택한 파일은 워커가 텍스트로 추출해 참고자료에 합칩니다.</div>
            </div>
            <div class="form-group">
              <label>직접 붙여넣기</label>
              <textarea id="nlm-source" rows="8" placeholder="뉴스 기사, 리포트, 인터뷰, PDF 텍스트, 메모 등을 붙여넣으세요. URL/파일/경로만 사용해도 됩니다."></textarea>
            </div>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
              <button class="btn btn-primary" id="nlm-submit" onclick="submitNotebookLM()">NotebookLM 대본 생성</button>
              <button class="btn btn-primary" id="nlm-send-hermes" onclick="sendNotebookLMToHermes()" disabled>Hermes 패키지로 보내기</button>
              <span class="info" id="nlm-send-hermes-hint">NotebookLM 대본 생성 후 활성화됩니다.</span>
            </div>
          </div>
          <div class="card">
            <div class="card-title">&#x1F4DC; 생성 결과</div>
            <div id="nlm-result" class="generated-result-detail">
              <div class="empty" style="padding:24px"><div class="icon">&#x1F4CC;</div>왼쪽에서 자료를 입력하고 워커로 생성하세요</div>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ Tab: History ═══ -->
      <div class="tab-content" id="tab-generated-results">
        <div class="generated-result-layout">
          <div class="card">
            <div class="card-title">&#x1F4D1; 생성 결과 목록</div>
            <p class="info" style="margin:-4px 0 16px">Hermes 자동 생성이 저장한 제목, 기획, 대본, 이미지 프롬프트, 영상 프롬프트를 확인합니다.</p>
            <div style="display:flex;gap:8px;margin-bottom:12px">
              <button class="btn btn-sm" onclick="loadGeneratedResults()">&#x1F504; 새로고침</button>
              <span class="info" id="generated-results-dir"></span>
            </div>
            <div id="generated-results-tables">
              <div class="generated-results-section">
                <div class="generated-results-heading">
                  <span>100% 완료 결과</span>
                  <span class="info" id="generated-results-completed-count">0건</span>
                </div>
                <table>
                  <thead><tr><th>ID</th><th>카테고리</th><th>제목</th><th>구성</th><th>생성일</th></tr></thead>
                  <tbody id="generated-results-completed-body"></tbody>
                </table>
              </div>
              <div class="generated-results-section">
                <div class="generated-results-heading">
                  <span>부분완료 결과</span>
                  <span class="info" id="generated-results-partial-count">0건 · 완료율 높은 순</span>
                </div>
                <table>
                  <thead><tr><th>ID</th><th>카테고리</th><th>제목</th><th>구성</th><th>생성일</th></tr></thead>
                  <tbody id="generated-results-partial-body"></tbody>
                </table>
              </div>
            </div>
            <div class="empty" id="generated-results-empty" style="display:none"><div class="icon">&#x1F4ED;</div>저장된 생성 결과가 없습니다</div>
          </div>
          <div class="card">
            <div class="card-title">&#x1F50E; 상세 확인</div>
            <div id="generated-result-detail" class="generated-result-detail">
              <div class="empty" style="padding:24px"><div class="icon">&#x1F4CC;</div>왼쪽 목록에서 결과를 선택하세요</div>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ Tab: Voicebox TTS Generation ═══ -->
      <div class="tab-content" id="tab-voicebox-tts">
        <div style="display:grid;grid-template-columns:320px 1fr 340px;gap:16px;height:calc(100vh - 120px);">
          
          <!-- 좌측: 주제 및 대본 목록 -->
          <div class="card" style="display:flex;flex-direction:column;overflow:hidden;padding:16px;">
            <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
              <span>&#x1F4DA; 대본 주제 선택</span>
              <button class="btn btn-sm" onclick="loadVoiceboxTopics()">&#x1F504; 새로고침</button>
            </div>
            <p class="info" style="font-size:11px;margin:4px 0 10px;">전체 대본이 포함된 주제를 선택하세요.</p>
            <div style="flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:8px;" id="voicebox-topics-list">
              <div class="info">주제 대본 목록을 불러오는 중...</div>
            </div>
          </div>

          <!-- 중앙: 전체 대본 텍스트 에디터/뷰어 -->
          <div class="card" style="display:flex;flex-direction:column;overflow:hidden;padding:16px;">
            <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
              <span id="voicebox-script-title">&#x1F4DC; 전체 대본 내용</span>
              <span id="voicebox-script-meta" class="badge" style="background:#238636;color:#fff;font-size:11px;">0자 대본</span>
            </div>
            <p class="info" style="font-size:11px;margin:4px 0 8px;">대본을 수정하거나 확인 후 우측에서 Voicebox TTS 생성을 진행할 수 있습니다.</p>
            <textarea id="voicebox-script-editor" style="flex:1;width:100%;background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:12px;color:#c9d1d9;font-size:13px;line-height:1.6;resize:none;outline:none;" placeholder="주제를 선택하면 전체 대본이 이곳에 자동으로 로딩됩니다..."></textarea>
          </div>

          <!-- 우측: Google 무료 TTS & Voicebox 설정, 생성, 오디오 미리듣기 및 Supabase 연동 -->
          <div class="card" style="display:flex;flex-direction:column;gap:14px;padding:16px;overflow-y:auto;">
            <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
              <span>⚙️ 무료 TTS 엔진 & 생성</span>
              <span class="badge" style="background:rgba(56,139,253,0.15);border:1px solid rgba(56,139,253,0.4);color:#58a6ff;font-size:10px;">무제한 무료</span>
            </div>

            <!-- 1. TTS 엔진 선택 -->
            <div>
              <label style="font-size:12px;color:#8b949e;display:block;margin-bottom:6px;font-weight:600;">TTS 공급 엔진 선택</label>
              <select id="voicebox-provider-select" onchange="onTtsProviderChange()" style="width:100%;padding:8px 10px;background:#0d1117;border:1px solid #58a6ff;border-radius:6px;color:#fff;font-size:12px;font-weight:bold;outline:none;">
                <option value="google" selected>🌐 Google 무료 TTS (gTTS - 제한 없음)</option>
                <option value="voicebox">⚡ Voicebox 신경망 TTS (Edge Neural / 고품질)</option>
              </select>
            </div>

            <!-- 2. 성우/보이스 프리셋 -->
            <div>
              <label id="voicebox-preset-label" style="font-size:12px;color:#8b949e;display:block;margin-bottom:6px;font-weight:600;">음성 보이스 / 성우 선택</label>
              <select id="voicebox-preset-select" style="width:100%;padding:8px 10px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#fff;font-size:12px;outline:none;">
                <option value="google_kr_standard">Google 한국어 표준 (기본 여성)</option>
                <option value="google_kr_alt">Google 한국어 보조 (남성/또렷한 톤)</option>
              </select>
            </div>

            <div>
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                <label style="font-size:12px;color:#8b949e;font-weight:600;">말하기 속도</label>
                <span id="voicebox-speed-val" style="color:#58a6ff;font-family:monospace;font-size:12px;font-weight:bold;">1.0x</span>
              </div>
              <input type="range" id="voicebox-speed-range" min="0.8" max="1.3" step="0.05" value="1.0" oninput="document.getElementById('voicebox-speed-val').textContent = this.value + 'x'" style="width:100%;">
            </div>

            <!-- 엔진 안내 배너 -->
            <div id="voicebox-engine-info" style="padding:10px;background:rgba(56,139,253,0.1);border:1px solid rgba(56,139,253,0.3);border-radius:8px;">
              <div style="font-size:11px;color:#58a6ff;font-weight:bold;">🌐 Google 무료 TTS 모드</div>
              <div style="font-size:11px;color:#8b949e;margin-top:2px;">ElevenLabs 크레딧 소모 없이 구글 공식 합성 음성을 무제한으로 생성합니다.</div>
            </div>

            <button id="voicebox-gen-btn" class="btn btn-primary" onclick="generateVoiceboxTts()" style="padding:10px;font-weight:bold;font-size:13px;display:flex;align-items:center;justify-content:center;gap:6px;">
              <span>🌐</span> Google 무료 TTS로 생성
            </button>

            <!-- 실시간 생성된 오디오 완료 카드 -->
            <div id="voicebox-audio-result-card" style="display:none;padding:12px;background:#161b22;border:1px solid #238636;border-radius:8px;flex-direction:column;gap:8px;box-shadow:0 0 10px rgba(35,134,54,0.2);">
              <div style="font-size:12px;color:#7ee787;font-weight:bold;display:flex;align-items:center;gap:4px;">
                <span>🎉</span> 방금 생성 완료된 음성
              </div>
              <audio id="voicebox-audio-player" controls style="width:100%;height:32px;"></audio>
              <div style="display:flex;justify-content:space-between;font-size:11px;color:#8b949e;" id="voicebox-audio-meta">
                <span>파일 크기: -</span>
                <span>생성 시간: -</span>
              </div>
              <button id="voicebox-save-btn" class="btn" onclick="saveVoiceboxToSupabase()" style="background:#238636;color:#fff;border:none;padding:10px;font-weight:bold;font-size:13px;margin-top:4px;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:6px;border-radius:6px;box-shadow:0 2px 4px rgba(0,0,0,0.3);">
                <span>&#x2601;</span> Supabase에 저장 & 유저앱 연동 완료
              </button>

              <!-- 연동 대상 주제 및 카테고리 실시간 확인 박스 -->
              <div style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:10px;margin-top:6px;display:flex;flex-direction:column;gap:5px;">
                <div style="font-size:10px;color:#8b949e;font-weight:bold;display:flex;align-items:center;justify-content:space-between;">
                  <span>🎯 저장 및 자동 연동 대상</span>
                  <span id="voicebox-target-id" style="color:#58a6ff;font-family:monospace;background:rgba(56,139,253,0.1);padding:1px 5px;border-radius:3px;">ID: -</span>
                </div>
                <div style="font-size:11px;color:#7ee787;font-weight:bold;display:flex;align-items:center;gap:4px;">
                  <span style="background:rgba(46,160,67,0.15);border:1px solid rgba(46,160,67,0.3);padding:1px 6px;border-radius:4px;" id="voicebox-target-category">카테고리</span>
                </div>
                <div style="font-size:12px;color:#f0f6fc;font-weight:bold;line-height:1.4;word-break:break-all;" id="voicebox-target-title">
                  선택된 주제 제목이 표시됩니다.
                </div>
              </div>
            </div>

            <!-- 생성 이력 (히스토리) 리스트 -->
            <div style="border-top:1px solid #30363d;padding-top:14px;margin-top:6px;display:flex;flex-direction:column;gap:10px;">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="font-size:12px;font-weight:bold;color:#c9d1d9;display:flex;align-items:center;gap:4px;">
                  <span>📜</span> 음성 생성 이력 (<span id="voicebox-history-count" style="color:#58a6ff;">0</span>)
                </span>
                <button class="btn btn-sm" onclick="loadVoiceboxHistory()" style="font-size:10px;padding:2px 8px;">새로고침</button>
              </div>
              <div id="voicebox-history-list" style="display:flex;flex-direction:column;gap:8px;max-height:280px;overflow-y:auto;padding-right:2px;">
                <div class="info" style="font-size:11px;">생성 이력을 불러오는 중...</div>
              </div>
            </div>

          </div>

        </div>
      </div>

      <div class="tab-content" id="tab-history">
        <div class="card">
          <div class="card-title">필터</div>
          <div class="form-row">
            <div class="form-group">
              <label>상태</label>
              <select id="hist-filter-status" onchange="loadHistory()">
                <option value="">전체</option>
                <option value="QUEUED">대기 중</option>
                <option value="CLAIMED">작업 준비</option>
                <option value="PREPARING">준비 중</option>
                <option value="RENDERING">처리 중</option>
                <option value="UPLOADING">결과 저장 중</option>
                <option value="COMPLETED">완료</option>
                <option value="FAILED">실패</option>
                <option value="CANCELED">취소됨</option>
              </select>
            </div>
            <div class="form-group">
              <label>작업 유형</label>
              <select id="hist-filter-type" onchange="loadHistory()">
                <option value="">전체</option>
                <option value="render_video">영상 렌더링</option>
                <option value="topic_research">주제 탐색</option>
                <option value="topic_benchmark_analyze">고성과 영상 분석</option>
                <option value="web_research">Gemini 웹 자료 조사</option>
                <option value="script_plan_generate">대본 기획 생성</option>
                <option value="script_generate">대본 생성</option>
              </select>
            </div>
          </div>
        </div>
        <div class="card">
          <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
            <span>📋 작업 파이프라인 및 히스토리</span>
            <span class="info" style="font-size:11px;">영상 단위 통합 진행 상황</span>
          </div>
          <div id="history-jobs-container" class="pipeline-list"></div>
          <div class="empty" id="history-empty" style="display:none"><div class="icon">&#x1F4CB;</div>작업이 없습니다</div>
        </div>
      </div>

      <!-- ═══ Tab: Logs ═══ -->
      <div class="tab-content" id="tab-logs">
        <div class="card">
          <div class="form-row" style="align-items: end;">
            <div class="form-group">
              <label>프로세스</label>
              <select id="log-process" onchange="loadLogs()">
                <option value="manager">작업 관리자</option>
                <option value="render_worker">영상 작업 Worker</option>
                <option value="remote_drive_worker">Drive API Render Worker</option>
                <option value="hermes_worker">AI 기획·대본 Worker</option>
                <option value="local_api">앱 연결 API</option>
                <option value="dashboard">대시보드</option>
              </select>
            </div>
            <button class="btn" onclick="loadLogs()">로그 불러오기</button>
          </div>
        </div>
        <div class="card">
          <div class="card-title">로그 출력</div>
          <div class="log-viewer" id="log-output">로그를 불러오는 중...</div>
        </div>
      </div>

      <!-- ═══ Tab: Settings ═══ -->
      <div class="tab-content" id="tab-settings">
        <!-- ═══ Worker Profile & PC Settings Card ═══ -->
        <div class="card" style="margin-bottom:20px;border:1px solid #388bfd;background:rgba(56,139,253,0.04);">
          <div class="card-title" style="display:flex;align-items:center;justify-content:space-between;">
            <div style="display:flex;align-items:center;gap:8px;">
              <span>💻</span> 워커 실행 모드 및 PC 설정
            </div>
            <span id="worker-profile-badge" style="font-size:12px;padding:3px 10px;border-radius:12px;background:#238636;color:#fff;font-weight:bold;">현재 모드: -</span>
          </div>
          <p style="color:#8b949e;margin-bottom:16px;font-size:13px;line-height:1.5;">
            이 컴퓨터가 수행할 워커 역할(렌더링 전용 / 대본 기획 전용 / 전체 통합)과 컴퓨터 이름을 설정합니다.<br>
            저장 시 로컬 .env 파일에 자동으로 기록되어 재시작 후에도 안전하게 유지됩니다.
          </p>

          <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:16px;margin-bottom:16px;">
            <div class="form-group">
              <label style="font-weight:bold;color:#f0f6fc;margin-bottom:6px;display:block;">🔘 워커 동작 역할 (Profile) *</label>
              <select id="worker-set-profile" style="width:100%;padding:10px 12px;border:1px solid #30363d;border-radius:6px;background:#0d1117;color:#e1e4e8;font-size:13px;font-weight:600;outline:none;">
                <option value="render_only">🎬 렌더링 전용 (render_only) - 영상 조립 및 렌더링만 처리 (렌더 PC 권장)</option>
                <option value="content_only">📝 대본·기획 전용 (content_only) - YouTube 탐색 및 대본 생성만 처리 (기획 PC 권장)</option>
                <option value="full">🚀 전체 통합 모드 (full) - 대본 생성 + 영상 렌더링 모두 실행</option>
              </select>
            </div>

            <div class="form-group">
              <label style="font-weight:bold;color:#f0f6fc;margin-bottom:6px;display:block;">🏷️ 이 컴퓨터 워커 이름 (Worker ID) *</label>
              <input id="worker-set-id" type="text" placeholder="예: render-pc-01, worker-office-1" style="width:100%;padding:9px 12px;border:1px solid #30363d;border-radius:6px;background:#0d1117;color:#e1e4e8;font-size:13px;font-family:monospace;outline:none;" />
              <div style="font-size:11px;color:#8b949e;margin-top:4px;">여러 PC에서 분산 렌더링 시 컴퓨터를 구분하는 고유 이름입니다.</div>
            </div>
          </div>

          <div style="border-top:1px solid #21262d;padding-top:14px;margin-top:12px;display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:16px;">
            <div class="form-group">
              <label style="color:#c9d1d9;font-size:12px;margin-bottom:4px;display:block;">🌐 중앙 서버 연동 주소 (선택)</label>
              <input id="worker-set-server-url" type="text" placeholder="예: https://your-server.com (미입력 시 단독 로컬 동작)" style="width:100%;padding:8px 12px;border:1px solid #30363d;border-radius:6px;background:#0d1117;color:#e1e4e8;font-size:12px;font-family:monospace;outline:none;" />
            </div>
            <div class="form-group">
              <label style="color:#c9d1d9;font-size:12px;margin-bottom:4px;display:block;">🔑 워커 인증 토큰 (선택)</label>
              <input id="worker-set-token" type="password" placeholder="중앙 서버 발급 토큰" style="width:100%;padding:8px 12px;border:1px solid #30363d;border-radius:6px;background:#0d1117;color:#e1e4e8;font-size:12px;font-family:monospace;outline:none;" />
            </div>
          </div>

          <div style="margin-top:18px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
            <button class="btn btn-primary" onclick="saveWorkerProfileSettings(true)" style="background:#238636;border-color:#2ea043;font-weight:bold;padding:9px 18px;display:flex;align-items:center;gap:6px;cursor:pointer;">
              <span>💾</span> 워커 설정 저장 & 서버 즉시 재시작
            </button>
            <button class="btn" onclick="saveWorkerProfileSettings(false)" style="padding:9px 14px;cursor:pointer;">
              설정만 저장
            </button>
            <span id="worker-settings-status" style="font-size:13px;color:#8b949e"></span>
          </div>
        </div>

        <div class="card">
          <div class="card-title">&#x2699; Hermes / AI API 설정</div>
          <p style="color:#8b949e;margin-bottom:16px;font-size:13px;">
            웹 어드민에서 설정한 값도 사용되지만, 여기서 직접 입력하면 로컬 .env 파일에 저장되어 즉시 적용됩니다.
            빈칸으로 두면 웹 어드민 값이 우선 적용됩니다.
          </p>
          <div id="settings-list"></div>
          <div style="margin-top:20px;display:flex;gap:12px;align-items:center;">
            <button class="btn btn-primary" onclick="saveAllSettings()">모든 변경사항 저장</button>
            <button class="btn" onclick="loadSettings()">다시 불러오기</button>
            <span id="settings-status" style="font-size:13px;color:#8b949e"></span>
          </div>
        </div>

        <div class="card" style="margin-top:16px;border:1px solid rgba(255,255,255,0.1);background:rgba(22,27,34,0.6);">
          <div class="card-title" style="display:flex;align-items:center;gap:8px;">
            <span>⚡</span> 워커 서버 프로세스 제어
          </div>
          <p style="color:#8b949e;font-size:13px;margin-bottom:16px;line-height:1.5;">
            워커 서버 프로세스를 완전히 종료하거나, 수정된 환경변수(.env) 및 코드를 즉시 적용하기 위해 서버를 재시작합니다.
          </p>
          <div style="display:flex;gap:12px;flex-wrap:wrap;">
            <button class="btn btn-primary" onclick="confirmRestartServer()" style="background:#238636;border-color:#2ea043;font-weight:bold;padding:8px 16px;display:flex;align-items:center;gap:6px;cursor:pointer;">
              <span>🔄</span> 워커 서버 완전 재시작 (Restart)
            </button>
            <button class="btn" onclick="confirmShutdownServer()" style="background:rgba(248,81,73,0.15);border:1px solid rgba(248,81,73,0.4);color:#f85149;font-weight:bold;padding:8px 16px;display:flex;align-items:center;gap:6px;cursor:pointer;">
              <span>🛑</span> 워커 서버 완전 종료 (Shutdown)
            </button>
          </div>
        </div>
      </div>

      <!-- ═══ Tab: Style Presets ═══ -->
      <div class="tab-content" id="tab-styles">
        <div class="card">
          <div class="card-title">&#x1F3A8; 이미지·대본 스타일 프리셋</div>
          <p class="info" style="margin:-4px 0 16px">여기서 저장한 스타일은 중앙 저장소와 AI Worker에 즉시 함께 반영됩니다. 대본 스타일은 다음 대본 기획과 생성 프롬프트에 그대로 적용됩니다.</p>
          <input type="hidden" id="style-edit-key">
          <div class="form-row">
            <div class="form-group">
              <label>스타일 타입 *</label>
              <select id="style-preset-type" onchange="updateStyleFormHelp()">
                <option value="image">이미지 스타일</option>
                <option value="script">대본 스타일</option>
              </select>
            </div>
            <div class="form-group">
              <label>스타일 코드 *</label>
              <input id="style-key-code" type="text" placeholder="예: realistic 또는 historical_drama">
            </div>
            <div class="form-group">
              <label>한글 표시명 *</label>
              <input id="style-name-ko" type="text" placeholder="예: 실사 영화풍">
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>베트남어 표시명</label>
              <input id="style-name-vi" type="text" placeholder="선택 사항">
            </div>
            <div class="form-group">
              <label>프리뷰 이미지 URL</label>
              <input id="style-image-url" type="text" placeholder="https://... (선택 사항)">
            </div>
          </div>
          <div class="form-group">
            <label id="style-prompt-label">프롬프트 템플릿 *</label>
            <textarea id="style-prompt-template" rows="5" placeholder="스타일에 적용할 핵심 지시사항을 작성하세요."></textarea>
            <p class="info" id="style-prompt-help" style="margin-top:6px"></p>
          </div>
          <div class="form-group" id="style-image-instruction-group">
            <label>AI 추가 지시사항</label>
            <textarea id="style-gemini-instruction" rows="3" placeholder="예: 화면 안에 텍스트나 말풍선을 넣지 마세요."></textarea>
            <p class="info" style="margin-top:6px">이미지 프롬프트 생성 시 함께 적용되는 추가 제약입니다.</p>
          </div>
          <div style="display:flex;gap:8px;justify-content:flex-end">
            <button class="btn" id="style-cancel-btn" onclick="resetStyleForm()" style="display:none">수정 취소</button>
            <button class="btn btn-primary" id="style-save-btn" onclick="saveStylePreset()">스타일 저장</button>
          </div>
        </div>

        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px">
            <div class="card-title" style="margin:0">등록된 스타일</div>
            <div style="display:flex;gap:8px">
              <button class="btn btn-sm" data-style-filter="image" onclick="setStyleFilter('image')">이미지 스타일</button>
              <button class="btn btn-sm" data-style-filter="script" onclick="setStyleFilter('script')">대본 스타일</button>
              <button class="btn btn-sm" onclick="loadStylePresets()">새로고침</button>
            </div>
          </div>
          <div id="style-store-notice" class="info" style="margin-bottom:12px"></div>
          <div id="style-presets-list" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px"></div>
        </div>
      </div>

      <!-- ═══ Tab: Category Image Style Mapping ═══ -->
      <div class="tab-content" id="tab-category-image-styles">
        <div class="card">
          <div class="card-title">카테고리별 이미지 스타일 매칭</div>
          <p class="info" style="margin:-4px 0 16px">수동으로 선택한 스타일은 해당 카테고리의 자동 이미지 스타일 선택보다 우선합니다. 자동 선택으로 돌리면 제목과 주제에 맞춰 Worker가 선택합니다.</p>
          <table>
            <thead><tr><th>카테고리</th><th>자동 선택 기본값</th><th>수동 우선 스타일</th><th>저장</th></tr></thead>
            <tbody id="category-image-styles-body"></tbody>
          </table>
          <div class="empty" id="category-image-styles-empty" style="display:none">이미지 스타일 정보를 불러오지 못했습니다.</div>
        </div>
      </div>

      <!-- ═══ Tab: YouTube Explore ═══ -->
      <div class="tab-content" id="tab-yt-explore">
        <!-- 버블 차트 카드 -->
        <div class="card">
          <div class="card-title">&#x1F4C8; 트렌드 키워드 클라우드</div>
          <div class="yt-filter-row">
            <button class="btn btn-sm yt-lang-btn active" data-lang="ko">한국어</button>
            <button class="btn btn-sm yt-lang-btn" data-lang="en">English</button>
            <button class="btn btn-sm yt-lang-btn" data-lang="ja">日本語</button>
            <select id="yt-period">
              <option value="now">실시간</option>
              <option value="week">이번 주</option>
              <option value="month">이번 달</option>
            </select>
            <select id="yt-age">
              <option value="all">전체 연령</option>
              <option value="10s">10대</option>
              <option value="20s">20대</option>
              <option value="30s">30대</option>
              <option value="40s">40대 이상</option>
            </select>
            <button class="btn btn-sm btn-primary" onclick="loadTrendKeywords()">&#x1F504; 새로고침</button>
          </div>
          <div id="bubble-chart-container" style="height:420px;position:relative;">
            <div id="bubble-chart"></div>
            <div class="bubble-loading" id="bubble-loading" style="display:none">키워드 생성 중...</div>
          </div>
        </div>

        <!-- YouTube 검색 카드 -->
        <div class="card">
          <div class="card-title">&#x1F50D; YouTube 영상 검색</div>
          <div class="yt-search-row">
            <input type="text" id="yt-search-query" placeholder="검색어를 입력하세요..."
                   style="flex:1" onkeydown="if(event.key==='Enter')searchYtVideos()">
            <select id="yt-search-order">
              <option value="relevance">관련도</option>
              <option value="date">최신순</option>
              <option value="viewCount">조회수</option>
              <option value="rating">평점</option>
            </select>
            <select id="yt-search-period">
              <option value="">전체 기간</option>
              <option value="now">오늘</option>
              <option value="week">이번 주</option>
              <option value="month">이번 달</option>
            </select>
            <select id="yt-search-lang">
              <option value="">언어 없음</option>
              <option value="ko">한국어</option>
              <option value="en">English</option>
              <option value="ja">日本語</option>
            </select>
            <button class="btn btn-primary" onclick="searchYtVideos()">검색</button>
          </div>
          <div id="yt-suggested-tags" style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;"></div>
        </div>

        <!-- 검색 결과 카드 -->
        <div class="card" id="yt-results-card" style="display:none">
          <div class="card-title">검색 결과 (<span id="yt-result-count">0</span>개)</div>
          <div style="overflow-x:auto">
            <table>
              <thead>
                <tr>
                  <th style="width:40px"></th>
                  <th style="width:120px">썸네일</th>
                  <th>제목</th>
                  <th style="width:140px">채널</th>
                  <th style="width:100px">게시일</th>
                  <th style="width:70px">조회수</th>
                  <th style="width:80px">구독자</th>
                  <th style="width:70px">기여도</th>
                  <th style="width:60px">성과</th>
                  <th style="width:60px">좋아요</th>
                  <th style="width:60px">작업</th>
                </tr>
              </thead>
              <tbody id="yt-results-body"></tbody>
            </table>
          </div>
          <div id="yt-search-loading" style="display:none;padding:20px;text-align:center;color:#8b949e">검색 중...</div>
        </div>
      </div>

      <!-- ═══ Tab: Hermes Autopilot ═══ -->
      <div class="tab-content" id="tab-hermes-autopilot">
        <div class="card">
          <div class="card-title">&#x1F916; Hermes 자동 대본 생성기 (Autopilot)</div>
          <p style="color:#8b949e;margin-bottom:16px;font-size:13px;">
            설정된 8가지 카테고리(탈북사연, 해외감동, 노후금융, 황혼19금, 옛날이야기, 한국사연, 무협, 경제)에 대해 
            유튜브 탐색 및 고성과 영상 분석 → 신규 주제 발굴 → 구조 기획 → 대본 생성을 자동으로 진행합니다.<br>
            생성된 대본 결과는 로컬 및 중앙 Supabase 서버(topics_queue)에 즉시 저장됩니다.
          </p>
          <div style="display:flex;gap:12px;align-items:center;margin-bottom:20px;">
            <label style="display:flex;align-items:center;gap:8px;font-size:12px;color:#8b949e;white-space:nowrap;">
              생성 수
              <input type="number" id="auto-start-limit" value="1" min="1" max="100" style="width:72px;padding:8px;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.1);color:#fff;border-radius:6px;outline:none;" />
            </label>
            <button class="btn btn-primary" id="auto-btn-start" onclick="startAutopilot()">▶ 자동 생성 시작</button>
            <button class="btn btn-danger" id="auto-btn-stop" onclick="stopAutopilot()" disabled>■ 자동 생성 중지</button>
            <span id="auto-status-text" class="badge badge-stopped">중지됨</span>
          </div>
          <div class="status-card" style="margin-bottom:16px;border-color:rgba(240,136,62,0.35);">
            <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;">
              <div>
                <div class="name">오프라인 사전검증</div>
                <div class="info">API 호출 없이 8개 카테고리 공통 게이트를 먼저 검사합니다.</div>
              </div>
              <div style="display:flex;gap:8px;align-items:center;">
                <span id="auto-harness-badge" class="badge badge-starting">확인 전</span>
                <button class="btn btn-secondary btn-sm" type="button" onclick="runOfflineHarness()">검증 실행</button>
              </div>
            </div>
            <div id="auto-harness-summary" class="info" style="margin-top:10px;">자동 생성 시작 전 서버에서 다시 실행됩니다.</div>
            <div id="auto-harness-failures" style="display:none;margin-top:10px;color:#f0883e;font-size:12px;line-height:1.5;"></div>
          </div>
          
          <div class="status-grid" style="grid-template-columns: 1fr 1fr; gap:16px; margin-bottom:16px;">
            <div class="status-card">
              <div class="name">현재 상태</div>
              <table style="width:100%">
                <tr><th style="width:120px">동작 여부</th><td id="auto-info-running">-</td></tr>
                <tr><th>현재 단계</th><td id="auto-info-step">-</td></tr>
                <tr><th>진행 카테고리</th><td id="auto-info-category">-</td></tr>
                <tr><th>최근 생성 주제</th><td id="auto-info-topic">-</td></tr>
                <tr><th>선정 이미지 스타일</th><td id="auto-info-image-style">-</td></tr>
                <tr><th>세션 생성량</th><td id="auto-info-generated">0 개</td></tr>
              </table>
            </div>
            <div class="status-card">
              <div class="name" id="auto-active-category-title">설정된 카테고리 (8개)</div>
              <div id="auto-active-category-badges" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;"></div>
            </div>
          </div>
        </div>

        <!-- ⚙️ Autopilot Settings Panel -->
        <div class="card" style="margin-top:16px;">
          <div class="card-title">&#x2699;&#xFE0F; 오토파일럿 작업량 및 카테고리 세팅</div>
          <div class="status-grid" style="grid-template-columns: 1fr 1fr; gap:20px;">
            <div class="status-card" style="padding:16px;background:rgba(255,255,255,0.01);">
              <div class="name" style="margin-bottom:12px;">⏰ 작업 및 정지 규칙 설정</div>
              <div style="margin-bottom:12px;">
                <label style="display:block;font-size:12px;color:#8b949e;margin-bottom:6px;">작업 모드</label>
                <select id="auto-setting-mode" onchange="toggleLimitInput()" style="width:100%;padding:8px;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.1);color:#fff;border-radius:6px;outline:none;">
                  <option value="infinite">무제한 지속 생성 🟢</option>
                  <option value="target_limit">목표 개수 생성 후 자동 정지 🟡</option>
                </select>
              </div>
              <div id="auto-limit-group" style="margin-bottom:12px;display:none;">
                <label style="display:block;font-size:12px;color:#8b949e;margin-bottom:6px;">목표 총 생성량 (개)</label>
                <input type="number" id="auto-setting-limit" value="10" min="1" style="width:100%;padding:8px;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.1);color:#fff;border-radius:6px;outline:none;" />
              </div>
              <div style="margin-bottom:12px;">
                <label style="display:block;font-size:12px;color:#8b949e;margin-bottom:6px;">카테고리별 최소 대기 대본 유지량 (버퍼)</label>
                <input type="number" id="auto-setting-buffer" value="5" min="1" style="width:100%;padding:8px;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.1);color:#fff;border-radius:6px;outline:none;" />
                <p style="font-size:10px;color:#6e7681;margin-top:4px;line-height:1.4;">* 큐에 사전 대본이 이 수치 이상 존재 시 해당 카테고리는 건너뜁니다.</p>
              </div>
              <div style="border-top:1px solid rgba(255,255,255,0.08);padding-top:12px;margin-top:12px;">
                <label style="display:flex;align-items:center;gap:8px;font-size:12px;color:#c9d1d9;margin-bottom:10px;cursor:pointer;">
                  <input type="checkbox" id="auto-setting-channel-discovery-enabled" checked />
                  벤치마크 채널 풀 자동 업데이트
                </label>
                <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;">
                  <label style="display:block;font-size:11px;color:#8b949e;">
                    최소 채널
                    <input type="number" id="auto-setting-channel-min" value="8" min="1" max="30" style="width:100%;margin-top:5px;padding:7px;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.1);color:#fff;border-radius:6px;outline:none;" />
                  </label>
                  <label style="display:block;font-size:11px;color:#8b949e;">
                    갱신 주기(시간)
                    <input type="number" id="auto-setting-channel-interval" value="24" min="1" max="168" style="width:100%;margin-top:5px;padding:7px;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.1);color:#fff;border-radius:6px;outline:none;" />
                  </label>
                  <label style="display:block;font-size:11px;color:#8b949e;">
                    검색 호출/회
                    <input type="number" id="auto-setting-channel-search-calls" value="1" min="0" max="3" style="width:100%;margin-top:5px;padding:7px;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.1);color:#fff;border-radius:6px;outline:none;" />
                  </label>
                </div>
                <p style="font-size:10px;color:#6e7681;margin-top:6px;line-height:1.4;">* 검색 API는 채널 풀 갱신 때만 제한적으로 사용하고, 실제 벤치마크 후보 수집은 RSS로 진행합니다.</p>
              </div>
              <button class="btn btn-secondary" onclick="saveAutopilotSettings()" style="width:100%;margin-top:8px;">💾 설정값 저장</button>
            </div>
            
            <div class="status-card" style="padding:16px;background:rgba(255,255,255,0.01);">
              <div class="name" style="margin-bottom:12px;">🎛️ 생성할 카테고리 필터</div>
              <p style="font-size:11px;color:#8b949e;margin-bottom:8px;">체크한 카테고리만 자동 생성에 포함됩니다.</p>
              <div style="display:grid;grid-template-columns:1fr;gap:8px;" id="auto-categories-checkboxes">
                <!-- Javascript will render checkboxes -->
              </div>
            </div>
          </div>
          <div class="status-card" style="padding:16px;background:rgba(255,255,255,0.01);margin-top:16px;">
            <div class="name" style="margin-bottom:8px;">📺 카테고리별 벤치마크 채널 ID</div>
            <p style="font-size:11px;color:#8b949e;margin-bottom:12px;line-height:1.5;">
              워커가 제한된 검색으로 좋은 채널을 발견해 자동 저장합니다. 필요하면 직접 보강하거나 제거할 수 있고, 여러 개는 줄바꿈, 쉼표, 공백으로 구분하세요.
            </p>
            <div id="auto-benchmark-channel-settings" style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;">
              <!-- Javascript will render channel ID textareas -->
            </div>
          </div>
        </div>
        
        <div class="card">
          <div class="card-title">자동 생성 로그</div>
          <div class="log-viewer" id="auto-logs" style="height: 350px;">자동 생성기 로그가 여기에 표시됩니다...</div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Job Detail Modal -->
<div class="modal-overlay" id="job-modal">
  <div class="modal">
    <span class="close" onclick="closeModal()">&times;</span>
    <h3 id="modal-title">작업 상세</h3>
    <div id="modal-body"></div>
  </div>
</div>

<!-- Toast Container -->
<div class="toast-container" id="toast-container"></div>

<script>
/* ── Globals ── */
let refreshInterval = null;
let countdown = 3;

/* ── API helpers ── */
async function api(method, path, body) {
  const opts = { method, headers: {'Content-Type': 'application/json'} };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  if (res.status === 401) { window.location.href = '/login'; return null; }
  return res.json();
}

function showToast(msg, type='success') {
  const c = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = msg;
  c.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

/* ── Tab switching ── */
const tabTitles = {
  'generated-results': '생성 결과 확인',
  'voicebox-tts': 'Voicebox TTS 음성 생성',
  'overview': '대시보드',
  'rendering': '렌더링 상황',
  'topic-search': '주제 찾기',
  'yt-explore': 'YouTube 탐색',
  'hermes-autopilot': 'Hermes 자동 생성',
  'hermes-gen': 'Hermes 제목 생성',
  'notebooklm': 'NotebookLM 대본 생성',
  'styles': '스타일 관리',
  'category-image-styles': '카테고리 이미지 스타일',
  'history': '작업 히스토리',
  'logs': '로그',
  'settings': '설정',
};

function switchTab(tabId) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + tabId).classList.add('active');
  document.querySelector(`.nav-item[data-tab="${tabId}"]`).classList.add('active');
  document.getElementById('page-title').textContent = tabTitles[tabId] || tabId;
  if (tabId === 'history') loadHistory();
  if (tabId === 'logs') loadLogs();
  if (tabId === 'rendering') loadRenderTab();
  if (tabId === 'settings') loadSettings();
  if (tabId === 'styles') loadStylePresets();
  if (tabId === 'category-image-styles') loadCategoryImageStyles();
  if (tabId === 'yt-explore') initYtExplore();
  if (tabId === 'hermes-autopilot') loadAutopilotStatus();
  if (tabId === 'generated-results') loadGeneratedResults();
  if (tabId === 'voicebox-tts') loadVoiceboxTtsTab();
}

/* ── Time formatting ── */
function fmtTime(ts) {
  if (!ts) return '-';
  const d = (typeof ts === 'number' || (!isNaN(Number(ts)) && !String(ts).includes('-') && !String(ts).includes('T'))) ? new Date(Number(ts) * 1000) : new Date(ts);
  return isNaN(d.getTime()) ? String(ts) : d.toLocaleString('ko-KR');
}
function fmtShort(ts) {
  if (!ts) return '-';
  const d = (typeof ts === 'number' || (!isNaN(Number(ts)) && !String(ts).includes('-') && !String(ts).includes('T'))) ? new Date(Number(ts) * 1000) : new Date(ts);
  return isNaN(d.getTime()) ? String(ts) : d.toLocaleTimeString('ko-KR');
}

/* ── Status badge ── */
const STATUS_LABELS = {
  QUEUED: '대기 중', PENDING: '대기 중', pending: '대기 중', CLAIMED: '작업 준비', PREPARING: '준비 중',
  RENDERING: '렌더링 중', rendering: '렌더링 중', UPLOADING: '결과 저장 중', COMPLETED: '완료', completed: '완료',
  FAILED: '실패', failed: '실패', CANCELED: '취소됨', canceled: '취소됨', ABANDONED: '중단됨',
  running: '실행 중', idle: '대기 중', stopped: '중지됨',
  starting: '시작 중', disabled: '사용 안 함',
};
const JOB_TYPE_LABELS = {
  render_video: '영상 렌더링',
  topic_research: '주제 탐색',
  topic_benchmark_analyze: '고성과 영상 분석',
  web_research: 'Gemini 웹 자료 조사',
  script_plan_generate: '대본 기획 생성',
  script_generate: '대본 생성',
  publish_metadata_generate: '설명·태그 생성',
  hermes_autopilot_step: 'Hermes 진행 상태',
};
const JOB_TYPE_DESCRIPTIONS = {
  render_video: '대본과 미디어를 조합해 최종 영상을 만들고 있습니다.',
  topic_research: '키워드와 시청자 반응을 바탕으로 콘텐츠 주제를 찾고 있습니다.',
  topic_benchmark_analyze: 'YouTube 고성과 영상의 제목, 구성, 반응을 분석하고 있습니다.',
  web_research: 'Gemini가 기사·논문·공식 자료를 검색해 대본 근거와 출처를 정리하고 있습니다.',
  script_plan_generate: '제목을 바탕으로 훅, 전개, 결말을 포함한 대본 기획을 만들고 있습니다.',
  script_generate: '기획을 바탕으로 시청 흐름을 고려한 대본을 작성하고 검수하고 있습니다.',
  publish_metadata_generate: '완성된 대본을 바탕으로 유튜브 설명, 태그, 해시태그를 만들고 있습니다.',
  hermes_autopilot_step: 'Autopilot이 다음 작업을 준비하고 있습니다.',
};
function humanStatus(s) {
  return STATUS_LABELS[s] || STATUS_LABELS[String(s || '').toLowerCase()] || s || '-';
}
function humanJobType(type) {
  return JOB_TYPE_LABELS[type] || type || '-';
}
function jobCategory(job) {
  const payload = job?.payload || {};
  return String(
    payload.category ||
    payload.category_name ||
    (job?.job_type === 'topic_benchmark_analyze' ? payload.keyword : '') ||
    payload.topic ||
    ''
  ).trim();
}
function jobTitle(job) {
  const payload = job?.payload || {};
  return String(payload.upload_title || payload.generated_title || '').trim();
}
function jobDescription(job) {
  const type = job?.job_type;
  const category = jobCategory(job);
  const title = jobTitle(job);
  const context = [
    category ? `카테고리: ${category}` : '',
    title ? `제목: ${title}` : '',
  ].filter(Boolean).join(' · ');
  const descriptions = {
    render_video: '최종 영상 렌더링 및 결과 파일 저장',
    topic_research: '키워드·카테고리 관련 주제 자료 조사',
    topic_benchmark_analyze: '고성과 영상의 제목·구성·반응 분석',
    web_research: '제목과 카테고리에 필요한 웹 자료 조사',
    script_plan_generate: '씬 구조·오프닝·결말 및 이미지·영상 프롬프트 기획',
    script_generate: '제목 약속에 맞춘 대본 작성 및 품질 검수',
    publish_metadata_generate: '업로드용 설명·태그·해시태그 생성',
  };
  const task = descriptions[type] || JOB_TYPE_DESCRIPTIONS[type] || '작업 정보를 처리하는 중';
  return context ? `${context} · ${task}` : task;
}
function legacyJobDescription(job) {
  return JOB_TYPE_DESCRIPTIONS[job?.job_type] || '작업 정보를 처리하고 있습니다.';
}
function displayProgress(job) {
  if (String(job?.status || '').toUpperCase() === 'COMPLETED') return 100;
  const value = Number(job?.progress || 0);
  return Math.max(0, Math.min(100, value));
}
function statusBadge(s) {
  if (!s) return '<span class="badge badge-idle">-</span>';
  return `<span class="badge badge-${String(s).toLowerCase()}">${humanStatus(s)}</span>`;
}

function isActiveHermesStatus(status) {
  return ['RUNNING', 'RENDERING', 'PREPARING', 'CLAIMED', 'QUEUED', 'PENDING'].includes(String(status || '').toUpperCase());
}

function hermesReadyAfterCompletedPipeline(jobs = []) {
  const hasActiveHermesJob = jobs.some(job => isHermesGenerationJob(job) && isActiveHermesStatus(job.status));
  if (hasActiveHermesJob) return false;
  const latestPipeline = groupJobsIntoPipelines(jobs)
    .filter(item => item.isPipeline)
    .sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0))[0];
  return Boolean(
    latestPipeline
    && latestPipeline.overallStatus === 'COMPLETED'
    && Number(latestPipeline.overallProgress || 0) >= 100
  );
}

/* ── Process cards ── */
function renderProcessCards(status, jobs = []) {
  const el = document.getElementById('process-cards');
  const procs = status.processes || {};
  const allowedProcesses = new Set(status.allowed_processes || Object.keys(procs));
  const workerProfile = status.worker_profile || 'full';
  let html = '';
  for (const [name, info] of Object.entries(procs)) {
    const s = info.status || 'stopped';
    const label = {render_worker:'영상 작업 Worker', hermes_worker:'AI 기획·대본 Worker', local_api:'앱 연결 API', updater:'업데이트 도구'}[name] || name;
    const icon = {render_worker:'\u{1F3AC}', hermes_worker:'\u{1F4E6}', local_api:'\u{1F310}', updater:'\u{1F504}'}[name] || '\u{1F4BB}';
    const progress = Math.max(0, Math.min(100, Number(info.progress || 0)));
    const currentJobId = typeof info.current_job === 'string'
      ? info.current_job
      : (info.current_job?.job_id || info.current_job?.id || '');
    const activeJob = jobs.find(job => job.job_id === currentJobId);
    const currentJob = activeJob
      ? `${humanJobType(activeJob.job_type)} - ${escapeHtml(jobDescription(activeJob))}`
      : (currentJobId ? `작업 처리 중 (${truncate(currentJobId, 8)})` : '진행 중인 작업 없음');
    const jobInfo = info.current_job && typeof info.current_job === 'object' ? info.current_job : null;
    const currentJobDetails = jobInfo && (jobInfo.project_name || jobInfo.asset_file_name || jobInfo.progress_message)
      ? `<div class="info" style="margin-top:6px;padding:8px 10px;border:1px solid rgba(88,166,255,.22);border-radius:6px;background:rgba(13,17,23,.55)">
          ${jobInfo.project_name ? `<div><span style="color:#8b949e">프로젝트:</span> ${escapeHtml(jobInfo.project_name)}</div>` : ''}
          ${jobInfo.asset_file_name ? `<div><span style="color:#8b949e">파일:</span> ${escapeHtml(jobInfo.asset_file_name)}</div>` : ''}
          ${jobInfo.progress_message ? `<div><span style="color:#8b949e">진행:</span> ${escapeHtml(jobInfo.progress_message)}</div>` : ''}
        </div>`
      : '';
    const workerDescription = {
      render_worker: '영상 조립, 렌더링, 결과 파일 저장을 담당합니다.',
      hermes_worker: '',
      local_api: 'AIR Studio 앱과 Worker 사이의 요청을 연결합니다.',
      updater: 'Worker 업데이트를 확인하고 적용합니다.',
    }[name] || '';
    const hasError = info.last_error && info.last_error.length > 0;
    const isRecentError = hasError && (!info.last_success_at || info.last_success_at < (Date.now()/1000 - 300));
    const normalizedStatus = String(s || '').toLowerCase();
    const disabledByProfile = !allowedProcesses.has(name) || normalizedStatus === 'disabled';
    const disabledReason = info.disabled_reason || `disabled by AIRWORKER_PROFILE=${workerProfile}`;
    const autoStart = !disabledByProfile && (name === 'render_worker' || name === 'local_api');
    const displayLabel = name === 'remote_drive_worker' ? 'Drive API Render Worker' : label;
    const displayIcon = name === 'remote_drive_worker' ? '☁️' : icon;
    const hermesPipelineDone = name === 'hermes_worker' && hermesReadyAfterCompletedPipeline(jobs);
    const processBusyStatuses = ['running', 'starting', 'busy', 'claimed', 'preparing', 'rendering', 'uploading'];
    const hasCurrentJob = Boolean(info.current_job || currentJobId);
    const hermesBusy = name === 'hermes_worker' && (processBusyStatuses.includes(normalizedStatus) || hasCurrentJob);
    const hermesStartDisabled = disabledByProfile || hermesBusy;
    const hermesStopDisabled = disabledByProfile || !hermesBusy || normalizedStatus === 'stopped';

    html += `<div class="status-card">
      <div class="name">${displayIcon} ${displayLabel} ${statusBadge(s)}</div>
      <div class="info">${currentJob}</div>
      ${workerDescription ? `<div class="info" style="margin-top:4px">${workerDescription}</div>` : ''}
      <div class="info" style="margin-top:4px">프로세스 번호: ${info.pid || '-'}</div>
      ${disabledByProfile ? `<div class="info" style="color:#f0ad4e;margin-top:6px;font-size:12px">프로파일 비활성화: ${escapeHtml(disabledReason)}</div>` : ''}
      ${progress > 0 ? `<div class="progress-bar"><div class="progress-fill" style="width:${progress}%"></div></div>` : ''}
      
      ${autoStart ? `<div class="info" style="color:#8b949e;margin-top:6px;font-size:12px">\u2705 프로그램 시작 시 자동 실행</div>` : name === 'hermes_worker' ? `
      <div style="display:flex;gap:8px;margin-top:8px;align-items:center">
        <input id="hermes-start-limit" type="number" value="1" min="1" max="100" aria-label="생성할 영상 수" title="생성할 영상 수" style="width:64px;padding:6px 8px;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.16);color:#fff;border-radius:6px;outline:none" />
        <button class="btn btn-sm btn-start" onclick="startHermesForLimit()" ${hermesStartDisabled ? 'disabled' : ''}>\u25B6 시작</button>
        <button class="btn btn-sm btn-stop" onclick="stopHermesGeneration()" ${hermesStopDisabled ? 'disabled' : ''}>\u23F9 중지</button>
      </div>
      ` : `
      <div style="display:flex;gap:8px;margin-top:8px">
        <button class="btn btn-sm btn-start" onclick="startProcess('${name}')" ${(s==='running'||s==='idle') ? 'disabled' : ''}>\u25B6 시작</button>
        <button class="btn btn-sm btn-stop" onclick="stopProcess('${name}')" ${s==='stopped' ? 'disabled' : ''}>\u23F9 중지</button>
      </div>`}
      ${currentJobDetails}
    </div>`;
  }
  const offlineBadge = document.getElementById('manager-offline-badge');
  if (offlineBadge) {
    offlineBadge.style.display = (status.manager_alive === false) ? 'inline-block' : 'none';
  }
  el.innerHTML = html;
}

/* ── Recent jobs ── */
function isHermesGenerationJob(job) {
  return job?.source === 'autopilot' || [
    'topic_benchmark_analyze',
    'topic_research',
    'web_research',
    'script_plan_generate',
    'script_generate',
    'publish_metadata_generate',
  ].includes(job?.job_type);
}

async function restartHermesFromCancelled(jobId, buttonEl) {
  const btn = buttonEl || null;
  const originalText = btn ? btn.textContent : '';
  if (!jobId) {
    showToast('이어하기 실패: 작업 ID가 없습니다.', 'error');
    return;
  }
  if (btn) {
    btn.disabled = true;
    btn.textContent = '요청 중...';
  }
  showToast(`이어하기 요청 중: ${String(jobId).substring(0, 8)}`, 'info');
  try {
    const result = await api('POST', `/api/hermes/pipelines/${jobId}/resume`);
    if (!result || result.success === false) {
      showToast(`재시작 실패: ${result?.error || '응답 없음'}`, 'error');
      return;
    }
    const nextJob = result.job_id ? ` 새 작업: ${String(result.job_id).substring(0, 8)}` : '';
    const nextStage = result.resumed_stage ? ` (${result.resumed_stage})` : '';
    showToast(`이어하기 시작됨.${nextJob}${nextStage}`, 'success');
    setTimeout(refreshAll, 800);
  } catch (e) {
    showToast(`재시작 실패: ${e}`, 'error');
  } finally {
    if (btn) {
      setTimeout(() => {
        btn.disabled = false;
        btn.textContent = originalText || '이어하기';
      }, 1200);
    }
  }
}

/* ── Pipeline Grouping & Rendering ── */
/* ── Pipeline Grouping & Rendering ── */
const PIPELINE_STEPS_CONFIG = [
  { key: 'research', type: 'web_research', label: '1. 웹 자료조사', icon: '🔍' },
  { key: 'plan', type: 'script_plan_generate', label: '2. 씬/비주얼 기획', icon: '📝' },
  { key: 'script', type: 'script_generate', label: '3. 대본·프롬프트', icon: '✍️' },
  { key: 'metadata', type: 'publish_metadata_generate', label: '4. 설명·태그', icon: '🏷️' },
];

const openPipelineDetails = new Set();

function stableHash(input) {
  let hash = 0;
  const text = String(input || '');
  for (let i = 0; i < text.length; i += 1) {
    hash = ((hash << 5) - hash) + text.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash).toString(36);
}

function pipelineTitleKey(category, title) {
  return `${String(category || '').trim().toLowerCase()}:::${String(title || '').trim().toLowerCase()}`;
}

function pipelineTitleOnlyKey(title) {
  return String(title || '').trim().toLowerCase();
}

function latestFailedJob(jobs, completedTypes = new Set()) {
  return [...(jobs || [])]
    .filter(j => {
      const type = String(j.job_type || '');
      if (completedTypes.has(type)) return false;
      return String(j.status || '').toUpperCase() === 'FAILED' || j.error_message;
    })
    .sort((a, b) => (b.completed_at || b.created_at || 0) - (a.completed_at || a.created_at || 0))[0] || null;
}

function hasCompletedHermesJobType(jobs, jobType) {
  return (jobs || []).some(j => {
    const type = String(j.job_type || '');
    const status = String(j.status || '').toUpperCase();
    return type === jobType && status === 'COMPLETED';
  });
}

function groupJobsIntoPipelines(jobs) {
  const pipelineMap = new Map();
  const benchmarkBatches = new Map();
  const otherJobs = [];

  // Pass 1: Build queueId -> title map so jobs with queueId can find their video title
  const queueIdToTitle = new Map();
  const titleToQueueId = new Map();
  const titleOnlyToQueueId = new Map();
  for (const job of jobs) {
    const payload = job.payload || {};
    const title = (payload.upload_title || payload.generated_title || payload.topic || '').trim();
    const category = jobCategory(job) || '?쇰컲';
    const qId = payload.topic_queue_id || payload.topic_id;
    if (qId && title) {
      queueIdToTitle.set(String(qId), title);
      titleToQueueId.set(pipelineTitleKey(category, title), String(qId));
      titleOnlyToQueueId.set(pipelineTitleOnlyKey(title), String(qId));
    }
  }

  for (const job of jobs) {
    const payload = job.payload || {};
    let title = (payload.upload_title || payload.generated_title || payload.topic || '').trim();
    const category = jobCategory(job) || '일반';
    let queueId = payload.topic_queue_id || payload.topic_id || '';
    
    // If title was missing on this job, try looking up from queueId
    if (!title && queueId && queueIdToTitle.has(String(queueId))) {
      title = queueIdToTitle.get(String(queueId));
    }
    if (!queueId && title) {
      queueId = titleToQueueId.get(pipelineTitleKey(category, title)) || titleOnlyToQueueId.get(pipelineTitleOnlyKey(title)) || '';
    }

    if (job.job_type === 'topic_benchmark_analyze' && !title) {
      // Standalone benchmark exploration job - group into benchmark batch
      const batchKey = `benchmark:::${category}`;
      if (!benchmarkBatches.has(batchKey)) {
        benchmarkBatches.set(batchKey, {
          id: 'bench_' + stableHash(batchKey),
          isBenchmarkBatch: true,
          category: category,
          title: `📊 고성과 벤치마크 & 주제 탐색`,
          jobs: [],
          created_at: job.created_at,
          updated_at: job.created_at,
        });
      }
      const batch = benchmarkBatches.get(batchKey);
      batch.jobs.push(job);
      if (job.created_at > batch.updated_at) batch.updated_at = job.created_at;
      if (job.created_at < batch.created_at) batch.created_at = job.created_at;
    } else if (title || queueId) {
      // Hermes Video Production Pipeline
      const groupKey = queueId
        ? `video_queue:::${String(queueId)}`
        : `video:::${category}:::${title}`;
      if (!pipelineMap.has(groupKey)) {
        pipelineMap.set(groupKey, {
          id: 'pipe_' + stableHash(groupKey),
          isPipeline: true,
          category: category,
          title: title || `Topic #${queueId}`,
          queueId: queueId,
          jobs: [],
          created_at: job.created_at,
          updated_at: job.created_at,
        });
      }
      const group = pipelineMap.get(groupKey);
      if (title && (!group.title || group.title.startsWith('Topic #'))) group.title = title;
      group.jobs.push(job);
      if (job.created_at > group.updated_at) group.updated_at = job.created_at;
      if (job.created_at < group.created_at) group.created_at = job.created_at;
    } else {
      otherJobs.push(job);
    }
  }

  // Process Video Pipelines
  const pipelineGroups = Array.from(pipelineMap.values()).map(g => {
    g.jobs.sort((a, b) => (a.created_at || 0) - (b.created_at || 0));

    const stepStatuses = {};
    const completedWebResearch = hasCompletedHermesJobType(g.jobs, 'web_research');
    const completedPlan = hasCompletedHermesJobType(g.jobs, 'script_plan_generate');
    const completedScript = hasCompletedHermesJobType(g.jobs, 'script_generate');
    const completedPublishMetadata = hasCompletedHermesJobType(g.jobs, 'publish_metadata_generate');
    const completedGenerationAfterBenchmark = completedWebResearch || completedPlan || completedScript || completedPublishMetadata;
    for (const step of PIPELINE_STEPS_CONFIG) {
      const matchingJob = [...g.jobs].reverse().find(j => j.job_type === step.type);
      if (matchingJob) {
        let status = String(matchingJob.status || '').toUpperCase();
        if (['RUNNING', 'RENDERING', 'PREPARING', 'CLAIMED'].includes(status)) {
          const priorCompletedJob = [...g.jobs].reverse().find(j => j.job_type === step.type && String(j.status || '').toUpperCase() === 'COMPLETED');
          if (priorCompletedJob) {
            status = 'COMPLETED';
          }
        }
        stepStatuses[step.key] = {
          status,
          job: matchingJob,
        };
      } else if (completedPublishMetadata) {
        stepStatuses[step.key] = {
          status: 'COMPLETED',
          job: null,
        };
      } else {
        stepStatuses[step.key] = {
          status: 'PENDING',
          job: null,
        };
      }
    }

    const totalSteps = PIPELINE_STEPS_CONFIG.length;
    const completedCount = PIPELINE_STEPS_CONFIG.filter(s => {
      return stepStatuses[s.key]?.status === 'COMPLETED';
    }).length;
    const completedTypes = new Set(
      g.jobs
        .filter(j => String(j.status || '').toUpperCase() === 'COMPLETED')
        .map(j => String(j.job_type || ''))
    );
    if (completedGenerationAfterBenchmark) {
      completedTypes.add('topic_benchmark_analyze');
    }
    const failedJob = latestFailedJob(g.jobs, completedTypes);
    const hasFailed = Boolean(failedJob);
    const hasCanceled = g.jobs.some(j => String(j.status || '').toUpperCase() === 'CANCELED');
    const hasRunning = g.jobs.some(j => ['RUNNING', 'RENDERING', 'PREPARING', 'CLAIMED'].includes(String(j.status || '').toUpperCase()));

    let overallStatus = 'PENDING';
    if (completedCount === totalSteps) overallStatus = 'COMPLETED';
    else if (hasRunning) overallStatus = 'RUNNING';
    else if (hasFailed) overallStatus = 'FAILED';
    else if (completedCount > 0 || hasCanceled) overallStatus = 'PAUSED';

    const overallProgress = Math.round((completedCount / totalSteps) * 100);
    const canResume = !hasRunning && completedCount > 0 && overallStatus !== 'COMPLETED';
    const lastError = failedJob?.error_message || '';

    return {
      isPipeline: true,
      id: g.id,
      category: g.category,
      title: g.title,
      queueId: g.queueId,
      overallStatus,
      overallProgress,
      completedCount,
      totalSteps,
      canResume,
      failedJob,
      lastError,
      stepStatuses,
      jobs: g.jobs,
      created_at: g.created_at,
      updated_at: g.updated_at,
    };
  });

  // Process Benchmark Batches
  const benchmarkGroups = Array.from(benchmarkBatches.values()).map(b => {
    b.jobs.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
    const completedCount = b.jobs.filter(j => String(j.status || '').toUpperCase() === 'COMPLETED').length;
    const hasFailed = b.jobs.some(j => String(j.status || '').toUpperCase() === 'FAILED');
    const hasRunning = b.jobs.some(j => ['RUNNING', 'CLAIMED'].includes(String(j.status || '').toUpperCase()));

    let overallStatus = 'COMPLETED';
    if (hasFailed) overallStatus = 'FAILED';
    else if (hasRunning) overallStatus = 'RUNNING';

    return {
      isBenchmarkBatch: true,
      id: b.id,
      category: b.category,
      title: `${b.title} (${b.jobs.length}회 실행)`,
      overallStatus,
      overallProgress: 100,
      completedCount,
      jobs: b.jobs,
      created_at: b.created_at,
      updated_at: b.updated_at,
    };
  });

  const combined = [
    ...pipelineGroups,
    ...benchmarkGroups,
    ...otherJobs.map(j => ({ isPipeline: false, job: j, updated_at: j.created_at }))
  ];
  combined.sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
  return combined;
}

function renderPipelineCard(item, prefix = 'rec') {
  if (item.isBenchmarkBatch) {
    const domId = `${prefix}_${item.id}`;
    const isOpen = openPipelineDetails.has(domId);
    const subjobsHtml = item.jobs.map(j => `
      <div class="pipeline-subjob-row">
        <div style="display:flex;align-items:center;gap:8px;">
          <a href="#" onclick="showJobDetail('${j.job_id}');return false" style="font-family:monospace;font-weight:bold;color:#58a6ff;">${j.job_id.substring(0,8)}</a>
          <span style="color:#c9d1d9;font-weight:600;">📊 고성과 벤치마크 분석</span>
          <span class="info" style="font-size:11px;">${escapeHtml(jobDescription(j))}</span>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          ${statusBadge(j.status)}
          <span style="font-size:11px;color:#8b949e;font-family:monospace;">${fmtTime(j.created_at)}</span>
        </div>
      </div>
    `).join('');

    return `
      <div class="pipeline-card" style="border-left: 3px solid #58a6ff; background: rgba(56,139,253,0.03);">
        <div class="pipeline-header">
          <div class="pipeline-title-group">
            <span class="pipeline-badge-category" style="background:rgba(56,139,253,0.15);border-color:rgba(56,139,253,0.4);color:#58a6ff;">📊 ${escapeHtml(item.category)}</span>
            <span class="pipeline-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</span>
          </div>
          <div class="pipeline-meta-group">
            <span class="badge badge-completed">${item.completedCount}건 완료</span>
            <span class="pipeline-time">${fmtTime(item.updated_at)}</span>
            <button class="pipeline-toggle-btn" onclick="togglePipelineDetails('${domId}')">
              <span id="${domId}_arrow">${isOpen ? '▲' : '▼'}</span> 상세 (${item.jobs.length})
            </button>
          </div>
        </div>
        <div id="${domId}_details" class="pipeline-details-accordion ${isOpen ? 'open' : ''}">
          <div style="font-size:11px;color:#8b949e;font-weight:bold;margin-bottom:8px;">📌 벤치마크 탐색 실행 로그</div>
          ${subjobsHtml}
        </div>
      </div>
    `;
  }

  if (!item.isPipeline) {
    const j = item.job;
    return `
      <div class="pipeline-card">
        <div class="pipeline-header">
          <div class="pipeline-title-group">
            <span class="pipeline-badge-category" style="background:rgba(56,139,253,0.15);border-color:rgba(56,139,253,0.4);color:#58a6ff;">${humanJobType(j.job_type)}</span>
            <span class="pipeline-title" title="${escapeHtml(jobDescription(j))}">${escapeHtml(jobDescription(j))}</span>
          </div>
          <div class="pipeline-meta-group">
            ${statusBadge(j.status)}
            <span class="pipeline-time">${fmtTime(j.created_at)}</span>
            <button class="btn btn-sm" onclick="showJobDetail('${j.job_id}')" style="font-size:10px;padding:2px 8px;">상세</button>
          </div>
        </div>
        ${(j.status === 'FAILED' || j.error_message) ? `
          <div style="color:#f0883e;margin-top:6px;font-size:12px;word-break:break-all;background:rgba(240,136,62,0.12);padding:6px 10px;border-radius:6px;border:1px solid rgba(240,136,62,0.35)">
            ⚠️ 오류: ${escapeHtml(j.error_message || '작업 실패')}
          </div>` : ''}
      </div>
    `;
  }

  const domId = `${prefix}_${item.id}`;
  const isOpen = openPipelineDetails.has(domId);
  const isAllComplete = item.overallStatus === 'COMPLETED';
  const isPaused = item.overallStatus === 'PAUSED';
  const statusClass = isAllComplete ? 'badge-completed' : (item.overallStatus === 'FAILED' ? 'badge-failed' : (isPaused ? 'badge-paused' : 'badge-rendering'));
  const displayStatusText = isAllComplete ? '제작 완료' : (item.overallStatus === 'FAILED' ? '오류' : (isPaused ? `이어 가능 (${item.completedCount}/${item.totalSteps})` : `진행 중 (${item.completedCount}/${item.totalSteps})`));
  const statusText = displayStatusText;
  const resumeJobId = item.failedJob?.job_id || item.jobs[item.jobs.length - 1]?.job_id || '';
  const errorSummary = item.lastError ? `
    <div class="pipeline-error-summary">
      <strong>오류 이유:</strong> ${escapeHtml(item.lastError)}
    </div>
  ` : '';

  const stepsHtml = PIPELINE_STEPS_CONFIG.map((step, idx) => {
    const stepInfo = item.stepStatuses[step.key];
    const st = stepInfo.status;
    let stepClass = 'step-pending';
    let stepBadgeIcon = '⚪';

    if (st === 'COMPLETED') {
      stepClass = 'step-done';
      stepBadgeIcon = '✓';
    } else if (['RUNNING', 'RENDERING', 'PREPARING', 'CLAIMED'].includes(st)) {
      stepClass = 'step-running';
      stepBadgeIcon = '⏳';
    } else if (st === 'FAILED') {
      stepClass = 'step-failed';
      stepBadgeIcon = '✕';
    }

    const clickAttr = stepInfo.job ? `onclick="showJobDetail('${stepInfo.job.job_id}')" style="cursor:pointer;" title="클릭하여 ${step.label} 상세 로그 보기"` : '';
    const arrow = idx < PIPELINE_STEPS_CONFIG.length - 1 ? `<span class="pipeline-step-arrow">➔</span>` : '';

    return `
      <div class="pipeline-step-item ${stepClass}" ${clickAttr}>
        <span>${step.icon}</span>
        <span>${step.label}</span>
        <span style="font-size:10px;opacity:0.9;">[${stepBadgeIcon}]</span>
      </div>
      ${arrow}
    `;
  }).join('');

  const subjobsHtml = item.jobs.map(j => `
    <div class="pipeline-subjob-row">
      <div style="display:flex;align-items:center;gap:8px;">
        <a href="#" onclick="showJobDetail('${j.job_id}');return false" style="font-family:monospace;font-weight:bold;color:#58a6ff;">${j.job_id.substring(0,8)}</a>
        <span style="color:#c9d1d9;font-weight:600;">${humanJobType(j.job_type)}</span>
        <span class="info" style="font-size:11px;">${escapeHtml(jobDescription(j))}</span>
      </div>
      <div style="display:flex;align-items:center;gap:8px;">
        ${statusBadge(j.status)}
        <span style="font-size:11px;color:#8b949e;font-family:monospace;">${fmtTime(j.created_at)}</span>
      </div>
    </div>
  `).join('');

  return `
    <div class="pipeline-card" style="${isAllComplete ? 'border: 1px solid rgba(46,160,67,0.4); box-shadow: 0 0 12px rgba(46,160,67,0.08);' : ''}">
      <div class="pipeline-header">
        <div class="pipeline-title-group">
          <span class="pipeline-badge-category">🔞 ${escapeHtml(item.category)}</span>
          <span class="pipeline-title" title="${escapeHtml(item.title)}" style="${isAllComplete ? 'color:#7ee787;font-weight:bold;' : ''}">"${escapeHtml(item.title)}"</span>
        </div>
        <div class="pipeline-meta-group">
          <span class="badge ${statusClass}">${statusText}</span>
          <span style="font-size:12px;font-weight:bold;color:${isAllComplete ? '#7ee787' : '#58a6ff'};font-family:monospace;">${item.overallProgress}%</span>
          <span class="pipeline-time">${fmtTime(item.updated_at)}</span>
          ${item.canResume ? `
            <button class="btn btn-sm btn-start pipeline-header-resume" onclick="restartHermesFromCancelled('${resumeJobId}', this)">
              이어하기
            </button>
          ` : ''}
          <button class="pipeline-toggle-btn" onclick="togglePipelineDetails('${domId}')">
            <span id="${domId}_arrow">${isOpen ? '▲' : '▼'}</span> 상세 (${item.jobs.length})
          </button>
        </div>
      </div>

      <!-- 4단계 가로 파이프라인 스텝 바 -->
      <div class="pipeline-steps-container">
        ${stepsHtml}
      </div>

      <!-- 아코디언 상세 영역 -->
      <div id="${domId}_details" class="pipeline-details-accordion ${isOpen ? 'open' : ''}">
        <div style="font-size:11px;color:#8b949e;font-weight:bold;margin-bottom:8px;">📌 포함된 세부 Job 및 로그</div>
        ${errorSummary}
        ${subjobsHtml}
        ${isAllComplete ? `
          <div class="pipeline-actions-footer">
            <button class="btn btn-sm btn-start" onclick="switchTab('generated-results')" style="font-size:11px;">
              👁️ 생성 결과 확인
            </button>
            <button class="btn btn-sm" onclick="switchTab('voicebox-tts')" style="font-size:11px;background:rgba(163,113,247,0.15);border-color:rgba(163,113,247,0.4);color:#d2a8ff;">
              🎙️ TTS 생성 이동
            </button>
          </div>
        ` : item.canResume ? `
          <div class="pipeline-actions-footer">
            <button class="btn btn-sm btn-start" onclick="restartHermesFromCancelled('${resumeJobId}', this)" style="font-size:11px;">
              이어하기
            </button>
          </div>
        ` : ''}
      </div>
    </div>
  `;
}

function togglePipelineDetails(domId) {
  const detailsEl = document.getElementById(`${domId}_details`);
  const arrowEl = document.getElementById(`${domId}_arrow`);
  if (!detailsEl) return;
  const isOpen = detailsEl.classList.contains('open');
  if (isOpen) {
    detailsEl.classList.remove('open');
    openPipelineDetails.delete(domId);
    if (arrowEl) arrowEl.textContent = '▼';
  } else {
    detailsEl.classList.add('open');
    openPipelineDetails.add(domId);
    if (arrowEl) arrowEl.textContent = '▲';
  }
}

function renderRecentJobs(jobs) {
  const el = document.getElementById('recent-jobs-container');
  const empty = document.getElementById('recent-empty');
  if (!el) return;
  if (!jobs.length) { el.innerHTML = ''; if (empty) empty.style.display = 'block'; return; }
  if (empty) empty.style.display = 'none';

  const pipelines = groupJobsIntoPipelines(jobs);
  el.innerHTML = pipelines.slice(0, 10).map(p => renderPipelineCard(p, 'rec')).join('');
}

let knownRenderJobIds = new Set();
let isFirstRenderJobFetch = true;

function playChimeSound() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(587.33, ctx.currentTime);
    osc.frequency.setValueAtTime(880, ctx.currentTime + 0.12);
    gain.gain.setValueAtTime(0.18, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.45);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.45);
  } catch(e) {}
}

function checkNewRenderJobs(jobs, pendingCount) {
  const badge = document.getElementById('render-nav-badge');
  if (badge) {
    if (pendingCount > 0) {
      badge.textContent = pendingCount;
      badge.style.display = 'inline-flex';
      badge.style.alignItems = 'center';
      badge.style.justifyContent = 'center';
    } else {
      badge.style.display = 'none';
    }
  }

  if (!Array.isArray(jobs) || !jobs.length) return;

  if (isFirstRenderJobFetch) {
    jobs.forEach(j => knownRenderJobIds.add(String(j.job_id)));
    isFirstRenderJobFetch = false;
    return;
  }

  for (const j of jobs) {
    const id = String(j.job_id);
    if (!knownRenderJobIds.has(id)) {
      knownRenderJobIds.add(id);
      const st = String(j.status || '').toUpperCase();
      if (st === 'PENDING' || st === 'QUEUED' || st === 'RENDERING') {
        const src = j.source === 'web_std' ? '웹STD 클라우드' : '로컬 워커';
        const title = j.project_name || j.job_id;
        showToast(`🔔 [${src}] 새로운 렌더링 작업이 감지되었습니다: ${title}`, 'info');
        playChimeSound();
      }
    }
  }
}

/* ── Render tab ── */
function loadRenderTab() {
  api('GET', '/api/rendering-jobs?limit=30').then(data => {
    if (!data) return;
    const jobs = data.jobs || [];
    checkNewRenderJobs(jobs, data.pending_count || 0);

    const el = document.getElementById('render-jobs-body');
    const empty = document.getElementById('render-empty');
    if (!jobs.length) { el.innerHTML = ''; empty.style.display = 'block'; return; }
    empty.style.display = 'none';

    el.innerHTML = jobs.map(j => {
      const srcBadge = j.source === 'web_std' 
        ? '<span class="badge" style="background:#8e44ad;color:#fff;">웹STD</span>' 
        : '<span class="badge" style="background:#2980b9;color:#fff;">로컬</span>';
      const isCompleted = String(j.status).toUpperCase() === 'COMPLETED';
      const resultLink = j.result_url 
        ? `<a href="${escapeHtml(j.result_url)}" target="_blank" class="btn btn-sm btn-outline" style="text-decoration:none;">결과 확인 &#x1F517;</a>` 
        : (isCompleted ? '<span style="color:#2ecc71;">완료됨</span>' : '-');
      const progress = displayProgress(j);

      return `<tr>
        <td>${srcBadge}</td>
        <td>
          <div style="font-weight:600;color:#58a6ff;">${escapeHtml(j.project_name || j.job_id.substring(0,8))} ${j.project_id ? `<span style="color:#8b949e;font-size:12px;">(${j.project_id})</span>` : ''}</div>
          <div style="font-size:11px;color:#8b949e;">${j.email && j.email !== '-' ? `<span style="color:#58a6ff;">${escapeHtml(j.email)}</span> · ` : ''}ID: ${escapeHtml(j.job_id.substring(0,12))}</div>
        </td>
        <td>${statusBadge(j.status)}</td>
        <td style="min-width:110px;">
          <div style="display:flex;align-items:center;gap:6px;">
            <div class="progress-bar" style="flex:1;height:8px;margin:0;"><div class="progress-fill" style="width:${progress}%"></div></div>
            <span style="font-size:12px;font-weight:600;">${progress}%</span>
          </div>
        </td>
        <td>
          <div>${escapeHtml(j.progress_message || j.error_message || '-')}</div>
          ${j.worker_id && j.worker_id !== '-' ? `<div style="font-size:11px;color:#8b949e;">담당: ${escapeHtml(j.worker_id)}</div>` : ''}
        </td>
        <td>${fmtShort(j.started_at || j.created_at)}</td>
        <td>${resultLink}</td>
      </tr>`;
    }).join('');

    // Show active render card
    const active = data.active_job || jobs.find(j => ['CLAIMED','PREPARING','RENDERING','UPLOADING'].includes(String(j.status).toUpperCase()));
    const acEl = document.getElementById('render-active-content');
    if (active) {
      const srcLabel = active.source === 'web_std' ? '[웹STD 클라우드 렌더]' : '[로컬 렌더]';
      acEl.innerHTML = `<div class="status-card" style="border-left:4px solid #58a6ff;">
        <div style="display:flex;align-items:center;justify-content:space-between;">
          <div class="name">${statusBadge(active.status)} <strong style="color:#58a6ff;">${srcLabel} ${escapeHtml(active.project_name || active.job_id)}</strong></div>
          <span style="font-size:12px;color:#8b949e;">시작: ${fmtShort(active.started_at || active.created_at)}</span>
        </div>
        <div class="info" style="margin-top:6px;">${escapeHtml(active.progress_message || '영상 렌더링을 진행하고 있습니다...')}</div>
        <div class="progress-bar" style="margin-top:8px;"><div class="progress-fill" style="width:${displayProgress(active)}%"></div></div>
        <div style="display:flex;align-items:center;justify-content:space-between;margin-top:6px;font-size:12px;color:#8b949e;">
          <span>진행률: ${displayProgress(active)}%</span>
          <span>작업자: ${escapeHtml(active.worker_id || 'AIR Worker')}</span>
        </div>
      </div>`;
    } else {
      acEl.innerHTML = '<div class="empty" style="padding:20px"><div class="icon">&#x274C;</div>현재 진행 중인 렌더 작업 없음</div>';
    }
  });
}

/* ── History tab ── */
/* Generated results tab */
let generatedResultsLoaded = false;

function getGeneratedTitle(data) {
  const structure = data?.structure || {};
  const titleGeneration = getGeneratedTitleGeneration(data);
  return data?.generated_title || data?.title || data?.upload_title || structure.upload_title || titleGeneration.generated_title || titleGeneration.final_title || '-';
}

function getGeneratedTitleGeneration(data) {
  if (data?.title_generation && Object.keys(data.title_generation).length) return data.title_generation;
  const benchmarkTitleGeneration = data?.benchmark_analysis?.title_generation;
  if (benchmarkTitleGeneration && Object.keys(benchmarkTitleGeneration).length) return benchmarkTitleGeneration;
  return {};
}

function getGeneratedPublishMetadata(data) {
  if (data?.publish_metadata && Object.keys(data.publish_metadata).length) return data.publish_metadata;
  const progressMetadata = data?.progress_payload?.publish_metadata;
  if (progressMetadata && Object.keys(progressMetadata).length) return progressMetadata;
  return {};
}

function getGeneratedPublishTitle(data, publishMetadata) {
  const metadata = publishMetadata || getGeneratedPublishMetadata(data);
  if (Array.isArray(metadata.titles) && metadata.titles.length) return String(metadata.titles[0] || '').trim();
  if (metadata.title) return String(metadata.title || '').trim();
  return getGeneratedTitle(data);
}

function getGeneratedPublishDescription(publishMetadata) {
  return String((publishMetadata || {}).description || '').trim();
}

function getGeneratedScenes(data) {
  const scenes = data?.structure?.scenes;
  return Array.isArray(scenes) ? scenes : [];
}

function getGeneratedImageGridPrompts(data) {
  const grids = data?.structure?.image_grid_prompts || data?.image_grid_prompts;
  return Array.isArray(grids) ? grids.filter(grid => String(grid?.prompt || '').trim()) : [];
}

function sceneVideoPrompt(scene) {
  return String(scene?.video_prompt || scene?.motion_desc || scene?.flow_prompt || scene?.camera_motion || '').trim();
}

const MAX_VIDEO_PROMPT_SCENES = 12;

function sceneNumber(scene, index) {
  const value = Number(scene?.scene_order || scene?.scene_number || index + 1);
  return Number.isFinite(value) ? value : index + 1;
}

function sceneRequiresVideoPrompt(scene, index) {
  if (scene?.video_prompt_required === false) return false;
  return sceneNumber(scene, index) <= MAX_VIDEO_PROMPT_SCENES;
}

function hasGeneratedMediaPrompts(structure, scenes) {
  const status = String(structure?.media_prompt_status || '').trim();
  if (status !== 'ready') return false;
  const imageGridPrompts = getGeneratedImageGridPrompts({ structure });
  return Array.isArray(scenes)
    && scenes.length > 0
    && imageGridPrompts.length > 0
    && scenes.every((scene, index) => !sceneRequiresVideoPrompt(scene, index) || sceneVideoPrompt(scene));
}

function generatedQualityGate(data) {
  const gate = data?.quality_gate || {};
  if (gate.status) return gate;
  const structure = data?.structure || {};
  const scenes = getGeneratedScenes(data);
  const mediaStatus = String(structure?.media_prompt_status || data?.media_prompt_status || '').trim();
  const missing = [];
  const review = [];
  if (!(data?.benchmark_analysis || data?.material_statuses?.benchmark === 'ready')) missing.push('benchmark');
  if (getGeneratedTitle(data) === '-') missing.push('title');
  if (!(data?.research_bundle || structure?.research_bundle || data?.material_statuses?.web_research === 'ready')) missing.push('web_research');
  if (!scenes.length && !data?.scene_count) missing.push('scenes');
  if (mediaStatus === 'fallback_ready' || data?.material_statuses?.plan_prompts === 'review') review.push('media_prompts_fallback');
  else if (!(mediaStatus === 'ready' && hasGeneratedMediaPrompts(structure, scenes))) missing.push('media_prompts');
  if (!(String(data?.script || '').trim() || data?.has_script || data?.material_statuses?.script === 'ready')) missing.push('script');
  if (!(Object.keys(getGeneratedPublishMetadata(data)).length || data?.material_statuses?.publish_metadata === 'ready')) missing.push('publish_metadata');
  const status = missing.length ? 'fail' : (review.length ? 'review' : 'pass');
  return { status, missing, review, media_prompt_status: mediaStatus, can_auto_render: status === 'pass' };
}

function generatedMaterialStatuses(data) {
  const structure = data?.structure || {};
  const scenes = getGeneratedScenes(data);
  const statuses = data?.material_statuses || {};
  return {
    benchmark: statuses.benchmark || (data?.benchmark_analysis ? 'ready' : 'missing'),
    title: statuses.title || (getGeneratedTitle(data) !== '-' ? 'ready' : 'missing'),
    web_research: statuses.web_research || ((data?.research_bundle || structure?.research_bundle) ? 'ready' : 'missing'),
    plan_prompts: statuses.plan_prompts || (String(structure?.media_prompt_status || '').trim() === 'fallback_ready' ? 'review' : (scenes.length && hasGeneratedMediaPrompts(structure, scenes) ? 'ready' : 'missing')),
    script: statuses.script || (String(data?.script || '').trim() ? 'ready' : 'missing'),
    publish_metadata: statuses.publish_metadata || (Object.keys(getGeneratedPublishMetadata(data)).length ? 'ready' : 'missing'),
  };
}

function renderMaterialBadges(statuses) {
  const labels = {
    benchmark: '벤치마크',
    title: '제목',
    web_research: '자료조사',
    plan_prompts: '씬/프롬프트',
    script: '대본',
    publish_metadata: '설명/태그',
  };
  return Object.entries(labels).map(([key, label]) => {
    const state = statuses?.[key] || 'missing';
    const cls = state === 'ready' ? 'badge-completed' : (state === 'review' ? 'badge-review' : (state === 'failed' ? 'badge-failed' : 'badge-idle'));
    return `<span class="badge ${cls}" title="${escapeHtml(label)}: ${escapeHtml(state)}">${escapeHtml(label)} ${escapeHtml(state)}</span>`;
  }).join(' ');
}

const GENERATED_MATERIAL_KEYS = ['benchmark', 'title', 'web_research', 'plan_prompts', 'script', 'publish_metadata'];

function generatedCompletionStats(row) {
  const statuses = generatedMaterialStatuses(row);
  const readyCount = GENERATED_MATERIAL_KEYS.filter(key => statuses?.[key] === 'ready').length;
  const percent = Math.round((readyCount / GENERATED_MATERIAL_KEYS.length) * 100);
  return {
    statuses,
    readyCount,
    totalCount: GENERATED_MATERIAL_KEYS.length,
    percent,
    isComplete: readyCount === GENERATED_MATERIAL_KEYS.length,
  };
}

function generatedSortTime(row) {
  return Number(row.completed_at || row.updated_at || 0);
}

function renderGeneratedRows(rows, emptyText) {
  if (!rows.length) {
    return `<tr><td colspan="5" class="info">${escapeHtml(emptyText)}</td></tr>`;
  }
  return rows.map(row => {
    const completion = row._completion || generatedCompletionStats(row);
    const ready = row.has_image_prompts && row.has_video_prompts;
    const promptState = ready
      ? '프롬프트 준비됨'
      : (row.has_legacy_visual_direction ? '구버전 시각 연출만 있음' : '프롬프트 없음');
    const scriptState = row.has_script ? `${row.script_chars || 0} chars` : 'script missing';
    const stageLabel = row.stage === 'metadata' ? 'metadata ready' : (row.stage === 'script' ? 'script ready' : (row.stage === 'plan' ? 'plan ready' : 'title ready'));
    const statusText = row.status && row.status !== 'COMPLETED' ? ` / ${row.status}` : '';
    const materialBadges = renderMaterialBadges(completion.statuses);
    const progressClass = completion.isComplete ? 'badge-completed' : (completion.percent >= 67 ? 'badge-review' : 'badge-idle');
    return `<tr>
      <td><a href="#" onclick="showGeneratedResult('${escapeHtml(row.id)}');return false">${escapeHtml(row.topic_queue_id || row.id)}</a></td>
      <td>${escapeHtml(row.category || '-')}</td>
      <td><strong>${escapeHtml(truncate(row.title || '-', 64))}</strong><div style="margin-top:6px;display:flex;gap:4px;flex-wrap:wrap">${materialBadges}</div></td>
      <td><span class="badge ${progressClass} generated-progress">${completion.percent}%</span> ${escapeHtml(stageLabel)}${escapeHtml(statusText)}<br><span class="info">${row.scene_count || 0} scenes, ${scriptState}, ${promptState}</span></td>
      <td>${fmtTime(row.completed_at || row.updated_at)}</td>
    </tr>`;
  }).join('');
}

function renderGeneratedEmptyState(diagnostics) {
  const lines = [];
  if (diagnostics) {
    lines.push(`Current step: ${diagnostics.current_step || '-'}`);
    if (diagnostics.last_run_status) lines.push(`Last run status: ${diagnostics.last_run_status}`);
    if (diagnostics.last_error) lines.push(`Last error: ${diagnostics.last_error}`);
    if (diagnostics.last_completed_result_id) lines.push(`Last completed result: ${diagnostics.last_completed_result_id}`);
    lines.push(`Completed final results: ${diagnostics.generated_count || 0}`);
    lines.push(`Benchmark/partial result files: ${diagnostics.partial_result_count || 0}`);
    if (diagnostics.latest_partial_at) lines.push(`Latest partial file: ${fmtTime(diagnostics.latest_partial_at)}`);
    const recentLogs = Array.isArray(diagnostics.recent_logs) ? diagnostics.recent_logs.slice(-4) : [];
    if (recentLogs.length) {
      lines.push('Recent logs:');
      recentLogs.forEach(log => lines.push(`- ${String(log).replace(/^\\[[^\\]]+\\]\\s*/, '')}`));
    }
  }
  const detail = lines.length
    ? `<div class="prompt-box" style="margin-top:12px;text-align:left;white-space:pre-wrap">${escapeHtml(lines.join('\n'))}</div>`
    : '';
  return `<div class="icon">&#x1F4ED;</div>저장 완료된 자동 생성 결과가 없습니다${detail}`;
}

async function loadGeneratedResults() {
  const completedBody = document.getElementById('generated-results-completed-body');
  const partialBody = document.getElementById('generated-results-partial-body');
  const empty = document.getElementById('generated-results-empty');
  const tables = document.getElementById('generated-results-tables');
  const dir = document.getElementById('generated-results-dir');
  const completedCount = document.getElementById('generated-results-completed-count');
  const partialCount = document.getElementById('generated-results-partial-count');
  if (!completedBody || !partialBody || !empty) return;
  completedBody.innerHTML = '<tr><td colspan="5" class="info">생성 결과를 불러오는 중...</td></tr>';
  partialBody.innerHTML = '';
  empty.style.display = 'none';
  if (tables) tables.style.display = 'block';
  const data = await api('GET', '/api/generated-results?limit=100');
  if (!data) return;
  if (dir) dir.textContent = data.dir || '';
  const rows = (data.results || []).map(row => ({ ...row, _completion: generatedCompletionStats(row) }));
  if (!rows.length) {
    completedBody.innerHTML = '';
    partialBody.innerHTML = '';
    if (tables) tables.style.display = 'none';
    empty.innerHTML = renderGeneratedEmptyState(data.diagnostics);
    empty.style.display = 'block';
    return;
  }
  const completedRows = rows
    .filter(row => row._completion.isComplete)
    .sort((a, b) => generatedSortTime(b) - generatedSortTime(a));
  const partialRows = rows
    .filter(row => !row._completion.isComplete)
    .sort((a, b) => (b._completion.percent - a._completion.percent) || (b._completion.readyCount - a._completion.readyCount) || (generatedSortTime(b) - generatedSortTime(a)));

  if (completedCount) completedCount.textContent = `${completedRows.length}건`;
  if (partialCount) partialCount.textContent = `${partialRows.length}건 · 완료율 높은 순`;
  completedBody.innerHTML = renderGeneratedRows(completedRows, '100% 완료된 결과가 없습니다.');
  partialBody.innerHTML = renderGeneratedRows(partialRows, '부분완료 결과가 없습니다.');
  generatedResultsLoaded = true;
  const firstRow = completedRows[0] || partialRows[0];
  if (firstRow) showGeneratedResult(firstRow.id);
}
async function showGeneratedResult(resultId) {
  const container = document.getElementById('generated-result-detail');
  if (!container) return;
  container.innerHTML = '<div class="info">상세 결과를 불러오는 중...</div>';
  const data = await api('GET', `/api/generated-results/${encodeURIComponent(resultId)}`);
  if (!data) return;
  const structure = data.structure || {};
  const scenes = getGeneratedScenes(data);
  const imageGridPrompts = getGeneratedImageGridPrompts(data);
  const script = data.script || '';
  const titleGeneration = getGeneratedTitleGeneration(data);
  const publishMetadata = getGeneratedPublishMetadata(data);
  const sources = Array.isArray(data._sources) ? data._sources : [];
  const errors = Array.isArray(data.errors) ? data.errors : [];
  const metaHtml = `
    <div class="generated-meta">
      <div class="label">파일 ID</div><div>${escapeHtml(data._file?.id || resultId)}</div>
      <div class="label">Queue ID</div><div>${escapeHtml(data.topic_queue_id || '-')}</div>
      <div class="label">카테고리</div><div>${escapeHtml(data.category || data.topic || '-')}</div>
      <div class="label">상태</div><div>${escapeHtml(data.status || '-')}</div>
      <div class="label">생성일</div><div>${fmtTime(data.completed_at || data._file?.updated_at)}</div>
      <div class="label">제목</div><div><strong>${escapeHtml(getGeneratedTitle(data))}</strong></div>
    </div>`;
  const planBits = [
    ['카테고리', data.category || structure.topic || '-'],
    ['제목 약속', structure.title_promise],
    ['오프닝 훅', structure.opening_hook],
    ['결말/페이오프', structure.payoff],
    ['전체 무드', structure.global_mood],
  ].filter(([, value]) => value).map(([label, value]) => `<div class="label">${escapeHtml(label)}</div><div>${escapeHtml(value)}</div>`).join('');
  let titleJson = '';
  if (Object.keys(titleGeneration).length) {
    const selectedTitle = titleGeneration.generated_title || titleGeneration.title || '-';
    const selectedScore = titleGeneration.selected_score || '-';
    const candidates = Array.isArray(titleGeneration.title_candidates) ? titleGeneration.title_candidates : [];

    let candidatesListHtml = '';
    if (candidates.length > 0) {
      candidatesListHtml = `
        <div style="margin-top:12px;">
          <div style="font-size:12px;font-weight:bold;color:#8b949e;margin-bottom:8px;">📋 기획 제목 후보군 (${candidates.length}개)</div>
          <div style="display:flex;flex-direction:column;gap:8px;">
            ${candidates.map((c, idx) => {
              const isSelected = (c.title === selectedTitle);
              return `
                <div style="padding:10px 12px;border-radius:6px;background:${isSelected ? 'rgba(46,160,67,0.12)' : '#0d1117'};border:1px solid ${isSelected ? '#2ea043' : '#30363d'};">
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                    <span style="font-weight:bold;color:${isSelected ? '#7ee787' : '#c9d1d9'};font-size:13px;">
                      ${isSelected ? '👑 [최종 선정] ' : `${idx + 1}. `}${escapeHtml(c.title || '-')}
                    </span>
                    <span class="badge ${isSelected ? 'badge-completed' : ''}" style="font-size:11px;font-weight:bold;">
                      ${c.score ? `${c.score}점` : (c.final_score ? `${c.final_score}점` : '')}
                    </span>
                  </div>
                  ${c.angle ? `<div style="font-size:11px;color:#8b949e;margin-bottom:2px;"><strong>기획 앵글:</strong> ${escapeHtml(c.angle)}</div>` : ''}
                  ${c.ai_reason ? `<div style="font-size:11px;color:#58a6ff;"><strong>평가 이유:</strong> ${escapeHtml(c.ai_reason)}</div>` : ''}
                </div>
              `;
            }).join('')}
          </div>
        </div>
      `;
    }

    titleJson = `
      <div style="display:flex;flex-direction:column;gap:8px;">
        <div class="generated-meta" style="grid-template-columns:110px 1fr;">
          <div class="label">최종 선정 제목</div>
          <div><strong style="color:#7ee787;font-size:13px;">${escapeHtml(selectedTitle)}</strong></div>
          <div class="label">종합 평가 점수</div>
          <div><span class="badge badge-completed" style="font-size:12px;">${escapeHtml(String(selectedScore))}점</span></div>
          <div class="label">카테고리</div>
          <div>${escapeHtml(titleGeneration.category || data.category || '-')}</div>
        </div>
        ${candidatesListHtml}
      </div>
    `;
  } else {
    titleJson = '<div class="info">제목 생성 상세 데이터가 없습니다.</div>';
  }
  const publishTitle = getGeneratedPublishTitle(data, publishMetadata);
  const publishDescription = getGeneratedPublishDescription(publishMetadata);
  const publishTags = Array.isArray(publishMetadata.tags) ? publishMetadata.tags : [];
  const publishHashtags = Array.isArray(publishMetadata.hashtags) ? publishMetadata.hashtags : [];
  const qualityGate = generatedQualityGate(data);
  const qualityClass = qualityGate.status === 'pass' ? 'badge-completed' : (qualityGate.status === 'review' ? 'badge-review' : 'badge-failed');
  const qualityText = qualityGate.status === 'pass'
    ? '자동 렌더 가능'
    : (qualityGate.status === 'review' ? `검수 필요: ${(qualityGate.review || []).join(', ') || 'review'}` : `렌더 보류: ${(qualityGate.missing || []).join(', ') || 'missing'}`);
  const qualityHtml = `<div class="generated-meta">
    <div class="label">품질 게이트</div><div><span class="badge ${qualityClass}">${escapeHtml(qualityGate.status)}</span> <span class="info">${escapeHtml(qualityText)}</span></div>
    <div class="label">자동 렌더</div><div>${qualityGate.can_auto_render ? '<span class="badge badge-completed">allowed</span>' : '<span class="badge badge-review">blocked</span>'}</div>
  </div>`;
  const metadataHtml = Object.keys(publishMetadata).length
    ? `<div class="generated-meta">
        <div class="label">예비 렌더링 영상제목</div><div><strong>${escapeHtml(publishTitle || '-')}</strong></div>
        <div class="label">예비 렌더링 상세</div><div><div class="prompt-box">${escapeHtml(publishDescription || '-')}</div></div>
        <div class="label">Tags</div><div>${escapeHtml(publishTags.join(', ') || '-')}</div>
        <div class="label">Hashtags</div><div>${escapeHtml(publishHashtags.join(' ') || '-')}</div>
      </div>`
    : '<div class="info">YouTube metadata is not available.</div>';
  const mediaReady = hasGeneratedMediaPrompts(structure, scenes);
  const mediaStatusLabel = String(structure.media_prompt_status || (mediaReady ? 'ready' : 'missing'));
  const mediaStatus = mediaReady
    ? `<span class="badge badge-completed">${escapeHtml(mediaStatusLabel)}</span>`
    : '<span class="badge badge-failed">missing</span> <span class="info">이 결과에는 2x2 이미지 프롬프트 또는 영상 프롬프트가 부족합니다.</span>';
  const gridHtml = imageGridPrompts.length ? imageGridPrompts.map((grid, idx) => {
    const sceneNumbers = Array.isArray(grid.scene_numbers) ? grid.scene_numbers.join(', ') : '-';
    const templateName = grid.template ? ` / ${grid.template}` : '';
    return `
    <div class="scene-card">
      <div class="scene-title">2x2 이미지 프롬프트 ${idx + 1}</div>
      <div class="info">씬 ${escapeHtml(sceneNumbers)}${escapeHtml(templateName)}</div>
      <div class="prompt-box">${escapeHtml(grid.prompt)}</div>
    </div>`;
  }).join('') : '<div class="info">저장된 2x2 이미지 프롬프트가 없습니다.</div>';
  const videoHtml = scenes.length ? scenes.map((scene, idx) => `
    <div class="scene-card">
      <div class="scene-title">Scene ${idx + 1}</div>
      <div class="info">${escapeHtml(scene.scene_summary || scene.summary || '-')}</div>
      ${scene.scene_situation ? `<div class="prompt-box">${escapeHtml(scene.scene_situation)}</div>` : ''}
      ${(!sceneVideoPrompt(scene) && scene.visual_direction) ? `
      <div style="margin-top:10px;font-weight:600">구버전 시각 연출 방향</div>
      <div class="prompt-box">${escapeHtml(scene.visual_direction)}</div>` : ''}
      <div style="margin-top:10px;font-weight:600">영상 프롬프트</div>
      <div class="prompt-box">${escapeHtml(scene.video_prompt || '저장된 영상 프롬프트가 없습니다.')}</div>
    </div>
  `).join('') : '<div class="info">장면 데이터가 없습니다.</div>';
  const errorsHtml = errors.length
    ? `<div class="generated-section"><h4>오류 / 중단 사유</h4><div class="prompt-box prompt-box-error">${escapeHtml(errors.join('\n\n'))}</div></div>`
    : '';
  const sourceHtml = sources.length
    ? `<div class="generated-section"><h4>저장 소스</h4><div class="prompt-box">${escapeHtml(JSON.stringify(sources, null, 2))}</div></div>`
    : '';
  container.innerHTML = `
    <div class="generated-section">
      <h4>기본 정보</h4>
      ${metaHtml}
      ${qualityHtml}
    </div>
    <div class="generated-section">
      <h4>제목 생성</h4>
      ${titleJson}
    </div>
    <div class="generated-section">
      <h4>예비 렌더링 업로드 정보</h4>
      ${metadataHtml}
    </div>
    <div class="generated-section">
      <h4>대본 기획</h4>
      ${planBits ? `<div class="generated-meta">${planBits}</div>` : '<div class="info">기획 데이터가 없습니다.</div>'}
    </div>
    <div class="generated-section">
      <h4>대본</h4>
      <div class="result-viewer" style="max-height:420px">${escapeHtml(script || '대본 데이터가 없습니다.')}</div>
    </div>
    <div class="generated-section">
      <h4>2x2 이미지 생성 프롬프트</h4>
      <div style="margin-bottom:10px">${mediaStatus}</div>
      ${gridHtml}
    </div>
    <div class="generated-section">
      <h4>영상 프롬프트</h4>
      ${videoHtml}
    </div>
    ${errorsHtml}
    ${sourceHtml}`;
}

function loadHistory() {
  const status = document.getElementById('hist-filter-status')?.value || '';
  const type = document.getElementById('hist-filter-type')?.value || '';
  let url = '/api/jobs?limit=100';
  if (status) url += `&status=${status}`;
  api('GET', url).then(data => {
    if (!data) return;
    let jobs = data.jobs || [];
    if (type) jobs = jobs.filter(j => j.job_type === type);
    const el = document.getElementById('history-jobs-container');
    const empty = document.getElementById('history-empty');
    if (!el) return;
    if (!jobs.length) { el.innerHTML = ''; if (empty) empty.style.display = 'block'; return; }
    if (empty) empty.style.display = 'none';

    const pipelines = groupJobsIntoPipelines(jobs);
    el.innerHTML = pipelines.map(p => renderPipelineCard(p, 'hist')).join('');
  });
}

/* ── Logs tab ── */
function loadLogs() {
  const proc = document.getElementById('log-process').value;
  api('GET', `/api/logs?process=${proc}&tail_lines=200`).then(data => {
    if (!data || data.error) {
      document.getElementById('log-output').textContent = data?.error || '로그를 불러올 수 없습니다';
      return;
    }
    document.getElementById('log-output').textContent = (data.lines || []).join('\n') || '(로그 없음)';
    document.getElementById('log-output').scrollTop = document.getElementById('log-output').scrollHeight;
  });
}

/* ── Shared style presets ── */
let stylePresets = [];
let styleFilter = 'image';

function updateStyleFormHelp() {
  const type = document.getElementById('style-preset-type').value;
  const isScript = type === 'script';
  document.getElementById('style-prompt-label').textContent = isScript ? '대본 작성 지시사항 *' : '이미지 프롬프트 템플릿 *';
  document.getElementById('style-prompt-template').placeholder = isScript
    ? '예: 1인칭 회고체로 시작하고, 대화는 짧게 사용하며, 장면마다 감정의 변화가 드러나게 작성하세요.'
    : '예: [SUBJECT], cinematic lighting, realistic textures, no text in image';
  document.getElementById('style-prompt-help').textContent = isScript
    ? '이 내용은 AI Worker의 대본 기획과 장면별 대본 생성 프롬프트에 그대로 들어갑니다.'
    : '이미지 프롬프트를 만들 때 스타일 접두어로 사용됩니다. 이미지·영상 프롬프트 생성 이관 단계에서 Worker가 직접 사용합니다.';
  document.getElementById('style-image-instruction-group').style.display = isScript ? 'none' : 'block';
}

function resetStyleForm() {
  document.getElementById('style-edit-key').value = '';
  document.getElementById('style-preset-type').value = 'image';
  document.getElementById('style-preset-type').disabled = false;
  document.getElementById('style-key-code').value = '';
  document.getElementById('style-key-code').readOnly = false;
  document.getElementById('style-name-ko').value = '';
  document.getElementById('style-name-vi').value = '';
  document.getElementById('style-image-url').value = '';
  document.getElementById('style-prompt-template').value = '';
  document.getElementById('style-gemini-instruction').value = '';
  document.getElementById('style-save-btn').textContent = '스타일 저장';
  document.getElementById('style-cancel-btn').style.display = 'none';
  updateStyleFormHelp();
}

function setStyleFilter(filter) {
  styleFilter = filter;
  document.querySelectorAll('[data-style-filter]').forEach(el => {
    el.classList.toggle('btn-primary', el.dataset.styleFilter === filter);
  });
  renderStylePresets();
}

function syncScriptStyleSelects() {
  const scriptStyles = stylePresets.filter(p => p.preset_type === 'script');
  for (const id of ['sp-style', 'sg-style']) {
    const select = document.getElementById(id);
    if (!select) continue;
    const selected = select.value || 'default';
    const options = [{key_code:'default', display_name_ko:'기본'}]
      .concat(scriptStyles.filter(p => p.key_code !== 'default'));
    select.innerHTML = options.map(p => `<option value="${escapeHtml(p.key_code)}">${escapeHtml(p.display_name_ko)} (${escapeHtml(p.key_code)})</option>`).join('');
    select.value = options.some(p => p.key_code === selected) ? selected : 'default';
  }
}

async function loadStylePresets() {
  const list = document.getElementById('style-presets-list');
  if (list) list.innerHTML = '<div class="info">스타일 목록을 불러오는 중...</div>';
  const data = await api('GET', '/api/style-presets');
  if (!data || data.error) {
    if (list) list.innerHTML = `<div class="info" style="color:#f85149">스타일 목록을 불러오지 못했습니다: ${escapeHtml(data?.error || '')}</div>`;
    return;
  }
  stylePresets = Array.isArray(data.presets) ? data.presets : [];
  document.getElementById('style-store-notice').textContent = data.shared_store_available
    ? '중앙 스타일 저장소와 연결됨. 저장 즉시 Worker의 생성 지침에도 반영됩니다.'
    : '중앙 스타일 저장소 연결이 없습니다. Worker 설정을 확인하세요.';
  syncScriptStyleSelects();
  renderStylePresets();
}

function renderStylePresets() {
  const list = document.getElementById('style-presets-list');
  if (!list) return;
  const presets = stylePresets.filter(p => p.preset_type === styleFilter);
  if (!presets.length) {
    list.innerHTML = '<div class="empty" style="padding:20px">등록된 스타일이 없습니다.</div>';
    return;
  }
  list.innerHTML = presets.map(p => `<div class="status-card" style="display:flex;flex-direction:column;gap:10px">
    <div style="display:flex;justify-content:space-between;gap:8px;align-items:flex-start">
      <div><strong>${escapeHtml(p.display_name_ko || p.key_code)}</strong>${p.display_name_vi ? `<div class="info">${escapeHtml(p.display_name_vi)}</div>` : ''}<div class="info">코드: ${escapeHtml(p.key_code)}</div></div>
      <div style="display:flex;gap:4px"><button class="btn btn-sm" onclick="editStylePreset('${escapeHtml(p.key_code)}')">수정</button><button class="btn btn-danger btn-sm" onclick="deleteStylePreset('${escapeHtml(p.preset_type)}','${escapeHtml(p.key_code)}')">삭제</button></div>
    </div>
    ${p.image_url ? `<img src="${escapeHtml(p.image_url)}" alt="" style="width:72px;height:72px;object-fit:cover;border-radius:6px;border:1px solid #30363d">` : ''}
    <div class="result-viewer" style="max-height:110px">${escapeHtml(p.prompt_template || '')}</div>
    ${p.gemini_instruction ? `<div class="info">추가 지시: ${escapeHtml(p.gemini_instruction)}</div>` : ''}
  </div>`).join('');
}

let categoryImageStyleCatalog = [];

async function loadCategoryImageStyles() {
  const body = document.getElementById('category-image-styles-body');
  const empty = document.getElementById('category-image-styles-empty');
  if (!body || !empty) return;
  body.innerHTML = '<tr><td colspan="4" class="info">카테고리와 이미지 스타일을 불러오는 중...</td></tr>';
  empty.style.display = 'none';
  const data = await api('GET', '/api/category-image-style-mappings');
  if (!data || data.error || !Array.isArray(data.categories) || !Array.isArray(data.styles)) {
    body.innerHTML = '';
    empty.textContent = `이미지 스타일 정보를 불러오지 못했습니다. ${data?.error || ''}`;
    empty.style.display = 'block';
    return;
  }
  categoryImageStyleCatalog = data.styles;
  if (!categoryImageStyleCatalog.length) {
    body.innerHTML = '';
    empty.textContent = '등록된 이미지 스타일이 없습니다. 먼저 스타일 관리에서 이미지 스타일을 등록하세요.';
    empty.style.display = 'block';
    return;
  }
  body.innerHTML = data.categories.map((item, index) => {
    const selectId = `category-image-style-${index}`;
    const automatic = escapeHtml(item.automatic_default || 'realistic');
    const options = [
      `<option value="">자동 선택 (${automatic})</option>`,
      ...categoryImageStyleCatalog.map(style => {
        const key = String(style.key_code || '');
        const label = `${style.display_name_ko || key} (${key})`;
        return `<option value="${escapeHtml(key)}" ${item.manual_override === key ? 'selected' : ''}>${escapeHtml(label)}</option>`;
      }),
    ].join('');
    return `<tr>
      <td><strong>${escapeHtml(item.name)}</strong></td>
      <td><code>${automatic}</code></td>
      <td><select id="${selectId}">${options}</select></td>
      <td><button class="btn btn-sm btn-primary" onclick="saveCategoryImageStyle('${escapeHtml(item.name)}', '${selectId}')">저장</button></td>
    </tr>`;
  }).join('');
}

async function saveCategoryImageStyle(category, selectId) {
  const select = document.getElementById(selectId);
  if (!select) return;
  select.disabled = true;
  try {
    const result = await api('PUT', `/api/category-image-style-mappings/${encodeURIComponent(category)}`, {
      image_style: select.value,
    });
    if (!result?.success) {
      showToast('카테고리 이미지 스타일 저장 실패: ' + (result?.error || '응답 없음'), 'error');
      return;
    }
    showToast(select.value ? `${category}: ${select.value} 수동 우선 적용` : `${category}: 자동 선택으로 전환`);
    await loadCategoryImageStyles();
  } catch (e) {
    showToast('카테고리 이미지 스타일 저장 통신 실패', 'error');
  } finally {
    select.disabled = false;
  }
}

function editStylePreset(key) {
  const preset = stylePresets.find(p => p.key_code === key);
  if (!preset) return;
  document.getElementById('style-edit-key').value = preset.key_code;
  document.getElementById('style-preset-type').value = preset.preset_type;
  document.getElementById('style-preset-type').disabled = true;
  document.getElementById('style-key-code').value = preset.key_code;
  document.getElementById('style-key-code').readOnly = true;
  document.getElementById('style-name-ko').value = preset.display_name_ko || '';
  document.getElementById('style-name-vi').value = preset.display_name_vi || '';
  document.getElementById('style-image-url').value = preset.image_url || '';
  document.getElementById('style-prompt-template').value = preset.prompt_template || '';
  document.getElementById('style-gemini-instruction').value = preset.gemini_instruction || '';
  document.getElementById('style-save-btn').textContent = '스타일 수정 저장';
  document.getElementById('style-cancel-btn').style.display = 'inline-flex';
  updateStyleFormHelp();
  document.getElementById('style-key-code').scrollIntoView({behavior:'smooth', block:'center'});
}

async function saveStylePreset() {
  const body = {
    preset_type: document.getElementById('style-preset-type').value,
    key_code: document.getElementById('style-key-code').value.trim(),
    display_name_ko: document.getElementById('style-name-ko').value.trim(),
    display_name_vi: document.getElementById('style-name-vi').value.trim(),
    image_url: document.getElementById('style-image-url').value.trim(),
    prompt_template: document.getElementById('style-prompt-template').value.trim(),
    gemini_instruction: document.getElementById('style-gemini-instruction').value.trim(),
  };
  if (!body.key_code || !body.display_name_ko || !body.prompt_template) {
    showToast('스타일 코드, 한글 표시명, 지시사항을 입력하세요.', 'error'); return;
  }
  const button = document.getElementById('style-save-btn');
  button.disabled = true;
  try {
    const data = await api('POST', '/api/style-presets', body);
    if (!data || data.detail || data.error) throw new Error(data?.detail || data?.error || '저장 실패');
    showToast('스타일을 저장했고 Worker 생성 지침에 반영했습니다.');
    resetStyleForm();
    await loadStylePresets();
  } catch (e) {
    showToast(`스타일 저장 실패: ${e.message || e}`, 'error');
  } finally {
    button.disabled = false;
  }
}

async function deleteStylePreset(type, key) {
  if (!confirm(`'${key}' 스타일을 삭제하시겠습니까? 이미 이 스타일을 선택한 카테고리는 기본 스타일로 처리됩니다.`)) return;
  const data = await api('DELETE', `/api/style-presets/${encodeURIComponent(type)}/${encodeURIComponent(key)}`);
  if (!data || data.detail || data.error) { showToast(`스타일 삭제 실패: ${data?.detail || data?.error || ''}`, 'error'); return; }
  showToast('스타일을 삭제했습니다.');
  resetStyleForm();
  await loadStylePresets();
}

/* ── Job detail modal ── */
async function showJobDetail(jobId) {
  const data = await api('GET', `/api/jobs/${jobId}`);
  if (!data) return;
  const el = document.getElementById('modal-body');
  document.getElementById('modal-title').textContent = `작업 상세: ${jobId.substring(0,12)}`;

  let html = `<table style="width:100%">
    <tr><th>ID</th><td>${data.job_id}</td></tr>
    <tr><th>작업</th><td><strong>${humanJobType(data.job_type)}</strong><br><span class="info">${escapeHtml(jobDescription(data))}</span></td></tr>
    <tr><th>상태</th><td>${statusBadge(data.status)}</td></tr>
    <tr><th>진행률</th><td>${displayProgress(data)}% — ${escapeHtml(data.progress_message || (data.status === 'COMPLETED' ? '작업 완료' : ''))}</td></tr>
    <tr><th>요청 위치</th><td>${escapeHtml(data.source || '-')}</td></tr>
    <tr><th>생성</th><td>${fmtTime(data.created_at)}</td></tr>
    <tr><th>시작</th><td>${fmtTime(data.started_at)}</td></tr>
    <tr><th>완료</th><td>${fmtTime(data.completed_at)}</td></tr>
    ${data.error_message ? `<tr><th>오류</th><td style="color:#f85149">${escapeHtml(data.error_message)}</td></tr>` : ''}
    ${data.output_path ? `<tr><th>출력</th><td>${escapeHtml(data.output_path)}</td></tr>` : ''}
  </table>`;

  // Payload
  if (data.payload && Object.keys(data.payload).length) {
    html += `<div class="card" style="margin-top:16px"><div class="card-title">작업 입력값</div><div class="result-viewer">${escapeHtml(JSON.stringify(data.payload, null, 2))}</div></div>`;
  }

  // Transitions timeline
  if (data.transitions && data.transitions.length) {
    html += `<div class="card" style="margin-top:16px"><div class="card-title">상태 전이</div><div class="timeline">`;
    for (const t of data.transitions) {
      html += `<div class="timeline-item">${statusBadge(t.to_status)} <span class="time">${fmtTime(t.at)}</span>${t.reason ? ` — ${escapeHtml(t.reason)}` : ''}</div>`;
    }
    html += `</div></div>`;
  }

  // Result
  if (data.result) {
    const resultText = JSON.stringify(data.result, null, 2);
    html += `<div class="card" style="margin-top:16px"><div class="card-title">결과</div><div class="result-viewer">${escapeHtml(resultText)}</div></div>`;
  }

  html += `<div style="margin-top:16px">${canCancel(data.status) ? `<button class="btn btn-danger" onclick="cancelJob('${jobId}');closeModal()">작업 취소</button>` : ''}</div>`;

  el.innerHTML = html;
  document.getElementById('job-modal').classList.add('active');
}

function closeModal() {
  document.getElementById('job-modal').classList.remove('active');
}

/* ── Submit: topic_research ── */
async function submitTopicResearch() {
  const keyword = document.getElementById('tr-keyword').value.trim();
  if (!keyword) { showToast('키워드를 입력하세요', 'error'); return; }
  const payload = {
    keyword,
    language: document.getElementById('tr-language').value,
    country: document.getElementById('tr-country').value.trim() || 'global',
    count: parseInt(document.getElementById('tr-count').value) || 10,
  };
  const res = await api('POST', '/api/jobs/submit', { job_type: 'topic_research', payload });
  if (res && res.job_id) {
    showToast(`주제 찾기 작업이 제출되었습니다: ${res.job_id.substring(0,8)}`);
    switchTab('history');
  } else {
    showToast('작업 제출 실패', 'error');
  }
}

/* ── Submit: topic_benchmark_analyze ── */
async function submitBenchmark() {
  const keyword = document.getElementById('ba-keyword').value.trim();
  if (!keyword) { showToast('키워드를 입력하세요', 'error'); return; }
  const payload = {
    keyword,
    language: document.getElementById('ba-language').value,
    video_type: document.getElementById('ba-video-type').value,
    max_candidates: parseInt(document.getElementById('ba-max-candidates').value) || 1,
  };
  const res = await api('POST', '/api/jobs/submit', { job_type: 'topic_benchmark_analyze', payload });
  if (res && res.job_id) {
    showToast(`벤치마크 분석 작업이 제출되었습니다: ${res.job_id.substring(0,8)}`);
    switchTab('history');
  } else {
    showToast('작업 제출 실패', 'error');
  }
}

/* ── Submit: script_plan_generate ── */
let notebookLMUploadedSources = [];
let notebookLMLastResultId = '';

async function handleNotebookLMFiles(files) {
  const statusEl = document.getElementById('nlm-file-status');
  const sourceEl = document.getElementById('nlm-source');
  const selected = Array.from(files || []);
  if (!selected.length) return;
  if (statusEl) statusEl.textContent = `${selected.length}개 파일 텍스트 추출 중...`;
  for (const file of selected) {
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await fetch('/api/notebooklm/extract-file', { method: 'POST', body: form });
      if (res.status === 401) {
        window.location.href = '/login';
        return;
      }
      const data = await res.json();
      if (!res.ok || data.success === false) {
        throw new Error(data.detail || data.error || '파일 추출 실패');
      }
      const block = `\n\n[업로드 파일: ${data.filename}]\n${data.text || ''}`;
      notebookLMUploadedSources.push({ filename: data.filename, chars: data.chars || 0 });
      if (sourceEl) sourceEl.value = `${sourceEl.value || ''}${block}`.trim();
    } catch (e) {
      showToast(`${file.name} 추출 실패: ${e.message || e}`, 'error');
    }
  }
  if (statusEl) {
    const total = notebookLMUploadedSources.reduce((sum, item) => sum + (item.chars || 0), 0);
    statusEl.textContent = `${notebookLMUploadedSources.length}개 파일 추출 완료 · ${total.toLocaleString()}자`;
  }
}

async function submitNotebookLM() {
  const sourceEl = document.getElementById('nlm-source');
  const resultEl = document.getElementById('nlm-result');
  const submitEl = document.getElementById('nlm-submit');
  const sendEl = document.getElementById('nlm-send-hermes');
  const sendHintEl = document.getElementById('nlm-send-hermes-hint');
  const sourceText = sourceEl?.value?.trim() || '';
  const sourceUrls = document.getElementById('nlm-urls')?.value?.trim() || '';
  const sourcePaths = document.getElementById('nlm-paths')?.value?.trim() || '';
  if (!sourceText && !sourceUrls && !sourcePaths) {
    showToast('참고 자료, URL, 파일 경로 중 하나 이상 입력하세요.', 'error');
    return;
  }
  const body = {
    source_text: sourceText,
    source_urls: sourceUrls,
    source_paths: sourcePaths,
    mode: document.getElementById('nlm-mode')?.value || 'dialogue_podcast',
    category: document.getElementById('nlm-category')?.value?.trim() || '옛날이야기',
    duration_minutes: parseInt(document.getElementById('nlm-duration')?.value, 10) || 15,
    custom_title: document.getElementById('nlm-title')?.value?.trim() || '',
  };
  if (submitEl) {
    submitEl.disabled = true;
    submitEl.textContent = 'NotebookLM 대본 생성 중...';
  }
  notebookLMLastResultId = '';
  if (sendEl) sendEl.disabled = true;
  if (sendHintEl) sendHintEl.textContent = 'NotebookLM 대본 생성 중입니다.';
  if (resultEl) {
    resultEl.innerHTML = '<div class="info">워커에서 Gemini/Claude 기반 대본을 생성하는 중입니다...</div>';
  }
  try {
    const data = await api('POST', '/api/notebooklm/generate', body);
    if (!data || data.success === false) {
      throw new Error(data?.detail || data?.error || 'NotebookLM 대본 생성 실패');
    }
    const result = data.result || {};
    const scenes = Array.isArray(result.scenes) ? result.scenes : [];
    const script = result.full_script || result.script || '';
    notebookLMLastResultId = data.id || '';
    if (sendEl) sendEl.disabled = !notebookLMLastResultId;
    if (sendHintEl) {
      sendHintEl.textContent = notebookLMLastResultId
        ? '생성 결과를 기존 Hermes 결과 확인/TTS/렌더 흐름으로 보냅니다.'
        : '결과 ID가 없어 보낼 수 없습니다.';
    }
    const sourceRows = (data.sources || []).map(src => {
      const label = src.value || src.filename || src.type || '-';
      const detail = src.error ? `오류: ${src.error}` : `${(src.chars || 0).toLocaleString()}자`;
      return `<div class="label">${escapeHtml(src.type || '-')}</div><div>${escapeHtml(label)} <span class="info">${escapeHtml(detail)}</span></div>`;
    }).join('');
    if (resultEl) {
      resultEl.innerHTML = `
        <div class="generated-section">
          <h4>기본 정보</h4>
          <div class="generated-meta">
            <div class="label">결과 ID</div><div>${escapeHtml(data.id || '-')}</div>
            <div class="label">제목</div><div><strong>${escapeHtml(result.title || '-')}</strong></div>
            <div class="label">카테고리</div><div>${escapeHtml(result.category || body.category)}</div>
            <div class="label">모드</div><div>${escapeHtml(result.dialogue_mode ? '2인 대화 팟캐스트' : '1인 심층 내레이션')}</div>
            <div class="label">씬 수</div><div>${scenes.length}</div>
          </div>
        </div>
        <div class="generated-section">
          <h4>참고자료 수집</h4>
          <div class="generated-meta">${sourceRows || '<div class="label">source</div><div>-</div>'}</div>
        </div>
        <div class="generated-section">
          <h4>훅</h4>
          <div class="prompt-box">${escapeHtml(result.hook || '-')}</div>
        </div>
        <div class="generated-section">
          <h4>대본</h4>
          <div class="result-viewer" style="max-height:420px">${escapeHtml(script || '-')}</div>
        </div>
        <div class="generated-section">
          <h4>씬 JSON</h4>
          <div class="result-viewer" style="max-height:320px">${escapeHtml(JSON.stringify(scenes.slice(0, 60), null, 2))}</div>
        </div>`;
    }
    showToast(`NotebookLM 대본 생성 완료: ${data.id}`);
  } catch (e) {
    if (resultEl) {
      resultEl.innerHTML = `<div class="prompt-box prompt-box-error">${escapeHtml(e.message || String(e))}</div>`;
    }
    showToast(`NotebookLM 대본 생성 실패: ${e.message || e}`, 'error');
  } finally {
    if (submitEl) {
      submitEl.disabled = false;
      submitEl.textContent = 'NotebookLM 대본 생성';
    }
  }
}

async function sendNotebookLMToHermes(resultId) {
  const targetId = resultId || notebookLMLastResultId;
  if (!targetId) {
    showToast('NotebookLM 결과 ID가 없습니다.', 'error');
    return;
  }
  const resultEl = document.getElementById('nlm-result');
  try {
    const data = await api('POST', `/api/notebooklm/${encodeURIComponent(targetId)}/send-to-hermes`);
    if (!data || data.success === false) {
      throw new Error(data?.detail || data?.error || 'Hermes 패키지 변환 실패');
    }
    showToast(`Hermes 패키지 저장 완료: ${data.id}`);
    if (resultEl) {
      const notice = document.createElement('div');
      notice.className = 'prompt-box';
      notice.innerHTML = `Hermes 패키지로 저장했습니다: <strong>${escapeHtml(data.id)}</strong><br>씬 ${data.scene_count || 0}개, 대본 ${(data.script_chars || 0).toLocaleString()}자`;
      resultEl.prepend(notice);
    }
    generatedResultsLoaded = false;
    switchTab('generated-results');
  } catch (e) {
    showToast(`Hermes 패키지 변환 실패: ${e.message || e}`, 'error');
  }
}

async function submitScriptPlan() {
  const topic = document.getElementById('sp-topic').value.trim();
  if (!topic) { showToast('주제를 입력하세요', 'error'); return; }
  const payload = {
    topic_queue_id: 'dashboard-' + Date.now(),
    topic,
    target_duration_seconds: parseInt(document.getElementById('sp-duration').value) || 600,
    script_style: document.getElementById('sp-style').value,
    language: document.getElementById('sp-language').value,
  };
  const res = await api('POST', '/api/jobs/submit', { job_type: 'script_plan_generate', payload });
  if (res && res.job_id) {
    showToast(`구조 생성 작업이 제출되었습니다: ${res.job_id.substring(0,8)}`);
    switchTab('history');
  } else {
    showToast('작업 제출 실패', 'error');
  }
}

/* ── Submit: script_generate ── */
async function submitScriptGenerate() {
  const topic = document.getElementById('sg-topic').value.trim();
  if (!topic) { showToast('주제를 입력하세요', 'error'); return; }
  let structure = undefined;
  const structText = document.getElementById('sg-structure').value.trim();
  if (structText) {
    try { structure = JSON.parse(structText); }
    catch(e) { showToast('구조 JSON 파싱 오류', 'error'); return; }
  }
  const payload = {
    topic_queue_id: 'dashboard-' + Date.now(),
    topic,
    structure: structure || null,
    target_duration_seconds: parseInt(document.getElementById('sg-duration').value) || 600,
    script_style: document.getElementById('sg-style').value,
    language: 'ko',
    narration_mode: document.getElementById('sg-narration-mode').value,
  };
  const res = await api('POST', '/api/jobs/submit', { job_type: 'script_generate', payload });
  if (res && res.job_id) {
    showToast(`대본 생성 작업이 제출되었습니다: ${res.job_id.substring(0,8)}`);
    switchTab('history');
  } else {
    showToast('작업 제출 실패', 'error');
  }
}

/* ── Cancel job ── */
async function cancelJob(jobId) {
  const res = await api('POST', `/api/jobs/${jobId}/cancel`);
  if (res && res.success !== false) {
    showToast(`작업 ${jobId.substring(0,8)} 취소됨`);
    refreshAll();
  } else {
    showToast(`취소 실패: ${res?.error || '알 수 없음'}`, 'error');
  }
}

/* ── Cancel helper ── */
function canCancel(status) {
  return ['QUEUED','CLAIMED','PREPARING','RENDERING','UPLOADING'].includes(status);
}

/* ── Process start / stop ── */
const PROCESS_API_NAME = { hermes_worker: 'hermes', render_worker: 'render', remote_drive_worker: 'remote-drive' };

async function startProcess(name) {
  try {
    if (window.latestWorkerStatus?.allowed_processes && !window.latestWorkerStatus.allowed_processes.includes(name)) {
      showToast(`${name} is disabled by AIRWORKER_PROFILE=${window.latestWorkerStatus.worker_profile || 'full'}`, 'warning');
      return;
    }
    const apiName = PROCESS_API_NAME[name] || name;
    const res = await api('POST', `/api/processes/${apiName}/start`);
    showToast(`${{hermes_worker:'AI 기획·대본 Worker', render_worker:'영상 작업 Worker'}[name] || name} 시작을 요청했습니다.`, 'info');
    setTimeout(refreshAll, 1500);
  } catch(e) {
    showToast(`시작 실패: ${e}`, 'error');
  }
}

async function startHermesForLimit() {
  const input = document.getElementById('hermes-start-limit');
  const targetLimit = Number.parseInt(input?.value, 10);
  if (!Number.isInteger(targetLimit) || targetLimit < 1 || targetLimit > 100) {
    showToast('생성 수는 1~100 사이로 입력하세요.', 'error');
    input?.focus();
    return;
  }

  try {
    const worker = await api('POST', '/api/processes/hermes/start');
    if (!worker?.success) {
      showToast('AI 기획·대본 Worker 시작 실패: ' + (worker?.error || '응답 없음'), 'error');
      return;
    }

    const autoStartInput = document.getElementById('auto-start-limit');
    if (autoStartInput) autoStartInput.value = String(targetLimit);
    const autopilot = await api('POST', '/api/autopilot/hermes/start', {
      settings: { mode: 'target_limit', target_limit: targetLimit },
    });
    if (!autopilot?.success) {
      showToast('자동 생성 시작 실패: ' + (autopilot?.error || '응답 없음'), 'error');
      return;
    }

    showToast(`AI Worker가 ${targetLimit}개 생성한 뒤 자동 생성을 멈춥니다.`, 'success');
    setTimeout(refreshAll, 1000);
  } catch (e) {
    showToast('AI Worker 시작 통신 실패', 'error');
  }
}

async function stopHermesGeneration() {
  try {
    const result = await api('POST', '/api/autopilot/hermes/stop');
    if (result?.success) {
      const cancelled = Number(result.cancelled_job_count || 0);
      showToast(`AI 기획·대본 Worker를 중지했습니다. 남은 자동 작업 ${cancelled}개도 취소했습니다.`, 'info');
    } else {
      showToast('AI 기획·대본 Worker 중지 실패: ' + (result?.error || '응답 없음'), 'error');
    }
    setTimeout(refreshAll, 1000);
  } catch (e) {
    showToast('AI Worker 중지 통신 실패', 'error');
  }
}

async function stopProcess(name) {
  try {
    if (window.latestWorkerStatus?.allowed_processes && !window.latestWorkerStatus.allowed_processes.includes(name)) {
      showToast(`${name} is disabled by AIRWORKER_PROFILE=${window.latestWorkerStatus.worker_profile || 'full'}`, 'warning');
      return;
    }
    const apiName = PROCESS_API_NAME[name] || name;
    const res = await api('POST', `/api/processes/${apiName}/stop`);
    showToast(`${{hermes_worker:'AI 기획·대본 Worker', render_worker:'영상 작업 Worker'}[name] || name} 중지를 요청했습니다.`, 'info');
    setTimeout(refreshAll, 1500);
  } catch(e) {
    showToast(`중지 실패: ${e}`, 'error');
  }
}

/* ── Utility ── */
function truncate(s, n) { return s && s.length > n ? s.substring(0, n) + '...' : (s || ''); }
function escapeHtml(s) { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

/* ── Refresh all ── */
async function refreshAll() {
  if (refreshAllInFlight) {
    return;
  }
  refreshAllInFlight = true;
  countdown = 3;
  try {
    const [jobs, status, renderJobsData] = await Promise.all([
      api('GET', '/api/jobs?limit=50'),
      api('GET', '/api/status'),
      api('GET', '/api/rendering-jobs?limit=10'),
    ]);
    if (renderJobsData) {
      checkNewRenderJobs(renderJobsData.jobs, renderJobsData.pending_count || 0);
    }
    if (!status) return;
    window.latestWorkerStatus = status;
    const recentJobs = jobs?.jobs || [];
    renderProcessCards(status, recentJobs);
    renderRecentJobs(recentJobs);

    // Refresh active tab-specific data
    const activeTab = document.querySelector('.nav-item.active')?.dataset.tab;
    if (activeTab === 'rendering') loadRenderTab();
    if (activeTab === 'history') loadHistory();
    if (activeTab === 'hermes-autopilot') loadAutopilotStatus();
  } catch(e) { /* silent */ }
  finally {
    refreshAllInFlight = false;
  }
}

/* ── Auto-refresh countdown ── */
setInterval(() => {
  countdown--;
  if (countdown <= 0) { countdown = 3; refreshAll(); }
  document.getElementById('refresh-timer').textContent = `${countdown}s 후 새로고침`;
}, 1000);

/* ── Logout ── */
async function doLogout() {
  await fetch('/auth/logout', { method: 'POST' });
  window.location.href = '/login';
}

/* ══════════════════════════════════════════════
   Settings Tab
   ══════════════════════════════════════════════ */

/* Setting label map for Korean UI */
const settingLabels = {
  'GEMINI_API_KEY': 'Gemini API Key',
  'CLAUDE_API_KEY': 'Claude API Key',
  'DEEPSEEK_API_KEY': 'DeepSeek API Key',
  'DEEPSEEK_BASE_URL': 'DeepSeek Base URL',
  'GLM_API_KEY': 'GLM API Key',
  'GLM_BASE_URL': 'GLM Base URL',
  'YOUTUBE_API_KEY': 'YouTube API Key',
  'YOUTUBE_API_KEYS': 'YouTube Backup API Keys',
  'ELEVENLABS_API_KEY': 'ElevenLabs API Key',
  'SUNO_API_KEY': 'Suno API Key',
  'TOPIC_GENERATION_MODEL': '제목 생성 모델',
  'TITLE_GENERATION_MODEL': '제목 후보 모델',
  'SCRIPT_GENERATION_MODEL': '대본 생성 모델',
  'SCRIPT_PLANNING_MODEL': '구조 생성 모델',
  'IMAGE_PROMPT_MODEL': '이미지/영상 프롬프트 모델',
};

/* Icons for API keys vs model settings */
const settingIcons = {
  'GEMINI_API_KEY': '&#x1F4E7;',
  'CLAUDE_API_KEY': '&#x1F4E7;',
  'DEEPSEEK_API_KEY': '&#x1F4E7;',
  'DEEPSEEK_BASE_URL': '&#x1F310;',
  'GLM_API_KEY': '&#x1F4E7;',
  'GLM_BASE_URL': '&#x1F310;',
  'YOUTUBE_API_KEY': '&#x1F3AC;',
  'YOUTUBE_API_KEYS': '&#x1F3AC;',
  'ELEVENLABS_API_KEY': '&#x1F3A4;',
  'SUNO_API_KEY': '&#x1F3B5;',
  'TOPIC_GENERATION_MODEL': '&#x1F916;',
  'TITLE_GENERATION_MODEL': '&#x1F916;',
  'SCRIPT_GENERATION_MODEL': '&#x1F916;',
  'SCRIPT_PLANNING_MODEL': '&#x1F916;',
  'IMAGE_PROMPT_MODEL': '&#x1F3A8;',
};

/* Track original values for dirty detection */
let settingsOriginal = {};


async function loadWorkerProfileSettings() {
  try {
    const data = await api('GET', '/api/worker-profile-settings');
    if (!data) return;
    const profileEl = document.getElementById('worker-set-profile');
    const idEl = document.getElementById('worker-set-id');
    const urlEl = document.getElementById('worker-set-server-url');
    const tokenEl = document.getElementById('worker-set-token');
    const badgeEl = document.getElementById('worker-profile-badge');

    if (profileEl) profileEl.value = data.worker_profile || 'full';
    if (idEl) idEl.value = data.worker_id || '';
    if (urlEl) urlEl.value = data.central_server_url || '';
    if (tokenEl) {
      tokenEl.value = data.worker_token || '';
      tokenEl.placeholder = data.worker_token_set ? '•••••••• (설정됨)' : '중앙 서버 발급 토큰';
    }
    if (badgeEl) {
      const modeNames = { 'render_only': '🎬 렌더링 전용', 'content_only': '📝 대본 기획 전용', 'full': '🚀 전체 통합' };
      badgeEl.textContent = `현재 모드: ${modeNames[data.worker_profile] || data.worker_profile}`;
    }
  } catch (e) {
    console.error('loadWorkerProfileSettings error:', e);
  }
}

async function saveWorkerProfileSettings(restartAfterSave = true) {
  const profile = document.getElementById('worker-set-profile').value;
  const worker_id = document.getElementById('worker-set-id').value.trim();
  const central_server_url = document.getElementById('worker-set-server-url').value.trim();
  const worker_token = document.getElementById('worker-set-token').value.trim();
  const statusEl = document.getElementById('worker-settings-status');

  statusEl.textContent = '저장 중...';
  statusEl.style.color = '#8b949e';

  try {
    const res = await api('POST', '/api/worker-profile-settings', {
      worker_profile: profile,
      worker_id: worker_id,
      central_server_url: central_server_url,
      worker_token: worker_token,
    });

    if (res && res.success) {
      showToast('워커 설정이 .env에 성공적으로 저장되었습니다.');
      statusEl.textContent = '저장 완료';
      statusEl.style.color = '#3fb950';
      await loadWorkerProfileSettings();

      if (restartAfterSave) {
        if (confirm('수정된 워커 모드를 적용하기 위해 지금 워커 서버를 재시작하시겠습니까?')) {
          confirmRestartServer();
        }
      }
    } else {
      showToast(`저장 실패: ${res?.error || '알 수 없음'}`, 'error');
      statusEl.textContent = '저장 실패';
      statusEl.style.color = '#f85149';
    }
  } catch (e) {
    statusEl.textContent = '오류: ' + e.message;
    statusEl.style.color = '#f85149';
  }
}

async function loadSettings() {
  loadWorkerProfileSettings();
  const data = await api('GET', '/api/settings');
  if (!data) return;
  const list = data.settings || [];
  const container = document.getElementById('settings-list');
  settingsOriginal = {};

  let html = '';
  for (const item of list) {
    const label = settingLabels[item.key] || item.key;
    const icon = settingIcons[item.key] || '&#x2699;';
    const placeholder = item.value || '';
    const setLabel = item.set ? '<span style="color:#3fb950;font-size:12px;margin-left:8px">&#x2714; 설정됨</span>' : '<span style="color:#8b949e;font-size:12px;margin-left:8px">미설정</span>';
    const inputControl = item.key === 'YOUTUBE_API_KEYS'
      ? `<textarea id="setting-${escapeHtml(item.key)}" class="setting-input"
            placeholder="${escapeHtml(placeholder)}"
            rows="4"
            style="width:100%;padding:8px 12px;border:1px solid #30363d;border-radius:6px;background:#0d1117;color:#e1e4e8;font-size:13px;font-family:monospace;outline:none;resize:vertical;"
          ></textarea>
          <div style="margin-top:4px;color:#8b949e;font-size:12px;">최대 5개까지 쉼표 또는 줄바꿈으로 입력하면 한도 초과 시 순서대로 대체 사용됩니다.</div>`
      : `<input type="text" id="setting-${escapeHtml(item.key)}" class="setting-input"
            placeholder="${escapeHtml(placeholder)}"
            style="width:100%;padding:8px 12px;border:1px solid #30363d;border-radius:6px;background:#0d1117;color:#e1e4e8;font-size:13px;font-family:monospace;outline:none;"
            onkeydown="if(event.key==='Enter'){event.preventDefault();saveSetting('${escapeHtml(item.key)}')}"
          />`;
    html += `
      <div class="setting-row" style="display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid #21262d;" data-key="${escapeHtml(item.key)}">
        <span style="font-size:18px;width:28px;text-align:center;">${icon}</span>
        <div style="flex:1;min-width:0;">
          <div style="font-weight:600;font-size:14px;margin-bottom:4px;">
            ${escapeHtml(label)} ${setLabel}
          </div>
          ${inputControl}
        </div>
        <button class="btn btn-sm btn-primary" onclick="saveSetting('${escapeHtml(item.key)}')" style="white-space:nowrap;">저장</button>
      </div>`;
    settingsOriginal[item.key] = item.value;
  }
  container.innerHTML = html;
  const apiSettingKeys = new Set([
    'GEMINI_API_KEY',
    'CLAUDE_API_KEY',
    'DEEPSEEK_API_KEY',
    'DEEPSEEK_BASE_URL',
    'GLM_API_KEY',
    'GLM_BASE_URL',
    'YOUTUBE_API_KEY',
    'YOUTUBE_API_KEYS',
    'ELEVENLABS_API_KEY',
    'SUNO_API_KEY',
  ]);
  const apiRows = [];
  const modelRows = [];
  for (const row of Array.from(container.querySelectorAll('.setting-row'))) {
    row.style.alignItems = 'flex-start';
    row.style.borderBottom = '1px solid #21262d';
    row.style.padding = '12px 0';
    const key = row.getAttribute('data-key') || '';
    if (apiSettingKeys.has(key)) apiRows.push(row.outerHTML);
    else modelRows.push(row.outerHTML);
  }
  container.innerHTML = `
    <div class="settings-grid">
      <div class="settings-panel">
        <div class="settings-panel-title">API Keys</div>
        <div class="settings-panel-note">YouTube primary and backup keys live here. Backup keys are used in order, up to 5 total keys.</div>
        ${apiRows.join('')}
      </div>
      <div class="settings-panel">
        <div class="settings-panel-title">Model Settings</div>
        <div class="settings-panel-note">Models used by Hermes for topics, titles, scripts, structure, and prompt generation.</div>
        ${modelRows.join('')}
      </div>
    </div>`;
  document.getElementById('settings-status').textContent = '';
}

async function saveSetting(key) {
  const input = document.getElementById('setting-' + key);
  const value = input.value.trim();
  const statusEl = document.getElementById('settings-status');
  statusEl.textContent = '저장 중...';
  statusEl.style.color = '#8b949e';

  const res = await api('POST', '/api/settings', { key, value });
  if (res && res.success) {
    showToast(`${settingLabels[key] || key} 저장 완료`);
    statusEl.textContent = '';
    await loadSettings();
  } else {
    showToast(`저장 실패: ${res?.error || '알 수 없음'}`, 'error');
    statusEl.textContent = '저장 실패';
    statusEl.style.color = '#f85149';
  }
}

async function saveAllSettings() {
  const inputs = document.querySelectorAll('.setting-input');
  let savedCount = 0;
  let errorCount = 0;
  const statusEl = document.getElementById('settings-status');
  statusEl.textContent = '저장 중...';
  statusEl.style.color = '#8b949e';

  for (const input of inputs) {
    const key = input.id.replace('setting-', '');
    const value = input.value.trim();
    // Only save if the user actually typed something new (not just the placeholder hint)
    if (value === '') continue;
    const res = await api('POST', '/api/settings', { key, value });
    if (res && res.success) savedCount++;
    else errorCount++;
  }

  if (errorCount === 0 && savedCount > 0) {
    showToast(`${savedCount}개 설정 저장 완료`);
    statusEl.textContent = '';
    await loadSettings();
  } else if (savedCount > 0) {
    showToast(`${savedCount}개 저장 완료, ${errorCount}개 실패`, 'warning');
    statusEl.textContent = `${savedCount}개 성공, ${errorCount}개 실패`;
    statusEl.style.color = '#d29922';
    await loadSettings();
  } else {
    showToast('변경사항 없음', 'info');
    statusEl.textContent = '변경사항 없음';
    statusEl.style.color = '#8b949e';
  }
}

/* ── YouTube Explore ── */
let ytExploreInitialized = false;
const BUBBLE_COLORS = {
  'Entertainment': '#58a6ff', 'Gaming': '#3fb950', 'Music': '#a371f7',
  'Technology': '#d29922', 'Education': '#f85149', 'Sports': '#79c0ff',
  'News': '#ffa657', 'Lifestyle': '#ff7b72', 'Cooking': '#d2a8ff',
  'Travel': '#7ee787', 'Finance': '#f0883e', 'Health': '#56d364',
  'Science': '#bc8cff', 'Comedy': '#79c0ff', 'Film': '#db61a2',
};
const BUBBLE_FALLBACK = '#8b949e';

function initYtExplore() {
  if (ytExploreInitialized) return;
  ytExploreInitialized = true;
  document.querySelectorAll('.yt-lang-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.yt-lang-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      loadTrendKeywords();
    });
  });
  loadTrendKeywords();
}

async function loadTrendKeywords() {
  const lang = (document.querySelector('.yt-lang-btn.active') || {}).dataset?.lang || 'ko';
  const period = document.getElementById('yt-period').value;
  const age = document.getElementById('yt-age').value;
  const cacheKey = 'yt-trending-' + lang;
  const cached = localStorage.getItem(cacheKey);
  if (cached) {
    try { renderBubbleChart(JSON.parse(cached)); } catch(e) {}
  }
  document.getElementById('bubble-loading').style.display = 'flex';
  try {
    const data = await api('GET', '/api/yt/trending-keywords?language=' + lang + '&period=' + period + '&age=' + age);
    if (data && data.error) {
      document.getElementById('bubble-chart').innerHTML = '<div style="text-align:center;padding:80px;color:#f85149">⚠ ' + data.error + '</div>';
    } else if (data && data.keywords && data.keywords.length > 0) {
      localStorage.setItem(cacheKey, JSON.stringify(data.keywords));
      renderBubbleChart(data.keywords);
    } else if (!cached) {
      document.getElementById('bubble-chart').innerHTML = '<div style="text-align:center;padding:80px;color:#8b949e">키워드 생성 결과가 비어있습니다. 다시 시도해주세요.</div>';
    }
  } catch(e) {
    console.error('loadTrendKeywords error:', e);
    document.getElementById('bubble-chart').innerHTML = '<div style="text-align:center;padding:80px;color:#f85149">⚠ 네트워크 오류: ' + e.message + '</div>';
  } finally {
    document.getElementById('bubble-loading').style.display = 'none';
  }
}

function renderBubbleChart(keywords) {
  const container = document.getElementById('bubble-chart');
  const width = container.parentElement.clientWidth || 800;
  const height = 420;
  d3.select('#bubble-chart').selectAll('*').remove();
  const svg = d3.select('#bubble-chart').append('svg')
    .attr('width', width).attr('height', height);
  const g = svg.append('g');
  const data = keywords.map((k, i) => ({
    id: i, keyword: k.keyword || '', translation: k.translation || '',
    volume: Math.max(Number(k.volume) || 20, 15),
    category: k.category || 'Other'
  }));
  const sizeScale = d3.scaleLinear().domain([15, 100]).range([40, 120]);
  const nodes = data.map(d => ({
    ...d, w: sizeScale(d.volume), h: sizeScale(d.volume) * 0.55
  }));
  const simulation = d3.forceSimulation(nodes)
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('charge', d3.forceManyBody().strength(5))
    .force('collision', d3.forceCollide().radius(d => Math.max(d.w, d.h) / 2 + 4).iterations(3))
    .force('x', d3.forceX(width / 2).strength(0.05))
    .force('y', d3.forceY(height / 2).strength(0.05));
  const nodeGroup = g.selectAll('g.bubble-node')
    .data(nodes).enter().append('g')
    .attr('class', 'bubble-node').call(d3.drag()
      .on('start', (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on('end', (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
    );
  nodeGroup.append('rect')
    .attr('rx', 8).attr('ry', 8)
    .attr('width', d => d.w).attr('height', d => d.h)
    .attr('x', d => -d.w / 2).attr('y', d => -d.h / 2)
    .attr('fill', d => (BUBBLE_COLORS[d.category] || BUBBLE_FALLBACK) + '22')
    .attr('stroke', d => BUBBLE_COLORS[d.category] || BUBBLE_FALLBACK)
    .attr('stroke-width', 1.5)
    .attr('cursor', 'pointer')
    .on('click', (e, d) => {
      document.getElementById('yt-search-query').value = d.keyword;
      searchYtVideos();
    });
  nodeGroup.append('text')
    .attr('text-anchor', 'middle').attr('dy', '-0.1em')
    .attr('fill', '#c9d1d9').attr('font-size', d => Math.max(10, Math.min(d.w * 0.15, 16)))
    .attr('font-weight', d => d.volume > 70 ? '700' : '400')
    .attr('pointer-events', 'none')
    .text(d => d.keyword.length > 12 ? d.keyword.slice(0, 11) + '…' : d.keyword);
  nodeGroup.append('text')
    .attr('text-anchor', 'middle').attr('dy', '1.2em')
    .attr('fill', '#8b949e').attr('font-size', d => Math.max(8, Math.min(d.w * 0.1, 12)))
    .attr('pointer-events', 'none')
    .text(d => d.volume);
  simulation.on('tick', () => {
    nodeGroup.attr('transform', d => 'translate(' + d.x + ',' + d.y + ')');
  });
}

async function searchYtVideos() {
  const query = document.getElementById('yt-search-query').value.trim();
  if (!query) return;
  const order = document.getElementById('yt-search-order').value;
  const period = document.getElementById('yt-search-period').value;
  const lang = document.getElementById('yt-search-lang').value;
  const body = { query, order, max_results: 12 };
  if (period) {
    const now = new Date();
    if (period === 'now') now.setDate(now.getDate() - 1);
    else if (period === 'week') now.setDate(now.getDate() - 7);
    else if (period === 'month') now.setMonth(now.getMonth() - 1);
    body.published_after = now.toISOString();
  }
  if (lang) body.relevance_language = lang;
  const loading = document.getElementById('yt-search-loading');
  const card = document.getElementById('yt-results-card');
  loading.style.display = 'block';
  card.style.display = 'block';
  document.getElementById('yt-results-body').innerHTML = '';
  document.getElementById('yt-result-count').textContent = '0';
  let searchError = null;
  try {
    const searchResult = await api('POST', '/api/yt/search', body);
    if (!searchResult || searchResult.error) {
      searchError = searchResult?.error || '검색 요청 실패';
      return;
    }
    const items = searchResult.items || [];
    if (items.length === 0) {
      searchError = 'EMPTY';
      return;
    }
    const videoIds = items.map(i => i.id.videoId).filter(Boolean).join(',');
    const channelIds = [...new Set(items.map(i => i.snippet.channelId).filter(Boolean))].join(',');
    const [videosRes, channelsRes] = await Promise.all([
      api('GET', '/api/yt/videos/' + videoIds),
      channelIds ? api('GET', '/api/yt/channel/' + channelIds) : Promise.resolve(null)
    ]);
    const videoMap = {};
    if (videosRes && videosRes.items) {
      videosRes.items.forEach(v => { videoMap[v.id] = v; });
    }
    const channelMap = {};
    if (channelsRes && channelsRes.items) {
      channelsRes.items.forEach(c => { channelMap[c.id] = c; });
    }
    const videos = items
      .filter(i => i.id && i.id.videoId && videoMap[i.id.videoId])
      .map(i => {
        const v = videoMap[i.id.videoId];
        const ch = channelMap[i.snippet.channelId] || {};
        const stats = v.statistics || {};
        const chStats = ch.statistics || {};
        const views = parseInt(stats.viewCount) || 0;
        const likes = parseInt(stats.likeCount) || 0;
        const subs = parseInt(chStats.subscriberCount) || 1;
        const chViews = parseInt(chStats.viewCount) || 0;
        const chCount = parseInt(chStats.videoCount) || 1;
        const chAvgViews = chViews / chCount;
        const contribution = chAvgViews > 0 ? ((views / chAvgViews) * 100) : 0;
        const performance = views / subs;
        return {
          videoId: v.id,
          title: v.snippet.title,
          thumbnail: (v.snippet.thumbnails || {}).high?.url || (v.snippet.thumbnails || {}).medium?.url || '',
          channelTitle: v.snippet.channelTitle,
          channelId: v.snippet.channelId,
          channelAvatar: (ch.snippet || {}).thumbnails?.default?.url || '',
          publishedAt: v.snippet.publishedAt,
          views, likes, subs, comments: parseInt(stats.commentCount) || 0,
          duration: (v.contentDetails || {}).duration || '',
          contribution: Math.round(contribution),
          performance: performance.toFixed(2),
          tags: (v.snippet || {}).tags || [],
        };
      });
    renderYtResults(videos);
    renderSuggestedTags(videos);
  } catch(e) {
    console.error('searchYtVideos error:', e);
    searchError = e.message || '네트워크 오류';
  } finally {
    loading.style.display = 'none';
    if (searchError) {
      document.getElementById('yt-results-body').innerHTML =
        '<tr><td colspan="11" style="text-align:center;padding:40px;color:#f85149">⚠ ' + searchError + '</td></tr>';
    }
  }
}

function renderYtResults(videos) {
  const tbody = document.getElementById('yt-results-body');
  document.getElementById('yt-result-count').textContent = videos.length;
  tbody.innerHTML = videos.map((v, i) => {
    const viralClass = v.contribution > 200 ? 'yt-viral-high' : v.contribution > 50 ? 'yt-viral-mid' : 'yt-viral-low';
    return '<tr>' +
      '<td style="text-align:center;color:#8b949e;font-size:12px">' + (i + 1) + '</td>' +
      '<td><img class="yt-thumb" src="' + escHtml(v.thumbnail) + '" loading="lazy" onerror="this.style.display=\'none\'"></td>' +
      '<td class="yt-title-cell" title="' + escHtml(v.title) + '">' +
        '<a href="https://youtube.com/watch?v=' + v.videoId + '" target="_blank" style="color:#c9d1d9;font-size:13px">' + escHtml(v.title) + '</a>' +
        '<div style="font-size:11px;color:#8b949e;margin-top:2px">' + parseDuration(v.duration) + '</div>' +
      '</td>' +
      '<td style="font-size:12px">' +
        '<img class="yt-channel-avatar" src="' + escHtml(v.channelAvatar) + '" onerror="this.style.display=\'none\'">' +
        escHtml(v.channelTitle) +
      '</td>' +
      '<td style="font-size:12px;color:#8b949e">' + formatDate(v.publishedAt) + '</td>' +
      '<td style="font-size:12px;text-align:right">' + formatNum(v.views) + '</td>' +
      '<td style="font-size:12px;text-align:right">' + formatNum(v.subs) + '</td>' +
      '<td style="text-align:center"><span class="yt-viral-score ' + viralClass + '">' + v.contribution + '%</span></td>' +
      '<td style="font-size:12px;text-align:right;color:#58a6ff">' + v.performance + 'x</td>' +
      '<td style="font-size:12px;text-align:right">' + formatNum(v.likes) + '</td>' +
      '<td style="text-align:center"><button class="btn btn-sm" onclick="openYtAnalysis(' + i + ')" style="font-size:11px">분석</button></td>' +
    '</tr>';
  }).join('');
  window._ytResults = videos;
}

function renderSuggestedTags(videos) {
  const tagCount = {};
  videos.forEach(v => {
    (v.tags || []).slice(0, 5).forEach(t => {
      if (t.length > 1 && t.length < 30) tagCount[t] = (tagCount[t] || 0) + 1;
    });
  });
  const sorted = Object.entries(tagCount).sort((a, b) => b[1] - a[1]).slice(0, 10);
  const container = document.getElementById('yt-suggested-tags');
  container.innerHTML = sorted.map(([tag]) =>
    '<span class="yt-tag" onclick="document.getElementById(\'yt-search-query\').value=\'' +
    escHtml(tag).replace(/'/g, "\\'") + '\';searchYtVideos()">' + escHtml(tag) + '</span>'
  ).join('');
}

function openYtAnalysis(idx) {
  const v = (window._ytResults || [])[idx];
  if (!v) return;
  const viralLabel = v.contribution > 200 ? '🔥 바이럴' : v.contribution > 50 ? '📈 우수' : '📊 보통';
  const text =
    '━━━ 영상 분석 ━━━\n\n' +
    '제목: ' + v.title + '\n' +
    '채널: ' + v.channelTitle + ' (구독자 ' + formatNum(v.subs) + ')\n' +
    '게시일: ' + formatDate(v.publishedAt) + '\n' +
    '재생 시간: ' + parseDuration(v.duration) + '\n\n' +
    '━━━ 성과 지표 ━━━\n\n' +
    '조회수: ' + formatNum(v.views) + '\n' +
    '좋아요: ' + formatNum(v.likes) + '\n' +
    '댓글: ' + formatNum(v.comments) + '\n' +
    '채널 기여도: ' + v.contribution + '% (' + viralLabel + ')\n' +
    '구독자 대비 조회수: ' + v.performance + 'x\n\n' +
    '━━━ 평가 ━━━\n\n' +
    (v.contribution > 200
      ? '✅ 이 영상은 채널 평균 조회수보다 ' + v.contribution + '% 더 높은 성과를 기록했습니다. 바이럴 영상으로 분류됩니다.'
      : v.contribution > 50
        ? '✅ 채널 평균 대비 ' + v.contribution + '% 높은 성과입니다. 우수한 영상입니다.'
        : '📊 채널 평균 수준의 성과입니다.') + '\n' +
    (v.performance > 1
      ? '\n✅ 구독자 수보다 ' + v.performance + '배 많은 조회수 — 비구독자 노출이 매우 높습니다.'
      : '') + '\n\n' +
    '태그: ' + (v.tags || []).slice(0, 15).join(', ');
  document.getElementById('modal-title').textContent = '영상 분석';
  document.getElementById('modal-body').innerHTML =
    '<div style="margin-bottom:12px"><a href="https://youtube.com/watch?v=' + v.videoId + '" target="_blank" class="btn btn-sm">' +
    '&#x1F517; YouTube에서 보기</a></div>' +
    '<div class="yt-analysis-text">' + escHtml(text) + '</div>';
  document.getElementById('job-modal').style.display = 'flex';
}

/* ── Utility helpers ── */
function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
function formatNum(n) {
  if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return String(n);
}
function formatDate(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  return d.getFullYear() + '.' + String(d.getMonth() + 1).padStart(2, '0') + '.' + String(d.getDate()).padStart(2, '0');
}
function parseDuration(dur) {
  if (!dur) return '-';
  const m = dur.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
  if (!m) return dur;
  const h = parseInt(m[1]) || 0, min = parseInt(m[2]) || 0, s = parseInt(m[3]) || 0;
  return (h ? h + ':' : '') + String(min).padStart(2, '0') + ':' + String(s).padStart(2, '0');
}

/* ── Autopilot functions ── */
let autopilotSettingsInitialized = false;
let autopilotStatusSnapshot = null;
let offlineHarnessLastRunAt = 0;
let offlineHarnessLastReport = null;
let offlineHarnessInFlight = null;
const OFFLINE_HARNESS_REFRESH_MS = 5 * 60 * 1000;
let refreshAllInFlight = false;
let autopilotStatusInFlight = null;
let renderingJobsPollInFlight = false;
const ALL_CATEGORIES = ["탈북사연", "해외감동", "노후금융", "황혼19금", "옛날이야기", "한국사연", "무협", "경제"];

function toggleLimitInput() {
  const mode = document.getElementById('auto-setting-mode').value;
  document.getElementById('auto-limit-group').style.display = (mode === 'target_limit') ? 'block' : 'none';
}

function renderCategoryCheckboxes(activeCats, durationMap) {
  const container = document.getElementById('auto-categories-checkboxes');
  if (!container) return;
  container.innerHTML = '';
  const durations = durationMap && typeof durationMap === 'object' ? durationMap : {};
  
  ALL_CATEGORIES.forEach((cat, index) => {
    const isChecked = activeCats ? activeCats.includes(cat) : true;
    const savedSeconds = parseInt(durations[cat], 10);
    const durationMinutes = Number.isFinite(savedSeconds) && savedSeconds > 0 ? Math.max(5, Math.min(150, Math.round(savedSeconds / 60))) : 150;
    const row = document.createElement('div');
    row.className = 'auto-cat-row';
    row.dataset.category = cat;
    row.style.cssText = 'display:grid;grid-template-columns:minmax(130px,1fr) 76px 86px auto auto;gap:8px;align-items:center;font-size:12px;color:#c9d1d9;background:rgba(255,255,255,0.02);padding:8px;border-radius:6px;border:1px solid rgba(255,255,255,0.05);';
    row.innerHTML = `
      <label style="display:flex;align-items:center;gap:6px;cursor:pointer;min-width:0;">
        <input type="checkbox" class="auto-cat-checkbox" value="${escapeHtml(cat)}" ${isChecked ? 'checked' : ''} style="cursor:pointer;" />
        <span style="font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(cat)}</span>
      </label>
      <input type="number" class="auto-cat-duration-minutes" data-category="${escapeHtml(cat)}" value="${durationMinutes}" min="5" max="150" title="Target video length in minutes" style="width:76px;padding:7px;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.1);color:#fff;border-radius:6px;outline:none;" />
      <input type="number" class="auto-cat-limit" id="auto-cat-limit-${index}" value="1" min="1" max="100" title="생성 수" style="width:86px;padding:7px;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.1);color:#fff;border-radius:6px;outline:none;" />
      <button class="btn btn-primary btn-sm auto-cat-start" type="button" data-category="${escapeHtml(cat)}" data-index="${index}">▶ 시작</button>
      <button class="btn btn-danger btn-sm auto-cat-stop" type="button" data-category="${escapeHtml(cat)}" data-index="${index}" disabled>■ 중지</button>
    `;
    container.appendChild(row);
    row.querySelector('.auto-cat-start')?.addEventListener('click', () => startCategoryAutopilot(cat, index));
    row.querySelector('.auto-cat-stop')?.addEventListener('click', () => stopCategoryAutopilot(cat));
  });
  updateCategoryRunControls(autopilotStatusSnapshot);
}

function parseBenchmarkChannelIds(value) {
  return String(value || '')
    .split(/[\s,;]+/)
    .map(v => v.trim())
    .filter(Boolean)
    .filter((v, idx, arr) => arr.indexOf(v) === idx);
}

function renderBenchmarkChannelSettings(savedMap) {
  const container = document.getElementById('auto-benchmark-channel-settings');
  if (!container) return;
  const map = savedMap && typeof savedMap === 'object' ? savedMap : {};
  container.innerHTML = '';
  ALL_CATEGORIES.forEach((cat, index) => {
    const ids = Array.isArray(map[cat]) ? map[cat] : parseBenchmarkChannelIds(map[cat]);
    const item = document.createElement('label');
    item.style.cssText = 'display:block;min-width:0;';
    item.innerHTML = `
      <span style="display:block;font-size:12px;color:#c9d1d9;font-weight:700;margin-bottom:5px;">${escapeHtml(cat)}</span>
      <textarea
        id="auto-benchmark-channels-${index}"
        data-category="${escapeHtml(cat)}"
        rows="3"
        spellcheck="false"
        placeholder="UCxxxxxxxx&#10;UCyyyyyyyy"
        style="width:100%;resize:vertical;min-height:66px;padding:8px;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.1);color:#fff;border-radius:6px;outline:none;font-size:12px;line-height:1.45;"
      >${escapeHtml(ids.join('\n'))}</textarea>
    `;
    container.appendChild(item);
  });
}

function getBenchmarkChannelSettingsFromUI() {
  const result = {};
  ALL_CATEGORIES.forEach(cat => { result[cat] = []; });
  document.querySelectorAll('#auto-benchmark-channel-settings textarea[data-category]').forEach(input => {
    const category = input.dataset.category || '';
    if (!ALL_CATEGORIES.includes(category)) return;
    result[category] = parseBenchmarkChannelIds(input.value);
  });
  return result;
}

function getCategoryDurationSettingsFromUI() {
  const result = {};
  ALL_CATEGORIES.forEach(cat => { result[cat] = 150 * 60; });
  document.querySelectorAll('.auto-cat-duration-minutes[data-category]').forEach(input => {
    const category = input.dataset.category || '';
    if (!ALL_CATEGORIES.includes(category)) return;
    const minutes = parseInt(input.value, 10);
    const safeMinutes = Number.isFinite(minutes) ? Math.max(5, Math.min(150, minutes)) : 150;
    result[category] = safeMinutes * 60;
  });
  return result;
}

function renderActiveCategoryBadges(activeCats) {
  const categories = Array.isArray(activeCats) ? activeCats : ALL_CATEGORIES;
  const title = document.getElementById('auto-active-category-title');
  const container = document.getElementById('auto-active-category-badges');
  if (title) title.textContent = `설정된 카테고리 (${categories.length}개)`;
  if (!container) return;
  container.innerHTML = '';

  if (categories.length === 0) {
    const empty = document.createElement('span');
    empty.style.cssText = 'color:#8b949e;font-size:12px;';
    empty.textContent = '선택된 카테고리가 없습니다.';
    container.appendChild(empty);
    return;
  }

  categories.forEach(cat => {
    const badge = document.createElement('span');
    badge.className = 'badge badge-preparing';
    badge.textContent = cat;
    container.appendChild(badge);
  });
}

function getSettingsFromUI() {
  const mode = document.getElementById('auto-setting-mode').value;
  const limit = parseInt(document.getElementById('auto-setting-limit').value) || 10;
  const buffer = parseInt(document.getElementById('auto-setting-buffer').value) || 5;
  const discoveryEnabled = Boolean(document.getElementById('auto-setting-channel-discovery-enabled')?.checked);
  const discoveryMin = parseInt(document.getElementById('auto-setting-channel-min')?.value) || 8;
  const discoveryInterval = parseInt(document.getElementById('auto-setting-channel-interval')?.value) || 24;
  const discoverySearchCalls = parseInt(document.getElementById('auto-setting-channel-search-calls')?.value) || 0;
  
  const checkboxes = document.querySelectorAll('.auto-cat-checkbox');
  const active_categories = [];
  checkboxes.forEach(cb => {
    if (cb.checked) active_categories.push(cb.value);
  });
  
  return {
    mode,
    target_limit: limit,
    min_buffer_per_category: buffer,
    active_categories,
    category_image_style_overrides: (autopilotStatusSnapshot && autopilotStatusSnapshot.settings && autopilotStatusSnapshot.settings.category_image_style_overrides) ? autopilotStatusSnapshot.settings.category_image_style_overrides : {},
    target_duration_seconds_by_category: getCategoryDurationSettingsFromUI(),
    benchmark_channel_ids_by_category: getBenchmarkChannelSettingsFromUI(),
    benchmark_channel_auto_discovery_enabled: discoveryEnabled,
    benchmark_channel_discovery_min_channels: discoveryMin,
    benchmark_channel_discovery_interval_hours: discoveryInterval,
    benchmark_channel_discovery_max_search_calls: discoverySearchCalls
  };
}

function updateCategoryRunControls(statusData) {
  const data = statusData || {};
  const isRunning = Boolean(data.is_running);
  const currentCategory = String(data.current_category || '');
  document.querySelectorAll('.auto-cat-row').forEach(row => {
    const category = row.dataset.category || '';
    const isCurrent = isRunning && category === currentCategory;
    row.style.borderColor = isCurrent ? 'rgba(35,134,54,0.65)' : 'rgba(255,255,255,0.05)';
    row.style.background = isCurrent ? 'rgba(35,134,54,0.08)' : 'rgba(255,255,255,0.02)';
  });
  document.querySelectorAll('.auto-cat-start').forEach(btn => {
    btn.disabled = isRunning;
    btn.title = isRunning ? '현재 생성이 끝나거나 중지된 뒤 시작할 수 있습니다.' : '이 카테고리만 생성 시작';
  });
  document.querySelectorAll('.auto-cat-stop').forEach(btn => {
    const category = btn.dataset.category || '';
    btn.disabled = !isRunning || category !== currentCategory;
    btn.title = category === currentCategory ? '현재 카테고리 생성 중지' : '현재 실행 중인 카테고리만 중지할 수 있습니다.';
  });
}

function categoryLimitValue(index) {
  const input = document.getElementById(`auto-cat-limit-${index}`);
  const value = Number.parseInt(input?.value || '1', 10);
  if (!Number.isInteger(value) || value < 1 || value > 100) return null;
  return value;
}

async function saveAutopilotSettings() {
  const settings = getSettingsFromUI();
  try {
    const res = await api('POST', '/api/autopilot/hermes/save_settings', { settings });
    if (res && res.success) {
      const savedSettings = res.settings || settings;
      renderActiveCategoryBadges(savedSettings.active_categories);
      renderCategoryCheckboxes(savedSettings.active_categories, savedSettings.target_duration_seconds_by_category);
      renderBenchmarkChannelSettings(savedSettings.benchmark_channel_ids_by_category);
      showToast('오토파일럿 설정이 저장되었습니다.', 'success');
    } else {
      showToast('설정 저장 실패: ' + (res?.error || '알 수 없음'), 'error');
    }
  } catch(e) {
    showToast('설정 저장 통신 실패', 'error');
  }
}

function renderOfflineHarness(report) {
  offlineHarnessLastReport = report;
  const badge = document.getElementById('auto-harness-badge');
  const summary = document.getElementById('auto-harness-summary');
  const failures = document.getElementById('auto-harness-failures');
  if (!badge || !summary || !failures) return;
  const failedChecks = (report?.checks || []).filter(check => !check.passed);
  if (report?.status === 'pass') {
    badge.className = 'badge badge-completed';
    badge.textContent = '통과';
    summary.textContent = `API 호출 ${report.api_calls || 0}회, ${report.check_count || 0}개 검증 통과`;
    failures.style.display = 'none';
    failures.innerHTML = '';
    return;
  }
  badge.className = 'badge badge-failed';
  badge.textContent = '실패';
  summary.textContent = `자동 생성 차단: ${failedChecks.length || report?.failed_count || 1}개 사전검증 실패`;
  failures.style.display = 'block';
  failures.innerHTML = failedChecks.slice(0, 8).map(check => {
    const name = escapeHtml(check.name || 'unknown check');
    const category = check.category ? ` [${escapeHtml(check.category)}]` : '';
    const detail = check.detail ? `<div style="color:#c9d1d9;margin-top:2px;">${escapeHtml(check.detail)}</div>` : '';
    return `<div style="margin-bottom:6px;">⚠ ${name}${category}${detail}</div>`;
  }).join('') || '<div>⚠ 사전검증 실패 상세를 확인할 수 없습니다.</div>';
}

async function runOfflineHarness({silent=false} = {}) {
  const now = Date.now();
  if (silent && offlineHarnessLastReport && (now - offlineHarnessLastRunAt) < OFFLINE_HARNESS_REFRESH_MS) {
    return offlineHarnessLastReport;
  }
  if (silent && !offlineHarnessLastReport) {
    return null;
  }
  if (offlineHarnessInFlight) {
    return offlineHarnessInFlight;
  }
  const badge = document.getElementById('auto-harness-badge');
  const summary = document.getElementById('auto-harness-summary');
  if (!silent && badge) {
    badge.className = 'badge badge-starting';
    badge.textContent = '검증 중';
  }
  if (!silent && summary) summary.textContent = '오프라인 사전검증을 실행 중입니다...';
  offlineHarnessInFlight = api('GET', '/api/autopilot/hermes/offline-harness' + (silent ? '' : '?force=true'));
  try {
    const report = await offlineHarnessInFlight;
    if (!report) return null;
    offlineHarnessLastRunAt = Date.now();
    renderOfflineHarness(report);
    if (!silent) {
      showToast(report.status === 'pass' ? '오프라인 사전검증 통과' : '오프라인 사전검증 실패: 자동 생성이 차단됩니다.', report.status === 'pass' ? 'success' : 'warning');
    }
    return report;
  } catch(e) {
    renderOfflineHarness({
      status: 'fail',
      failed_count: 1,
      checks: [{ name: 'offline harness request failed', passed: false, detail: e.message || String(e), category: 'dashboard' }],
    });
    if (!silent) showToast('오프라인 사전검증 요청 실패', 'error');
    return null;
  } finally {
    offlineHarnessInFlight = null;
  }
}

async function loadAutopilotStatus() {
  if (autopilotStatusInFlight) {
    return autopilotStatusInFlight;
  }
  autopilotStatusInFlight = (async () => {
  try {
    const data = await api('GET', '/api/autopilot/hermes/status');
    if (!data) return;
    autopilotStatusSnapshot = data;
    
    const isRunning = data.is_running;
    const lastRunStatus = String(data.last_run_status || '').toLowerCase();
    const isFailed = !isRunning && lastRunStatus === 'failed';
    const isCompleted = !isRunning && lastRunStatus === 'completed';
    document.getElementById('auto-btn-start').disabled = isRunning;
    document.getElementById('auto-btn-stop').disabled = !isRunning;
    
    const statusBadgeEl = document.getElementById('auto-status-text');
    if (isRunning) {
      statusBadgeEl.className = 'badge badge-running';
      statusBadgeEl.textContent = '동작 중';
    } else if (isFailed) {
      statusBadgeEl.className = 'badge badge-failed';
      statusBadgeEl.textContent = '최근 실행 실패';
    } else if (isCompleted) {
      statusBadgeEl.className = 'badge badge-completed';
      statusBadgeEl.textContent = '완료';
    } else {
      statusBadgeEl.className = 'badge badge-stopped';
      statusBadgeEl.textContent = '중지됨';
    }
    
    const runLabel = isRunning
      ? '<span style="color:#3fb950;font-weight:bold;">실행 중</span>'
      : (isFailed
        ? '<span style="color:#f85149;font-weight:bold;">최근 실행 실패</span>'
        : (isCompleted ? '<span style="color:#3fb950;font-weight:bold;">완료</span>' : '중지됨'));
    document.getElementById('auto-info-running').innerHTML = runLabel;
    document.getElementById('auto-info-step').textContent = isFailed && data.last_error
      ? `마지막 오류 - ${data.last_error}`
      : (data.current_step || '-');
    document.getElementById('auto-info-category').textContent = data.current_category || '-';
    document.getElementById('auto-info-topic').textContent = data.current_topic || '-';
    document.getElementById('auto-info-image-style').textContent = data.current_image_style || '-';
    
    if (data.session_stats) {
      const generated = data.session_stats.generated_count || 0;
      document.getElementById('auto-info-generated').textContent = generated + ' 개';
    }

    if (data.settings) {
      renderActiveCategoryBadges(data.settings.active_categories);
    } else {
      renderActiveCategoryBadges(null);
    }
    updateCategoryRunControls(data);
    
    // UI 초기화 (최초 1회만 설정 채워넣음)
    if (!autopilotSettingsInitialized && data.settings) {
      document.getElementById('auto-setting-mode').value = data.settings.mode || 'infinite';
      document.getElementById('auto-setting-limit').value = data.settings.target_limit || 10;
      document.getElementById('auto-setting-buffer').value = data.settings.min_buffer_per_category || 5;
      document.getElementById('auto-setting-channel-discovery-enabled').checked = data.settings.benchmark_channel_auto_discovery_enabled !== false;
      document.getElementById('auto-setting-channel-min').value = data.settings.benchmark_channel_discovery_min_channels || 8;
      document.getElementById('auto-setting-channel-interval').value = data.settings.benchmark_channel_discovery_interval_hours || 24;
      document.getElementById('auto-setting-channel-search-calls').value = data.settings.benchmark_channel_discovery_max_search_calls ?? 1;
      
      toggleLimitInput();
      renderCategoryCheckboxes(data.settings.active_categories, data.settings.target_duration_seconds_by_category);
      renderBenchmarkChannelSettings(data.settings.benchmark_channel_ids_by_category);
      updateCategoryRunControls(data);
      autopilotSettingsInitialized = true;
    } else if (!autopilotSettingsInitialized) {
      // 폰백 렌더링
      renderCategoryCheckboxes(null, null);
      renderBenchmarkChannelSettings(null);
      updateCategoryRunControls(data);
      autopilotSettingsInitialized = true;
    }
    
    const logsEl = document.getElementById('auto-logs');
    if (data.logs && data.logs.length > 0) {
      logsEl.textContent = data.logs.join('\n');
      logsEl.scrollTop = logsEl.scrollHeight;
    } else {
      logsEl.textContent = '로그가 없습니다.';
    }
  } catch(e) {
    console.error('loadAutopilotStatus error:', e);
  } finally {
    autopilotStatusInFlight = null;
  }
  })();
  return autopilotStatusInFlight;
}

async function startCategoryAutopilot(category, index) {
  if (autopilotStatusSnapshot?.is_running) {
    showToast('이미 자동 생성이 실행 중입니다. 현재 작업을 중지하거나 완료 후 다시 시작하세요.', 'warning');
    return;
  }
  const limit = categoryLimitValue(index);
  if (!limit) {
    showToast('카테고리별 생성 수는 1~100 사이로 입력하세요.', 'error');
    return;
  }
  const settings = {
    ...getSettingsFromUI(),
    mode: 'target_limit',
    target_limit: limit,
    min_buffer_per_category: 1,
    active_categories: [category],
    force_generate: true,
  };
  document.getElementById('auto-start-limit').value = limit;
  document.getElementById('auto-setting-mode').value = 'target_limit';
  document.getElementById('auto-setting-limit').value = limit;
  document.getElementById('auto-setting-buffer').value = 1;
  toggleLimitInput();
  try {
    const harness = await runOfflineHarness({silent:false});
    if (!harness || harness.status !== 'pass') {
      showToast('오프라인 사전검증 실패로 자동 생성 시작을 중단했습니다.', 'warning');
      return;
    }
    const res = await api('POST', '/api/autopilot/hermes/start', { settings });
    if (res && res.success) {
      showToast(`${category}: ${limit}개 생성 시작`, 'success');
      loadAutopilotStatus();
    } else {
      if (res?.offline_harness) renderOfflineHarness(res.offline_harness);
      showToast(`${category} 생성 시작 실패: ` + (res?.detail || res?.error || '알 수 없음'), 'error');
    }
  } catch(e) {
    showToast(`${category} 생성 시작 통신 실패`, 'error');
  }
}

async function stopCategoryAutopilot(category) {
  if (!autopilotStatusSnapshot?.is_running) {
    showToast('현재 실행 중인 자동 생성이 없습니다.', 'info');
    return;
  }
  if (autopilotStatusSnapshot.current_category && autopilotStatusSnapshot.current_category !== category) {
    showToast(`현재 실행 중인 카테고리는 ${autopilotStatusSnapshot.current_category}입니다.`, 'warning');
    return;
  }
  await stopAutopilot();
}

async function startAutopilot() {
  const settings = getSettingsFromUI();
  const startLimit = Number.parseInt(document.getElementById('auto-start-limit').value, 10);
  if (!Number.isInteger(startLimit) || startLimit < 1 || startLimit > 100) {
    showToast('생성 수는 1~100 사이로 입력하세요.', 'error');
    return;
  }
  settings.mode = 'target_limit';
  settings.target_limit = startLimit;
  document.getElementById('auto-setting-mode').value = 'target_limit';
  document.getElementById('auto-setting-limit').value = startLimit;
  toggleLimitInput();
  try {
    const harness = await runOfflineHarness({silent:false});
    if (!harness || harness.status !== 'pass') {
      showToast('오프라인 사전검증 실패로 자동 생성 시작을 중단했습니다.', 'warning');
      return;
    }
    const res = await api('POST', '/api/autopilot/hermes/start', { settings });
    if (res && res.success) {
      showToast(`Hermes가 ${startLimit}개 생성 후 자동 정지합니다.`, 'success');
      loadAutopilotStatus();
    } else {
      if (res?.offline_harness) renderOfflineHarness(res.offline_harness);
      showToast('자동 생성기 시작 실패: ' + (res?.detail || res?.error || '알 수 없음'), 'error');
    }
  } catch(e) {
    showToast('자동 생성기 시작 통신 실패', 'error');
  }
}

async function stopAutopilot() {
  try {
    const res = await api('POST', '/api/autopilot/hermes/stop');
    if (res && res.success) {
      showToast('Hermes 자동 생성기 중지 요청됨.', 'info');
      loadAutopilotStatus();
    } else {
      showToast('자동 생성기 중지 실패: ' + (res?.error || '알 수 없음'), 'error');
    }
  } catch(e) {
    showToast('자동 생성기 중지 통신 실패', 'error');
  }
}


/* ─── Voicebox TTS Controller ─── */

async function loadVoiceboxHistory() {
  const container = document.getElementById('voicebox-history-list');
  const countEl = document.getElementById('voicebox-history-count');
  if (!container) return;
  
  try {
    const res = await api('GET', '/api/voicebox/history');
    const history = (res && res.history) ? res.history : [];
    
    if (countEl) countEl.textContent = history.length;
    
    if (!history.length) {
      container.innerHTML = '<div class="empty" style="padding:12px;font-size:11px;">생성된 음성 파일이 없습니다.</div>';
      return;
    }
    
    container.innerHTML = history.map((item, idx) => `
      <div style="background:#161b22;border:1px solid #30363d;border-radius:6px;padding:8px 10px;display:flex;flex-direction:column;gap:6px;">
        <div style="display:flex;justify-content:space-between;align-items:center;font-size:11px;">
          <span style="font-weight:bold;color:#58a6ff;font-family:monospace;font-size:10px;" class="truncate">${escapeHtml(item.filename)}</span>
          <span style="color:#8b949e;font-size:10px;">${item.size_kb} KB</span>
        </div>
        <div style="font-size:10px;color:#8b949e;margin-top:-2px;">🕒 ${item.created_at}</div>
        <audio src="${item.url}" controls style="width:100%;height:26px;margin-top:2px;"></audio>
        <div style="display:flex;gap:6px;margin-top:2px;">
          <a href="${item.url}" download="${item.filename}" class="btn btn-sm" style="flex:1;text-align:center;font-size:10px;padding:3px 0;background:#21262d;color:#c9d1d9;text-decoration:none;border-radius:4px;border:1px solid #30363d;">
            ⬇️ 다운로드
          </a>
          <button onclick="selectHistoryAudio('${item.filename}')" class="btn btn-sm" style="flex:1.4;font-size:10px;padding:3px 0;background:#238636;color:#fff;border:none;border-radius:4px;font-weight:bold;">
            ☁️ Supabase 연동
          </button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    container.innerHTML = '<div class="empty" style="padding:12px;font-size:11px;color:#f85149;">이력 불러오기 실패</div>';
  }
}

function selectHistoryAudio(filename) {
  voiceboxCurrentAudioFile = filename;
  const player = document.getElementById('voicebox-audio-player');
  const resultCard = document.getElementById('voicebox-audio-result-card');
  const meta = document.getElementById('voicebox-audio-meta');
  
  if (player) {
    player.src = `/api/voicebox/audio/${filename}?t=${Date.now()}`;
    player.load();
  }
  if (meta) {
    meta.innerHTML = `<span>선택된 파일: ${filename}</span><span>준비 완료</span>`;
  }
  if (resultCard) {
    resultCard.style.display = 'flex';
  }
  showToast(`선택된 파일(${filename})로 Supabase 연동 준비가 되었습니다. 'Supabase에 저장' 버튼을 누르세요.`, 'success');
}

let voiceboxCurrentTopic = null;
let voiceboxCurrentAudioFile = null;

async function loadVoiceboxTtsTab() {
  await loadVoiceboxPresets();
  await loadVoiceboxTopics();
  await loadVoiceboxHistory();
}

let allVoiceboxPresets = [];

async function loadVoiceboxPresets() {
  try {
    const data = await api('GET', '/api/voicebox/presets?provider=all');
    if (!data || !data.presets) return;
    allVoiceboxPresets = data.presets;
    onTtsProviderChange();
  } catch (e) {
    console.error('Failed to load voicebox presets:', e);
  }
}

function onTtsProviderChange() {
  const providerSelect = document.getElementById('voicebox-provider-select');
  const presetSelect = document.getElementById('voicebox-preset-select');
  const genBtn = document.getElementById('voicebox-gen-btn');
  const engineInfo = document.getElementById('voicebox-engine-info');
  const provider = providerSelect ? providerSelect.value : 'google';

  if (!presetSelect) return;

  const filtered = allVoiceboxPresets.filter(p => p.provider === provider);
  presetSelect.innerHTML = filtered.map(p => `
    <option value="${p.id}">${p.name} ${p.gender ? '(' + (p.gender === 'female' ? '여성' : '남성') + ')' : ''}</option>
  `).join('');

  if (provider === 'google') {
    if (genBtn) genBtn.innerHTML = '<span>🌐</span> Google 무료 TTS로 생성';
    if (engineInfo) {
      engineInfo.innerHTML = `
        <div style="font-size:11px;color:#58a6ff;font-weight:bold;">🌐 Google 무료 TTS 모드</div>
        <div style="font-size:11px;color:#8b949e;margin-top:2px;">ElevenLabs 크레딧 소모 없이 구글 공식 합성 음성을 무제한으로 생성합니다.</div>
      `;
    }
  } else {
    if (genBtn) genBtn.innerHTML = '<span>⚡</span> Voicebox 신경망 TTS로 생성';
    if (engineInfo) {
      engineInfo.innerHTML = `
        <div style="font-size:11px;color:#a371f7;font-weight:bold;">⚡ Voicebox 고품질 신경망 모드</div>
        <div style="font-size:11px;color:#8b949e;margin-top:2px;">자연스러운 한국어 성우 프리셋으로 고품질 음성을 생성합니다.</div>
      `;
    }
  }
}

let voiceboxTopicsCache = [];

async function loadVoiceboxTopics() {
  const container = document.getElementById('voicebox-topics-list');
  if (!container) return;
  container.innerHTML = '<div class="info">대본 목록 로딩 중...</div>';
  
  try {
    const data = await api('GET', '/api/voicebox/topics');
    const topics = (data && data.topics) ? data.topics : [];
    voiceboxTopicsCache = topics;
    
    if (!topics.length) {
      container.innerHTML = '<div class="empty" style="padding:16px;">생성된 대본이 없습니다.</div>';
      return;
    }
    
    container.innerHTML = topics.map((r, idx) => `
      <div onclick="selectVoiceboxTopicByIndex(${idx})" style="padding:10px;background:#161b22;border:1px solid #30363d;border-radius:6px;cursor:pointer;transition:all;" onmouseover="this.style.borderColor='#58a6ff'" onmouseout="this.style.borderColor='#30363d'">
        <div style="font-weight:bold;color:#c9d1d9;font-size:12px;margin-bottom:4px;" class="truncate">${escapeHtml(r.title)}</div>
        <div style="display:flex;justify-content:space-between;align-items:center;font-size:10px;color:#8b949e;">
          <span style="background:rgba(255,255,255,0.06);padding:1px 6px;border-radius:4px;">${r.category || '일반'}</span>
          <div style="display:flex;align-items:center;gap:4px;">
            ${r.has_audio ? '<span style="color:#2ea043;font-weight:bold;">⚡ TTS 완료</span>' : ''}
            <span>${(r.script || '').length.toLocaleString()}자</span>
          </div>
        </div>
      </div>
    `).join('');
    
    if (topics.length > 0) {
      selectVoiceboxTopicByIndex(0);
    }
  } catch (e) {
    container.innerHTML = '<div class="empty" style="padding:16px;color:#f85149;">대본 목록 로딩 실패: ' + e + '</div>';
  }
}

function selectVoiceboxTopicByIndex(idx) {
  const item = voiceboxTopicsCache[idx];
  if (!item) return;
  
  voiceboxCurrentTopic = item;
  voiceboxCurrentAudioFile = null;
  
  const editor = document.getElementById('voicebox-script-editor');
  const titleEl = document.getElementById('voicebox-script-title');
  const metaEl = document.getElementById('voicebox-script-meta');
  const resultCard = document.getElementById('voicebox-audio-result-card');
  
  if (editor) editor.value = item.script || '';
  if (titleEl) titleEl.textContent = `📜 ${item.title}`;
  if (metaEl) metaEl.textContent = `${(item.script || '').length.toLocaleString()}자 대본`;
  if (resultCard) resultCard.style.display = 'none';

  const targetIdEl = document.getElementById('voicebox-target-id');
  const targetCatEl = document.getElementById('voicebox-target-category');
  const targetTitleEl = document.getElementById('voicebox-target-title');

  if (targetIdEl) targetIdEl.textContent = `ID: #${item.topic_id || item.id}`;
  if (targetCatEl) targetCatEl.textContent = `📁 ${item.category || '카테고리'}`;
  if (targetTitleEl) targetTitleEl.textContent = item.title || '주제';
}

async function selectVoiceboxTopic(resultId) {
  try {
    const data = await api('GET', `/api/generated-results/${encodeURIComponent(resultId)}`);
    if (!data) return;
    
    voiceboxCurrentTopic = data;
    voiceboxCurrentAudioFile = null;
    
    const editor = document.getElementById('voicebox-script-editor');
    const titleEl = document.getElementById('voicebox-script-title');
    const metaEl = document.getElementById('voicebox-script-meta');
    const resultCard = document.getElementById('voicebox-audio-result-card');
    
    if (editor) editor.value = data.script || '';
    if (titleEl) titleEl.textContent = `📜 ${data.title || data.topic}`;
    if (metaEl) metaEl.textContent = `${(data.script || '').length.toLocaleString()}자 대본`;
    if (resultCard) resultCard.style.display = 'none';
  } catch (e) {
    showToast('대본 로딩 실패', 'error');
  }
}

async function generateVoiceboxTts() {
  const editor = document.getElementById('voicebox-script-editor');
  const btn = document.getElementById('voicebox-gen-btn');
  const providerSelect = document.getElementById('voicebox-provider-select');
  const presetSelect = document.getElementById('voicebox-preset-select');
  const speedRange = document.getElementById('voicebox-speed-range');
  const provider = providerSelect ? providerSelect.value : 'google';
  
  if (!editor || !editor.value.trim()) {
    showToast('대본 내용이 비어 있습니다.', 'warning');
    return;
  }
  
  btn.disabled = true;
  btn.innerHTML = `<span>⏳</span> ${provider === 'google' ? 'Google 무료' : 'Voicebox'} TTS 음성 생성 중...`;
  
  try {
    const payload = {
      script: editor.value.trim(),
      provider: provider,
      voice_id: presetSelect ? presetSelect.value : (provider === 'google' ? 'google_kr_standard' : 'narrator_calm_kr'),
      speed: speedRange ? parseFloat(speedRange.value) : 1.0,
      topic_id: voiceboxCurrentTopic ? voiceboxCurrentTopic.topic_id : null,
    };
    
    const res = await api('POST', '/api/voicebox/generate', payload);
    if (!res || !res.success) {
      showToast('TTS 생성 실패: ' + (res?.detail || res?.error || '오류'), 'error');
      return;
    }
    
    voiceboxCurrentAudioFile = res.filename;
    
    const resultCard = document.getElementById('voicebox-audio-result-card');
    const player = document.getElementById('voicebox-audio-player');
    const meta = document.getElementById('voicebox-audio-meta');
    
    if (player) {
      player.src = `/api/voicebox/audio/${res.filename}?t=${Date.now()}`;
      player.load();
    }
    if (meta) {
      meta.innerHTML = `<span>크기: ${(res.file_size / 1024).toFixed(1)} KB</span><span>소요: ${res.elapsed_seconds}초</span><span>엔진: ${provider.toUpperCase()}</span>`;
    }
    if (resultCard) {
      resultCard.style.display = 'flex';
      const targetIdEl = document.getElementById('voicebox-target-id');
      const targetCatEl = document.getElementById('voicebox-target-category');
      const targetTitleEl = document.getElementById('voicebox-target-title');
      if (voiceboxCurrentTopic) {
        if (targetIdEl) targetIdEl.textContent = `ID: #${voiceboxCurrentTopic.topic_id || voiceboxCurrentTopic.id}`;
        if (targetCatEl) targetCatEl.textContent = `📁 ${voiceboxCurrentTopic.category || '카테고리'}`;
        if (targetTitleEl) targetTitleEl.textContent = voiceboxCurrentTopic.title || '주제';
      }
    }
    
    showToast(`🎉 ${provider === 'google' ? 'Google 무료' : 'Voicebox'} TTS 생성이 완료되었습니다! (${res.elapsed_seconds}초 소요)`, 'success');
    await loadVoiceboxHistory();
  } catch (e) {
    showToast('TTS 생성 통신 오류: ' + e, 'error');
  } finally {
    btn.disabled = false;
    onTtsProviderChange();
  }
}

async function saveVoiceboxToSupabase() {
  if (!voiceboxCurrentAudioFile) {
    showToast('먼저 TTS를 생성해주세요.', 'warning');
    return;
  }
  
  const saveBtn = document.getElementById('voicebox-save-btn');
  saveBtn.disabled = true;
  saveBtn.textContent = '☁️ Supabase 저장 중...';
  
  try {
    const topicId = (voiceboxCurrentTopic && voiceboxCurrentTopic.topic_id) ? voiceboxCurrentTopic.topic_id : (voiceboxCurrentTopic ? voiceboxCurrentTopic.id : null);
    const presetSelect = document.getElementById('voicebox-preset-select');
    
    const payload = {
      topic_id: topicId,
      audio_filename: voiceboxCurrentAudioFile,
      voice_id: presetSelect ? presetSelect.value : 'voicebox',
    };
    
    const res = await api('POST', '/api/voicebox/save-to-supabase', payload);
    if (res && res.success) {
      showToast('✅ ' + res.message, 'success');
      saveBtn.textContent = '✅ Supabase 연동 완료';
    } else {
      showToast('Supabase 저장 실패: ' + (res?.detail || '오류'), 'error');
      saveBtn.disabled = false;
      saveBtn.textContent = '☁️ Supabase에 저장 & 유저앱 연동 완료';
    }
  } catch (e) {
    showToast('Supabase 저장 통신 실패: ' + e, 'error');
    saveBtn.disabled = false;
    saveBtn.textContent = '☁️ Supabase에 저장 & 유저앱 연동 완료';
  }
}


/* ── Server Process Management ── */
async function confirmRestartServer() {
  if (!confirm('워커 서버를 완전히 재시작하시겠습니까?\n\n프로세스를 모두 종료한 뒤 다시 시작합니다. 보통 10~20초 정도 걸리며, 준비되면 페이지가 자동 새로고침됩니다.')) return;
  showToast('워커 서버를 재시작하는 중입니다... 잠시만 기다려주세요.', 'info');
  try {
    await api('POST', '/api/server/restart');
  } catch (e) {}
  showRestartModal();
}

async function confirmShutdownServer() {
  if (!confirm('워커 서버를 완전히 종료하시겠습니까?\n\n종료 후에는 바탕화면 앱 또는 실행 스크립트로 직접 다시 켜야 합니다.')) return;
  showToast('워커 서버를 완전히 종료합니다.', 'warning');
  try {
    await api('POST', '/api/server/shutdown');
  } catch (e) {}
  document.body.innerHTML = `
    <div style="height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;background:#0d1117;color:#c9d1d9;font-family:sans-serif;text-align:center;">
      <div style="font-size:48px;margin-bottom:16px;">🛑</div>
      <h2 style="color:#f85149;">워커 서버가 완전히 종료되었습니다</h2>
      <p style="color:#8b949e;margin-top:8px;">다시 실행하려면 AIR Studio 데스크톱 앱이나 워커 실행기를 시작하세요.</p>
    </div>
  `;
}

function showRestartModal() {
  let count = 45;
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay active';
  overlay.style.zIndex = '9999';
  overlay.innerHTML = `
    <div class="modal" style="text-align:center;max-width:380px;padding:30px 20px;">
      <div style="font-size:36px;margin-bottom:12px;">🔄</div>
      <h3 style="margin-bottom:8px;">워커 서버 재시작 중</h3>
      <p style="color:#8b949e;margin:12px 0 20px;font-size:13px;" id="restart-countdown-text">서버가 다시 응답할 때까지 확인 중입니다... (<span id="restart-sec" style="color:#58a6ff;font-weight:bold;">45</span>초)</p>
      <div class="refresh-indicator" style="display:inline-block;padding:6px 14px;background:#21262d;border-radius:20px;font-size:12px;color:#58a6ff;">준비되면 자동 새로고침됩니다</div>
    </div>
  `;
  document.body.appendChild(overlay);
  
  const reloadAfterRestart = () => {
    const url = new URL(window.location.href);
    url.searchParams.set('restarted', String(Date.now()));
    window.location.replace(url.toString());
  };
  const startedAt = Date.now();
  const timer = setInterval(async () => {
    count--;
    const secEl = document.getElementById('restart-sec');
    if (secEl) secEl.textContent = Math.max(count, 0);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2500);
    try {
      const res = await fetch(`/api/status?restart_probe=${Date.now()}`, {
        cache: 'no-store',
        signal: controller.signal,
      });
      if (res.ok) {
        const data = await res.json();
        if (data?.manager_alive) {
          clearInterval(timer);
          reloadAfterRestart();
          return;
        }
      }
    } catch (e) {}
    finally {
      clearTimeout(timeoutId);
    }
    if (count <= 0 || Date.now() - startedAt > 45000) {
      clearInterval(timer);
      reloadAfterRestart();
    }
  }, 1000);
}


/* ── Init ── */
refreshAll();

// 3초마다 렌더링 상황 배지 실시간 동기화
setInterval(() => {
  if (refreshAllInFlight || renderingJobsPollInFlight) return;
  renderingJobsPollInFlight = true;
  api('GET', '/api/rendering-jobs?limit=10').then(data => {
    if (data) {
      checkNewRenderJobs(data.jobs || [], data.pending_count || 0);
    }
  }).catch(() => {}).finally(() => {
    renderingJobsPollInFlight = false;
  });
}, 10000);
</script>
</body>
</html>"""
