import sys
from pathlib import Path

# Ensure project root is in sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from worker_config import ensure_project_root_on_path
ensure_project_root_on_path()

import asyncio
import json
import os
import re
import time
import httpx
import traceback
from datetime import datetime, timezone
from difflib import SequenceMatcher

import job_store
from worker_config import STATE_DIR, OUTPUT_DIR, PROJECT_ROOT
import logging
from services import ai_router

logger = logging.getLogger("hermes_autopilot")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

STATE_FILE = STATE_DIR / "hermes_autopilot_state.json"
RESULTS_DIR = OUTPUT_DIR / "hermes_autopilot_results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
EXTERNAL_RUNNING_STATE_GRACE_SECONDS = 10 * 60

CATEGORIES = [
    "탈북사연",
    "해외감동",
    "노후금융",
    "황혼19금",
    "옛날이야기",
    "한국사연",
    "무협",
    "경제"
]

MIN_CATEGORY_TARGET_DURATION_SECONDS = 5 * 60
DEFAULT_CATEGORY_TARGET_DURATION_SECONDS = 150 * 60
MAX_CATEGORY_TARGET_DURATION_SECONDS = 150 * 60
DEFAULT_TARGET_DURATION_SECONDS_BY_CATEGORY = {
    category: DEFAULT_CATEGORY_TARGET_DURATION_SECONDS
    for category in CATEGORIES
}


