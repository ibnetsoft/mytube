"""
AIR Studio 시스템 트레이 상태 수집기
로컬 렌더링, 원격 렌더 큐, Hermes 워커 상태를 주기적으로 수집하고
변경을 감지하여 콜백을 트리거합니다.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import requests

# 프로젝트 모듈 경로 확보
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from config import config


# ─── 상태 데이터 클래스 ────────────────────────────────────────────────

@dataclass
class RenderJobStatus:
    """단일 렌더 작업 상태"""
    project_id: int
    project_name: str
    status: str          # rendering | completed | failed | pending
    progress: int        # 0-100, -1 = 실패
    source: str          # local | drive_api | queue
    message: str = ""

    @property
    def is_active(self) -> bool:
        return self.status == "rendering"

    @property
    def is_done(self) -> bool:
        return self.status in ("completed", "failed")


@dataclass
class HermesJobStatus:
    """단일 Hermes 작업 상태"""
    job_id: str
    job_type: str        # topic_research | topic_benchmark_analyze
    status: str          # pending | claimed | completed | failed
    worker_id: Optional[str] = None
    progress: int = 0

    @property
    def is_active(self) -> bool:
        return self.status == "claimed"

    @property
    def is_done(self) -> bool:
        return self.status in ("completed", "failed")


@dataclass
class TraySnapshot:
    """트레이에 표시할 전체 상태 스냅샷"""
    render_jobs: List[RenderJobStatus] = field(default_factory=list)
    hermes_jobs: List[HermesJobStatus] = field(default_factory=list)

    @property
    def active_renders(self) -> List[RenderJobStatus]:
        return [j for j in self.render_jobs if j.is_active]

    @property
    def active_hermes(self) -> List[HermesJobStatus]:
        return [j for j in self.hermes_jobs if j.is_active]

    @property
    def overall_status(self) -> str:
        """트레이 아이콘에 표시할 요약 상태"""
        if self.active_renders:
            avg = sum(j.progress for j in self.active_renders) // len(self.active_renders)
            return f"rendering:{avg}"
        if self.active_hermes:
            count = len(self.active_hermes)
            return f"hermes:{count}"
        return "idle"

    @property
    def tooltip_text(self) -> str:
        """트레이 툴팁 텍스트"""
        if self.active_renders:
            jobs = self.active_renders
            if len(jobs) == 1:
                return f"AIR Studio - 렌더링 중 ({jobs[0].progress}%)"
            return f"AIR Studio - {len(jobs)}개 렌더링 중"
        if self.active_hermes:
            count = len(self.active_hermes)
            return f"AIR Studio - Hermes {count}개 작업 중"
        return "AIR Studio - 대기 중"


# ─── 상태 수집기 ────────────────────────────────────────────────────

class TrayStatusCollector:
    """
    로컬/원격 렌더 상태 + Hermes 상태를 주기적으로 수집하고,
    이전 스냅샷과 비교하여 변경된 이벤트를 콜백으로 전달합니다.
    """

    def __init__(self, poll_interval: float = 10.0):
        self._poll_interval = poll_interval
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_snapshot: Optional[TraySnapshot] = None

        # 변경 감지 콜백: (old_snapshot, new_snapshot, changes_dict)
        self._on_change: Optional[Callable] = None

    # ── 공개 API ──

    def set_on_change(self, callback: Callable):
        """상태 변경 감지 콜백 등록

        callback(old_snapshot: TraySnapshot, new_snapshot: TraySnapshot,
                 changes: dict)
        changes 구조:
            "render_completed": [RenderJobStatus, ...]
            "render_failed": [RenderJobStatus, ...]
            "render_started": [RenderJobStatus, ...]
            "render_progress": [RenderJobStatus, ...]  # 진행률 변경만
            "hermes_completed": [HermesJobStatus, ...]
            "hermes_failed": [HermesJobStatus, ...]
            "hermes_started": [HermesJobStatus, ...]
        """
        self._on_change = callback

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        print("[TrayStatusCollector] 상태 수집기 시작 "
              f"(간격: {self._poll_interval}s)")

    def stop(self):
        self._running = False

    def get_current_snapshot(self) -> TraySnapshot:
        with self._lock:
            return self._last_snapshot or TraySnapshot()

    # ── 내부 폴링 루프 ──

    def _poll_loop(self):
        while self._running:
            try:
                snapshot = self._collect_snapshot()
                changes = self._detect_changes(self._last_snapshot, snapshot)

                with self._lock:
                    self._last_snapshot = snapshot

                if changes and self._on_change:
                    try:
                        self._on_change(self._last_snapshot, snapshot, changes)
                    except Exception as cb_err:
                        print(f"[TrayStatusCollector] 콜백 에러: {cb_err}")

            except Exception as e:
                print(f"[TrayStatusCollector] 폴링 에러: {e}")

            time.sleep(self._poll_interval)

    # ── 상태 수집 ──

    def _collect_snapshot(self) -> TraySnapshot:
        snapshot = TraySnapshot()

        # 1) 로컬 렌더 진행률 (in-memory RENDER_PROGRESS dict)
        self._collect_local_render_progress(snapshot)

        # 2) 로컬 렌더 큐 상태 (RenderQueueWorker)
        self._collect_queue_worker_status(snapshot)

        # 3) 원격 Drive API 렌더 상태 (Supabase)
        self._collect_remote_render_status(snapshot)

        # 4) Hermes 워커 상태 (Supabase)
        self._collect_hermes_status(snapshot)

        return snapshot

    def _collect_local_render_progress(self, snapshot: TraySnapshot):
        """services/progress.py의 RENDER_PROGRESS dict에서 로컬 렌더 상태 읽기"""
        try:
            from services.progress import RENDER_PROGRESS
            from database import db

            for project_id_str, data in list(RENDER_PROGRESS.items()):
                pid = int(project_id_str) if project_id_str.isdigit() else 0
                status = data.get("status", "unknown")
                progress = data.get("progress", 0)

                # 프로젝트명 조회
                project_name = str(project_id_str)
                try:
                    project = db.get_project_by_id(pid)
                    if project:
                        project_name = project.get("title", project_name) or project_name
                except Exception:
                    pass

                job = RenderJobStatus(
                    project_id=pid,
                    project_name=project_name,
                    status=status,
                    progress=progress,
                    source="local",
                )
                # 중복 방지: 동일 project_id+source 가 이미 있으면 갱신
                self._upsert_render_job(snapshot, job)
        except Exception as e:
            print(f"[TrayStatusCollector] 로컬 렌더 상태 수집 실패: {e}")

    def _collect_queue_worker_status(self, snapshot: TraySnapshot):
        """RenderQueueWorker의 활성/대기 작업 상태 수집"""
        try:
            from services.render_queue_worker import render_queue_worker
            queue_status = render_queue_worker.get_queue_status()

            # 활성 작업
            active = queue_status.get("active")
            if active:
                job = RenderJobStatus(
                    project_id=active.get("project_id", 0),
                    project_name=active.get("project_name", "Unknown"),
                    status="rendering",
                    progress=active.get("progress", 0),
                    source="queue",
                    message=active.get("message", ""),
                )
                self._upsert_render_job(snapshot, job)

            # 대기 큐
            for item in queue_status.get("queue", []):
                job = RenderJobStatus(
                    project_id=item.get("project_id", 0),
                    project_name=item.get("project_name", "Unknown"),
                    status="pending",
                    progress=0,
                    source="queue",
                )
                self._upsert_render_job(snapshot, job)
        except Exception as e:
            print(f"[TrayStatusCollector] 큐 워커 상태 수집 실패: {e}")

    def _collect_remote_render_status(self, snapshot: TraySnapshot):
        """Supabase remote_render_queue에서 원격 렌더 상태 수집"""
        try:
            supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            if not supabase_url or not supabase_key:
                return

            headers = {
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
            }

            # 진행 중 + 최근 완료(1시간 이내) 작업만 조회
            import datetime as _dt
            since = (_dt.datetime.utcnow() - _dt.timedelta(hours=1)).isoformat()

            params = {
                "or": f"(status.eq.rendering,status.eq.pending,status.eq.completed,status.eq.failed)",
                "updated_at": f"gte.{since}",
                "order": "updated_at.desc",
                "limit": "20",
            }

            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            resp = requests.get(
                f"{supabase_url.rstrip('/')}/rest/v1/remote_render_queue",
                headers=headers,
                params=params,
                timeout=10,
                verify=False,
                proxies={"http": None, "https": None},
            )

            if resp.status_code == 200:
                for row in resp.json():
                    job = RenderJobStatus(
                        project_id=row.get("project_id", 0),
                        project_name=row.get("project_name", "Remote"),
                        status=row.get("status", "unknown"),
                        progress=row.get("progress", 0),
                        source="drive_api",
                        message=row.get("message", ""),
                    )
                    self._upsert_render_job(snapshot, job)
        except Exception as e:
            print(f"[TrayStatusCollector] 원격 렌더 상태 수집 실패: {e}")

    def _collect_hermes_status(self, snapshot: TraySnapshot):
        """Supabase remote_hermes_queue에서 Hermes 워커 상태 수집"""
        try:
            supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            if not supabase_url or not supabase_key:
                return

            headers = {
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
            }

            import datetime as _dt
            since = (_dt.datetime.utcnow() - _dt.timedelta(hours=1)).isoformat()

            params = {
                "or": "(status.eq.pending,status.eq.claimed,status.eq.completed,status.eq.failed)",
                "updated_at": f"gte.{since}",
                "order": "updated_at.desc",
                "limit": "10",
            }

            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            resp = requests.get(
                f"{supabase_url.rstrip('/')}/rest/v1/remote_hermes_queue",
                headers=headers,
                params=params,
                timeout=10,
                verify=False,
                proxies={"http": None, "https": None},
            )

            if resp.status_code == 200:
                for row in resp.json():
                    job = HermesJobStatus(
                        job_id=str(row.get("id", "")),
                        job_type=row.get("job_type", "unknown"),
                        status=row.get("status", "unknown"),
                        worker_id=row.get("worker_id"),
                    )
                    snapshot.hermes_jobs.append(job)
        except Exception as e:
            print(f"[TrayStatusCollector] Hermes 상태 수집 실패: {e}")

    # ── 중복 관리 ──

    @staticmethod
    def _upsert_render_job(snapshot: TraySnapshot, job: RenderJobStatus):
        """동일 project_id+source의 기존 작업을 갱신하거나 추가"""
        key = (job.project_id, job.source)
        for i, existing in enumerate(snapshot.render_jobs):
            if (existing.project_id, existing.source) == key:
                snapshot.render_jobs[i] = job
                return
        snapshot.render_jobs.append(job)

    # ── 변경 감지 ──

    @staticmethod
    def _detect_changes(
        old: Optional[TraySnapshot],
        new: TraySnapshot,
    ) -> dict:
        """이전 스냅샷과 비교하여 변경된 이벤트 목록 반환"""
        if old is None:
            return {}  # 첫 수집은 변경 없음

        changes: dict[str, list] = {
            "render_completed": [],
            "render_failed": [],
            "render_started": [],
            "render_progress": [],
            "hermes_completed": [],
            "hermes_failed": [],
            "hermes_started": [],
        }

        # 기존 작업 맵 구성
        old_renders = {(j.project_id, j.source): j for j in old.render_jobs}
        old_hermes = {j.job_id: j for j in old.hermes_jobs}

        # 렌더 변경 감지
        for job in new.render_jobs:
            key = (job.project_id, job.source)
            prev = old_renders.get(key)

            if prev is None:
                # 새로 나타난 작업
                if job.is_active:
                    changes["render_started"].append(job)
            else:
                if prev.status != job.status:
                    if job.status == "completed":
                        changes["render_completed"].append(job)
                    elif job.status == "failed":
                        changes["render_failed"].append(job)
                    elif job.is_active and not prev.is_active:
                        changes["render_started"].append(job)
                elif prev.progress != job.progress and job.is_active:
                    changes["render_progress"].append(job)

        # 완료된 렌더가 이전에 활성이었으면 completed/failed로
        for key, prev_job in old_renders.items():
            if key not in {(j.project_id, j.source) for j in new.render_jobs}:
                if prev_job.is_active:
                    # 큐에서 사라진 작업 — 진행 상태 불명이므로 무시
                    pass

        # Hermes 변경 감지
        for job in new.hermes_jobs:
            prev = old_hermes.get(job.job_id)

            if prev is None:
                if job.is_active:
                    changes["hermes_started"].append(job)
            else:
                if prev.status != job.status:
                    if job.status == "completed":
                        changes["hermes_completed"].append(job)
                    elif job.status == "failed":
                        changes["hermes_failed"].append(job)
                    elif job.is_active and not prev.is_active:
                        changes["hermes_started"].append(job)

        # 빈 항목 제거
        return {k: v for k, v in changes.items() if v}


# ── 모듈 수준 싱글톤 ──

tray_status_collector = TrayStatusCollector(poll_interval=10.0)
