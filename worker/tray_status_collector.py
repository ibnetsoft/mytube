"""
AIR Worker 시스템 트레이 상태 수집기.

Manager 프로세스와 같은 프로세스에서 동작하므로,
상태 파일(manager_status.json)과 job_store(SQLite)를 직접 읽습니다.
HTTP 경유 없이 zero-overhead로 상태를 수집합니다.

이전 폴링 결과와 비교하여 변경이 있을 때만 알림/업데이트를 트리거합니다.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from logging_setup import get_logger
from worker_config import MANAGER_STATUS_FILE, STATE_DIR

logger = get_logger("tray_status_collector")

STATE_FILES = {
    "render_worker": STATE_DIR / "render_worker.json",
    "hermes_worker": STATE_DIR / "hermes_worker.json",
    "local_api": STATE_DIR / "local_api.json",
}


@dataclass
class WorkerProcessStatus:
    """단일 워커 프로세스의 상태."""
    name: str
    status: str = "stopped"
    pid: Optional[int] = None
    progress: Optional[int] = None
    current_job_id: Optional[str] = None
    current_job_type: Optional[str] = None
    progress_message: Optional[str] = None
    last_error: Optional[str] = None
    restarts: int = 0
    disabled_reason: Optional[str] = None


@dataclass
class JobSummary:
    """트레이에 표시할 작업 요약."""
    job_id: str
    job_type: str
    status: str
    progress: int = 0
    progress_message: Optional[str] = None
    source: str = "local"


@dataclass
class TraySnapshot:
    """트레이 UI 전체 상태 스냅샷."""
    worker_id: str = ""
    processes: dict[str, WorkerProcessStatus] = field(default_factory=dict)
    active_jobs: list[JobSummary] = field(default_factory=list)
    recent_jobs: list[JobSummary] = field(default_factory=list)
    hermes_paused: bool = False

    # 변경 감지용 — 이전 스냅샷과 비교하여 어떤 이벤트가 발생했는지 반환
    completed_jobs: list[JobSummary] = field(default_factory=list)
    failed_jobs: list[JobSummary] = field(default_factory=list)

    @property
    def tooltip(self) -> str:
        """트레이 아이콘 tooltip 텍스트."""
        for name in ("render_worker", "hermes_worker"):
            proc = self.processes.get(name)
            if proc and proc.status == "running" and proc.progress is not None:
                return f"AIR Worker - {proc.progress}%"
        any_running = any(
            p.status == "running" for p in self.processes.values()
        )
        if any_running:
            return "AIR Worker - 작업 중"
        return "AIR Worker - 대기 중"


def _read_json_file(path: Path) -> Optional[dict]:
    """JSON 파일 읽기 (실패 시 None 반환)."""
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.debug(f"JSON 파일 읽기 실패 ({path}): {e}")
        return None


def collect_snapshot() -> TraySnapshot:
    """현재 상태를 수집하여 TraySnapshot 반환.

    같은 프로세스 내에서 실행되므로:
    - manager_status.json (Manager가 매 틱마다 기록)를 직접 읽어 프로세스 상태 획득
    - job_store.list_jobs()로 작업 목록 획득
    """
    import job_store

    snap = TraySnapshot()

    # 1) manager_status.json에서 프로세스 상태 읽기
    mgr_status = _read_json_file(MANAGER_STATUS_FILE)
    if mgr_status:
        snap.worker_id = mgr_status.get("worker_id", "")
        snap.hermes_paused = mgr_status.get("hermes_paused", False)

        for name, proc_info in mgr_status.get("processes", {}).items():
            current_job = proc_info.get("current_job") or {}
            job_id = current_job.get("job_id") if isinstance(current_job, dict) else None
            job_type = current_job.get("job_type") if isinstance(current_job, dict) else None

            snap.processes[name] = WorkerProcessStatus(
                name=name,
                status=proc_info.get("status", "stopped"),
                pid=proc_info.get("pid"),
                progress=proc_info.get("progress"),
                current_job_id=job_id,
                current_job_type=job_type,
                last_error=proc_info.get("last_error"),
                restarts=proc_info.get("restart_count_total", 0),
                disabled_reason=proc_info.get("disabled_reason"),
            )

    # 2) job_store에서 작업 목록 조회
    try:
        active = job_store.list_jobs(status=None, limit=20)
        for job in active:
            summary = JobSummary(
                job_id=job["job_id"],
                job_type=job["job_type"],
                status=job["status"],
                progress=job.get("progress", 0),
                progress_message=job.get("progress_message"),
                source=job.get("source", "local"),
            )
            if job["status"] in job_store.ACTIVE_STATUSES or job["status"] == job_store.QUEUED:
                snap.active_jobs.append(summary)
            snap.recent_jobs.append(summary)
    except Exception as e:
        logger.debug(f"job_store 조회 실패: {e}")

    return snap


class TrayStatusCollector:
    """주기적 상태 폴링 + 변경 감지.

    Usage:
        collector = TrayStatusCollector()
        collector.start(on_change=callback_func)
        ...
        collector.stop()
    """

    def __init__(self, poll_interval: float = 3.0):
        self._poll_interval = poll_interval
        self._prev_snapshot: Optional[TraySnapshot] = None
        self._prev_job_statuses: dict[str, str] = {}  # job_id -> status
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._latest_snapshot = TraySnapshot()

    @property
    def latest(self) -> TraySnapshot:
        with self._lock:
            return self._latest_snapshot

    def collect_and_diff(self) -> TraySnapshot:
        """상태 수집 + 이전과의 변경 감지. 반환된 snapshot에 completed_jobs/failed_jobs가 채워집니다."""
        current = collect_snapshot()

        completed = []
        failed = []

        with self._lock:
            prev = self._prev_snapshot
            prev_statuses = dict(self._prev_job_statuses)

            # 작업 상태 변경 감지
            for job in current.recent_jobs:
                old_status = prev_statuses.get(job.job_id)
                if old_status is not None:
                    if old_status in ("RENDERING", "UPLOADING", "PREPARING") and job.status == "COMPLETED":
                        completed.append(job)
                    elif old_status in ("RENDERING", "UPLOADING", "PREPARING", "QUEUED") and job.status == "FAILED":
                        failed.append(job)

            # 현재 활성 작업의 상태 기록
            new_statuses = {}
            for job in current.recent_jobs:
                new_statuses[job.job_id] = job.status

            current.completed_jobs = completed
            current.failed_jobs = failed

            self._prev_snapshot = current
            self._prev_job_statuses = new_statuses
            self._latest_snapshot = current

        return current

    def poll_once(self) -> TraySnapshot:
        """단일 폴링 (테스트/초기화용)."""
        return self.collect_and_diff()

    def start(self, on_change=None):
        """백그라운드 폴링 스레드 기동.

        Args:
            on_change: 변경 감지 시 호출될 콜백. 인자: TraySnapshot
        """
        if self._running:
            return

        self._running = True

        def _loop():
            while self._running:
                try:
                    snap = self.collect_and_diff()
                    if on_change and (snap.completed_jobs or snap.failed_jobs or snap.active_jobs):
                        on_change(snap)
                except Exception as e:
                    logger.debug(f"상태 폴링 오류: {e}")

                import time
                # 풀링 간격을 0.5초 단위로 체크하여 빠른 종료 가능
                for _ in range(int(self._poll_interval / 0.5)):
                    if not self._running:
                        break
                    time.sleep(0.5)

        self._thread = threading.Thread(target=_loop, daemon=True, name="tray-status-poller")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5)