class QualityGateError(RuntimeError):
    """Raised when a generated package is complete but not good enough to publish."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _format_view_count(value) -> str:
    try:
        return f"{int(value):,}회"
    except (TypeError, ValueError):
        return "확인 불가"


def _is_real_youtube_candidate(candidate: dict) -> bool:
    video_id = str(candidate.get("video_id") or "")
    return bool(video_id) and not video_id.startswith("dummy_")

class HermesAutopilotManager:
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(HermesAutopilotManager, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized:
            return
        self.is_running = False
        self.current_step = "idle"
        self.current_category = ""
        self.current_topic = ""
        self.current_topic_queue_id = ""
        self.current_image_style = ""
        self.last_run_status = "idle"
        self.last_error = ""
        self.last_completed_result_id = ""
        self._quality_feedback: list[str] = []
        self.logs = []
        self.loop_task = None
        
        # 신규 설정 및 통계 기본값
        self.settings = {
            "mode": "infinite",
            "target_limit": 10,
            "min_buffer_per_category": 5,
            "active_categories": CATEGORIES.copy(),
            "category_image_style_overrides": {},
            "benchmark_channel_ids_by_category": {},
            "benchmark_channel_auto_discovery_enabled": True,
            "benchmark_channel_discovery_min_channels": 8,
            "benchmark_channel_discovery_interval_hours": 24,
            "benchmark_channel_discovery_max_search_calls": 1,
            "benchmark_channel_discovery_last_at": {},
            "target_duration_seconds_by_category": DEFAULT_TARGET_DURATION_SECONDS_BY_CATEGORY.copy(),
            "force_generate": False,
            "quality_max_attempts": 1,
        }
        self.session_stats = {
            "generated_count": 0
        }
        
        self.initialized = True
        self._load_state()

    def _load_state(self):
        """Loads state from local JSON storage if exists."""
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                self.is_running = data.get("is_running", False)
                self.current_step = data.get("current_step", "idle")
                self.current_category = data.get("current_category", "")
                self.current_topic = data.get("current_topic", "")
                self.current_topic_queue_id = str(data.get("current_topic_queue_id") or "")
                self.current_image_style = data.get("current_image_style", "")
                self.last_run_status = data.get("last_run_status", "idle")
                self.last_error = data.get("last_error", "")
                self.last_completed_result_id = str(data.get("last_completed_result_id") or "")
                self.logs = data.get("logs", [])
                if self.last_run_status == "idle" and self.logs:
                    recent_text = "\n".join(str(item) for item in self.logs[-12:]).lower()
                    if "generation failed" in recent_text or "처리 중 에러" in recent_text or "error" in recent_text:
                        self.last_run_status = "failed"
                        self.last_error = self.last_error or self.logs[-1]
                        self.current_step = "failed"
                        self._save_state()
                
                # settings 로드
                loaded_settings = data.get("settings", {})
                if loaded_settings:
                    # 리스트 인스턴스 복사 누락 보완
                    for k, v in loaded_settings.items():
                        if k in self.settings:
                            self.settings[k] = v
                
                # stats 로드
                loaded_stats = data.get("session_stats", {})
                if loaded_stats:
                    self.session_stats.update(loaded_stats)
                
                # If it crashed/restarted while running, reset running flag gracefully
                if self.is_running:
                    self.is_running = False
                    self.last_run_status = "stopped"
                    self.current_step = "stopped"
                    self.add_log("시스템 재시작으로 인해 오토파일럿이 중단되었습니다. 대기 상태로 전환합니다.")
                    self._save_state()
            except Exception as e:
                logger.warning(f"Failed to load autopilot state: {e}")

    def _save_state(self):
        """Saves current state to local JSON storage."""
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "is_running": self.is_running,
                "current_step": self.current_step,
                "current_category": self.current_category,
                "current_topic": self.current_topic,
                "current_topic_queue_id": self.current_topic_queue_id,
                "current_image_style": self.current_image_style,
                "last_run_status": self.last_run_status,
                "last_error": self.last_error,
                "last_completed_result_id": self.last_completed_result_id,
                "logs": self.logs[-200:],  # keep last 200 logs
                "settings": self.settings,
                "session_stats": self.session_stats,
                "updated_at": time.time()
            }
            STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save autopilot state: {e}")

    def _active_autopilot_jobs(self) -> list[dict]:
        return [
            job
            for job in job_store.list_jobs(limit=100)
            if job.get("source") == "autopilot"
            and job.get("status") in {job_store.QUEUED, *job_store.ACTIVE_STATUSES}
        ]

    def _apply_persisted_status_fields(self, data: dict) -> None:
        self.current_step = data.get("current_step") or self.current_step
        self.current_category = data.get("current_category", self.current_category)
        self.current_topic = data.get("current_topic", self.current_topic)
        self.current_topic_queue_id = str(data.get("current_topic_queue_id") or self.current_topic_queue_id or "")
        self.current_image_style = data.get("current_image_style", self.current_image_style)
        self.last_run_status = data.get("last_run_status") or self.last_run_status
        self.last_error = data.get("last_error", self.last_error)
        self.last_completed_result_id = str(data.get("last_completed_result_id") or self.last_completed_result_id or "")
        if isinstance(data.get("logs"), list):
            self.logs = data["logs"]
        if isinstance(data.get("session_stats"), dict):
            self.session_stats.update(data["session_stats"])
        if isinstance(data.get("settings"), dict):
            for key, value in data["settings"].items():
                if key in self.settings:
                    self.settings[key] = value

    def _apply_external_running_state(self) -> None:
        """Hydrate a running Autopilot state saved by another dashboard process."""
        if self.is_running or not STATE_FILE.exists():
            return
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(data, dict) or not data.get("is_running"):
            return

        updated_at = 0.0
        try:
            updated_at = float(data.get("updated_at") or 0)
        except (TypeError, ValueError):
            updated_at = 0.0
        is_recent = bool(updated_at and time.time() - updated_at <= EXTERNAL_RUNNING_STATE_GRACE_SECONDS)
        if not is_recent and not self._active_autopilot_jobs():
            return

        self.is_running = True
        self._apply_persisted_status_fields(data)
        self.last_run_status = "running"

    def _apply_external_terminal_state(self) -> None:
        """Let the persisted terminal state win over stale in-memory running state.

        During dashboard/manager restarts there can briefly be two dashboard
        processes. One process may finish or stop Autopilot and persist
        ``is_running=False`` while another still has an old in-memory
        ``is_running=True`` snapshot. The status endpoint powers the page
        buttons, so reconcile before returning it.
        """
        if not self.is_running or not STATE_FILE.exists():
            return
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(data, dict) or data.get("is_running"):
            return

        if self._active_autopilot_jobs():
            return

        self.is_running = False
        self._apply_persisted_status_fields(data)
        self.current_step = data.get("current_step") or "stopped"
        self.last_run_status = data.get("last_run_status") or "stopped"

    def _apply_completed_worker_pipeline_state(self) -> None:
        """Reflect completed resume-driven Worker pipelines on the Autopilot page."""
        if self.is_running:
            return
        latest = None
        for job in job_store.list_jobs(limit=100):
            if (
                job.get("source") == "autopilot"
                and job.get("job_type") == "publish_metadata_generate"
                and job.get("status") == job_store.COMPLETED
            ):
                if latest is None or float(job.get("completed_at") or 0) > float(latest.get("completed_at") or 0):
                    latest = job
        if not latest:
            return

        latest_completed_at = float(latest.get("completed_at") or 0)
        state_updated_at = 0.0
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    state_updated_at = float(data.get("updated_at") or 0)
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                state_updated_at = 0.0

        if self.last_run_status == "completed" and self.last_completed_result_id == latest.get("job_id"):
            return
        if state_updated_at and state_updated_at > latest_completed_at and self.last_run_status not in {"failed", "stopped"}:
            return

        payload = latest.get("payload") if isinstance(latest.get("payload"), dict) else {}
        self.current_step = "completed"
        self.current_category = str(payload.get("category") or payload.get("category_name") or self.current_category or "")
        self.current_topic = str(payload.get("topic") or payload.get("upload_title") or self.current_topic or "")
        self.last_run_status = "completed"
        self.last_error = ""
        self.last_completed_result_id = str(latest.get("job_id") or self.last_completed_result_id or "")
        self.session_stats["generated_count"] = max(1, int(self.session_stats.get("generated_count") or 0))
        self._save_state()

    def _normalize_active_categories(self, value) -> list[str]:
        if not isinstance(value, list):
            return CATEGORIES.copy()
        valid = set(CATEGORIES)
        normalized = []
        for item in value:
            category = str(item or "").strip()
            if category not in valid:
                for encoding in ("latin1", "cp1252"):
                    try:
                        repaired = category.encode(encoding).decode("utf-8").strip()
                    except UnicodeError:
                        continue
                    if repaired in valid:
                        category = repaired
                        break
            if category in valid and category not in normalized:
                normalized.append(category)
        return normalized

    def _normalize_category_image_style_overrides(self, value) -> dict:
        current = dict(self.settings.get("category_image_style_overrides") or {})
        if not isinstance(value, dict) or not value:
            return current
        for cat, style in value.items():
            if cat not in CATEGORIES:
                continue
            style_str = str(style or "").strip().lower()
            if style_str:
                current[cat] = style_str
            else:
                current.pop(cat, None)
        return current

    def _apply_settings(self, new_settings: dict | None = None):
        if new_settings is not None and "force_generate" not in new_settings:
            self.settings["force_generate"] = False
        for k, v in (new_settings or {}).items():
            if k not in self.settings:
                continue
            if k == "active_categories":
                self.settings[k] = self._normalize_active_categories(v)
            elif k == "benchmark_channel_ids_by_category":
                self.settings[k] = self._normalize_benchmark_channel_settings(v)
            elif k == "benchmark_channel_discovery_last_at":
                self.settings[k] = self._normalize_category_timestamp_settings(v)
            elif k == "target_duration_seconds_by_category":
                self.settings[k] = self._normalize_category_duration_settings(v)
            elif k == "category_image_style_overrides":
                self.settings[k] = self._normalize_category_image_style_overrides(v)
            else:
                self.settings[k] = v

        self.settings["category_image_style_overrides"] = self._normalize_category_image_style_overrides(
            self.settings.get("category_image_style_overrides", {})
        )
        self.settings["active_categories"] = self._normalize_active_categories(
            self.settings.get("active_categories", CATEGORIES)
        )
        self.settings["benchmark_channel_ids_by_category"] = self._normalize_benchmark_channel_settings(
            self.settings.get("benchmark_channel_ids_by_category", {})
        )
        self.settings["benchmark_channel_discovery_last_at"] = self._normalize_category_timestamp_settings(
            self.settings.get("benchmark_channel_discovery_last_at", {})
        )
        self.settings["target_duration_seconds_by_category"] = self._normalize_category_duration_settings(
            self.settings.get("target_duration_seconds_by_category", {})
        )
        try:
            self.settings["target_limit"] = max(1, min(100, int(self.settings.get("target_limit", 1))))
        except (TypeError, ValueError):
            self.settings["target_limit"] = 1
        try:
            self.settings["min_buffer_per_category"] = max(0, int(self.settings.get("min_buffer_per_category", 5)))
        except (TypeError, ValueError):
            self.settings["min_buffer_per_category"] = 5
        self.settings["quality_max_attempts"] = 1
        try:
            self.settings["benchmark_channel_discovery_min_channels"] = max(
                1, min(30, int(self.settings.get("benchmark_channel_discovery_min_channels", 8)))
            )
        except (TypeError, ValueError):
            self.settings["benchmark_channel_discovery_min_channels"] = 8
        try:
            self.settings["benchmark_channel_discovery_interval_hours"] = max(
                1, min(168, int(self.settings.get("benchmark_channel_discovery_interval_hours", 24)))
            )
        except (TypeError, ValueError):
            self.settings["benchmark_channel_discovery_interval_hours"] = 24
        try:
            self.settings["benchmark_channel_discovery_max_search_calls"] = max(
                0, min(3, int(self.settings.get("benchmark_channel_discovery_max_search_calls", 1)))
            )
        except (TypeError, ValueError):
            self.settings["benchmark_channel_discovery_max_search_calls"] = 1
        if self.settings.get("mode") not in {"infinite", "target_limit"}:
            self.settings["mode"] = "target_limit"
        self.settings["force_generate"] = bool(self.settings.get("force_generate", False))
        self.settings["benchmark_channel_auto_discovery_enabled"] = bool(
            self.settings.get("benchmark_channel_auto_discovery_enabled", True)
        )

    def _normalize_benchmark_channel_settings(self, value) -> dict:
        if not isinstance(value, dict):
            return {}
        normalized = {}
        for category in CATEGORIES:
            raw = value.get(category)
            if isinstance(raw, str):
                parts = re.split(r"[\s,;]+", raw)
            elif isinstance(raw, list):
                parts = raw
            else:
                parts = []
            ids = []
            for item in parts:
                channel_id = str(item or "").strip()
                if channel_id and channel_id not in ids:
                    ids.append(channel_id)
            normalized[category] = ids
        return normalized

    def _normalize_category_timestamp_settings(self, value) -> dict:
        if not isinstance(value, dict):
            return {}
        normalized = {}
        for category in CATEGORIES:
            try:
                timestamp = float(value.get(category) or 0)
            except (TypeError, ValueError):
                timestamp = 0.0
            if timestamp > 0:
                normalized[category] = timestamp
        return normalized

    def _normalize_category_duration_settings(self, value) -> dict:
        normalized = DEFAULT_TARGET_DURATION_SECONDS_BY_CATEGORY.copy()
        if not isinstance(value, dict):
            return normalized
        for category in CATEGORIES:
            try:
                seconds = int(value.get(category) or 0)
            except (TypeError, ValueError):
                seconds = 0
            if seconds > 0:
                normalized[category] = max(
                    MIN_CATEGORY_TARGET_DURATION_SECONDS,
                    min(MAX_CATEGORY_TARGET_DURATION_SECONDS, seconds),
                )
        return normalized

    def _target_duration_seconds_for_category(self, category: str) -> int:
        durations = self.settings.get("target_duration_seconds_by_category") or {}
        try:
            return int(
                durations.get(category)
                or DEFAULT_TARGET_DURATION_SECONDS_BY_CATEGORY.get(category)
                or DEFAULT_CATEGORY_TARGET_DURATION_SECONDS
            )
        except (TypeError, ValueError):
            return (
                DEFAULT_TARGET_DURATION_SECONDS_BY_CATEGORY.get(category)
                or DEFAULT_CATEGORY_TARGET_DURATION_SECONDS
            )

    def _merge_channel_ids(self, *groups: list[str]) -> list[str]:
        merged = []
        for group in groups:
            for item in group or []:
                channel_id = str(item or "").strip()
                if channel_id and channel_id not in merged:
                    merged.append(channel_id)
        return merged[:30]

    def _load_local_benchmark_channels(self, category: str) -> list[str]:
        paths = [
            PROJECT_ROOT / "data" / "youtube_benchmark_channels.json",
            PROJECT_ROOT / "worker" / "youtube_benchmark_channels.json",
        ]
        keys = [category, str(category or "").casefold(), "default", "*"]
        for path in paths:
            if not path.exists():
                continue
            try:
                parsed = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                self.add_log(f"로컬 벤치마크 채널 풀 읽기 실패({path.name}): {exc}")
                continue
            if isinstance(parsed, dict):
                for key in keys:
                    value = parsed.get(key)
                    if isinstance(value, list):
                        channel_ids = self._merge_channel_ids(value)
                        if channel_ids:
                            return channel_ids
                    elif isinstance(value, str):
                        channel_ids = self._merge_channel_ids(re.split(r"[\s,;]+", value))
                        if channel_ids:
                            return channel_ids
            elif isinstance(parsed, list):
                channel_ids = self._merge_channel_ids(parsed)
                if channel_ids:
                    return channel_ids
        return []

    async def _fetch_remote_benchmark_channels(self, supabase_url: str, headers: dict, category: str) -> list[str]:
        if not supabase_url or not headers.get("apikey") or not category:
            return []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{supabase_url}/rest/v1/benchmark_channel_pool",
                    headers=headers,
                    params={
                        "select": "channel_id",
                        "category_name": f"eq.{category}",
                        "active": "eq.true",
                        "order": "last_seen_at.desc",
                        "limit": "30",
                    },
                )
            if response.status_code == 404:
                self.add_log("Supabase benchmark_channel_pool 테이블이 아직 없습니다. 로컬 채널 캐시를 사용합니다.")
                return []
            if response.status_code != 200:
                self.add_log(f"Supabase 채널 풀 조회 실패(status={response.status_code}): {response.text[:160]}")
                return []
            return self._merge_channel_ids([row.get("channel_id") for row in response.json() or []])
        except Exception as exc:
            self.add_log(f"Supabase 채널 풀 조회 실패(무시): {exc}")
            return []

    async def _upsert_remote_benchmark_channels(
        self,
        supabase_url: str,
        headers: dict,
        category: str,
        channel_ids: list[str],
        *,
        source: str = "auto",
        discovery_query: str = "",
    ) -> None:
        channel_ids = self._merge_channel_ids(channel_ids)
        if not supabase_url or not headers.get("apikey") or not category or not channel_ids:
            return
        now_iso = datetime.now(timezone.utc).isoformat()
        allowed_source = source if source in {"auto", "manual", "local_sync", "import"} else "auto"
        rows = [
            {
                "category_name": category,
                "channel_id": channel_id,
                "source": allowed_source,
                "discovery_query": discovery_query or None,
                "active": True,
                "last_seen_at": now_iso,
                "updated_at": now_iso,
            }
            for channel_id in channel_ids
        ]
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{supabase_url}/rest/v1/benchmark_channel_pool",
                    headers={
                        **headers,
                        "Prefer": "resolution=merge-duplicates,return=minimal",
                    },
                    params={"on_conflict": "category_name,channel_id"},
                    json=rows,
                )
            if response.status_code == 404:
                self.add_log("Supabase benchmark_channel_pool 테이블이 없어 채널 풀 원격 저장을 건너뜁니다.")
                return
            if response.status_code not in (200, 201, 204):
                self.add_log(f"Supabase 채널 풀 저장 실패(status={response.status_code}): {response.text[:160]}")
                return
            self.add_log(f"Supabase 채널 풀 저장 완료: {category} {len(channel_ids)}개")
        except Exception as exc:
            self.add_log(f"Supabase 채널 풀 저장 실패(무시): {exc}")

    async def _mark_remote_benchmark_channels_used(
        self,
        supabase_url: str,
        headers: dict,
        category: str,
        channel_ids: list[str],
    ) -> None:
        channel_ids = self._merge_channel_ids(channel_ids)
        if not supabase_url or not headers.get("apikey") or not category or not channel_ids:
            return
        quoted_ids = ",".join(channel_ids)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.patch(
                    f"{supabase_url}/rest/v1/benchmark_channel_pool",
                    headers={**headers, "Prefer": "return=minimal"},
                    params={
                        "category_name": f"eq.{category}",
                        "channel_id": f"in.({quoted_ids})",
                    },
                    json={
                        "last_used_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
        except Exception:
            pass

    def _should_discover_benchmark_channels(self, category: str, existing_channel_ids: list[str]) -> bool:
        if not self.settings.get("benchmark_channel_auto_discovery_enabled", True):
            return False
        if int(self.settings.get("benchmark_channel_discovery_max_search_calls") or 0) <= 0:
            return False
        min_channels = int(self.settings.get("benchmark_channel_discovery_min_channels") or 8)
        if len(existing_channel_ids or []) < min_channels:
            return True
        last_map = self.settings.get("benchmark_channel_discovery_last_at") or {}
        last_at = float(last_map.get(category) or 0)
        interval_seconds = int(self.settings.get("benchmark_channel_discovery_interval_hours") or 24) * 3600
        return (time.time() - last_at) >= interval_seconds

    async def _auto_discover_benchmark_channels(
        self,
        category: str,
        benchmark_keywords: list[str],
        existing_channel_ids: list[str],
        supabase_url: str = "",
        headers: dict | None = None,
    ) -> list[str]:
        headers = headers or {}
        existing = list(existing_channel_ids or [])
        if not self._should_discover_benchmark_channels(category, existing):
            return existing

        max_calls = int(self.settings.get("benchmark_channel_discovery_max_search_calls") or 1)
        queries = []
        for value in [*(benchmark_keywords or []), category]:
            query = " ".join(str(value or "").split()).strip()
            if query and query not in queries:
                queries.append(query)
        queries = queries[:max_calls]
        if not queries:
            return existing

        self.add_log(
            f"채널 풀 자동 업데이트: {category} 검색 {len(queries)}회 "
            f"(현재 {len(existing)}개, 목표 {self.settings.get('benchmark_channel_discovery_min_channels')}개)"
        )
        discovered = []
        discovery_query = ""
        attempted = False
        try:
            from services.youtube_data_api import async_youtube_get
            for query in queries:
                discovery_query = discovery_query or query
                attempted = True
                data = await async_youtube_get(
                    "search",
                    {
                        "part": "snippet",
                        "q": query,
                        "type": "video",
                        "maxResults": 5,
                        "order": "viewCount",
                        "relevanceLanguage": "ko",
                        "videoDuration": "medium",
                    },
                    timeout=12,
                )
                if data.get("error"):
                    self.add_log(f"채널 자동 업데이트 실패: {query} - {data.get('message') or data.get('error')}")
                    continue
                for item in data.get("items", []):
                    snippet = item.get("snippet") or {}
                    channel_id = str(snippet.get("channelId") or "").strip()
                    if not channel_id or channel_id in existing or channel_id in discovered:
                        continue
                    try:
                        import hermes_worker

                        is_relevant = hermes_worker._is_relevant_rss_candidate(
                            {
                                "title": snippet.get("title") or "",
                                "description": snippet.get("description") or "",
                                "channel_title": snippet.get("channelTitle") or "",
                            },
                            {
                                "category": category,
                                "category_name": category,
                                "search_keywords": benchmark_keywords or [],
                            },
                            category,
                        )
                    except Exception:
                        is_relevant = True
                    if not is_relevant:
                        self.add_log(
                            f"Discarded off-category discovered channel for '{category}': "
                            f"{snippet.get('channelTitle') or channel_id} / {snippet.get('title') or ''}"
                        )
                        continue
                    discovered.append(channel_id)
                    self.add_log(
                        f"새 벤치마크 채널 발견: {category} / "
                        f"{snippet.get('channelTitle') or channel_id} ({channel_id})"
                    )
        finally:
            if attempted:
                last_map = dict(self.settings.get("benchmark_channel_discovery_last_at") or {})
                last_map[category] = time.time()
                self.settings["benchmark_channel_discovery_last_at"] = self._normalize_category_timestamp_settings(last_map)

        if not discovered:
            self._save_state()
            return existing

        channel_map = self._normalize_benchmark_channel_settings(
            self.settings.get("benchmark_channel_ids_by_category") or {}
        )
        merged = [*existing, *discovered]
        channel_map[category] = merged[:30]
        self.settings["benchmark_channel_ids_by_category"] = channel_map
        self._save_state()
        self.add_log(f"채널 풀 자동 업데이트 완료: {category} {len(existing)}개 -> {len(channel_map[category])}개")
        await self._upsert_remote_benchmark_channels(
            supabase_url,
            headers,
            category,
            discovered,
            source="auto",
            discovery_query=discovery_query,
        )
        return channel_map[category]

    @staticmethod
    def _has_ready_media_prompts(structure: dict | None) -> bool:
        if not isinstance(structure, dict):
            return False
        scenes = structure.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            return False
        if structure.get("media_prompt_status") != "ready":
            return False
        max_video_prompt_scenes = 12
        for index, scene in enumerate(scenes, start=1):
            if not isinstance(scene, dict):
                return False
            if scene.get("media_prompt_status") != "ready":
                return False
            try:
                scene_number = int(scene.get("scene_order") or scene.get("scene_number") or index)
            except (TypeError, ValueError):
                scene_number = index
            requires_video_prompt = (
                scene.get("video_prompt_required") is not False
                and scene_number <= max_video_prompt_scenes
            )
            if requires_video_prompt and not str(scene.get("video_prompt") or "").strip():
                return False
        try:
            from services.image_grid_prompts import validate_image_grid_prompt_readiness
            validate_image_grid_prompt_readiness(
                scenes,
                structure.get("image_grid_prompts"),
                status=structure.get("image_grid_prompt_status"),
                require_status="ready",
            )
        except Exception:
            return False
        return True

    def add_log(self, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        if len(self.logs) > 300:
            self.logs = self.logs[-200:]
        logger.info(message)
        self._save_state()

    async def _mark_current_topic_failed(self, error: Exception):
        """Make a failed pre-generation visible to the user-facing topic/project."""
        topic_id = str(self.current_topic_queue_id or "").strip()
        if not topic_id:
            return
        supabase_url = (os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
        if not supabase_url or not supabase_key:
            return
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        message = str(error)[:2000]
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.patch(
                    f"{supabase_url}/rest/v1/topics_queue?id=eq.{topic_id}",
                    headers=headers,
                    json={
                        "pregenerated_structure_status": "failed",
                        "pregenerated_script_status": "failed",
                        "pregeneration_error": message,
                    },
                )
                if response.status_code not in (200, 204):
                    # Older schemas may not have pregeneration_error yet.
                    await client.patch(
                        f"{supabase_url}/rest/v1/topics_queue?id=eq.{topic_id}",
                        headers=headers,
                        json={
                            "pregenerated_structure_status": "failed",
                            "pregenerated_script_status": "failed",
                        },
                    )
        except Exception as exc:
            logger.warning("Failed to publish pre-generation failure for %s: %s", topic_id, exc)

    def get_status(self) -> dict:
        self._apply_settings()
        self._apply_external_running_state()
        self._apply_external_terminal_state()
        self._apply_completed_worker_pipeline_state()
        if not self.is_running and self.last_run_status == "running":
            self.last_run_status = "stopped"
            self.current_step = "stopped"
            self._save_state()
        return {
            "is_running": self.is_running,
            "current_step": self.current_step,
            "current_category": self.current_category,
            "current_topic": self.current_topic,
            "current_image_style": self.current_image_style,
            "last_run_status": self.last_run_status,
            "last_error": self.last_error,
            "last_completed_result_id": self.last_completed_result_id,
            "logs": self.logs,
            "settings": self.settings,
            "session_stats": self.session_stats
        }

    def _target_limit_reached(self) -> bool:
        if self.settings.get("mode") != "target_limit":
            return False
        try:
            generated = int(self.session_stats.get("generated_count", 0))
        except (TypeError, ValueError):
            generated = 0
        try:
            limit = int(self.settings.get("target_limit", 1))
        except (TypeError, ValueError):
            limit = 1
        return generated >= max(1, limit)

    def _stop_after_target_limit_failure(self, error: Exception) -> bool:
        if self.settings.get("mode") != "target_limit":
            return False
        self.last_run_status = "failed"
        self.last_error = str(error)
        self.current_step = "failed"
        self.is_running = False
        self.add_log(
            "Target-limit generation failed quality checks. "
            "Autopilot stopped without starting another title."
        )
        self._save_state()
        return True

    async def start(self, custom_settings: dict = None):
        async with self._lock:
            resume = bool((custom_settings or {}).get("resume"))
            self._resume_requested = resume
            self._apply_external_running_state()
            self._apply_external_terminal_state()
            if self.is_running:
                return {"success": True, "already_running": True}
            
            if custom_settings:
                self._apply_settings(custom_settings)
            else:
                self._apply_settings()
            if not self.settings.get("active_categories"):
                return {"success": False, "error": "At least one active category is required."}
            
            if not resume:
                self.session_stats["generated_count"] = 0
                self.last_completed_result_id = ""
                self.current_category = ""
                self.current_topic = ""
                self.current_topic_queue_id = ""
                self.current_image_style = ""
            self.last_run_status = "running"
            self.last_error = ""
            self.is_running = True
            self.current_step = "initializing"
            self.add_log("Hermes 자동 생성기(Autopilot) 시작 요청됨.")
            self.add_log(f"적용 설정: 모드={self.settings['mode']}, 제한량={self.settings['target_limit']}개, 최소유지량={self.settings['min_buffer_per_category']}개, 활성카테고리={len(self.settings['active_categories'])}개")
            
            self.loop_task = asyncio.create_task(self._run_loop())
            self._save_state()
            return {"success": True}

    async def save_settings(self, new_settings: dict):
        async with self._lock:
            self._apply_settings(new_settings)
            self._save_state()
            return {"success": True, "settings": self.settings}

    async def save_category_image_style_override(self, category: str, style_key: str | None):
        """Persist a Worker-local manual style choice with higher priority than AI selection."""
        if category not in CATEGORIES:
            return {"success": False, "error": "지원하지 않는 카테고리입니다."}
        normalized = str(style_key or "").strip().lower()
        async with self._lock:
            overrides = dict(self.settings.get("category_image_style_overrides") or {})
            if normalized:
                overrides[category] = normalized
            else:
                overrides.pop(category, None)
            self.settings["category_image_style_overrides"] = overrides
            self._save_state()
        self.add_log(
            f"이미지 스타일 수동 매칭 변경: {category} -> "
            f"{normalized or '자동 선택'}"
        )
        return {"success": True, "override": normalized or None}

    async def stop(self):
        async with self._lock:
            if not self.is_running:
                return {"success": False, "error": "실행 중이 아닙니다."}
            
            self.is_running = False
            self.last_run_status = "stopped"
            self.add_log("오토파일럿 중지 요청됨. 현재 진행 중인 스텝이 끝나는 대로 정지합니다.")
            if self.loop_task:
                self.loop_task.cancel()
            if self.last_run_status == "completed":
                self.current_step = "completed"
            elif self.last_run_status == "failed":
                self.current_step = "failed"
            else:
                self.current_step = "stopped"
            self._save_state()
            return {"success": True}

    def _extract_json_object(self, text: str) -> dict:
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text or "").strip()
        try:
            return json.loads(cleaned)
        except Exception:
            pass
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass

        # Gemini occasionally returns a valid-looking object with one broken
        # comma or quote. Recover title fields so one malformed response does
        # not restart the whole category loop or duplicate benchmark jobs.
        recovered_titles = []
        for title_match in re.finditer(r"[\"']title[\"']\s*:\s*([\"'])(.*?)(?<!\\)\1", cleaned, re.S):
            value = title_match.group(2).strip()
            if value and value not in recovered_titles:
                recovered_titles.append(value)
        if recovered_titles:
            return {
                "title_candidates": [
                    {"title": title, "angle": "recovered_from_malformed_ai_json"}
                    for title in recovered_titles[:10]
                ],
                "_parse_recovered": True,
            }

        # Callers already have category-safe fallbacks. Returning an empty
        # object lets them use those fallbacks instead of retrying forever.
        return {"_parse_recovered": False, "_parse_error": "AI response was not valid JSON"}

    def _clean_title_text(self, value: str) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        wrapping_pairs = [('"', '"'), ("'", "'"), ("`", "`"), ("“", "”"), ("‘", "’"), ("[", "]"), ("(", ")"), ("{", "}")]
        changed = True
        while changed and len(text) >= 2:
            changed = False
            for opening, closing in wrapping_pairs:
                if text.startswith(opening) and text.endswith(closing):
                    text = text[len(opening):-len(closing)].strip()
                    changed = True
                    break
        return re.sub(r"^\s*(?:\d+[\).\-\s]+|[-*]+\s*)", "", text).strip()

    def _title_similarity(self, left: str, right: str) -> float:
        a = re.sub(r"\s+", "", (left or "").lower())
        b = re.sub(r"\s+", "", (right or "").lower())
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a, b).ratio()

    def _category_label_terms(self, category: str) -> list[str]:
        terms = {
            "탈북사연": ["탈북사연", "탈북 사연"],
            "해외감동": ["해외감동", "해외 감동"],
            "노후금융": ["노후금융", "노후 금융"],
            "황혼19금": ["황혼19금", "황혼 19금", "19금", "19 금"],
            "옛날이야기": ["옛날이야기", "옛날 이야기", "전래이야기", "전래 이야기", "전래동화", "전래 동화"],
            "한국사연": ["한국사연", "한국 사연"],
            "무협": ["무협"],
            "경제": ["경제"],
        }
        return terms.get(category, [category] if category else [])

    def _contains_category_label(self, text: str, category: str) -> bool:
        raw = str(text or "")
        normalized = re.sub(r"[\s\W_]+", "", raw.lower())
        for term in self._category_label_terms(category):
            if not term:
                continue
            if term in raw:
                return True
            if re.sub(r"[\s\W_]+", "", term.lower()) in normalized:
                return True
        return False

    def _is_usable_title_candidate(self, title: str, category: str) -> bool:
        def has_balanced_quotes(value: str) -> bool:
            checks = [
                ('"', '"'),
                ("'", "'"),
                ("“", "”"),
                ("‘", "’"),
                ("「", "」"),
                ("『", "』"),
            ]
            for opening, closing in checks:
                if opening == closing:
                    if value.count(opening) % 2:
                        return False
                elif value.count(opening) != value.count(closing):
                    return False
            return True

        normalized_title = re.sub(r"[\s\W_]+", "", (title or "").lower())
        normalized_category = re.sub(r"[\s\W_]+", "", (category or "").lower())
        hard_meta_terms = [
            "스토리텔링", "성공 공식", "공식", "벤치마킹", "패턴", "알고리즘", "콘텐츠",
            "조회수", "분석", "전략", "비법", "비밀", "비결", "노하우", "해부",
            "대공개", "법칙", "불문율", "황금률", "치트키", "마스터의 길",
            "어떻게 쓰는", "쓰는 법", "만드는 법", "흥행", "몰입감",
            "storytelling", "formula", "secret", "strategy", "pattern", "analysis",
        ]
        forbidden_terms = [
            "성공 공식", "스토리텔링", "벤치마킹", "패턴", "알고리즘",
            "콘텐츠", "조회수", "분석", "전략", "공식", "비결", "연출",
            "노하우", "비법", "비밀", "해부", "황금률", "치트키", "필독", "마스터",
            "모든 것", "덕후", "팬덤", "명작", "망작", "작품", "시청자",
            "몰입감", "클리셰", "떡상", "황금 패턴", "대공개", "법칙", "불문율",
            "반전 사연", "반전 스토리",
        ]
        category_forbidden_terms = {
            "옛날이야기": [
                "옛날이야기", "전래이야기", "전래동화", "고전 재해석",
                "현대적 재해석", "MZ", "넷플릭스", "K-콘텐츠", "대박 콘텐츠",
            ],
        }
        return bool(
            normalized_title
            and normalized_title != normalized_category
            and 12 <= len(title) <= 90
            and has_balanced_quotes(title)
            and not self._contains_category_label(title, category)
            and not any(term.lower() in (title or "").lower() for term in hard_meta_terms)
            and not any(term in title for term in forbidden_terms)
            and not any(term in title for term in category_forbidden_terms.get(category, []))
        )

    def _is_usable_production_topic(self, topic: str, category: str) -> bool:
        text = (topic or "").strip()
        lowered = text.lower()
        if len(text) < 8:
            return False
        meta_terms = [
            "스토리텔링", "성공 공식", "공식", "벤치마킹", "패턴", "알고리즘", "콘텐츠",
            "조회수", "분석", "전략", "비법", "비밀", "비결", "노하우", "해부",
            "대공개", "법칙", "불문율", "황금률", "치트키", "마스터의 길",
            "어떻게 쓰는", "쓰는 법", "만드는 법", "흥행", "몰입감",
            "storytelling", "formula", "secret", "strategy", "pattern", "analysis",
        ]
        if any(term.lower() in lowered for term in meta_terms):
            return False
        if self._contains_category_label(text, category):
            return False
        if category == "무협" and not any(
            token in text
            for token in ["무사", "검", "강호", "문파", "사부", "제자", "고수", "복수", "비급", "천하", "객잔", "협객"]
        ):
            return False
        return True

    def _category_fallback_title(self, category: str) -> str:
        fallbacks = {
            "무협": "버림받은 삼류무사가 사부의 낡은 검보를 펼친 날",
            "탈북사연": "두만강 앞에서 마지막 선택을 해야 했던 한 가족의 밤",
            "해외감동": "낯선 나라의 작은 친절이 한 노인의 하루를 바꾼 순간",
            "노후금융": "월세 걱정하던 60대가 시골집 한 채로 생활비를 줄인 방법",
            "황혼19금": "평생 숨겨온 편지 한 장이 황혼의 마음을 흔든 날",
            "옛날이야기": "마을에서 쫓겨난 며느리가 십 년 뒤 들고 온 보따리",
            "한국사연": "가족을 위해 참아온 가장이 명절 아침에 남긴 한마디",
            "경제": "월급은 그대로인데 장바구니가 먼저 무너진 이유",
        }
        return fallbacks.get(category, f"{category} 속 평범한 선택이 인생을 바꾼 순간")

    def _score_title_candidate(
        self,
        title: str,
        category: str,
        benchmark_titles: list[str],
        learning_profile: dict | None = None,
    ) -> tuple[int, list[str]]:
        score = 70
        reasons = []
        length = len(title)
        forbidden_terms = [
            "성공 공식", "스토리텔링 비법", "벤치마킹", "패턴", "알고리즘",
            "콘텐츠", "조회수", "분석", "전략", "공식", "비결 분석",
            "스토리텔링", "연출", "노하우", "비법", "비밀", "해부", "황금률",
            "치트키", "필독", "마스터", "모든 것", "덕후", "팬덤",
            "명작", "망작", "작품", "시청자", "몰입감", "클리셰", "대공개", "법칙",
            "불문율", "반전 사연", "반전 스토리",
        ]
        hype_terms = ["충격", "소름", "레전드", "대박", "실화냐"]

        if 28 <= length <= 58:
            score += 12
            reasons.append("good_length")
        else:
            score -= abs(43 - length)
            reasons.append("length_penalty")

        if any(term in title for term in forbidden_terms):
            score -= 80
            reasons.append("meta_or_report_like_term")

        if self._contains_category_label(title, category):
            score -= 90
            reasons.append("literal_category_label")

        if category == "무협" and not any(term in title for term in ["무사", "검", "강호", "사부", "문파", "제자", "혈교", "마교", "비급", "복수", "천하", "고수"]):
            score -= 25
            reasons.append("not_martial_story_premise")

        hype_count = sum(1 for term in hype_terms if term in title)
        if hype_count:
            score -= 8 * hype_count
            reasons.append("hype_term_penalty")

        if re.search(r"\d", title):
            score += 5
            reasons.append("specific_detail")

        if any(token in title for token in ["왜", "뒤", "순간", "이유", "벌어진 일", "결국", "알게 된"]):
            score += 6
            reasons.append("curiosity_gap")

        max_similarity = max([self._title_similarity(title, t) for t in benchmark_titles] or [0.0])
        if max_similarity >= 0.72:
            score -= 40
            reasons.append("too_similar_to_benchmark")
        elif max_similarity >= 0.55:
            score -= 15
            reasons.append("somewhat_similar_to_benchmark")

        learning_profile = learning_profile or {}
        failed_titles = learning_profile.get("failed_titles") or []
        successful_titles = learning_profile.get("successful_titles") or []
        failed_similarity = max([self._title_similarity(title, t) for t in failed_titles] or [0.0])
        success_similarity = max([self._title_similarity(title, t) for t in successful_titles] or [0.0])
        if failed_similarity >= 0.62:
            score -= 22
            reasons.append("too_similar_to_failed_memory")
        if 0.22 <= success_similarity <= 0.58:
            score += 7
            reasons.append("structurally_close_to_success_memory")
        elif success_similarity >= 0.72:
            score -= 12
            reasons.append("too_similar_to_success_memory")

        if title.endswith(("다", "요", "음")) and "?" not in title:
            score -= 4
            reasons.append("sentence_like_ending")

        return max(0, min(100, score)), reasons

    def _select_title_plan(
        self,
        raw_plan: dict,
        category: str,
        benchmark_titles: list[str],
        learning_profile: dict | None = None,
    ) -> dict:
        raw_candidates = raw_plan.get("title_candidates") or raw_plan.get("titles") or []
        if not isinstance(raw_candidates, list):
            raw_candidates = []

        scored = []
        seen = set()
        for item in raw_candidates:
            if isinstance(item, dict):
                title = self._clean_title_text(item.get("title"))
                angle = str(item.get("angle") or "").strip()
            else:
                title = self._clean_title_text(item)
                angle = ""
            if not title or title in seen or not self._is_usable_title_candidate(title, category):
                continue
            seen.add(title)
            score, reasons = self._score_title_candidate(title, category, benchmark_titles, learning_profile)
            scored.append({"title": title, "angle": angle, "score": score, "score_reasons": reasons})

        scored.sort(key=lambda item: item["score"], reverse=True)
        viable = [item for item in scored if item["score"] >= 35]
        if viable:
            scored = viable
        else:
            fallback = self._clean_title_text(self._category_fallback_title(category))
            score, reasons = self._score_title_candidate(fallback, category, benchmark_titles, learning_profile)
            scored = [{"title": fallback, "angle": "fallback_low_quality_candidates", "score": score, "score_reasons": reasons}]

        selected = scored[0]
        return {
            "category": category,
            "generated_title": selected["title"],
            "selected_score": selected["score"],
            "title_candidates": scored[:10],
            "raw_plan": raw_plan,
            "learning_profile": learning_profile or {},
        }

    def _category_title_style(self, category: str) -> str:
        styles = {
            "탈북사연": "Use a human survival-story frame: one person, a concrete danger or choice, emotional stakes, and a restrained documentary tone.",
            "해외감동": "Use an emotional true-story frame: unexpected kindness, a visible conflict, and a warm reversal without melodrama.",
            "노후금융": "Use a retirement-money frame: concrete amounts, everyday anxiety, a decision, and a credible result. Avoid investment-hype wording.",
            "황혼19금": "Use a mature-life relationship frame: loneliness, secret, regret, reunion, or late-life choice. Keep it suggestive but not explicit.",
            "옛날이야기": "Write an in-world folk tale premise only: begin with a character, place, object, or incident, then reveal the conflict. Never use the category label '옛날이야기' in a title. Never mention retelling, modern adaptation, MZ, Netflix, content success, or how to make a folk tale.",
            "한국사연": "Use a Korean real-life story frame: family conflict, sacrifice, betrayal, workplace or neighborhood detail, and emotional payoff.",
            "무협": "Use a martial-arts fiction frame: weak/abandoned protagonist, sect conflict, hidden skill, revenge or awakening. Keep it genre-native.",
            "경제": "Use an economy-explainer frame: specific money/market signal, personal consequence, and a question viewers need answered.",
        }
        return styles.get(category, "Use concrete human stakes, a natural Korean YouTube title rhythm, and a clear curiosity gap.")

    def _title_generation_models(self) -> list[str]:
        from config import config as app_config

        candidates = [
            app_config.TITLE_GENERATION_MODEL,
            app_config.TOPIC_GENERATION_MODEL,
            "gemini-3-flash-preview",
            "gemini-2.5-flash",
        ]
        models: list[str] = []
        for model in candidates:
            model = str(model or "").strip()
            if model and model not in models:
                models.append(model)
        return models or ["gemini-2.5-flash"]

    async def _generate_title_text_with_fallback(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        task_type: str,
    ) -> str:
        last_error: Exception | None = None
        for model in self._title_generation_models():
            try:
                if model.lower().startswith("gemini"):
                    from services.gemini_service import gemini_service

                    return await gemini_service.generate_text(
                        prompt,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        task_type=task_type,
                    )
                return await ai_router.generate_text(
                    prompt,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    task_type=task_type,
                )
            except Exception as e:
                last_error = e
                logger.warning(f"{task_type} failed with model={model}; trying fallback if available: {e}")
        raise last_error or RuntimeError(f"{task_type} failed without a configured model")

    async def _ai_evaluate_title_plan(self, category: str, plan: dict, benchmark_titles: list[str]) -> dict:
        candidates = plan.get("title_candidates") or []
        if not candidates:
            return plan

        prompt = f"""
