import datetime
import json
import os
import shutil
import tempfile
import time
import zipfile
import argparse
import sys
import re

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
        self.use_gpu = os.getenv("USE_GPU_RENDER", "false").lower() == "true"
        self.output_folder_id = os.getenv("REMOTE_RENDER_DRIVE_FOLDER_ID") or getattr(config, "REMOTE_RENDER_DRIVE_FOLDER_ID", "")
        self.google_token_path = os.getenv("REMOTE_RENDER_GOOGLE_TOKEN_PATH") or getattr(config, "REMOTE_RENDER_GOOGLE_TOKEN_PATH", "")
        self.supabase_url = (os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
        self.supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
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
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        kwargs.setdefault("timeout", 30)
        kwargs.setdefault("verify", False)
        kwargs.setdefault("proxies", {"http": None, "https": None})
        response = requests.request(method, url, headers=self.headers, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f"Supabase request failed: {response.status_code} {response.text}")
        if response.text:
            return response.json()
        return None

    def fetch_next_job(self):
        params = {
            "select": "*",
            "render_mode": "eq.drive_api",
            "status": "eq.pending",
            "order": "created_at.asc",
            "limit": "1",
        }
        rows = self._request("GET", self.queue_url, params=params) or []
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
            "message": f"Claimed by {self.worker_id}",
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
        email = (job.get("email") or "").strip()
        if not email:
            email = "unknown-user"
        project_name = (job.get("project_name") or "").strip() or f"project_{job.get('project_id') or job.get('id')}"
        folder = google_drive_service.ensure_project_folder(
            email,
            project_name,
            token_path=self.google_token_path or None,
            root_folder_id=self.output_folder_id or None,
        )
        if not folder or not folder.get("id"):
            raise RuntimeError(f"Failed to prepare Drive project folder for email/project: {email} / {project_name}")
        return folder

    def process_job(self, job):
        job_id = job["id"]
        asset_file_id = job.get("asset_file_id")
        if not asset_file_id:
            raise RuntimeError("Queue job is missing asset_file_id.")

        temp_dir = tempfile.mkdtemp(prefix=f"remote_drive_render_{job_id}_")
        zip_path = os.path.join(temp_dir, "asset_package.zip")
        try:
            self.update_job(job_id, progress=5, message="Downloading asset package from Google Drive.")
            downloaded = google_drive_service.download_file(asset_file_id, zip_path, token_path=self.google_token_path or None)
            if not downloaded:
                raise RuntimeError("Failed to download asset package from Google Drive.")

            self.update_job(job_id, progress=12, message="Extracting asset package.")
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)

            self.update_job(job_id, progress=20, message="Rendering video on remote worker.")
            remote_render_executor_func(job_id, temp_dir, use_gpu=self.use_gpu)

            output_path = os.path.join(temp_dir, "output.mp4")
            if not os.path.exists(output_path):
                raise RuntimeError("Render completed but output.mp4 was not found.")

            self.update_job(job_id, progress=92, message="Uploading rendered video to Google Drive.")
            result_filename = self._build_result_filename(job)
            result_folder = self._resolve_result_folder(job)
            drive_file = google_drive_service.upsert_file(
                output_path,
                token_path=self.google_token_path or None,
                folder_id=result_folder.get("id"),
                filename=result_filename,
                mimetype="video/mp4",
                description=f"Picadiri remote render result for queue job {job_id}",
                make_public=False,
            )
            if not drive_file or not drive_file.get("id"):
                raise RuntimeError("Failed to upload rendered video to Google Drive.")

            thumbnail_file = None
            thumbnail_filename = None
            packaged_thumbnail = None
            project_metadata_file = None
            config_path = os.path.join(temp_dir, "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f_conf:
                    packaged_config = json.load(f_conf)
                thumbnail_filename = packaged_config.get("thumbnail_filename")
                if thumbnail_filename:
                    packaged_thumbnail = os.path.join(temp_dir, thumbnail_filename)
                if packaged_thumbnail and os.path.exists(packaged_thumbnail):
                    thumbnail_file = google_drive_service.upsert_file(
                        packaged_thumbnail,
                        token_path=self.google_token_path or None,
                        folder_id=result_folder.get("id"),
                        filename=thumbnail_filename,
                        mimetype="image/png" if thumbnail_filename.lower().endswith(".png") else "image/jpeg",
                        description=f"Picadiri thumbnail for queue job {job_id}",
                        make_public=False,
                    )

                upload_metadata = dict(packaged_config.get("project_upload_metadata") or {})
                upload_metadata.update({
                    "employee_email": job.get("email") or upload_metadata.get("employee_email") or "",
                    "video_file": drive_file.get("name"),
                    "thumbnail_file": thumbnail_filename,
                    "drive_folder_id": result_folder.get("id"),
                    "drive_video_file_id": drive_file.get("id"),
                    "drive_thumbnail_file_id": (thumbnail_file or {}).get("id") if thumbnail_file else None,
                    "render_mode": "drive_api",
                })
                metadata_path = os.path.join(temp_dir, "metadata.json")
                with open(metadata_path, "w", encoding="utf-8") as f_meta:
                    json.dump(upload_metadata, f_meta, ensure_ascii=False, indent=2)
                project_metadata_file = google_drive_service.upsert_file(
                    metadata_path,
                    token_path=self.google_token_path or None,
                    folder_id=result_folder.get("id"),
                    filename="metadata.json",
                    mimetype="application/json",
                    description=f"Picadiri metadata for queue job {job_id}",
                    make_public=False,
                )

            self.update_job(
                job_id,
                status="completed",
                progress=100,
                message="Remote Drive API render completed.",
                result_file_id=drive_file.get("id"),
                result_file_name=drive_file.get("name"),
                metadata={
                    **(job.get("metadata") or {}),
                    "result_folder_id": result_folder.get("id"),
                    "result_folder_name": result_folder.get("name"),
                    "result_video_file_id": drive_file.get("id"),
                    "result_thumbnail_file_id": (thumbnail_file or {}).get("id") if thumbnail_file else None,
                    "result_metadata_file_id": (project_metadata_file or {}).get("id") if project_metadata_file else None,
                },
                completed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )
        except Exception as e:
            self.update_job(
                job_id,
                status="failed",
                progress=-1,
                message=f"Remote Drive API render failed: {e}",
                error_message=str(e),
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
    parser = argparse.ArgumentParser(description="Picadiri Google Drive API remote render worker")
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
