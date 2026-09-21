import datetime
import json
import os
import re
import uuid

import requests

import database as db
from config import config
from services.auth_service import auth_service
from services.google_drive_service import google_drive_service
from services.project_publish_service import queue_project_for_admin_publish
from services.remote_render_service import package_project_assets
from services.web_admin_client import web_admin_client


class RemoteDriveRenderService:
    """Google Drive API + Supabase queue entrypoint for remote rendering."""

    def _load_remote_drive_settings(self):
        """Ensure Drive API render settings saved in web-admin are available locally."""
        if getattr(config, "REMOTE_RENDER_DRIVE_FOLDER_ID", "") and getattr(config, "REMOTE_RENDER_GOOGLE_TOKEN_PATH", ""):
            return
        try:
            config.load_remote_keys_from_supabase()
        except Exception:
            pass

    def _get_drive_folder_id(self):
        self._load_remote_drive_settings()
        return (
            db.get_global_setting("remote_render_drive_folder_id", "")
            or getattr(config, "REMOTE_RENDER_DRIVE_FOLDER_ID", "")
            or None
        )

    def _get_google_token_path(self):
        self._load_remote_drive_settings()
        return (
            db.get_global_setting("remote_render_google_token_path", "")
            or getattr(config, "REMOTE_RENDER_GOOGLE_TOKEN_PATH", "")
            or None
        )

    def _desktop_auth(self):
        """[AIR-0225B] email/session_token for the desktop-render-queue bridge.
        Returns None if the user isn't logged in with a valid session (no
        service_role fallback - that key no longer ships in the desktop
        package, see worknote/AIR-0225B-stage0-service-role-removal-investigation.md)."""
        email = auth_service.get_user_email()
        token = auth_service.get_session_token()
        if not email or not token:
            return None
        return email, token

    def _post_queue_row(self, payload):
        auth = self._desktop_auth()
        if not auth:
            raise RuntimeError("Supabase queue credentials are not configured.")
        email, token = auth

        response = requests.post(
            f"{web_admin_client.dashboard_url}/api/desktop-render-queue",
            json={"email": email, "session_token": token, "payload": payload},
            timeout=20,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"remote_render_queue insert failed: {response.status_code} {response.text}")
        data = response.json()
        if not data.get("success"):
            raise RuntimeError(f"remote_render_queue insert failed: {data.get('error')}")
        return data.get("row")

    def get_queue_row(self, task_id: str):
        auth = self._desktop_auth()
        if not auth:
            return None
        email, token = auth

        response = requests.get(
            f"{web_admin_client.dashboard_url}/api/desktop-render-queue",
            params={"email": email, "session_token": token, "task_id": task_id},
            timeout=15,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"remote_render_queue fetch failed: {response.status_code} {response.text}")
        data = response.json()
        if not data.get("success"):
            raise RuntimeError(f"remote_render_queue fetch failed: {data.get('error')}")
        return data.get("row")

    def list_queue_rows(self, *, statuses=None, limit: int = 50):
        auth = self._desktop_auth()
        if not auth:
            return []
        email, token = auth

        params = {"email": email, "session_token": token, "limit": str(max(1, int(limit)))}
        if statuses:
            joined = ",".join(str(s).strip() for s in statuses if str(s).strip())
            if joined:
                params["statuses"] = joined

        response = requests.get(
            f"{web_admin_client.dashboard_url}/api/desktop-render-queue",
            params=params,
            timeout=15,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"remote_render_queue list failed: {response.status_code} {response.text}")
        data = response.json()
        if not data.get("success"):
            raise RuntimeError(f"remote_render_queue list failed: {data.get('error')}")
        rows = data.get("rows")
        return rows if isinstance(rows, list) else []

    def _project_output_dir(self, project_id: int):
        project = db.get_project(project_id) or {}
        safe_name = re.sub(r'[\\/*?:"<>|]', "", project.get("name") or f"project_{project_id}").strip().replace(" ", "_")
        today = config.get_kst_time().strftime("%Y%m%d")
        folder_name = f"{safe_name}_{today}"
        abs_path = os.path.join(config.OUTPUT_DIR, folder_name)
        os.makedirs(abs_path, exist_ok=True)
        return abs_path, f"/output/{folder_name}"

    def sync_completed_result(self, project_id: int):
        settings = db.get_project_settings(project_id) or {}
        task_id = settings.get("remote_task_id")
        if not task_id:
            return None

        row = self.get_queue_row(task_id)
        if not row:
            return None

        status = row.get("status")
        row_metadata = row.get("metadata") or {}
        if status == "failed":
            db.update_project(project_id, status="failed")
            db.update_project_setting(project_id, "remote_render_error", row.get("error_message") or row.get("message"))
            db.update_project_setting(project_id, "admin_publish_status", "render_failed")
            return row

        if status != "completed" or not row.get("result_file_id"):
            db.update_project_setting(project_id, "remote_render_progress", str(row.get("progress", 0)))
            db.update_project_setting(project_id, "remote_render_message", row.get("message") or "")
            return row

        output_dir, web_dir = self._project_output_dir(project_id)
        filename = row.get("result_file_name") or f"remote_drive_render_{project_id}.mp4"
        if not filename.lower().endswith(".mp4"):
            filename = f"{filename}.mp4"
        local_path = os.path.join(output_dir, filename)

        if not os.path.exists(local_path):
            token_path = self._get_google_token_path()
            downloaded = google_drive_service.download_file(row["result_file_id"], local_path, token_path=token_path)
            if not downloaded:
                raise RuntimeError("Failed to download completed remote render result from Google Drive.")

        web_video_path = f"{web_dir}/{filename}"
        db.update_project_setting(project_id, "video_path", web_video_path)
        db.update_project_setting(project_id, "remote_result_file_id", row.get("result_file_id"))
        db.update_project_setting(project_id, "remote_result_file_name", row.get("result_file_name"))
        db.update_project_setting(project_id, "drive_project_folder_id", row_metadata.get("result_folder_id"))
        db.update_project_setting(project_id, "drive_project_folder_name", row_metadata.get("result_folder_name"))
        db.update_project_setting(project_id, "drive_video_file_id", row_metadata.get("result_video_file_id") or row.get("result_file_id"))
        db.update_project_setting(project_id, "drive_video_file_name", row_metadata.get("result_video_file_name") or row.get("result_file_name"))
        db.update_project_setting(project_id, "drive_thumbnail_file_id", row_metadata.get("result_thumbnail_file_id"))
        db.update_project_setting(project_id, "drive_thumbnail_file_name", row_metadata.get("result_thumbnail_file_name"))
        db.update_project_setting(project_id, "drive_metadata_file_id", row_metadata.get("result_metadata_file_id"))
        db.update_project_setting(project_id, "drive_metadata_file_name", row_metadata.get("result_metadata_file_name"))
        db.update_project_setting(project_id, "remote_render_progress", "100")
        db.update_project_setting(project_id, "remote_render_message", "원격 렌더링 완료")
        db.update_project_setting(project_id, "admin_publish_ready", "1")
        db.update_project_setting(project_id, "admin_publish_ready_at", datetime.datetime.now(datetime.timezone.utc).isoformat())
        db.update_project_setting(project_id, "admin_publish_status", "pending_review")
        db.update_project(project_id, status="rendered")
        refreshed_settings = db.get_project_settings(project_id) or {}
        try:
            queue_project_for_admin_publish(
                project_id,
                requested_privacy=refreshed_settings.get("upload_privacy") or "private",
                requested_publish_at=refreshed_settings.get("upload_schedule_at"),
                requested_channel_id=refreshed_settings.get("youtube_channel_id"),
            )
        except Exception as publish_queue_error:
            db.update_project_setting(project_id, "admin_publish_status", "publish_queue_failed")
            db.update_project_setting(project_id, "admin_publish_error", str(publish_queue_error))
        return row

    def enqueue_packaged_project(self, project_id: int, package_path: str, metadata=None, token_path=None):
        project = db.get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        if not package_path or not os.path.exists(package_path):
            raise RuntimeError("Remote render package file does not exist.")

        root_folder_id = self._get_drive_folder_id()
        token_path = token_path or self._get_google_token_path()
        task_id = str(uuid.uuid4())

        # [AIR-0227E] Asset packages now land in the same category/project
        # subfolder the rendered result is later saved into
        # (remote_drive_worker.py::_resolve_result_folder uses the identical
        # category-or-email + project-name pair), instead of a single flat
        # root folder - keeps the asset zip and its eventual output together
        # for anyone browsing Drive directly. Job discovery/claiming is
        # entirely Supabase-row-driven (fetch_next_job queries
        # remote_render_queue, not Drive folders) and asset download is by
        # Drive file id, not folder path - so this is purely organizational,
        # no functional dependency on where the zip physically sits.
        settings = db.get_project_settings(project_id) or {}
        category_name = settings.get("preferred_youtube_channel_name") or settings.get("preferred_youtube_channel_handle")
        email = auth_service.get_user_email() or project.get("employee_email") or "unknown"
        project_name = project.get("name") or f"Project {project_id}"

        upload_folder_id = root_folder_id
        try:
            asset_folder = google_drive_service.ensure_project_folder(
                category_name or email,
                project_name,
                token_path=token_path,
                root_folder_id=root_folder_id,
            )
            if asset_folder and asset_folder.get("id"):
                upload_folder_id = asset_folder.get("id")
        except Exception as e:
            print(f"[RemoteDriveRenderService] Failed to resolve category folder, uploading to root instead: {e}")

        drive_file = google_drive_service.upload_file(
            package_path,
            token_path=token_path,
            folder_id=upload_folder_id,
            mimetype="application/zip",
            description=f"AIR remote render asset package for project {project_id}",
            make_public=False,
        )
        if not drive_file or not drive_file.get("id"):
            raise RuntimeError("Failed to upload remote render asset package to Google Drive.")

        # [NEW] Generate referral code upon first rendering if not exists
        try:
            auth_service.ensure_referral_code_generated()
        except Exception as e:
            print(f"Failed to generate referral code: {e}")

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        queue_metadata = dict(metadata or {})
        queue_metadata.setdefault("queue_scope", "remote_render")
        queue_metadata.setdefault("worker_platform", "korea_render_pc")
        queue_metadata.setdefault("upload_owner", "web_admin")
        queue_metadata.setdefault("publish_owner", "web_admin")
        queue_metadata.setdefault("visibility_control", "web_admin_pending")
        queue_metadata.setdefault("package_transport", "google_drive_api")
        queue_metadata.setdefault("job_stage", "pending")

        if category_name:
            queue_metadata["category_name"] = category_name

        queue_metadata.update(
            {
                "asset_file_id": drive_file.get("id"),
                "asset_file_name": drive_file.get("name"),
                "asset_file_size": drive_file.get("size"),
                "asset_md5": drive_file.get("md5Checksum"),
                "asset_web_link": drive_file.get("webViewLink"),
                "source": "picadiri_local_app",
            }
        )
        payload = {
            "id": task_id,
            "project_id": int(project_id),
            "project_name": project.get("name") or f"Project {project_id}",
            "email": auth_service.get_user_email() or project.get("employee_email") or "unknown",
            "status": "pending",
            "progress": 0,
            "message": "Google Drive에 에셋 패키지 업로드 완료. 원격 워커 대기 중.",
            "render_mode": "drive_api",
            "asset_file_id": drive_file.get("id"),
            "asset_file_name": drive_file.get("name"),
            "metadata": queue_metadata,
            "updated_at": now,
        }
        row = self._post_queue_row(payload)

        db.update_project(project_id, status="remote_queued")
        db.update_project_setting(project_id, "remote_task_id", task_id)
        db.update_project_setting(project_id, "remote_render_mode", "drive_api")
        db.update_project_setting(project_id, "remote_asset_file_id", drive_file.get("id"))
        db.update_project_setting(project_id, "remote_asset_file_name", drive_file.get("name"))
        db.update_project_setting(project_id, "remote_asset_web_link", drive_file.get("webViewLink"))
        db.update_project_setting(project_id, "admin_publish_ready", "0")
        db.update_project_setting(project_id, "admin_publish_status", "render_pending")
        db.update_project_setting(project_id, "final_asset_bundle_sent", "1")
        db.update_project_setting(project_id, "final_asset_bundle_sent_at", now)
        db.update_project_setting(project_id, "remote_render_queue_payload", json.dumps(payload, ensure_ascii=False))

        return {
            "task_id": task_id,
            "queue_row": row,
            "drive_file": drive_file,
            "metadata": queue_metadata,
        }

    def enqueue_project(self, project_id: int, use_subtitles: bool = True, resolution: str = "1080p", token_path=None):
        project = db.get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        zip_path = None

        try:
            zip_path = package_project_assets(project_id, use_subtitles=use_subtitles, resolution=resolution)
            if not zip_path or not os.path.exists(zip_path):
                raise RuntimeError("Failed to create remote render asset package.")
            metadata = {
                "use_subtitles": use_subtitles,
                "resolution": resolution,
            }
            return self.enqueue_packaged_project(project_id, zip_path, metadata=metadata, token_path=token_path)
        finally:
            if zip_path:
                try:
                    os.remove(zip_path)
                except Exception:
                    pass


remote_drive_render_service = RemoteDriveRenderService()