You are a strict Korean YouTube title editor.

Evaluate these candidate titles for:
1. natural Korean YouTube phrasing
2. click desire
3. fit with the category and the concrete title promise
4. low plagiarism risk against benchmark titles
5. low overpromise/clickbait risk

Hard rejection:
- Reject any candidate about storytelling, formulas, secrets, rules, principles, content strategy, analysis, or how to create/write the genre.
- For story categories, the best title must be the actual story premise itself, not a lecture about why the genre works.
- For martial-arts fiction, reject titles about 무협 스토리텔링, 불문율, 공식, 비법, 법칙, 성공, or 마스터의 길.
- Reject any title that literally contains the internal category label. Examples: "옛날이야기", "옛날 이야기", "황혼19금", "황혼 19금", "탈북사연", "해외감동", "한국사연", "노후금융", "무협", "경제".

CATEGORY: {category}
CATEGORY STYLE: {self._category_title_style(category)}
BENCHMARK TITLES: {json.dumps(benchmark_titles, ensure_ascii=False)}
LEARNING MEMORY: {json.dumps(plan.get("learning_profile") or {}, ensure_ascii=False)}
CANDIDATES: {json.dumps(candidates, ensure_ascii=False)}

Return ONLY JSON:
{{
  "evaluations": [
    {{"title": "same candidate title", "ai_score": 0, "reason": "short reason", "risk": "low|medium|high"}}
  ],
  "best_title": "exact title from candidates"
}}
"""
        try:
            raw_text = await self._generate_title_text_with_fallback(
                prompt,
                temperature=0.25,
                max_tokens=2000,
                task_type="hermes_autopilot_title_eval",
            )
            evaluation = self._extract_json_object(raw_text)
        except Exception as e:
            plan["evaluation_error"] = str(e)
            return plan

        by_title = {
            self._clean_title_text(item.get("title")): item
            for item in evaluation.get("evaluations", [])
            if isinstance(item, dict)
        }
        for candidate in candidates:
            ai_item = by_title.get(candidate["title"])
            if not ai_item:
                continue
            try:
                ai_score = max(0, min(100, int(ai_item.get("ai_score", 0))))
            except (TypeError, ValueError):
                ai_score = 0
            candidate["ai_score"] = ai_score
            candidate["ai_reason"] = str(ai_item.get("reason") or "").strip()
            candidate["risk"] = str(ai_item.get("risk") or "").strip()
            risk_penalty = 12 if candidate["risk"] == "high" else 5 if candidate["risk"] == "medium" else 0
            candidate["final_score"] = round(candidate["score"] * 0.45 + ai_score * 0.55 - risk_penalty, 2)

        for candidate in candidates:
            candidate.setdefault("final_score", candidate["score"])

        best_title = self._clean_title_text(evaluation.get("best_title"))
        candidates.sort(key=lambda item: (item.get("final_score", 0), item.get("score", 0)), reverse=True)
        selected = next((item for item in candidates if item["title"] == best_title), candidates[0])
        plan["generated_title"] = selected["title"]
        plan["selected_score"] = selected.get("final_score", selected.get("score", 0))
        plan["title_candidates"] = candidates[:10]
        plan["ai_evaluation"] = evaluation
        return plan

    async def _validate_title_against_script(self, category: str, title_plan: dict, script_text: str) -> dict:
        current_title = title_plan.get("generated_title") or ""
        candidates = title_plan.get("title_candidates") or []
        script_preview = (script_text or "")[:6000]
        prompt = f"""
