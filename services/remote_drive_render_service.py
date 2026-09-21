import datetime
import json
import os
import re
import uuid
from urllib.parse import quote

import requests

import database as db
from config import config
from services.auth_service import auth_service
from services.project_publish_service import queue_project_for_admin_publish
from services.remote_render_service import package_project_assets
from services.web_admin_client import web_admin_client


class RemoteDriveRenderService:
    """GCS API + Supabase queue entrypoint for remote rendering."""

    def _load_gcs_settings(self):
        """Ensure GCS render settings saved in web-admin are available locally."""
        try:
            config.load_remote_keys_from_supabase()
        except Exception:
            pass

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

    def _get_gcs_credentials(self):
        self._load_gcs_settings()
        client_email = os.getenv("GCS_CLIENT_EMAIL") or getattr(config, "GCS_CLIENT_EMAIL", "")
        private_key = os.getenv("GCS_PRIVATE_KEY") or getattr(config, "GCS_PRIVATE_KEY", "")
        project_id = os.getenv("GCS_PROJECT_ID") or getattr(config, "GCS_PROJECT_ID", "")
        bucket_name = os.getenv("GCS_BUCKET_NAME") or getattr(config, "GCS_BUCKET_NAME", "")
        if not (client_email and private_key and bucket_name):
            raise RuntimeError("GCS credentials are not configured.")
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        creds = service_account.Credentials.from_service_account_info(
            {
                "type": "service_account",
                "project_id": project_id,
                "private_key": private_key.replace("\\n", "\n"),
                "client_email": client_email,
                "token_uri": "https://oauth2.googleapis.com/token",
            },
            scopes=["https://www.googleapis.com/auth/devstorage.read_write"],
        )
        creds.refresh(Request())
        return creds, bucket_name

    def _upload_file_to_gcs(self, file_path: str, object_path: str, mime_type: str):
        creds, bucket = self._get_gcs_credentials()
        clean_path = str(object_path or "").strip().replace("\\", "/").lstrip("/")
        if not clean_path:
            raise RuntimeError("GCS object path is empty.")
        url = f"https://storage.googleapis.com/upload/storage/v1/b/{quote(bucket, safe='')}/o?uploadType=media&name={quote(clean_path, safe='')}"
        with open(file_path, "rb") as file_obj:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {creds.token}", "Content-Type": mime_type},
                data=file_obj,
                timeout=300,
            )
        if response.status_code not in (200, 201):
            raise RuntimeError(f"GCS upload failed: {response.status_code} {response.text[:300]}")
        return {
            "bucket": bucket,
            "path": clean_path,
            "size": os.path.getsize(file_path),
            "media_url": f"https://storage.googleapis.com/{quote(bucket, safe='')}/{quote(clean_path, safe='/')}",
        }

    def _download_http_file(self, url: str, local_path: str):
        response = requests.get(url, stream=True, timeout=300)
        if response.status_code >= 400:
            raise RuntimeError(f"GCS result download failed: {response.status_code}")
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        partial_path = f"{local_path}.download"
        with open(partial_path, "wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output.write(chunk)
        os.replace(partial_path, local_path)
        return local_path

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
        filename = row.get("result_file_name") or f"remote_gcs_render_{project_id}.mp4"
        if not filename.lower().endswith(".mp4"):
            filename = f"{filename}.mp4"
        local_path = os.path.join(output_dir, filename)

        if not os.path.exists(local_path):
            result_url = row_metadata.get("result_public_url") or row_metadata.get("gcs_public_url") or row.get("result_file_id")
            if not result_url or not str(result_url).startswith("http"):
                raise RuntimeError("Completed remote render result does not include a GCS download URL.")
            self._download_http_file(str(result_url), local_path)

        web_video_path = f"{web_dir}/{filename}"
        db.update_project_setting(project_id, "video_path", web_video_path)
        db.update_project_setting(project_id, "remote_result_file_id", row.get("result_file_id"))
        db.update_project_setting(project_id, "remote_result_file_name", row.get("result_file_name"))
        db.update_project_setting(project_id, "gcs_video_path", row_metadata.get("gcs_path"))
        db.update_project_setting(project_id, "gcs_video_url", row_metadata.get("gcs_public_url") or row_metadata.get("result_public_url"))
        db.update_project_setting(project_id, "gcs_thumbnail_url", row_metadata.get("gcs_thumbnail_url"))
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

        task_id = str(uuid.uuid4())
        gcs_package_path = f"remote-render-packages/{project_id}/{task_id}/asset_package.zip"
        gcs_file = self._upload_file_to_gcs(package_path, gcs_package_path, "application/zip")

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
        queue_metadata.setdefault("package_transport", "gcs_package")
        queue_metadata.setdefault("job_stage", "pending")
        
        settings = db.get_project_settings(project_id) or {}
        category_name = settings.get("preferred_youtube_channel_name") or settings.get("preferred_youtube_channel_handle")
        if category_name:
            queue_metadata["category_name"] = category_name

        queue_metadata.update(
            {
                "asset_file_id": task_id,
                "asset_file_name": os.path.basename(package_path),
                "asset_file_size": gcs_file.get("size"),
                "asset_web_link": gcs_file.get("media_url"),
                "gcs_asset_package": {
                    "gcs_bucket": gcs_file.get("bucket"),
                    "gcs_path": gcs_file.get("path"),
                },
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
            "message": "GCS에 에셋 패키지 업로드 완료. 원격 워커 대기 중.",
            "render_mode": "gcs_api",
            "asset_file_id": task_id,
            "asset_file_name": os.path.basename(package_path),
            "metadata": queue_metadata,
            "updated_at": now,
        }
        row = self._post_queue_row(payload)

        db.update_project(project_id, status="remote_queued")
        db.update_project_setting(project_id, "remote_task_id", task_id)
        db.update_project_setting(project_id, "remote_render_mode", "gcs_api")
        db.update_project_setting(project_id, "remote_asset_file_id", task_id)
        db.update_project_setting(project_id, "remote_asset_file_name", os.path.basename(package_path))
        db.update_project_setting(project_id, "remote_asset_web_link", gcs_file.get("media_url"))
        db.update_project_setting(project_id, "admin_publish_ready", "0")
        db.update_project_setting(project_id, "admin_publish_status", "render_pending")
        db.update_project_setting(project_id, "final_asset_bundle_sent", "1")
        db.update_project_setting(project_id, "final_asset_bundle_sent_at", now)
        db.update_project_setting(project_id, "remote_render_queue_payload", json.dumps(payload, ensure_ascii=False))

        return {
            "task_id": task_id,
            "queue_row": row,
            "gcs_file": gcs_file,
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
