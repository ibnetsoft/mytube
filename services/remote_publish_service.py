import datetime
import json
import os
import shutil
import tempfile
from typing import Any, Callable, Dict, Optional

import database as db
from config import config
from services.google_drive_service import google_drive_service
from services.web_admin_client import web_admin_client
from services.youtube_upload_service import youtube_upload_service


ProgressCallback = Callable[[int, str], None]


class RemotePublishService:
    """Publish approved web-admin requests directly from their Drive bundle."""

    def __init__(self, worker_id: str):
        self.worker_id = worker_id

    @staticmethod
    def _now() -> str:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    @staticmethod
    def _response_rows(response, action: str) -> list:
        if response is None:
            raise RuntimeError(f"{action}: Supabase connection is not configured.")
        if response.status_code not in (200, 201, 204):
            raise RuntimeError(f"{action}: HTTP {response.status_code} {response.text[:300]}")
        if not response.text:
            return []
        payload = response.json()
        return payload if isinstance(payload, list) else []

    def fetch_next_request(self) -> Optional[Dict[str, Any]]:
        response = web_admin_client.supabase_get(
            "publishing_requests",
            params={
                "select": "*",
                "status": "in.(approved,release_requested)",
                "order": "created_at.asc",
                "limit": "100",
            },
            timeout=15,
        )
        rows = self._response_rows(response, "Failed to fetch publishing queue")
        return next((row for row in rows if self._is_remote_worker_request(row)), None)

    @staticmethod
    def _is_remote_worker_request(request: Dict[str, Any]) -> bool:
        metadata = request.get("metadata") or {}
        return (
            metadata.get("source") == "render_queue_admin_upload"
            or metadata.get("upload_source") == "remote_drive_bundle"
        )

    def claim_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        request_id = request.get("id")
        source_status = str(request.get("status") or "")
        if not request_id or source_status not in ("approved", "release_requested"):
            return None

        operation = "release" if source_status == "release_requested" else "upload"
        metadata = {
            **(request.get("metadata") or {}),
            "publish_operation": operation,
            "publish_worker_id": self.worker_id,
            "publish_claimed_at": self._now(),
        }
        response = web_admin_client.supabase_patch(
            "publishing_requests",
            {"status": "to_be_published", "metadata": metadata},
            params={"id": f"eq.{request_id}", "status": f"eq.{source_status}"},
            timeout=15,
        )
        rows = self._response_rows(response, "Failed to claim publishing request")
        return rows[0] if rows else None

    def process_claimed_request(
        self,
        request: Dict[str, Any],
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, Any]:
        metadata = request.get("metadata") or {}
        operation = metadata.get("publish_operation") or "upload"
        try:
            if operation == "release":
                return self._release_to_public(request, progress_callback)
            return self._upload_from_drive(request, progress_callback)
        except Exception as exc:
            self._mark_failed(request, exc, operation)
            raise

    @staticmethod
    def _report(callback: Optional[ProgressCallback], progress: int, message: str) -> None:
        if callback:
            callback(progress, message)

    @staticmethod
    def _normalize_list(value: Any) -> list[str]:
        if isinstance(value, str):
            value = value.split(",")
        if not isinstance(value, list):
            return []
        result = []
        for item in value:
            cleaned = str(item or "").strip()
            if cleaned and cleaned not in result:
                result.append(cleaned)
        return result

    @staticmethod
    def _resolve_channel(metadata: Dict[str, Any]):
        channel_id = metadata.get("channel_id") or metadata.get("upload_channel_id")
        if channel_id in (None, ""):
            raise RuntimeError("YouTube upload channel is not assigned.")

        channel = db.get_channel(int(channel_id))
        if not channel:
            raise RuntimeError(f"YouTube channel {channel_id} is not configured on this render PC.")

        token_path = channel.get("credentials_path")
        if token_path and not os.path.isabs(token_path):
            token_path = os.path.join(config.BASE_DIR, token_path)
        if token_path:
            token_path = os.path.normpath(token_path)
        if not token_path or not os.path.exists(token_path):
            raise RuntimeError(f"YouTube token is missing for channel {channel.get('name') or channel_id}.")
        return channel, token_path

    @staticmethod
    def _load_drive_metadata(file_id: Optional[str]) -> Dict[str, Any]:
        if not file_id:
            return {}
        raw = google_drive_service.read_text_file(file_id)
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid YouTube metadata.json: {exc}") from exc

    def _upload_from_drive(
        self,
        request: Dict[str, Any],
        progress_callback: Optional[ProgressCallback],
    ) -> Dict[str, Any]:
        request_id = request.get("id")
        metadata = request.get("metadata") or {}
        video_file_id = metadata.get("drive_video_file_id") or metadata.get("result_video_file_id")
        if not video_file_id:
            raise RuntimeError("Drive video file ID is missing from the publishing request.")

        channel, token_path = self._resolve_channel(metadata)
        self._report(progress_callback, 10, "YouTube 업로드 메타데이터 확인 중...")
        drive_metadata = self._load_drive_metadata(
            metadata.get("drive_metadata_file_id") or metadata.get("result_metadata_file_id")
        )

        title = str(
            drive_metadata.get("title")
            or metadata.get("title")
            or metadata.get("project_name")
            or "Untitled Video"
        ).strip()
        description = str(drive_metadata.get("description") or metadata.get("description") or "")
        tags = self._normalize_list(drive_metadata.get("tags") or metadata.get("tags"))
        hashtags = self._normalize_list(drive_metadata.get("hashtags") or metadata.get("hashtags"))
        merged_tags = self._normalize_list(tags + hashtags)[:15]

        temp_dir = tempfile.mkdtemp(prefix=f"remote_publish_{request_id}_")
        thumbnail_warning = None
        try:
            video_name = str(metadata.get("drive_video_file_name") or "video.mp4")
            video_ext = os.path.splitext(video_name)[1] or ".mp4"
            video_path = os.path.join(temp_dir, f"video{video_ext}")
            self._report(progress_callback, 25, "Google Drive에서 완성 영상을 다운로드 중...")
            if not google_drive_service.download_file(video_file_id, video_path):
                raise RuntimeError("Failed to download the rendered video from Google Drive.")

            thumbnail_path = None
            thumbnail_file_id = metadata.get("drive_thumbnail_file_id") or metadata.get("result_thumbnail_file_id")
            if thumbnail_file_id:
                thumb_name = str(metadata.get("drive_thumbnail_file_name") or "thumbnail.jpg")
                thumb_ext = os.path.splitext(thumb_name)[1] or ".jpg"
                candidate = os.path.join(temp_dir, f"thumbnail{thumb_ext}")
                self._report(progress_callback, 45, "Google Drive에서 썸네일을 다운로드 중...")
                if google_drive_service.download_file(thumbnail_file_id, candidate):
                    thumbnail_path = candidate

            self._report(progress_callback, 60, f"{channel.get('name') or 'YouTube'} 채널에 비공개 업로드 중...")
            result = youtube_upload_service.upload_video(
                file_path=video_path,
                title=title,
                description=description,
                tags=merged_tags,
                category_id=str(metadata.get("youtube_category_id") or "22"),
                privacy_status=str(metadata.get("privacy_status") or "private"),
                publish_at=metadata.get("publish_at"),
                token_path=token_path,
                proxy=channel.get("proxy"),
            )
            video_id = (result or {}).get("id")
            if not video_id:
                raise RuntimeError("YouTube upload did not return a video ID.")

            if thumbnail_path:
                try:
                    self._report(progress_callback, 90, "YouTube 썸네일 적용 중...")
                    youtube_upload_service.set_thumbnail(
                        video_id=video_id,
                        thumbnail_path=thumbnail_path,
                        token_path=token_path,
                        proxy=channel.get("proxy"),
                    )
                except Exception as exc:
                    thumbnail_warning = str(exc)

            youtube_url = f"https://youtu.be/{video_id}"
            completed_metadata = {
                **metadata,
                "videoId": video_id,
                "youtube_video_id": video_id,
                "youtube_url": youtube_url,
                "upload_source": "remote_drive_bundle",
                "published_at": self._now(),
                "publish_error": None,
                "thumbnail_warning": thumbnail_warning,
            }
            self._patch_request(
                request_id,
                {"status": "published", "video_url": youtube_url, "metadata": completed_metadata},
            )
            self._sync_render_queue(metadata, "published", {
                "youtube_video_id": video_id,
                "youtube_url": youtube_url,
                "youtube_uploaded_at": completed_metadata["published_at"],
            })
            self._report(progress_callback, 100, "YouTube 비공개 업로드 완료")
            return {"status": "published", "video_id": video_id, "url": youtube_url}
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _release_to_public(
        self,
        request: Dict[str, Any],
        progress_callback: Optional[ProgressCallback],
    ) -> Dict[str, Any]:
        request_id = request.get("id")
        metadata = request.get("metadata") or {}
        video_id = metadata.get("videoId") or metadata.get("youtube_video_id")
        if not video_id:
            raise RuntimeError("YouTube video ID is missing from the release request.")

        channel, token_path = self._resolve_channel(metadata)
        self._report(progress_callback, 50, "YouTube 영상을 공개로 전환 중...")
        youtube_upload_service.update_video_privacy(
            str(video_id),
            "public",
            token_path=token_path,
            proxy=channel.get("proxy"),
        )
        public_url = f"https://youtu.be/{video_id}"
        completed_metadata = {
            **metadata,
            "youtube_url": public_url,
            "made_public_at": self._now(),
            "release_error": None,
        }
        self._patch_request(
            request_id,
            {"status": "public", "video_url": public_url, "metadata": completed_metadata},
        )
        self._sync_render_queue(metadata, "public", {
            "youtube_video_id": video_id,
            "youtube_url": public_url,
            "youtube_public_at": completed_metadata["made_public_at"],
        })
        self._report(progress_callback, 100, "YouTube 공개 전환 완료")
        return {"status": "public", "video_id": video_id, "url": public_url}

    def _patch_request(self, request_id: Any, payload: Dict[str, Any]) -> None:
        response = web_admin_client.supabase_patch(
            "publishing_requests",
            payload,
            params={"id": f"eq.{request_id}"},
            timeout=20,
        )
        rows = self._response_rows(response, "Failed to update publishing request")
        if not rows:
            raise RuntimeError(f"Publishing request {request_id} no longer exists.")

    def _sync_render_queue(
        self,
        metadata: Dict[str, Any],
        publish_status: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        project_id = metadata.get("project_id")
        if project_id in (None, ""):
            return
        try:
            response = web_admin_client.supabase_get(
                "remote_render_queue",
                params={
                    "select": "id,metadata,result_file_id",
                    "project_id": f"eq.{project_id}",
                    "status": "eq.completed",
                    "order": "created_at.desc",
                    "limit": "5",
                },
                timeout=15,
            )
            rows = self._response_rows(response, "Failed to find completed render queue row")
            expected_video_id = metadata.get("drive_video_file_id") or metadata.get("result_video_file_id")
            row = next(
                (item for item in rows if not expected_video_id or item.get("result_file_id") == expected_video_id),
                rows[0] if rows else None,
            )
            if not row:
                return
            queue_metadata = {
                **(row.get("metadata") or {}),
                "admin_publish_ready": True,
                "admin_publish_status": publish_status,
                "admin_action_required": "release" if publish_status == "published" else None,
                **(extra or {}),
            }
            web_admin_client.supabase_patch(
                "remote_render_queue",
                {"metadata": queue_metadata},
                params={"id": f"eq.{row['id']}"},
                timeout=15,
            )
        except Exception:
            # The publishing request is authoritative; queue badges are best effort.
            return

    def _mark_failed(self, request: Dict[str, Any], exc: Exception, operation: str) -> None:
        request_id = request.get("id")
        metadata = request.get("metadata") or {}
        error_text = str(exc)
        fallback_status = "published" if operation == "release" else "failed"
        failed_metadata = {
            **metadata,
            "publish_error" if operation == "upload" else "release_error": error_text,
            "failed_at" if operation == "upload" else "release_failed_at": self._now(),
        }
        try:
            self._patch_request(
                request_id,
                {"status": fallback_status, "metadata": failed_metadata},
            )
        finally:
            self._sync_render_queue(
                metadata,
                "publish_failed" if operation == "upload" else "release_failed",
                {"publish_error": error_text},
            )