You are a strict Korean YouTube metadata QA editor.

Check whether the selected upload title honestly matches the generated script.

CATEGORY: {category}
SELECTED TITLE: {current_title}
OTHER CANDIDATES: {json.dumps(candidates, ensure_ascii=False)}
SCRIPT PREVIEW:
{script_preview}

Rules:
- If the title promises a fact, twist, money amount, relationship, event, or reveal that the script does not support, status must be "revise".
- Prefer an existing candidate when it fits the script better.
- If you suggest a new title, keep it natural Korean and 28-58 characters.
- Never revise into a title about storytelling, formulas, secrets, rules, principles, content strategy, analysis, or how to create/write the genre.
- For martial-arts fiction, the title must sound like the title of a martial-arts story incident, not a documentary about 무협 writing or 무협 storytelling.
- Never revise into a title that literally contains the internal category label, such as 옛날이야기, 황혼19금, 탈북사연, 해외감동, 한국사연, 노후금융, 무협, or 경제.

Return ONLY JSON:
{{
  "status": "pass|revise",
  "title": "final title",
  "reason": "short Korean reason"
}}
"""
        try:
            raw_text = await self._generate_title_text_with_fallback(
                prompt,
                temperature=0.2,
                max_tokens=1000,
                task_type="hermes_autopilot_title_script_fit",
            )
            result = self._extract_json_object(raw_text)
        except Exception as e:
            title_plan["script_fit_error"] = str(e)
            return title_plan

        proposed_title = self._clean_title_text(result.get("title") or current_title)
        if result.get("status") == "revise" and proposed_title and self._is_usable_title_candidate(proposed_title, category):
            candidate_titles = [item.get("title") for item in candidates]
            if proposed_title not in candidate_titles:
                score, reasons = self._score_title_candidate(proposed_title, category, candidate_titles)
                candidates.append({
                    "title": proposed_title,
                    "angle": "script_fit_revision",
                    "score": score,
                    "final_score": score,
                    "score_reasons": reasons,
                })
            title_plan["generated_title"] = proposed_title
            title_plan["selected_score"] = next(
                (item.get("final_score", item.get("score", 0)) for item in candidates if item.get("title") == proposed_title),
                title_plan.get("selected_score", 0),
            )

        title_plan["title_candidates"] = candidates[:10]
        title_plan["script_fit"] = result
        return title_plan

    async def _fetch_learning_profile(
        self,
        supabase_url: str,
        headers: dict,
        category_id: str | None,
        category: str,
    ) -> dict:
        if not supabase_url or not headers.get("apikey"):
            return {}

        params = {
            "select": "generated_title,production_topic,title_score,script_score,outcome_quality,feedback_source,metrics,evaluation,created_at",
            "order": "created_at.desc",
            "limit": "30",
        }
        if category_id:
            params["category_id"] = f"eq.{category_id}"
        else:
            params["category_name"] = f"eq.{category}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{supabase_url}/rest/v1/content_generation_feedback",
                    headers=headers,
                    params=params,
                )
            if response.status_code != 200:
                self.add_log(f"Learning memory unavailable (status={response.status_code}): {response.text[:160]}")
                return {}
            rows = response.json()
        except Exception as e:
            self.add_log(f"Learning memory fetch failed (ignored): {e}")
            return {}

        performance_rows = []
        if category_id:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        f"{supabase_url}/rest/v1/video_learning_snapshots",
                        headers=headers,
                        params={
                            "select": "outcome_label,performance_score,learning_summary,recommendations,metrics,generation_context,captured_at",
                            "generation_context->>category_id": f"eq.{category_id}",
                            "order": "captured_at.desc",
                            "limit": "20",
                        },
                    )
                if response.status_code == 200:
                    performance_rows = response.json()
                elif response.status_code not in (400, 404):
                    self.add_log(f"Performance learning unavailable (status={response.status_code}): {response.text[:160]}")
            except Exception as e:
                self.add_log(f"Performance learning fetch failed (ignored): {e}")

        successful_titles = []
        failed_titles = []
        successful_script_patterns = []
        failed_script_patterns = []
        recurring_avoid_rules = []
        for row in rows or []:
            title = str(row.get("generated_title") or "").strip()
            evaluation = row.get("evaluation") or {}
            quality_report = evaluation.get("worker_script_quality_report") or {}
            blueprint = evaluation.get("narrative_blueprint") or {}
            title_score = float(row.get("title_score") or 0)
            script_score = float(row.get("script_score") or 0)
            blended = title_score * 0.45 + script_score * 0.55
            quality = row.get("outcome_quality")
            if quality in ("excellent", "good") or blended >= 75:
                if title:
                    successful_titles.append(title)
                strengths = [str(item).strip() for item in (quality_report.get("strengths") or []) if str(item or "").strip()]
                if strengths:
                    successful_script_patterns.extend(strengths[:3])
                if isinstance(blueprint, dict):
                    pattern = {
                        "logline": blueprint.get("logline"),
                        "central_conflict": blueprint.get("central_conflict"),
                        "turning_point": blueprint.get("turning_point"),
                        "final_payoff": blueprint.get("final_payoff"),
                    }
                    if any(pattern.values()):
                        successful_script_patterns.append(pattern)
            elif quality in ("poor", "rejected") or blended < 55:
                if title:
                    failed_titles.append(title)
                issues = [
                    str(item).strip()
                    for item in [
                        *(quality_report.get("critical_issues") or []),
                        *(quality_report.get("revision_notes") or []),
                    ]
                    if str(item or "").strip()
                ]
                failed_script_patterns.extend(issues[:5])
                recurring_avoid_rules.extend(issues[:5])

        performance_lessons = []
        for row in performance_rows or []:
            label = row.get("outcome_label")
            score = row.get("performance_score")
            summary = str(row.get("learning_summary") or "").strip()
            recommendations = row.get("recommendations") if isinstance(row.get("recommendations"), list) else []
            context = row.get("generation_context") or {}
            if summary or recommendations:
                performance_lessons.append({
                    "outcome": label,
                    "score": score,
                    "title": context.get("title"),
                    "summary": summary,
                    "recommendations": recommendations[:3],
                })

        def _dedupe(items, limit: int):
            seen = set()
            result = []
            for item in items:
                key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, dict) else str(item)
                if not key or key in seen:
                    continue
                seen.add(key)
                result.append(item)
                if len(result) >= limit:
                    break
            return result

        return {
            "sample_count": len(rows or []),
            "performance_sample_count": len(performance_rows or []),
            "successful_titles": successful_titles[:8],
            "failed_titles": failed_titles[:8],
            "successful_script_patterns": _dedupe(successful_script_patterns, 10),
            "failed_script_patterns": _dedupe(failed_script_patterns, 12),
            "performance_lessons": _dedupe(performance_lessons, 8),
            "script_generation_rules": {
                "reuse": "Reuse only abstract hook, tension, reveal, and payoff patterns from successful rows.",
                "avoid": _dedupe(recurring_avoid_rules, 10),
                "never": [
                    "Do not copy titles, names, incidents, or wording from previous outputs.",
                    "Do not write meta commentary about storytelling, strategy, analysis, algorithms, or content creation.",
                    "Do not save a script that fails the category promise or title promise.",
                ],
            },
            "recent_feedback": [
                {
                    "title": row.get("generated_title"),
                    "quality": row.get("outcome_quality"),
                    "title_score": row.get("title_score"),
                    "script_score": row.get("script_score"),
                    "source": row.get("feedback_source"),
                    "metrics": row.get("metrics") or {},
                    "script_quality": ((row.get("evaluation") or {}).get("worker_script_quality_report") or {}),
                }
                for row in (rows or [])[:10]
            ],
        }

    async def _generate_title_plan(
        self,
        category: str,
        candidates: list[dict],
        learning_profile: dict | None = None,
    ) -> dict:
        compact_candidates = []
        for candidate in candidates[:3]:
            compact_candidates.append({
                "title": candidate.get("title", ""),
                "view_count": candidate.get("view_count", 0),
                "subscriber_count": candidate.get("subscriber_count", 0),
                "performance_ratio": candidate.get("performance_ratio", 0.0),
                "analysis": candidate.get("analysis", {}),
                "success_strategies": candidate.get("success_strategies", []),
            })
        benchmark_titles = [item.get("title", "") for item in compact_candidates if item.get("title")]
        category_style = self._category_title_style(category)
        learning_profile = learning_profile or {}
        prompt = f"""
