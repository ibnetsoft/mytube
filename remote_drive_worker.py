import datetime
import json
import os
import shutil
import tempfile
import time
import threading
import zipfile
import argparse
import sys
import re
import traceback
from urllib.parse import quote

import requests

from config import config
from services.google_drive_service import google_drive_service
from services.remote_render_service import remote_render_executor_func

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _configure_ffmpeg_for_worker():
    try:
        import glob
        import shutil as _shutil
        import imageio_ffmpeg

        ffmpeg_candidates = []
        if os.getenv("IMAGEIO_FFMPEG_EXE"):
            ffmpeg_candidates.append(os.getenv("IMAGEIO_FFMPEG_EXE"))
        ffmpeg_candidates.extend(
            glob.glob(
                os.path.join(
                    os.getcwd(),
                    "venv",
                    "Lib",
                    "site-packages",
                    "imageio_ffmpeg",
                    "binaries",
                    "ffmpeg*.exe",
                )
            )
        )
        if _shutil.which("ffmpeg"):
            ffmpeg_candidates.append(_shutil.which("ffmpeg"))

        ffmpeg_path = next((p for p in ffmpeg_candidates if p and os.path.exists(p)), None)
        if not ffmpeg_path:
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

        if ffmpeg_path and os.path.exists(ffmpeg_path):
            os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg_path
            ffmpeg_dir = os.path.dirname(ffmpeg_path)
            current_path = os.environ.get("PATH", "")
            if ffmpeg_dir and ffmpeg_dir not in current_path.split(os.pathsep):
                os.environ["PATH"] = current_path + os.pathsep + ffmpeg_dir if current_path else ffmpeg_dir
            print(f"[RemoteDriveWorker] FFmpeg configured: {ffmpeg_path}")
    except Exception as e:
        print(f"[RemoteDriveWorker] FFmpeg setup warning: {e}")


