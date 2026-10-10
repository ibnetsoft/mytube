"""Monitor public YouTube videos and persist learning signals.

This is intentionally best-effort. Monitoring failures must never block the
upload/release flow; they only reduce the amount of learning data available.
"""

from __future__ import annotations

import datetime
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional

from config import config
from services.web_admin_client import web_admin_client


MONITORING_SLOTS_HOURS = [1, 6, 24, 72, 168, 336, 720]


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt: datetime.datetime) -> str:
    return dt.astimezone(datetime.timezone.utc).isoformat()


def _parse_datetime(value: Any) -> Optional[datetime.datetime]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed.astimezone(datetime.timezone.utc)
    except Exception:
        return None


def _extract_video_id(metadata: Dict[str, Any], video_url: str = "") -> str:
    candidates = [
        metadata.get("videoId"),
        metadata.get("video_id"),
        metadata.get("youtube_video_id"),
        metadata.get("youtube_url"),
        video_url,
    ]
    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text:
            continue
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
            return text
        patterns = [
            r"[?&]v=([A-Za-z0-9_-]{11})",
            r"youtu\.be/([A-Za-z0-9_-]{11})",
            r"/shorts/([A-Za-z0-9_-]{11})",
            r"/embed/([A-Za-z0-9_-]{11})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
    return ""


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _duration_seconds(value: str) -> Optional[int]:
    if not value:
        return None
    match = re.fullmatch(
        r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?",
        value,
    )
    if not match:
        return None
    parts = {key: int(val or 0) for key, val in match.groupdict().items()}
    return parts["days"] * 86400 + parts["hours"] * 3600 + parts["minutes"] * 60 + parts["seconds"]


class YouTubeMonitoringService:
    def __init__(self):
        self.running = False
        self.thread = None
        self.interval = int(os.getenv("YOUTUBE_MONITOR_INTERVAL_SECONDS", "3600") or "3600")
        self.batch_limit = int(os.getenv("YOUTUBE_MONITOR_BATCH_LIMIT", "50") or "50")

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        print("[YouTubeMonitor] Service started.")

    def stop(self):
        self.running = False

    def _run(self):
        while self.running:
            try:
                self.collect_due_public_videos()
            except Exception as exc:
                print(f"[YouTubeMonitor] cycle failed: {exc}")
            time.sleep(max(60, self.interval))

    def collect_due_public_videos(self) -> Dict[str, int]:
        result = {"seen": 0, "due": 0, "captured": 0, "failed": 0}
        if not web_admin_client.has_supabase():
            return result

        api_key = self._youtube_api_key()
        if not api_key:
            return result

        requests_list = self._fetch_public_requests()
        now = _utc_now()
        for req in requests_list:
            result["seen"] += 1
            metadata = req.get("metadata") or {}
            video_id = _extract_video_id(metadata, req.get("video_url") or "")
            if not video_id:
                continue

            public_at = (
                _parse_datetime(metadata.get("made_public_at"))
                or _parse_datetime(metadata.get("published_at"))
                or _parse_datetime(req.get("created_at"))
            )
            if not public_at:
                continue

            slot = self._next_due_slot(metadata, public_at, now)
            if slot is None:
                continue
            result["due"] += 1

            try:
                metrics = self._fetch_video_metrics(video_id, api_key)
                if not metrics:
                    continue
                self._persist_capture(req, metadata, video_id, slot, public_at, metrics)
                result["captured"] += 1
            except Exception as exc:
                result["failed"] += 1
                print(f"[YouTubeMonitor] capture failed video={video_id}: {exc}")

        if result["due"] or result["captured"] or result["failed"]:
            print(f"[YouTubeMonitor] {result}")
        return result

    def _youtube_api_key(self) -> str:
        try:
            config.load_remote_keys_from_supabase()
        except Exception:
            pass
        keys = config.youtube_api_keys()
        return keys[0] if keys else ""

    def _fetch_public_requests(self) -> List[Dict[str, Any]]:
        response = web_admin_client.supabase_get(
            "publishing_requests",
            params={
                "select": "id,user_id,video_url,status,metadata,created_at",
                "status": "eq.public",
                "order": "created_at.desc",
                "limit": str(max(1, self.batch_limit)),
            },
            timeout=15,
        )
        if response is None or response.status_code >= 300:
            body = response.text[:200] if response is not None else "no response"
            print(f"[YouTubeMonitor] public request fetch failed: {body}")
            return []
        try:
            rows = response.json() or []
            return rows if isinstance(rows, list) else []
        except Exception:
            return []

    def _next_due_slot(
        self,
        metadata: Dict[str, Any],
        public_at: datetime.datetime,
        now: datetime.datetime,
    ) -> Optional[int]:
        monitoring = metadata.get("youtube_monitoring") or {}
        captured = {int(item) for item in monitoring.get("captured_slots_hours") or [] if str(item).isdigit()}
        hours_since_public = max(0, int((now - public_at).total_seconds() // 3600))
        due_slots = [slot for slot in MONITORING_SLOTS_HOURS if slot <= hours_since_public and slot not in captured]
        return due_slots[0] if due_slots else None

    def _fetch_video_metrics(self, video_id: str, api_key: str) -> Dict[str, Any]:
        from services.youtube_data_api import sync_youtube_get

        data = sync_youtube_get(
            "videos",
            {
                "part": "snippet,statistics,contentDetails",
                "id": video_id,
            },
            timeout=20,
        )
        items = data.get("items") or []
        if not items:
            raise RuntimeError("Video not found or not accessible through YouTube Data API.")
        item = items[0]
        stats = item.get("statistics") or {}
        snippet = item.get("snippet") or {}
        details = item.get("contentDetails") or {}
        return {
            "video_id": video_id,
            "title": snippet.get("title") or "",
            "channel_id": snippet.get("channelId") or "",
            "channel_title": snippet.get("channelTitle") or "",
            "published_at": snippet.get("publishedAt") or "",
            "duration_seconds": _duration_seconds(details.get("duration") or ""),
            "views": _to_int(stats.get("viewCount")),
            "likes": _to_int(stats.get("likeCount")),
            "comments": _to_int(stats.get("commentCount")),
            "raw_payload": item,
        }

    def _score(self, metrics: Dict[str, Any], slot_hours: int) -> Dict[str, Any]:
        views = max(0, int(metrics.get("views") or 0))
        likes = max(0, int(metrics.get("likes") or 0))
        comments = max(0, int(metrics.get("comments") or 0))
        views_per_hour = views / max(1, slot_hours)
        engagement_rate = (likes + comments * 2) / max(1, views)

        reach_score = min(40.0, views_per_hour / 25.0 * 40.0)
        engagement_score = min(35.0, engagement_rate / 0.04 * 35.0)
        comment_score = min(15.0, comments / max(1, views / 1000.0) / 20.0 * 15.0)
        freshness_score = 10.0 if slot_hours <= 24 else 6.0 if slot_hours <= 168 else 3.0
        total = round(reach_score + engagement_score + comment_score + freshness_score, 2)

        if total >= 75:
            label = "winner"
        elif engagement_rate >= 0.04 and views_per_hour < 10:
            label = "retention_good_low_reach"
        elif total >= 45:
            label = "promising"
        elif views_per_hour < 3:
            label = "underperforming"
        else:
            label = "neutral"

        return {
            "performance_score": total,
            "outcome_label": label,
            "views_per_hour": round(views_per_hour, 2),
            "engagement_rate": round(engagement_rate, 5),
        }

    def _build_learning_summary(self, metrics: Dict[str, Any], score: Dict[str, Any], slot_hours: int) -> Dict[str, Any]:
        label = score["outcome_label"]
        recommendations = []
        if label == "winner":
            recommendations.append("Reuse this title/topic pattern as a positive reference.")
            recommendations.append("Prioritize similar opening structure and metadata tone.")
        elif label == "retention_good_low_reach":
            recommendations.append("Content engagement is acceptable; test a stronger title and thumbnail.")
        elif label == "underperforming":
            recommendations.append("Avoid repeating this exact title/topic packaging without revision.")
            recommendations.append("Review hook, thumbnail promise, and category fit before generating similar videos.")
        else:
            recommendations.append("Keep as neutral benchmark data until later capture slots mature.")

        return {
            "summary": (
                f"{slot_hours}h public capture: {metrics.get('views', 0)} views, "
                f"{metrics.get('likes', 0)} likes, {metrics.get('comments', 0)} comments. "
                f"Score {score['performance_score']} ({label})."
            ),
            "recommendations": recommendations,
        }

    def _persist_capture(
        self,
        req: Dict[str, Any],
        metadata: Dict[str, Any],
        video_id: str,
        slot_hours: int,
        public_at: datetime.datetime,
        metrics: Dict[str, Any],
    ):
        now = _utc_now()
        project_id = metadata.get("project_id")
        score = self._score(metrics, slot_hours)
        learning = self._build_learning_summary(metrics, score, slot_hours)
        generation_context = {
            "title": metadata.get("title") or metrics.get("title"),
            "description": metadata.get("description"),
            "tags": metadata.get("tags"),
            "hashtags": metadata.get("hashtags"),
            "category_id": metadata.get("category_id"),
            "channel_id": metadata.get("channel_id"),
            "app_mode": metadata.get("app_mode"),
            "track_count": metadata.get("track_count"),
            "total_duration_seconds": metadata.get("total_duration_seconds") or metrics.get("duration_seconds"),
            "source": metadata.get("source"),
        }
        metric_payload = {
            "sync_key": f"ytmetric:{video_id}:{slot_hours}",
            "publishing_request_id": req.get("id"),
            "user_id": req.get("user_id"),
            "local_project_id": project_id,
            "video_id": video_id,
            "captured_at": _iso(now),
            "hours_since_public": slot_hours,
            "views": metrics.get("views", 0),
            "likes": metrics.get("likes", 0),
            "comments": metrics.get("comments", 0),
            "duration_seconds": metrics.get("duration_seconds"),
            "score": score,
            "metadata": generation_context,
            "raw_payload": metrics.get("raw_payload") or {},
        }
        snapshot_payload = {
            "sync_key": f"ytlearning:{video_id}:{slot_hours}",
            "publishing_request_id": req.get("id"),
            "user_id": req.get("user_id"),
            "local_project_id": project_id,
            "video_id": video_id,
            "captured_at": _iso(now),
            "hours_since_public": slot_hours,
            "performance_score": score["performance_score"],
            "outcome_label": score["outcome_label"],
            "learning_summary": learning["summary"],
            "recommendations": learning["recommendations"],
            "metrics": metric_payload,
            "generation_context": generation_context,
        }

        web_admin_client.upsert_by_key("youtube_video_metrics", "sync_key", metric_payload["sync_key"], metric_payload, timeout=15)
        web_admin_client.upsert_by_key("video_learning_snapshots", "sync_key", snapshot_payload["sync_key"], snapshot_payload, timeout=15)

        if project_id not in (None, ""):
            event_payload = {
                "sync_key": f"event:youtube_monitor:{video_id}:{slot_hours}",
                "local_event_id": None,
                "local_project_id": project_id,
                "project_sync_id": metadata.get("project_sync_id"),
                "user_id": req.get("user_id"),
                "employee_email": metadata.get("employee_email"),
                "project_name": metadata.get("project_name") or metadata.get("title") or "",
                "project_topic": metadata.get("topic") or "",
                "event_type": "youtube_public_metrics_captured",
                "stage": "youtube_monitoring",
                "source": "youtube_monitoring_service",
                "payload": snapshot_payload,
                "local_created_at": _iso(now),
                "synced_at": _iso(now),
            }
            web_admin_client.upsert_by_key("project_learning_events", "sync_key", event_payload["sync_key"], event_payload, timeout=15)

        monitoring = metadata.get("youtube_monitoring") or {}
        captured_slots = sorted({
            *(int(item) for item in monitoring.get("captured_slots_hours") or [] if str(item).isdigit()),
            slot_hours,
        })
        next_metadata = {
            **metadata,
            "youtube_monitoring": {
                **monitoring,
                "captured_slots_hours": captured_slots,
                "last_captured_at": _iso(now),
                "last_slot_hours": slot_hours,
                "last_metrics": {
                    "views": metrics.get("views", 0),
                    "likes": metrics.get("likes", 0),
                    "comments": metrics.get("comments", 0),
                    **score,
                },
            },
        }
        web_admin_client.supabase_patch(
            "publishing_requests",
            {"metadata": next_metadata},
            params={"id": f"eq.{req.get('id')}"},
            timeout=15,
        )


youtube_monitoring_service = YouTubeMonitoringService()