You are a senior Korean YouTube title strategist.

Create multiple fresh upload-title candidates for an AI-generated longform Korean video.

CATEGORY:
{category}

CATEGORY-SPECIFIC TITLE STYLE:
{category_style}

BENCHMARK VIDEOS TO LEARN FROM:
{json.dumps(compact_candidates, ensure_ascii=False)}

LEARNING MEMORY FROM PREVIOUS GENERATED OUTPUTS:
{json.dumps(learning_profile, ensure_ascii=False)}

Rules:
- CATEGORY is the internal genre/category label, not a generated story topic.
- Do not generate, return, or invent a separate production_topic, topic, premise, theme, lesson, secret, rule, formula, or storytelling method.
- Generate 10 Korean upload title candidates.
- Titles must sound like real Korean YouTube titles, not reports or analysis memos.
- The category is an internal label only. Never put the literal category label in the upload title.
- Bad examples: "옛날이야기", "옛날 이야기", "황혼19금", "황혼 19금", "탈북사연", "해외감동", "한국사연", "노후금융", "무협", "경제".
- Good titles describe the incident itself: a person, place, conflict, secret, decision, consequence, amount, or reveal.
- Do not copy benchmark titles, names, exact incidents, or phrasing.
- Avoid these words and phrases in titles: 성공 공식, 스토리텔링, 벤치마킹, 패턴, 황금 패턴, 비밀, 비결, 반전 사연, 반전 스토리, 알고리즘, 콘텐츠, 조회수, 분석, 전략, 공식, 연출, 노하우, 해부, 대공개, 법칙, 불문율.
- Never write creator-education, writing-advice, critique, or "how to make good stories" titles. The title must be the title of the fictional/story video itself.
- Never use benchmark analysis as subject matter. Use it only for pacing/hook structure. If the benchmark says "storytelling pattern", do NOT create a video about storytelling patterns.
- For the 옛날이야기 category, never write the words 옛날이야기, 전래동화, MZ, 넷플릭스, 재해석, or K-콘텐츠 in a title. Title the incident itself, such as a character's choice, a village conflict, a hidden object, or a consequence.
- For martial-arts fiction, titles must describe an in-world premise: a martial artist, sect, master, secret manual, betrayal, revenge, awakening, or Jianghu incident.
- For martial-arts fiction, NEVER create titles about martial-arts storytelling, martial-arts success rules, martial-arts formulas, martial-arts secrets, or "the way to write martial arts". Create the actual martial-arts story.
- Prefer concrete situations, human stakes, curiosity, and a natural documentary/story tone.
- Keep titles roughly 28-58 Korean characters.
- Use successful learning-memory titles only as structural inspiration; do not copy their wording.
- Avoid title shapes that are similar to failed or rejected learning-memory titles.

Return ONLY valid JSON in this schema:
{{
  "title_candidates": [
    {{"title": "업로드 제목 후보", "angle": "why it may work"}}
  ]
}}
"""
        raw_text = await self._generate_title_text_with_fallback(
            prompt,
            temperature=0.85,
            max_tokens=2500,
            task_type="hermes_autopilot_title_gen",
        )
        raw_plan = self._extract_json_object(raw_text)
        raw_plan.pop("production_topic", None)
        raw_plan.pop("topic", None)
        plan = self._select_title_plan(raw_plan, category, benchmark_titles, learning_profile)
        plan["category_style"] = category_style
        return await self._ai_evaluate_title_plan(category, plan, benchmark_titles)

    def _available_image_styles(self) -> list[dict]:
        """Read the Worker-managed image styles without inventing style keys."""
        try:
            from services.web_admin_client import web_admin_client
            remote = web_admin_client.fetch_style_presets(["image"])
            if remote:
                return remote
        except Exception as e:
            logger.warning(f"Image style catalog sync failed; using local cache: {e}")

        try:
            import database as db
            local = db.get_style_presets()
            return [
                {
                    "key_code": key,
                    "display_name_ko": value.get("display_name_ko") or key,
                    "prompt_template": value.get("prompt_value") or "",
                    "gemini_instruction": value.get("gemini_instruction") or "",
                }
                for key, value in local.items()
            ]
        except Exception as e:
            logger.warning(f"Local image style catalog unavailable: {e}")
            return []

    async def _select_image_style(
        self,
        category: str,
        upload_title: str,
        category_default: str,
        manual_override: str | None = None,
    ) -> dict:
        """Select one existing visual style for a generated video.

        The model may choose only from the Worker style catalog. A category
        default remains the fallback so a temporary AI/API failure never
        leaves the topic without a usable visual direction.
        """
        if not manual_override:
            manual_override = (self.settings.get("category_image_style_overrides") or {}).get(category)

        styles = self._available_image_styles()
        by_key = {}
        for item in styles:
            k = str(item.get("key_code") or "").strip().lower()
            if k:
                by_key[k] = item
                by_key[k.replace(" ", "_")] = item
                by_key[k.replace("_", " ")] = item
            name_ko = str(item.get("display_name_ko") or "").strip().lower()
            if name_ko:
                by_key[name_ko] = item
                by_key[name_ko.replace(" ", "")] = item

        manual_clean = str(manual_override or "").strip().lower()
        if manual_clean:
            matched_item = (
                by_key.get(manual_clean)
                or by_key.get(manual_clean.replace(" ", "_"))
                or by_key.get(manual_clean.replace("_", " "))
            )
            if not matched_item:
                for k, item in by_key.items():
                    if manual_clean in k or k in manual_clean:
                        matched_item = item
                        break
            if matched_item:
                canonical_key = str(matched_item.get("key_code") or manual_clean).strip()
                return {
                    "assigned_image_style": canonical_key,
                    "automatic_style": None,
                    "selection_source": "worker_manual_override",
                    "reason": f"Worker에서 수동 지정한 카테고리 이미지 스타일({canonical_key})을 우선 적용합니다.",
                }

        fallback = str(category_default or "").strip().lower()
        if fallback not in by_key:
            fallback = "realistic" if "realistic" in by_key else (next(iter(by_key.keys())) if by_key else "realistic")
        if not by_key:
            return {
                "assigned_image_style": fallback,
                "automatic_style": fallback,
                "selection_source": "fallback",
                "reason": "등록된 이미지 스타일 목록을 읽지 못해 카테고리 기본값을 사용합니다.",
            }

        catalog = [
            {
                "key": key,
                "name": item.get("display_name_ko") or key,
                "description": str(item.get("prompt_template") or "")[:260],
            }
            for key, item in by_key.items()
        ]

        category_style_hint = ""
        if category == "옛날이야기":
            category_style_hint = (
                "\nSPECIAL RULE FOR '옛날이야기': This is traditional Korean folk/historical tales (Joseon era). "
                "Strongly prioritize traditional Korean, oriental ink, folk art, historical illustration, or K-webtoon styles "
                "(e.g., oriental_ink, joseon_historical, k_webtoon, folk_art). Avoid generic Western/modern realism unless specifically indicated."
            )

        prompt = f"""
You are a visual director for a Korean YouTube longform video.
Choose exactly one visual style for this specific video from the provided catalog.
Do not invent a key. Do not default to realistic merely because it is safe.
Use the category default as a strong prior, but override it only when the title's era, genre, and emotional tone clearly need a different existing style.
{category_style_hint}

CATEGORY: {category}
CATEGORY DEFAULT STYLE: {fallback}
UPLOAD TITLE: {upload_title}

AVAILABLE STYLE CATALOG:
{json.dumps(catalog, ensure_ascii=False)}