class RemoteDriveWorker:
    def __init__(self):
        _configure_ffmpeg_for_worker()
        try:
            config.load_remote_keys_from_supabase()
        except Exception as e:
            print(f"[RemoteDriveWorker] Failed to load web admin settings: {e}")
        self.worker_id = os.getenv("REMOTE_RENDER_WORKER_ID") or f"worker-{os.getpid()}"
        self.poll_interval = int(os.getenv("REMOTE_RENDER_POLL_INTERVAL", "10"))
        # This render PC has a verified NVENC path. Operators can still set
        # USE_GPU_RENDER=false when diagnosing a graphics-driver issue.
        self.use_gpu = os.getenv("USE_GPU_RENDER", "true").lower() == "true"
        self.output_folder_id = os.getenv("REMOTE_RENDER_DRIVE_FOLDER_ID") or getattr(config, "REMOTE_RENDER_DRIVE_FOLDER_ID", "")
        self.google_token_path = os.getenv("REMOTE_RENDER_GOOGLE_TOKEN_PATH") or getattr(config, "REMOTE_RENDER_GOOGLE_TOKEN_PATH", "")
        self.supabase_url = (os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
        self.supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
        self.max_concurrent_jobs = int(os.getenv("REMOTE_RENDER_MAX_CONCURRENT_JOBS", "1"))
        if not self.supabase_url or not self.supabase_key:
            raise RuntimeError("NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.")

    @property
    def queue_url(self):
        return f"{self.supabase_url}/rest/v1/remote_render_queue"

    @property
    def headers(self):
        return {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _request(self, method, url, **kwargs):
        import urllib3
        ssl_verify = os.getenv("SUPABASE_SSL_NO_VERIFY", "false").lower() == "true"
        if ssl_verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            kwargs.setdefault("verify", False)
        else:
            kwargs.setdefault("verify", True)
        kwargs.setdefault("timeout", 30)
        kwargs.setdefault("proxies", {"http": None, "https": None})
        response = requests.request(method, url, headers=self.headers, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f"Supabase request failed: {response.status_code} {response.text}")
        if response.text:
            return response.json()
        return None

    def _active_rendering_count(self):
        active_after = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)
        ).isoformat()
        params = {
            "select": "id",
            "render_mode": "eq.drive_api",
            "status": "eq.rendering",
            "updated_at": f"gt.{active_after}",
        }
        rows = self._request("GET", self.queue_url, params=params) or []
        return len(rows)

    def fetch_next_job(self):
        if self.max_concurrent_jobs > 0 and self._active_rendering_count() >= self.max_concurrent_jobs:
            return None
        params = {
            "select": "*",
            "render_mode": "eq.drive_api",
            "status": "eq.pending",
            "order": "created_at.asc",
            "limit": "1",
        }
        rows = self._request("GET", self.queue_url, params=params) or []
        return rows[0] if rows else None

    def get_job(self, job_id):
        rows = self._request(
            "GET",
            self.queue_url,
            params={
                "select": "id,status,progress,message,error_message",
                "id": f"eq.{job_id}",
                "limit": "1",
            },
        ) or []
        return rows[0] if rows else None

    def check(self):
        print("[RemoteDriveWorker] Configuration check")
        print(f"  worker_id: {self.worker_id}")
        print(f"  supabase_url: {self.supabase_url or '(missing)'}")
        print(f"  drive_folder_id: {self.output_folder_id or '(root or unset)'}")
        print(f"  google_token_path: {self.google_token_path or '(default YouTube token)'}")
        if self.google_token_path and not os.path.exists(self.google_token_path):
            print("  warning: google_token_path does not exist on this PC.")
        job = self.fetch_next_job()
        if job:
            print(f"  next_job: {job.get('id')} project={job.get('project_id')} asset={job.get('asset_file_name') or job.get('asset_file_id')}")
        else:
            print("  next_job: none")
        return job

    def claim_job(self, job):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        url = f"{self.queue_url}?id=eq.{job['id']}&status=eq.pending"
        rows = self._request("PATCH", url, json={
            "status": "rendering",
            "progress": 1,
            "message": f"{self.worker_id}에서 작업을 가져감",
            "worker_id": self.worker_id,
            "claimed_at": now,
            "updated_at": now,
        }) or []
        return rows[0] if rows else None

    def update_job(self, job_id, **fields):
        fields["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        url = f"{self.queue_url}?id=eq.{job_id}"
        rows = self._request("PATCH", url, json=fields) or []
        return rows[0] if rows else None

    def _build_result_filename(self, job):
        project_name = (job.get("project_name") or "").strip()
        if not project_name:
            project_name = f"project_{job.get('project_id') or job.get('id')}"
        safe_name = re.sub(r'[\\\\/:*?\"<>|]+', " ", project_name)
        safe_name = re.sub(r"\s+", " ", safe_name).strip().rstrip(".")
        if not safe_name:
            safe_name = f"project_{job.get('project_id') or job.get('id')}"
        return f"{safe_name}.mp4"

    def _resolve_result_folder(self, job):
        metadata = job.get("metadata") or {}
        manifest_folder_id = (metadata.get("drive_folder_id") or metadata.get("result_folder_id") or "").strip()
        if manifest_folder_id:
            folder_meta = google_drive_service.get_file_metadata(
                manifest_folder_id,
                token_path=self.google_token_path or None,
                fields="id, name, mimeType, parents, webViewLink",
            )
            if folder_meta and folder_meta.get("id"):
                return {"id": folder_meta.get("id"), "name": folder_meta.get("name") or "std-project"}

        email = (job.get("email") or "").strip()
        if not email:
            email = "unknown-user"

        category_name = metadata.get("category_name")
        folder_category = category_name if category_name else email
        
        project_name = (job.get("project_name") or "").strip() or f"project_{job.get('project_id') or job.get('id')}"
        folder = google_drive_service.ensure_project_folder(
            folder_category,
            project_name,
            token_path=self.google_token_path or None,
            root_folder_id=self.output_folder_id or None,
        )
        if not folder or not folder.get("id"):
            raise RuntimeError(f"Drive 프로젝트 폴더 준비 실패 (카테고리/프로젝트: {folder_category} / {project_name})")
        return folder

    def _refresh_drive_settings(self):
        config.load_remote_keys_from_supabase()
        self.output_folder_id = os.getenv("REMOTE_RENDER_DRIVE_FOLDER_ID") or getattr(config, "REMOTE_RENDER_DRIVE_FOLDER_ID", "")

    def _safe_manifest_path(self, relative_path):
        normalized = str(relative_path or "").replace("\\", "/").strip("/")
        parts = [part for part in normalized.split("/") if part]
        if not parts or any(part in {".", ".."} for part in parts):
            raise RuntimeError(f"잘못된 렌더 파일 경로입니다: {relative_path}")
        return os.path.join(*parts)

    def _download_from_supabase_storage(self, source, destination_path):
        """Fetch a private Storage object with an atomic local write (1st Priority Storage)."""
        if not isinstance(source, dict):
            return False
        bucket = str(source.get("bucket") or "").strip()
        object_path = str(source.get("path") or "").strip().replace("\\", "/").lstrip("/")
        if not bucket or not object_path or ".." in object_path.split("/"):
            return False

        url = f"{self.supabase_url}/storage/v1/object/{quote(bucket, safe='')}/{quote(object_path, safe='/')}"
        partial_path = f"{destination_path}.download"
        try:
            response = requests.get(
                url,
                headers={"apikey": self.supabase_key, "Authorization": f"Bearer {self.supabase_key}"},
                stream=True,
                timeout=120,
                proxies={"http": None, "https": None},
            )
            if response.status_code != 200:
                return False
            os.makedirs(os.path.dirname(destination_path), exist_ok=True)
            with open(partial_path, "wb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        output.write(chunk)
            if not os.path.exists(partial_path) or os.path.getsize(partial_path) <= 0:
                return False
            os.replace(partial_path, destination_path)
            return True
        except requests.RequestException:
            return False
        finally:
            try:
                if os.path.exists(partial_path):
                    os.remove(partial_path)
            except OSError:
                pass

    def _get_gcs_credentials(self):
        """Build Google Cloud Service Account credentials for GCS operations."""
        client_email = os.getenv("GCS_CLIENT_EMAIL") or getattr(config, "GCS_CLIENT_EMAIL", "")
        private_key = os.getenv("GCS_PRIVATE_KEY") or getattr(config, "GCS_PRIVATE_KEY", "")
        project_id = os.getenv("GCS_PROJECT_ID") or getattr(config, "GCS_PROJECT_ID", "")
        bucket_name = os.getenv("GCS_BUCKET_NAME") or getattr(config, "GCS_BUCKET_NAME", "")
        if not (client_email and private_key and bucket_name):
            return None
        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request
            formatted_key = private_key.replace("\\n", "\n")
            info = {
                "type": "service_account",
                "project_id": project_id,
                "private_key": formatted_key,
                "client_email": client_email,
                "token_uri": "https://oauth2.googleapis.com/token",
            }
            creds = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/devstorage.read_write"],
            )
            creds.refresh(Request())
            return creds, bucket_name
        except Exception as e:
            print(f"[RemoteDriveWorker] GCS credentials setup failed: {e}")
            return None

    def _download_from_gcs_storage(self, source, destination_path):
        """Fetch a GCS object with atomic local write (2nd Priority Storage)."""
        if not isinstance(source, dict):
            return False
        # 1. Try V4 Signed URL if provided
        signed_url = source.get("gcs_signed_url")
        if signed_url:
            partial_path = f"{destination_path}.gcsdownload"
            try:
                res = requests.get(
                    signed_url,
                    stream=True,
                    timeout=120,
                    proxies={"http": None, "https": None},
                )
                if res.status_code == 200:
                    os.makedirs(os.path.dirname(destination_path), exist_ok=True)
                    with open(partial_path, "wb") as output:
                        for chunk in res.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                output.write(chunk)
                    if os.path.exists(partial_path) and os.path.getsize(partial_path) > 0:
                        os.replace(partial_path, destination_path)
                        return True
            except requests.RequestException:
                pass
            finally:
                if os.path.exists(partial_path):
                    try:
                        os.remove(partial_path)
                    except OSError:
                        pass

        # 2. Try direct GCS REST API with Service Account
        bucket = str(source.get("gcs_bucket") or source.get("bucket") or "").strip()
        object_path = str(source.get("gcs_path") or source.get("path") or "").strip().replace("\\", "/").lstrip("/")
        if bucket and object_path and ".." not in object_path.split("/"):
            creds_info = self._get_gcs_credentials()
            if creds_info:
                creds, default_bucket = creds_info
                target_bucket = bucket or default_bucket
                url = f"https://storage.googleapis.com/storage/v1/b/{quote(target_bucket, safe='')}/o/{quote(object_path, safe='')}?alt=media"
                headers = {"Authorization": f"Bearer {creds.token}"}
                partial_path = f"{destination_path}.gcsdownload"
                try:
                    res = requests.get(
                        url,
                        headers=headers,
                        stream=True,
                        timeout=120,
                        proxies={"http": None, "https": None},
                    )
                    if res.status_code == 200:
                        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
                        with open(partial_path, "wb") as output:
                            for chunk in res.iter_content(chunk_size=1024 * 1024):
                                if chunk:
                                    output.write(chunk)
                        if os.path.exists(partial_path) and os.path.getsize(partial_path) > 0:
                            os.replace(partial_path, destination_path)
                            return True
                except requests.RequestException:
                    pass
                finally:
                    if os.path.exists(partial_path):
                        try:
                            os.remove(partial_path)
                        except OSError:
                            pass
        return False

    def _upload_to_supabase_storage(self, file_path, bucket, object_path, mime_type="video/mp4"):
        """Upload a file to Supabase Storage bucket (1st Priority)."""
        if not file_path or not os.path.exists(file_path):
            return None
        clean_bucket = str(bucket or "").strip()
        clean_path = str(object_path or "").strip().replace("\\", "/").lstrip("/")
        if not clean_bucket or not clean_path:
            return None
        url = f"{self.supabase_url}/storage/v1/object/{quote(clean_bucket, safe='')}/{quote(clean_path, safe='/')}"
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": mime_type,
            "x-upsert": "true",
        }
        try:
            with open(file_path, "rb") as f:
                res = requests.post(
                    url,
                    headers=headers,
                    data=f,
                    timeout=300,
                    proxies={"http": None, "https": None},
                )
            if res.status_code in (200, 201):
                public_url = f"{self.supabase_url}/storage/v1/object/public/{quote(clean_bucket, safe='')}/{quote(clean_path, safe='/')}"
                return {
                    "bucket": clean_bucket,
                    "path": clean_path,
                    "public_url": public_url,
                }
            else:
                print(f"[RemoteDriveWorker] Supabase upload failed with status {res.status_code}: {res.text[:200]}")
        except Exception as e:
            print(f"[RemoteDriveWorker] Supabase upload error: {e}")
        return None

    def _upload_to_gcs_storage(self, file_path, object_path, mime_type="video/mp4"):
        """Upload a file to Google Cloud Storage (2nd Priority)."""
        if not file_path or not os.path.exists(file_path):
            return None
        creds_info = self._get_gcs_credentials()
        if not creds_info:
            return None
        creds, bucket = creds_info
        clean_path = str(object_path or "").strip().replace("\\", "/").lstrip("/")
        url = f"https://storage.googleapis.com/upload/storage/v1/b/{quote(bucket, safe='')}/o?uploadType=media&name={quote(clean_path, safe='')}"
        headers = {
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": mime_type,
        }
        try:
            with open(file_path, "rb") as f:
                res = requests.post(
                    url,
                    headers=headers,
                    data=f,
                    timeout=300,
                    proxies={"http": None, "https": None},
                )
            if res.status_code in (200, 201):
                public_url = f"https://storage.googleapis.com/{quote(bucket, safe='')}/{quote(clean_path, safe='/')}"
                return {
                    "bucket": bucket,
                    "path": clean_path,
                    "public_url": public_url,
                }
            else:
                print(f"[RemoteDriveWorker] GCS upload failed with status {res.status_code}: {res.text[:200]}")
        except Exception as e:
            print(f"[RemoteDriveWorker] GCS upload error: {e}")
        return None

    def _download_asset_with_fallback(self, job_id, drive_file_id, destination_path, *, storage_source=None, label):
        """Read Storage first (1st Supabase, 2nd GCS); Drive is only for legacy or missing Storage files."""
        # 1st Priority: Supabase Storage
        if storage_source and self._download_from_supabase_storage(storage_source, destination_path):
            return "supabase_storage"

        # 2nd Priority: Google Cloud Storage
        if storage_source and self._download_from_gcs_storage(storage_source, destination_path):
            return "gcs_storage"

        # 3rd Priority: Google Drive (legacy fallback)
        if drive_file_id:
            attempts = max(1, int(os.getenv("REMOTE_RENDER_DRIVE_DOWNLOAD_ATTEMPTS", "3")))
            for attempt in range(1, attempts + 1):
                try:
                    os.makedirs(os.path.dirname(destination_path), exist_ok=True)
                    downloaded = google_drive_service.download_file(
                        drive_file_id,
                        destination_path,
                        token_path=self.google_token_path or None,
                    )
                    if downloaded and os.path.exists(destination_path):
                        return "google_drive"
                except Exception:
                    pass
                if attempt < attempts:
                    self.update_job(job_id, message=f"Google Drive 다운로드 재시도 중 ({attempt}/{attempts}): {label}")
                    time.sleep(attempt)

        # Retry Supabase or GCS once more before declaring complete failure
        if storage_source:
            if self._download_from_supabase_storage(storage_source, destination_path):
                return "supabase_storage"
            if self._download_from_gcs_storage(storage_source, destination_path):
                return "gcs_storage"

        raise RuntimeError(f"에셋 다운로드 실패 (1차 Supabase, 2차 GCS, 3차 Drive 모두 실패): {label}")

    def _prepare_drive_folder_manifest_job(self, job_id, job, temp_dir, config_file_id):
        config_path = os.path.join(temp_dir, "config.json")
        self.update_job(job_id, progress=5, message="렌더 설정 파일 다운로드 중 (1차 Supabase / 2차 GCS)...")
        metadata = job.get("metadata") or {}
        supabase_cfg = metadata.get("supabase_config") or {}
        gcs_cfg = metadata.get("gcs_config") or {}
        config_storage_source = {
            "bucket": supabase_cfg.get("bucket"),
            "path": supabase_cfg.get("path"),
            "gcs_bucket": supabase_cfg.get("gcs_bucket") or gcs_cfg.get("bucket"),
            "gcs_path": supabase_cfg.get("gcs_path") or gcs_cfg.get("path"),
            "gcs_signed_url": supabase_cfg.get("gcs_signed_url") or gcs_cfg.get("signed_url"),
        }
        if not config_storage_source["bucket"] and not config_storage_source["gcs_bucket"] and not config_storage_source["gcs_signed_url"]:
            config_storage_source = None

        self._download_asset_with_fallback(
            job_id,
            config_file_id,
            config_path,
            storage_source=config_storage_source,
            label="config.json",
        )

        with open(config_path, "r", encoding="utf-8") as f_conf:
            packaged_config = json.load(f_conf)

        manifest = packaged_config.get("asset_manifest") or {}
        files = manifest.get("files") or []
        if not files:
            raise RuntimeError("렌더 설정 파일에 다운로드할 에셋 목록이 없습니다.")

        total = len(files)
        for index, item in enumerate(files, start=1):
            drive_file_id = item.get("drive_file_id")
            relative_path = item.get("path")
            has_storage = (
                (item.get("supabase_bucket") and item.get("supabase_path"))
                or (item.get("storage_bucket") and item.get("storage_path"))
                or item.get("gcs_signed_url")
                or (item.get("gcs_bucket") and item.get("gcs_path"))
            )
            if (not drive_file_id and not has_storage) or not relative_path:
                raise RuntimeError("렌더 에셋 목록에 저장소 위치 또는 경로가 없습니다.")
            local_rel_path = self._safe_manifest_path(relative_path)
            local_path = os.path.join(temp_dir, local_rel_path)
            progress = 6 + int((index / max(total, 1)) * 12)
            self.update_job(
                job_id,
                progress=progress,
                message=f"렌더 에셋 다운로드 중... ({index}/{total})",
            )
            storage_source = {
                "bucket": item.get("supabase_bucket") or item.get("storage_bucket"),
                "path": item.get("supabase_path") or item.get("storage_path"),
                "gcs_bucket": item.get("gcs_bucket"),
                "gcs_path": item.get("gcs_path"),
                "gcs_signed_url": item.get("gcs_signed_url"),
            }
            if not storage_source["bucket"] and not storage_source["gcs_bucket"] and not storage_source["gcs_signed_url"]:
                storage_source = None
            self._download_asset_with_fallback(
                job_id,
                drive_file_id,
                local_path,
                storage_source=storage_source,
                label=relative_path,
            )

    def process_job(self, job):
        self._refresh_drive_settings()
        job_id = job["id"]
        asset_file_id = job.get("asset_file_id")
        if not asset_file_id:
            raise RuntimeError("큐 작업에 asset_file_id가 없습니다.")

        temp_dir = tempfile.mkdtemp(prefix=f"remote_drive_render_{job_id}_")
        zip_path = os.path.join(temp_dir, "asset_package.zip")
        try:
            metadata = job.get("metadata") or {}
            if (
                metadata.get("package_transport") in ("google_drive_folder", "storage_direct", "gcs_folder")
                or metadata.get("config_file_id")
                or metadata.get("supabase_config")
                or metadata.get("gcs_config")
            ):
                config_file_id = metadata.get("config_file_id") or asset_file_id
                self._prepare_drive_folder_manifest_job(job_id, job, temp_dir, config_file_id)
            else:
                self.update_job(job_id, progress=5, message="Google Drive에서 에셋 패키지 다운로드 중...")
                self._download_asset_with_fallback(
                    job_id,
                    asset_file_id,
                    zip_path,
                    storage_source=metadata.get("supabase_asset_package"),
                    label=job.get("asset_file_name") or "asset_package.zip",
                )

                self.update_job(job_id, progress=12, message="에셋 패키지 압축 해제 중...")
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(temp_dir)

            self.update_job(job_id, progress=20, message="원격 워커에서 영상 렌더링 중...")
            progress_file = os.path.join(temp_dir, "progress.txt")
            progress_stop = threading.Event()

            def sync_render_progress():
                last_reported = None
                while not progress_stop.wait(2):
                    try:
                        with open(progress_file, "r", encoding="utf-8") as f_progress:
                            progress_payload = json.load(f_progress)
                        progress = int(progress_payload.get("progress") or 20)
                        progress = max(20, min(91, progress))
                        message = str(progress_payload.get("message") or "원격 워커에서 영상 렌더링 중...")
                        current = (progress, message)
                        if current != last_reported:
                            self.update_job(job_id, progress=progress, message=message)
                            last_reported = current
                    except (OSError, ValueError, json.JSONDecodeError):
                        continue
                    except Exception:
                        # A transient queue update failure must not stop rendering.
                        continue

            progress_thread = threading.Thread(target=sync_render_progress, name=f"remote-render-progress-{job_id}", daemon=True)
            progress_thread.start()
            try:
                remote_render_executor_func(job_id, temp_dir, use_gpu=self.use_gpu)
            finally:
                progress_stop.set()
                progress_thread.join(timeout=3)

            output_path = os.path.join(temp_dir, "output.mp4")
            if not os.path.exists(output_path):
                raise RuntimeError("렌더링은 완료됐지만 output.mp4 파일을 찾을 수 없습니다.")

            self.update_job(job_id, progress=92, message="렌더링된 영상을 저장소(1차 Supabase / 2차 GCS)에 업로드 중...")
            result_filename = self._build_result_filename(job)

            # 1st Priority: Supabase Storage
            supabase_render_bucket = os.getenv("SUPABASE_RENDER_BUCKET") or "content-assets"
            supabase_render_path = f"std-renders/{job_id}/{result_filename}"
            supabase_video = self._upload_to_supabase_storage(
                output_path,
                bucket=supabase_render_bucket,
                object_path=supabase_render_path,
                mime_type="video/mp4",
            )
            if supabase_video:
                print(f"[RemoteDriveWorker] 1차 Supabase 저장소 영상 업로드 성공: {supabase_render_path}")

            # 2nd Priority: Google Cloud Storage
            gcs_render_path = f"std-renders/{job_id}/{result_filename}"
            gcs_video = self._upload_to_gcs_storage(
                output_path,
                object_path=gcs_render_path,
                mime_type="video/mp4",
            )
            if gcs_video:
                print(f"[RemoteDriveWorker] 2차 GCS 저장소 영상 업로드 성공: {gcs_render_path}")

            # 3rd Priority: Google Drive (Fallback / Legacy)
            drive_file = None
            result_folder = None
            try:
                result_folder = self._resolve_result_folder(job)
                drive_file = google_drive_service.upsert_file(
                    output_path,
                    token_path=self.google_token_path or None,
                    folder_id=result_folder.get("id"),
                    filename=result_filename,
                    mimetype="video/mp4",
                    description=f"AIR remote render result for queue job {job_id}",
                    make_public=False,
                )
                if drive_file and drive_file.get("id"):
                    print(f"[RemoteDriveWorker] 3차 Google Drive 영상 업로드 성공: {drive_file.get('id')}")
            except Exception as drive_err:
                print(f"[RemoteDriveWorker] Google Drive 업로드 건너뜀/실패 (1차 Supabase/2차 GCS로 지속): {drive_err}")

            if not supabase_video and not gcs_video and not drive_file:
                raise RuntimeError("렌더링된 영상을 저장소(1차 Supabase, 2차 GCS, 3차 Drive) 어디에도 업로드하지 못했습니다.")

            thumbnail_file = None
            thumbnail_filename = None
            packaged_thumbnail = None
            supabase_thumb = None
            gcs_thumb = None
            project_metadata_file = None
            config_path = os.path.join(temp_dir, "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f_conf:
                    packaged_config = json.load(f_conf)
                thumbnail_filename = packaged_config.get("thumbnail_filename")
                if thumbnail_filename:
                    packaged_thumbnail = os.path.join(temp_dir, thumbnail_filename)
                if packaged_thumbnail and os.path.exists(packaged_thumbnail):
                    thumb_mime = "image/png" if thumbnail_filename.lower().endswith(".png") else "image/jpeg"
                    supabase_thumb = self._upload_to_supabase_storage(
                        packaged_thumbnail,
                        bucket=supabase_render_bucket,
                        object_path=f"std-renders/{job_id}/{thumbnail_filename}",
                        mime_type=thumb_mime,
                    )
                    gcs_thumb = self._upload_to_gcs_storage(
                        packaged_thumbnail,
                        object_path=f"std-renders/{job_id}/{thumbnail_filename}",
                        mime_type=thumb_mime,
                    )
                    if result_folder and result_folder.get("id"):
                        try:
                            thumbnail_file = google_drive_service.upsert_file(
                                packaged_thumbnail,
                                token_path=self.google_token_path or None,
                                folder_id=result_folder.get("id"),
                                filename=thumbnail_filename,
                                mimetype=thumb_mime,
                                description=f"AIR thumbnail for queue job {job_id}",
                                make_public=False,
                            )
                        except Exception as thumb_err:
                            print(f"[RemoteDriveWorker] Google Drive 썸네일 업로드 건너뜀/실패: {thumb_err}")

                queue_metadata = job.get("metadata") or {}
                upload_metadata = dict(packaged_config.get("project_upload_metadata") or {})
                upload_metadata.update({
                    "employee_email": job.get("email") or upload_metadata.get("employee_email") or "",
                    "video_file": (drive_file or {}).get("name") or result_filename,
                    "thumbnail_file": thumbnail_filename,
                    "drive_folder_id": (result_folder or {}).get("id"),
                    "drive_video_file_id": (drive_file or {}).get("id"),
                    "drive_thumbnail_file_id": (thumbnail_file or {}).get("id") if thumbnail_file else None,
                    "supabase_video_path": (supabase_video or {}).get("path"),
                    "supabase_thumbnail_path": (supabase_thumb or {}).get("path"),
                    "gcs_video_path": (gcs_video or {}).get("path"),
                    "gcs_thumbnail_path": (gcs_thumb or {}).get("path"),
                    "render_mode": "drive_api",
                })
                for key in ("track_count", "track_durations", "total_duration_seconds", "app_mode", "render_style", "queue_type"):
                    if queue_metadata.get(key) is not None:
                        upload_metadata[key] = queue_metadata.get(key)
                metadata_path = os.path.join(temp_dir, "metadata.json")
                with open(metadata_path, "w", encoding="utf-8") as f_meta:
                    json.dump(upload_metadata, f_meta, ensure_ascii=False, indent=2)

                self._upload_to_supabase_storage(
                    metadata_path,
                    bucket=supabase_render_bucket,
                    object_path=f"std-renders/{job_id}/metadata.json",
                    mime_type="application/json",
                )
                self._upload_to_gcs_storage(
                    metadata_path,
                    object_path=f"std-renders/{job_id}/metadata.json",
                    mime_type="application/json",
                )
                if result_folder and result_folder.get("id"):
                    try:
                        project_metadata_file = google_drive_service.upsert_file(
                            metadata_path,
                            token_path=self.google_token_path or None,
                            folder_id=result_folder.get("id"),
                            filename="metadata.json",
                            mimetype="application/json",
                            description=f"AIR metadata for queue job {job_id}",
                            make_public=False,
                        )
                    except Exception as meta_err:
                        print(f"[RemoteDriveWorker] Google Drive 메타데이터 업로드 건너뜀/실패: {meta_err}")

            result_public_url = (supabase_video or {}).get("public_url") or (gcs_video or {}).get("public_url")
            result_file_id = (drive_file or {}).get("id") or result_public_url or supabase_render_path
            storage_provider = "supabase" if supabase_video else ("gcs" if gcs_video else "google_drive")
            storage_summary = []
            if supabase_video:
                storage_summary.append("Supabase (1차)")
            if gcs_video:
                storage_summary.append("GCS (2차)")
            if drive_file:
                storage_summary.append("Drive (3차)")

            self.update_job(
                job_id,
                status="completed",
                progress=100,
                message=f"렌더링 완료 ({' + '.join(storage_summary)} 저장 완료)",
                result_file_id=result_file_id,
                result_file_name=result_filename,
                metadata={
                    **(job.get("metadata") or {}),
                    "job_stage": "completed",
                    "admin_publish_ready": True,
                    "admin_publish_status": "pending_review",
                    "admin_action_required": "review_and_upload",
                    "storage_provider": storage_provider,
                    "storage_bucket": (supabase_video or {}).get("bucket"),
                    "storage_path": (supabase_video or {}).get("path"),
                    "result_public_url": result_public_url,
                    "gcs_bucket": (gcs_video or {}).get("bucket"),
                    "gcs_path": (gcs_video or {}).get("path"),
                    "gcs_public_url": (gcs_video or {}).get("public_url"),
                    "result_folder_id": (result_folder or {}).get("id"),
                    "result_folder_name": (result_folder or {}).get("name"),
                    "result_video_file_id": (drive_file or {}).get("id"),
                    "result_thumbnail_file_id": (thumbnail_file or {}).get("id") if thumbnail_file else None,
                    "result_metadata_file_id": (project_metadata_file or {}).get("id") if project_metadata_file else None,
                },
                completed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )
        except Exception as e:
            error_detail = "\n".join(
                [
                    f"Exception: {type(e).__name__}: {e}",
                    "Traceback:",
                    traceback.format_exc(),
                ]
            ).strip()
            self.update_job(
                job_id,
                status="failed",
                progress=-1,
                message=f"렌더링 실패: {e}",
                error_message=error_detail,
            )
            raise
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def run_forever(self):
        print(f"[RemoteDriveWorker] Started as {self.worker_id}")
        while True:
            try:
                job = self.fetch_next_job()
                if not job:
                    time.sleep(self.poll_interval)
                    continue
                claimed = self.claim_job(job)
                if not claimed:
                    continue
                print(f"[RemoteDriveWorker] Processing job {claimed['id']}")
                self.process_job(claimed)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"[RemoteDriveWorker] Error: {e}")
                time.sleep(self.poll_interval)

    def run_once(self):
        print(f"[RemoteDriveWorker] Running one polling cycle as {self.worker_id}")
        job = self.fetch_next_job()
        if not job:
            print("[RemoteDriveWorker] No pending drive_api job.")
            return 0
        claimed = self.claim_job(job)
        if not claimed:
            print("[RemoteDriveWorker] Job was already claimed by another worker.")
            return 0
        print(f"[RemoteDriveWorker] Processing job {claimed['id']}")
        self.process_job(claimed)
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIR Google Drive API remote render worker")
    parser.add_argument("--once", action="store_true", help="process at most one pending job and exit")
    parser.add_argument("--check", action="store_true", help="check settings and pending queue, then exit")
    args = parser.parse_args()

    worker = RemoteDriveWorker()
    if args.check:
        worker.check()
    elif args.once:
        worker.run_once()
    else:
        worker.run_forever()