Return ONLY JSON:
{{"style_key":"one catalog key", "reason":"short Korean reason"}}
""".strip()
        try:
            from config import config as app_config
            model = app_config.TITLE_GENERATION_MODEL or app_config.TOPIC_GENERATION_MODEL or "gemini-2.5-flash"
            raw = await ai_router.generate_text(
                prompt,
                model=model,
                temperature=0.2,
                max_tokens=500,
                task_type="hermes_image_style_select",
            )
            selected = self._extract_json_object(raw)
            style_key = str(selected.get("style_key") or "").strip().lower()
            if style_key not in by_key:
                raise ValueError(f"invalid image style key: {style_key!r}")
            return {
                "assigned_image_style": style_key,
                "automatic_style": style_key,
                "selection_source": "ai_catalog_selection",
                "reason": str(selected.get("reason") or "AI가 영상의 장르와 정서에 맞춰 선택했습니다.").strip()[:300],
                "category_default": fallback,
            }
        except Exception as e:
            logger.warning(f"Image style selection failed; using category default '{fallback}': {e}")
            return {
                "assigned_image_style": fallback,
                "automatic_style": fallback,
                "selection_source": "category_default_fallback",
                "reason": "스타일 자동 선택을 완료하지 못해 카테고리 기본 스타일을 사용합니다.",
                "category_default": fallback,
            }

    async def _discover_benchmark_keywords(self, category: str) -> list[str]:
        """Turn an internal category into concrete YouTube search phrases."""
        seed_map = {
            "경제": ["금값", "국제유가", "엔비디아 주가", "일본 금리", "미국 물가", "환율 전망", "부동산 시장"],
            "노후금융": ["국민연금", "퇴직연금", "노후 준비", "은퇴 자금", "건강보험료", "고령층 재테크"],
            "해외감동": ["해외 감동 실화", "외국인 한국 경험", "세계 감동 뉴스", "국제 미담"],
            "탈북사연": ["북한 탈북 실화", "탈북민 증언", "북한 생활 실상", "북한 가족 이야기"],
            "옛날이야기": [
                "조선시대 야담 실화", "옛날 한국 풍습 미스터리", "조선 기이한 이야기",
                "한국 민간 설화 전설", "조선시대 기담", "조선 양반 평민 사건",
                "옛날 시골 전설 기담", "고전 설화 명장면", "조선시대 미스터리 실화",
                "옛날이야기 감동 실화"
            ],
            "한국사연": ["한국 가족 사연", "실화 반전 이야기", "한국인 인생 사연", "시청자 사연"],
            "황혼19금": ["황혼 이혼", "중년 부부 갈등", "노년의 사랑", "50대 인생 사연"],
            "무협": ["무협 소설 명장면", "강호 복수극", "무림 고수 전설", "무협 몰락한 문파"],
        }
        seeds = seed_map.get(category, [category])
        if category == "옛날이야기":
            return seeds[:10]
        category_hint = ""
        if category == "경제":
            category_hint = (
                "\nFor the economy category only, use concrete subjects such as gold, oil, stocks, "
                "interest rates, inflation, exchange rates, housing, companies, and policy rather "
                "than the word 경제 alone."
            )
        prompt = f"""
You are a Korean YouTube trend researcher.
The internal genre label is: {category}
Generate 8 concrete Korean YouTube search phrases that people would actually search for now.
Do not return the genre label itself or generic phrases such as the genre followed by 이야기.
Prefer named issues, events, people, places, numbers, conflicts, or questions.
{category_hint}
Return ONLY a JSON array of strings.
"""
        discovered: list[str] = []
        try:
            from config import config as app_config
            raw = await ai_router.generate_text(
                prompt,
                model=app_config.TOPIC_GENERATION_MODEL or "gemini-2.5-flash",
                temperature=0.55,
                max_tokens=800,
                task_type="hermes_benchmark_keyword_discovery",
                use_search=True,
                # Gemini does not support responseMimeType together with
                # Google Search grounding. Parse the JSON array defensively
                # from the normal text response instead.
                json_mode=False,
            )
            match = re.search(r"\[[\s\S]*\]", raw or "")
            parsed = json.loads(match.group(0)) if match else []
            if isinstance(parsed, list):
                discovered = [str(item).strip() for item in parsed if str(item).strip()]
        except Exception as exc:
            self.add_log(f"Benchmark keyword discovery fallback for '{category}': {exc}")

        def is_allowed_keyword(item: str) -> bool:
            normalized_item = item.lower()
            if category == "옛날이야기":
                allowed_terms = [
                    "조선", "옛날", "전래", "민담", "민간", "설화", "풍습", "무속",
                    "마을", "시골", "전설", "야담", "고전", "한국", "기이", "괴담",
                    "미스터리", "한옥", "선비", "며느리", "구전", "옛이야기",
                ]
                blocked_terms = [
                    "금값", "코스피", "환율", "금리", "주가", "etf", "부동산", "pf",
                    "경제", "물가", "인플레이션", "유가", "달러", "원화", "투자",
                    "매수", "매도", "주식", "채권", "나스닥", "비트코인",
                ]
                if any(term in normalized_item for term in blocked_terms):
                    return False
                return any(term in item for term in allowed_terms)
            return True

        keywords: list[str] = []
        # Use trusted category seeds first. AI-discovered phrases are only an
        # expansion layer and must remain inside the selected category.
        for item in [*seeds, *discovered]:
            normalized = re.sub(r"\s+", " ", item).strip()
            if not normalized or normalized == category or normalized in keywords:
                continue
            if not is_allowed_keyword(normalized):
                self.add_log(f"Discarded off-category benchmark keyword for '{category}': {normalized}")
                continue
            keywords.append(normalized)
        return keywords[:10]

    def _load_cached_benchmark_result(self, category: str) -> dict | None:
        """Use the newest real benchmark when YouTube quota is temporarily unavailable.

        This is intentionally a continuity fallback, not a synthetic benchmark:
        every returned candidate must still have a real YouTube video id and
        API-backed performance metadata from a prior successful run.
        """
        def is_category_match(title: str) -> bool:
            if category != "옛날이야기":
                return True
            allowed_terms = [
                "조선", "옛날", "전래", "민담", "민간", "설화", "풍습", "무속",
                "마을", "시골", "전설", "야담", "고전", "한국", "기이", "괴담",
                "미스터리", "한옥", "선비", "며느리", "구전", "옛이야기", "정조",
            ]
            blocked_terms = [
                "금값", "코스피", "환율", "금리", "주가", "etf", "부동산", "pf",
                "경제", "물가", "인플레이션", "유가", "달러", "원화", "투자",
                "매수", "매도", "주식", "채권", "나스닥", "비트코인",
            ]
            lowered = title.lower()
            if any(term in lowered for term in blocked_terms):
                return False
            return any(term in title for term in allowed_terms)

        result_dir = Path(OUTPUT_DIR) / "hermes_results"
        files = sorted(result_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in files:
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if f'"job_type": "topic_benchmark_analyze"' not in raw:
                continue
            if f'"keyword": "{category}"' not in raw or '"status": "COMPLETED"' not in raw:
                continue

            candidates = []
            # Older benchmark files may contain malformed nested AI text. The
            # compact fields below are enough for title planning and are
            # extracted from each candidate block without trusting that text.
            blocks = re.findall(
                r'"search_rank"\s*:\s*\d+[\s\S]*?(?="search_rank"\s*:|\]\s*,\s*"audit_path")',
                raw,
            )
            for block in blocks[:3]:
                def field(pattern, default=""):
                    match = re.search(pattern, block)
                    return match.group(1) if match else default

                video_id = field(r'"video_id"\s*:\s*"([^"]+)"')
                title = field(r'"title"\s*:\s*"((?:\\.|[^"\\])*)"')
                if not video_id or video_id.startswith("dummy_") or not title:
                    continue
                try:
                    title = json.loads(f'"{title}"')
                except Exception:
                    pass
                if not is_category_match(title):
                    self.add_log(f"Discarded off-category cached benchmark for '{category}': {title}")
                    continue
                candidates.append({
                    "title": title,
                    "video_id": video_id,
                    "view_count": int(field(r'"view_count"\s*:\s*(\d+)', "0")),
                    "subscriber_count": int(field(r'"subscriber_count"\s*:\s*(\d+)', "0")),
                    "performance_ratio": float(field(r'"performance_ratio"\s*:\s*([\d.]+)', "0")),
                    "performance_data_source": "youtube_api_cached",
                    "analysis": {},
                    "success_strategies": [],
                })
            if candidates:
                return {
                    "candidates": candidates,
                    "audit_summary": {"cached_from": str(path), "cache_reason": "youtube_api_unavailable"},
                    "cached": True,
                }
        return None

    async def _run_loop(self):
        try:
            self.add_log("오토파일럿 백그라운드 태스크가 성공적으로 기동되었습니다.")
            idx = 0
            resume_category = getattr(self, "_resume_requested", False) and self.current_category
            self._resume_requested = False
            
            while self.is_running:
                if self._target_limit_reached():
                    self.add_log("Target limit already reached. Autopilot stopped.")
                    break

                active_cats = self._normalize_active_categories(
                    self.settings.get("active_categories", CATEGORIES)
                )
                self.settings["active_categories"] = active_cats
                if not active_cats:
                    self.add_log("No active categories configured. Autopilot stopped.")
                    break

                if resume_category in active_cats and idx == 0:
                    idx = active_cats.index(resume_category)
                    resume_category = None
                category = active_cats[idx % len(active_cats)]
                idx += 1
                self._quality_feedback = []
                
                # 활성 카테고리 체크
                active_cats = self.settings.get("active_categories", CATEGORIES)
                if category not in active_cats:
                    logger.info(f"카테고리 '{category}'는 설정에서 비활성화되어 있어 스킵합니다.")
                    await asyncio.sleep(0.5)
                    continue
                
                self.current_category = category
                self.current_step = f"[{category}] 유튜브 탐색 준비"
                self.add_log(f"==================================================")
                self.add_log(f"카테고리 '{category}'의 생성 루프 시작")
                
                try:
                    max_quality_attempts = int(self.settings.get("quality_max_attempts", 1))
                    for quality_attempt in range(1, max_quality_attempts + 1):
                        try:
                            if quality_attempt > 1:
                                self.add_log(
                                    f"품질 게이트 재생성 루프: '{category}' "
                                    f"{quality_attempt}/{max_quality_attempts}회차 시작"
                                )
                            await self._process_category(category)
                            break
                        except QualityGateError as quality_error:
                            self._quality_feedback = quality_error.errors[:20]
                            self.add_log(
                                f"❌ 품질 게이트 실패({quality_attempt}/{max_quality_attempts}): "
                                f"{quality_error}"
                            )
                            await self._mark_current_topic_failed(quality_error)
                            self.current_topic_queue_id = ""
                            if self._stop_after_target_limit_failure(quality_error):
                                break
                            if quality_attempt >= max_quality_attempts:
                                raise
                            await asyncio.sleep(2.0)
                    if not self.is_running:
                        break
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    error_detail = str(e) or repr(e) or type(e).__name__
                    self.last_run_status = "failed"
                    self.last_error = error_detail
                    self.add_log(f"❌ 카테고리 '{category}' 처리 중 에러 발생: {error_detail}")
                    logger.error(traceback.format_exc())
                    await self._mark_current_topic_failed(e)
                    if self.settings.get("mode") == "target_limit":
                        self.current_step = "generation_failed"
                        self.add_log(
                            "Target-limit generation failed before the full result was completed. "
                            "Autopilot stopped without selecting another title."
                        )
                        self.is_running = False
                        break
                    error_text = str(e).lower()
                    if any(marker in error_text for marker in (
                        "youtube search unavailable",
                        "youtube statistics unavailable",
                        "실제 youtube",
                        "youtube reference",
                        "benchmark cannot continue",
                    )):
                        self.current_step = "waiting_for_youtube_data"
                        self.add_log("YouTube benchmark data is unavailable. Autopilot stopped; retry after the API is available.")
                        self.is_running = False
                        break
                    await asyncio.sleep(5.0)  # 에러 발생 시 잠시 대기
                
                # 다음 카테고리 시작 전 짧은 간격
                if self._target_limit_reached():
                    self.add_log("Target limit reached after completed generation. Autopilot stopped.")
                    break

                await asyncio.sleep(3.0)

        except asyncio.CancelledError:
            self.last_run_status = "stopped"
            self.add_log("오토파일럿 루프가 취소되었습니다. 정지 완료.")
        finally:
            self.is_running = False
            if self.last_run_status == "completed":
                self.current_step = "completed"
            elif self.last_run_status == "failed":
                self.current_step = "failed"
            else:
                self.current_step = "stopped"
            self._save_state()

    async def _process_category(self, category: str):
        # 0. Supabase URL 및 키 읽기
        supabase_url = (os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
        
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json"
        }
        
        # categories 테이블에서 ID 확인 시도
        category_id = None
        # The category's default style is the authoritative choice for
        # automatic production. Carry it through the queue row, plan, and
        # script jobs instead of silently forcing every category to default.
        category_script_style = "default"
        category_image_style = "realistic"
        if supabase_url and supabase_key:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.get(
                        f"{supabase_url}/rest/v1/categories?select=id,name,default_script_style,default_image_style",
                        headers=headers
                    )
                    if r.status_code == 200:
                        cats = r.json()
                        for c in cats:
                            if c.get("name") == category:
                                category_id = c.get("id")
                                category_script_style = str(c.get("default_script_style") or "default").strip() or "default"
                                category_image_style = str(c.get("default_image_style") or "realistic").strip() or "realistic"
                                break
            except Exception as e:
                self.add_log(f"Supabase 카테고리 ID 조회 실패 (무시): {e}")

        # [신규] 카테고리별 최소 대기주제 유지량(min_buffer_per_category) 검사
        if supabase_url and supabase_key and category_id and not self.settings.get("force_generate"):
            try:
                min_buffer = self.settings.get("min_buffer_per_category", 5)
                async with httpx.AsyncClient(timeout=10.0) as client:
                    # Count only topics that the user app can actually expose:
                    # plan ready + script ready + scene image/video prompts ready.
                    r = await client.get(
                        f"{supabase_url}/rest/v1/topics_queue?select=id,pregenerated_structure,pregenerated_script"
                        f"&category_id=eq.{category_id}"
                        f"&status=eq.pending"
                        f"&pregenerated_structure_status=eq.ready"
                        f"&pregenerated_script_status=eq.ready"
                        f"&pregenerated_structure=not.is.null"
                        f"&pregenerated_script=not.is.null",
                        headers=headers
                    )
                    if r.status_code == 200:
                        existing_rows = r.json()
                        existing_pregens = [
                            row for row in existing_rows
                            if self._has_ready_media_prompts(row.get("pregenerated_structure"))
                            and str(row.get("pregenerated_script") or "").strip()
                        ]
                        if len(existing_pregens) >= min_buffer:
                            self.add_log(f"📋 '{category}' 카테고리는 이미 노출 가능한 준비 완료 주제가 {len(existing_pregens)}개 존재합니다. (설정 유지량: {min_buffer}개)")
                            self.add_log("목표 개수를 충족하여 생성을 생략합니다.")
                            return
            except Exception as e:
                self.add_log(f"Supabase 대기주제 개수 조회 실패 (무시하고 진행): {e}")
        elif self.settings.get("force_generate"):
            self.add_log(f"'{category}' 카테고리 강제 생성 모드: 기존 대기 대본 수와 관계없이 생성합니다.")

        # Do not persist a category-name placeholder.  Exploration can use a
        # local correlation ID; the real queue row is created only after title QA.
        topic_queue_id = f"local-auto-{int(time.time())}"
        self.add_log(f"적용 대본 스타일: {category_script_style}")

        # 2. 유튜브 탐색 및 분석 실행
        self.current_step = "유튜브 탐색 및 고성과 분석"
        self.add_log(f"유튜브에서 '{category}' 관련 인기 영상 탐색 시작...")
        
        benchmark_keywords = await self._discover_benchmark_keywords(category)
        self.add_log(f"Benchmark search keywords for '{category}': {', '.join(benchmark_keywords)}")
        benchmark_channel_ids = (
            (self.settings.get("benchmark_channel_ids_by_category") or {}).get(category)
            or []
        )
        local_channel_ids = self._load_local_benchmark_channels(category)
        if local_channel_ids:
            benchmark_channel_ids = self._merge_channel_ids(benchmark_channel_ids, local_channel_ids)
            self.add_log(f"로컬 벤치마크 채널 풀 적용: {category} {len(local_channel_ids)}개")
        remote_channel_ids = await self._fetch_remote_benchmark_channels(supabase_url, headers, category)
        if remote_channel_ids:
            benchmark_channel_ids = self._merge_channel_ids(remote_channel_ids, benchmark_channel_ids)
            channel_map = self._normalize_benchmark_channel_settings(
                self.settings.get("benchmark_channel_ids_by_category") or {}
            )
            channel_map[category] = benchmark_channel_ids
            self.settings["benchmark_channel_ids_by_category"] = channel_map
            self._save_state()
            self.add_log(f"Supabase 채널 풀 적용: {category} 원격 {len(remote_channel_ids)}개 병합")
        benchmark_channel_ids = await self._auto_discover_benchmark_channels(
            category,
            benchmark_keywords,
            benchmark_channel_ids,
            supabase_url,
            headers,
        )
        if benchmark_channel_ids:
            self.add_log(f"벤치마크 채널 RSS 풀 적용: {category} 채널 {len(benchmark_channel_ids)}개")
            await self._upsert_remote_benchmark_channels(
                supabase_url,
                headers,
                category,
                benchmark_channel_ids,
                source="local_sync",
            )
            await self._mark_remote_benchmark_channels_used(supabase_url, headers, category, benchmark_channel_ids)
        else:
            self.add_log(
                f"⚠️ {category} 벤치마크 채널 풀을 확보하지 못했습니다. "
                "YouTube 검색 쿼터/키 상태를 확인해야 합니다."
            )
        benchmark_job_id = job_store.submit_job(
            job_type="topic_benchmark_analyze",
            payload={
                "keyword": category,
                "category": category,
                "language": "ko",
                "video_type": "longform",
                "max_candidates": 3,
                "search_pool_size": 20,
                "search_keywords": benchmark_keywords,
                "benchmark_channel_ids": benchmark_channel_ids,
                "topic_queue_id": topic_queue_id
            },
            priority=100,
            source="autopilot"
        )
        self.add_log(f"-> topic_benchmark_analyze 작업 제출 완료 (Job ID: {benchmark_job_id})")
        
        # 작업 완료 대기
        try:
            await self._wait_for_job(benchmark_job_id)
            # 결과 읽기
            result_data = self._read_result_file(benchmark_job_id)
        except Exception as benchmark_error:
            cached = self._load_cached_benchmark_result(category)
            if not cached:
                raise
            result_data = cached
            self.add_log(
                f"YouTube API 일시 오류로 최근 실제 벤치마크를 재사용합니다: "
                f"{cached['audit_summary'].get('cached_from')} ({benchmark_error})"
            )
        if not result_data or "candidates" not in result_data or not result_data["candidates"]:
            raise RuntimeError("유튜브 벤치마크 탐색 결과 분석 데이터가 유효하지 않습니다.")
            
        candidates = result_data["candidates"]
        audit_path = result_data.get("audit_path")
        audit_summary = result_data.get("audit_summary") or {}
        best_candidate = candidates[0]
        video_title = best_candidate.get("title", "")
        performance_ratio = best_candidate.get("performance_ratio", 0.0)
        self.add_log(f"📈 벤치마크 탐색 완료: 대본 기획에 참조할 영상 {len(candidates)}개")
        for index, candidate in enumerate(candidates, start=1):
            if not _is_real_youtube_candidate(candidate):
                self.add_log(f"⚠️ 참조 영상 #{index}: 실제 YouTube 영상을 찾지 못해 대체값이 반환되었습니다. 이 결과로 생성하지 않습니다.")
                raise RuntimeError("실제 YouTube 참조 영상을 확보하지 못했습니다.")
            if candidate.get("performance_data_source") not in ("youtube_api", "youtube_api_cached", "youtube_rss_seed"):
                self.add_log(f"⚠️ 참조 영상 #{index}: YouTube 조회수 통계를 확인하지 못했습니다. 임의 성과 수치로는 생성하지 않습니다.")
                raise RuntimeError("실제 YouTube 성과 통계를 확보하지 못했습니다.")
            video_id = candidate.get("video_id")
            self.add_log(f"📺 참조 영상 #{index}: {candidate.get('title') or '(제목 없음)'}")
            self.add_log(
                f"   채널: {candidate.get('channel_title') or '확인 불가'} | "
                f"조회수: {_format_view_count(candidate.get('view_count'))} | "
                f"구독자 대비: {candidate.get('performance_ratio', 0)}배"
            )
            self.add_log(f"   URL: https://www.youtube.com/watch?v={video_id}")
        self.add_log(f"✅ 대표 참조 영상: '{video_title}' (구독자 대비 조회수 {performance_ratio}배)")

        # 3. AI 기반 새로운 영상 제목 생성
        self.current_step = "신규 오리지널 영상 제목 생성"
        self.add_log("학습된 벤치마크 분석 내용을 토대로 신규 유튜브 제목 기획 중...")
        
        
        learning_profile = await self._fetch_learning_profile(
            supabase_url,
            headers,
            str(category_id) if category_id else None,
            category,
        )
        if learning_profile.get("sample_count"):
            self.add_log(f"Learning memory loaded: {learning_profile['sample_count']} prior feedback row(s)")
        title_plan = await self._generate_title_plan(category, candidates, learning_profile)
        generated_title = title_plan["generated_title"]
        if not self._is_usable_title_candidate(generated_title, category):
            raise RuntimeError(f"Title QA rejected generated upload title: {generated_title!r}")
        self.current_step = "Gemini 웹 자료 조사"
        if result_data.get("cached"):
            research_sources = [
                {
                    "title": str(candidate.get("title") or "YouTube benchmark video"),
                    "url": f"https://www.youtube.com/watch?v={candidate.get('video_id')}",
                }
                for candidate in candidates[:3]
                if candidate.get("video_id")
            ]
            research_bundle = {
                "research_brief": "최근 실제 YouTube 벤치마크의 제목과 공개 성과를 바탕으로 기획을 이어갑니다.",
                "verified_facts": [],
                "story_material": "벤치마크 영상의 구조와 시청 반응을 참고하되 사실 주장은 별도로 검증합니다.",
                "risk_notes": ["실시간 웹 조사 대신 최근 저장된 YouTube 벤치마크를 사용함"],
                "sources": research_sources,
                "research_mode": "cached_benchmark_sources",
            }
            self.add_log(f"최근 실제 벤치마크 출처 {len(research_sources)}개로 웹 조사 단계를 대체합니다.")
        else:
            self.add_log(f"🔎 Gemini 웹 검색으로 '{generated_title}' 대본 자료를 조사합니다.")
            research_job_id = job_store.submit_job(
                job_type="web_research",
                payload={
                    "category": category,
                    "topic": category,
                    "upload_title": generated_title,
                    "benchmark_sources": [
                        {
                            "title": str(candidate.get("title") or "YouTube benchmark video"),
                            "url": f"https://www.youtube.com/watch?v={candidate.get('video_id')}",
                        }
                        for candidate in candidates[:3]
                        if candidate.get("video_id")
                    ],
                },
                priority=100,
                source="autopilot",
            )
            await self._wait_for_job(research_job_id)
            research_result = self._read_result_file(research_job_id) or {}
            research_bundle = research_result.get("research_bundle") or {}
            research_sources = research_bundle.get("sources") or []
        if not research_sources:
            raise RuntimeError("Gemini 웹 조사 결과에 검증 가능한 출처가 없습니다.")
        self.add_log(f"📚 Gemini 웹 자료 조사 완료: 출처 {len(research_sources)}개")
        for source in research_sources:
            self.add_log(f"   자료: {source.get('title') or '(제목 없음)'} | {source.get('url')}")
        manual_image_style = (self.settings.get("category_image_style_overrides") or {}).get(category)
        image_style_plan = await self._select_image_style(
            category, generated_title, category_image_style, manual_image_style
        )
        assigned_image_style = image_style_plan["assigned_image_style"]
        self.current_image_style = assigned_image_style
        self.add_log(
            f"이미지 스타일 확정: {assigned_image_style} "
            f"({image_style_plan.get('selection_source')}) - {image_style_plan.get('reason')}"
        )
        benchmark_payload = {
            "benchmark_job_id": benchmark_job_id,
            "audit_path": audit_path,
            "audit_summary": audit_summary,
            "candidates": candidates,
            "selected_candidate": best_candidate,
            "web_research": research_bundle,
            "title_generation": title_plan,
            "image_style_selection": image_style_plan,
        }
        self.current_topic = generated_title
        self.add_log(f"AI title selected for category '{category}': '{generated_title}'")
        self.add_log(f"AI title selected: '{generated_title}' (score={title_plan['selected_score']})")

        # Persist the category separately from the QA-approved upload title.
        if supabase_url and supabase_key:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    row_data = {
                        "topic": generated_title,
                        "assigned_employee_email": "hermes_worker@local",
                        "language": "ko",
                        "status": "pending",
                        "is_auto_generated": True,
                        "pregenerated_structure_status": "queued",
                        "pregenerated_script_status": "queued",
                        "benchmark_status": "ready",
                        "title_status": "ready",
                        "web_research_status": "ready",
                        "publish_metadata_status": "none",
                        "benchmark_analysis": benchmark_payload,
                        "generated_title": generated_title,
                        "title_candidates": title_plan["title_candidates"],
                        "assigned_script_style": category_script_style,
                        "assigned_image_style": assigned_image_style,
                    }
                    if category_id:
                        row_data["category_id"] = category_id
                    r = await client.post(
                        f"{supabase_url}/rest/v1/topics_queue",
                        headers={**headers, "Prefer": "return=representation"},
                        json=row_data,
                    )
                    if r.status_code not in (200, 201, 204) and "Could not find" in r.text:
                        optional_columns = {
                            "benchmark_status",
                            "title_status",
                            "web_research_status",
                            "publish_metadata_status",
                            "benchmark_analysis",
                            "generated_title",
                            "title_candidates",
                            "assigned_script_style",
                            "assigned_image_style",
                            "pregenerated_structure_status",
                            "pregenerated_script_status",
                        }
                        fallback_row_data = {
                            key: value for key, value in row_data.items()
                            if key not in optional_columns
                        }
                        self.add_log("Supabase schema is missing optional topic columns. Retrying topic insert with minimal fields.")
                        r = await client.post(
                            f"{supabase_url}/rest/v1/topics_queue",
                            headers={**headers, "Prefer": "return=representation"},
                            json=fallback_row_data,
                        )
                    if r.status_code not in (200, 201, 204):
                        raise RuntimeError(f"Supabase approved topic insert failed: {r.status_code} {r.text[:200]}")
                    response_rows = r.json()
                    topic_queue_id = response_rows[0].get("id") if isinstance(response_rows, list) else response_rows.get("id")
                    self.current_topic_queue_id = str(topic_queue_id or "")
                    if not topic_queue_id:
                        raise RuntimeError("Supabase approved topic insert did not return an ID")
                    self.add_log(f"Supabase: 검증된 업로드 제목 '{generated_title}' 등록 완료")
            except Exception as e:
                reason = str(e) or repr(e) or type(e).__name__
                self.current_topic_queue_id = str(topic_queue_id)
                self.add_log(
                    "Supabase 검증 제목 등록 실패: "
                    f"{reason}. 로컬 작업 ID({topic_queue_id})로 계속 생성합니다."
                )

        # 4. 구조 및 씬 기획 생성
        self.current_step = "대본 구조 및 씬 기획"
        self.add_log(f"카테고리 '{category}', 제목 '{generated_title}'의 씬 구조(Scene Plan) 생성 시작...")
        
        target_duration_seconds = self._target_duration_seconds_for_category(category)
        plan_job_id = job_store.submit_job(
            job_type="script_plan_generate",
            payload={
                "topic_queue_id": topic_queue_id,
                "category": category,
                "category_name": category,
                "category_id": category_id,
                "topic": generated_title,
                "target_duration_seconds": target_duration_seconds,
                "script_style": category_script_style,
                "image_style": assigned_image_style,
                "image_style_selection": image_style_plan,
                "language": "ko",
                "benchmark_analysis": {**(best_candidate.get("analysis") or best_candidate), "web_research": research_bundle},
                "upload_title": generated_title,
                "title_generation": title_plan,
                "research_bundle": research_bundle,
                "learning_profile": learning_profile,
                "defer_ready_until_quality_gate": True,
                "quality_feedback": getattr(self, "_quality_feedback", []),
            },
            priority=100,
            source="autopilot"
        )
        self.add_log(f"-> script_plan_generate 작업 제출 완료 (Job ID: {plan_job_id})")
        
        await self._wait_for_job(plan_job_id)
        
        plan_data = self._read_result_file(plan_job_id)
        if not plan_data or "structure" not in plan_data:
            raise RuntimeError("대본 구조 생성 데이터가 유효하지 않습니다.")
            
        structure = plan_data["structure"]
        scene_count = structure.get("scene_count", 0)
        self.add_log(f"📋 대본 구조 기획 성공. 총 {scene_count}개 씬 분할")

        # Supabase에 구조 동기화
        if supabase_url and supabase_key and topic_queue_id:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.patch(
                        f"{supabase_url}/rest/v1/topics_queue?id=eq.{topic_queue_id}",
                        headers={**headers, "Prefer": "return=minimal"},
                        json={
                            "pregenerated_structure": structure,
                            "pregenerated_structure_status": "queued",
                            "total_scenes": scene_count
                        }
                    )
                    if r.status_code in (200, 204):
                        self.add_log("Supabase: 대본 구조 임시 저장 완료(품질 게이트 전 ready 보류)")
            except Exception as e:
                self.add_log(f"Supabase 대본 구조 동기화 실패: {e}")

        # 5. 최종 대본 텍스트 생성
        self.current_step = "나레이션 대본 집필"
        self.add_log(f"씬 구조를 바탕으로 나레이션 본문 생성 중...")
        
        script_job_id = job_store.submit_job(
            job_type="script_generate",
            payload={
                "topic_queue_id": topic_queue_id,
                "category": category,
                "category_name": category,
                "category_id": category_id,
                "topic": generated_title,
                "structure": structure,
                "target_duration_seconds": target_duration_seconds,
                "script_style": category_script_style,
                "image_style": assigned_image_style,
                "image_style_selection": image_style_plan,
                "language": "ko",
                "narration_mode": "dramatic_single",
                "upload_title": generated_title,
                "title_generation": title_plan,
                "learning_profile": learning_profile,
                "defer_ready_until_quality_gate": True,
                "quality_feedback": getattr(self, "_quality_feedback", []),
            },
            priority=100,
            source="autopilot",
            max_retries=0,
        )
        self.add_log(f"-> script_generate 작업 제출 완료 (Job ID: {script_job_id})")
        
        await self._wait_for_job(script_job_id)
        
        script_data = self._read_result_file(script_job_id)
        if not script_data or "script" not in script_data:
            raise RuntimeError("대본 생성 본문 데이터가 유효하지 않습니다.")
            
        final_script = script_data["script"]
        if isinstance(script_data.get("structure"), dict):
            structure = script_data["structure"]
        narrative_blueprint = script_data.get("narrative_blueprint")
        script_quality_report = script_data.get("script_quality_report")
        sfx_cues = script_data.get("sfx_cues") or []
        sfx_cues_json = script_data.get("sfx_cues_json") or json.dumps(sfx_cues, ensure_ascii=False)
        char_count = len(final_script)
        self.add_log(f"✍️ 최종 대본 집필 완료 (총 글자수: {char_count}자)")

        title_plan = await self._validate_title_against_script(category, title_plan, final_script)
        generated_title = title_plan["generated_title"]
        benchmark_payload["title_generation"] = title_plan
        self.current_topic = generated_title
        self.add_log(f"Script-fit title: '{generated_title}'")

        self.current_step = "YouTube 설명·태그 생성"
        metadata_job_id = job_store.submit_job(
            job_type="publish_metadata_generate",
            payload={
                "topic_queue_id": topic_queue_id,
                "category": category,
                "category_name": category,
                "category_id": category_id,
                "topic": generated_title,
                "script": final_script,
                "structure": structure,
                "upload_title": generated_title,
                "title_generation": title_plan,
                "narrative_blueprint": narrative_blueprint or {},
                "script_quality_report": script_quality_report or {},
                "sfx_cues": sfx_cues,
                "sfx_cues_json": sfx_cues_json,
                "language": "ko",
                "defer_ready_until_quality_gate": True,
                "quality_feedback": getattr(self, "_quality_feedback", []),
            },
            priority=100,
            source="autopilot",
        )
        self.add_log(f"-> publish_metadata_generate 작업 제출 완료 (Job ID: {metadata_job_id})")
        await self._wait_for_job(metadata_job_id)
        metadata_data = self._read_result_file(metadata_job_id) or {}
        publish_metadata = metadata_data.get("publish_metadata") or {}
        if not publish_metadata:
            raise RuntimeError("publish_metadata_generate returned no publish_metadata")

        summary_payload = {
            "topic_queue_id": topic_queue_id,
            "category": category,
            "original_benchmark_title": video_title,
            "performance_ratio": performance_ratio,
            "benchmark_analysis": benchmark_payload,
            "benchmark_job_id": benchmark_job_id,
            "benchmark_audit_path": audit_path,
            "benchmark_audit_summary": audit_summary,
            "generated_title": generated_title,
            "title_generation": title_plan,
            "title_candidates": title_plan["title_candidates"],
            "narrative_blueprint": narrative_blueprint,
            "script_quality_report": script_quality_report,
            "sfx_cues": sfx_cues,
            "sfx_cues_json": sfx_cues_json,
            "image_style": assigned_image_style,
            "assigned_image_style": assigned_image_style,
            "image_style_selection": image_style_plan,
            "publish_metadata": publish_metadata,
            "structure": structure,
            "script": final_script,
            "char_count": char_count,
            "completed_at": time.time()
        }

        from services.generation_quality_gate import validate_generation_package

        quality_errors = validate_generation_package(summary_payload, category=category)
        if quality_errors:
            self.add_log("품질 게이트가 최종 패키지를 거부했습니다:")
            for error in quality_errors[:12]:
                self.add_log(f"  - {error}")
            raise QualityGateError(quality_errors)
        self.add_log("✅ 품질 게이트 통과: 대본/이미지/영상프롬프트/2x2/메타데이터 검증 완료")

        # Supabase에 최종 대본 동기화 및 큐 완료 처리
        if supabase_url and supabase_key and topic_queue_id:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.patch(
                        f"{supabase_url}/rest/v1/topics_queue?id=eq.{topic_queue_id}",
                        headers={**headers, "Prefer": "return=minimal"},
                        json={
                            "topic": generated_title,
                            "pregenerated_script": final_script,
                            "pregenerated_script_status": "ready",
                            "pregenerated_structure": structure,
                            "pregenerated_structure_status": "ready",
                            "total_scenes": structure.get("scene_count") or len(structure.get("scenes") or []),
                            "generated_title": generated_title,
                            "title_candidates": title_plan["title_candidates"],
                            "benchmark_analysis": benchmark_payload,
                            "narrative_blueprint": narrative_blueprint,
                            "script_quality_report": script_quality_report,
                            "publish_metadata": publish_metadata,
                            "progress_payload": {
                                "publish_metadata": publish_metadata,
                                "sfx_cues": sfx_cues,
                                "sfx_cues_json": sfx_cues_json,
                                "pregenerated_script_status": "ready",
                                "prepared_topic_ready": True,
                                "prepared_topic_ready_at": datetime.utcnow().isoformat() + "Z",
                            },
                            "publish_metadata_status": "ready",
                            "status": "pending"
                        }
                    )
                    if r.status_code not in (200, 204):
                        r = await client.patch(
                            f"{supabase_url}/rest/v1/topics_queue?id=eq.{topic_queue_id}",
                            headers={**headers, "Prefer": "return=minimal"},
                            json={
                                "topic": generated_title,
                                "pregenerated_script": final_script,
                                "pregenerated_script_status": "ready",
                                "pregenerated_structure": structure,
                                "pregenerated_structure_status": "ready",
                                "total_scenes": structure.get("scene_count") or len(structure.get("scenes") or []),
                                "generated_title": generated_title,
                                "title_candidates": title_plan["title_candidates"],
                                "benchmark_analysis": benchmark_payload,
                                "progress_payload": {
                                    "publish_metadata": publish_metadata,
                                    "sfx_cues": sfx_cues,
                                    "sfx_cues_json": sfx_cues_json,
                                    "pregenerated_script_status": "ready",
                                    "prepared_topic_ready": True,
                                    "prepared_topic_ready_at": datetime.utcnow().isoformat() + "Z",
                                },
                                "status": "pending"
                            }
                        )
                    if r.status_code in (200, 204):
                        self.add_log("Supabase: 대본 본문 및 상태(completed) 동기화 완료")
            except Exception as e:
                self.add_log(f"Supabase 대본 본문 동기화 실패: {e}")

        # 6. 로컬에 종합 최종 결과물 저장
        self.current_step = "로컬 저장 완료"
        self.add_log("종합 데이터를 로컬 결과 디렉토리에 백업 중...")
        
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        local_result_path = RESULTS_DIR / f"{topic_queue_id}.json"
        
        local_result_path.write_text(
            json.dumps(summary_payload, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        self.session_stats["generated_count"] += 1
        self._quality_feedback = []
        self.last_run_status = "completed"
        self.last_error = ""
        self.last_completed_result_id = str(topic_queue_id)
        self._save_state()
        self.add_log(
            f"Completed full generation count: "
            f"{self.session_stats['generated_count']}/{self.settings.get('target_limit', 10)}"
        )
        self.add_log(f"💾 로컬 백업 완료: {local_result_path}")
        self.add_log(f"🎉 '{category}' 카테고리의 1회차 자동 생성 완료!")

        # 세션 통계 및 목표 도달 점검
        mode = self.settings.get("mode", "infinite")
        limit = self.settings.get("target_limit", 10)
        generated = self.session_stats["generated_count"]
        
        if mode == "target_limit" and generated >= limit:
            self.add_log(f"🏁 설정된 목표 생성 총량({limit}개)에 도달했습니다. (현재 생성량: {generated}개)")
            self.is_running = False
            self.last_run_status = "completed"
            self.current_step = "completed"
            self._save_state()

    async def _wait_for_job(self, job_id: str):
        """Waits until the job state is COMPLETED, FAILED or CANCELED."""
        self.add_log(f"작업({job_id}) 처리 대기 시작...")
        
        while self.is_running:
            job = job_store.get_job(job_id)
            if not job:
                raise RuntimeError(f"작업({job_id})을 job_store에서 찾을 수 없습니다.")
                
            status = job.get("status")
            progress = job.get("progress", 0)
            progress_msg = job.get("progress_message", "")
            
            if status == "COMPLETED":
                self.add_log(f"작업 완료: {job_id}")
                return
            elif status in ("FAILED", "CANCELED"):
                err_msg = job.get("error_message") or "알 수 없는 에러"
                raise RuntimeError(f"작업({job_id})이 실패/취소되었습니다. 상태: {status}, 원인: {err_msg}")
                
            # 진행 상태 로그 노출
            step_desc = f"진행률 {progress}%"
            if progress_msg:
                step_desc += f" ({progress_msg})"
            self.current_step = f"Hermes 작업 처리 중 ({step_desc})"
            
            await asyncio.sleep(3.0)
            
        # 루프가 정지된 경우 취소 에러 발생
        raise asyncio.CancelledError()

    def _read_result_file(self, job_id: str) -> dict | None:
        """Reads result JSON file from hermes_results folder."""
        result_path = OUTPUT_DIR / "hermes_results" / f"{job_id}.json"
        if result_path.exists():
            try:
                return json.loads(result_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"Failed to read result file {result_path}: {e}")
        return None
