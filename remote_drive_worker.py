import datetime
import json
import os
import shutil
import tempfile
import time
import zipfile

import requests

from config import config
from services.google_drive_service import google_drive_service
from services.remote_render_service import remote_render_executor_func


class RemoteDriveWorker:
    def __init__(self):
        try:
            config.load_remote_keys_from_supabase()
        except Exception as e:
            print(f"[RemoteDriveWorker] Failed to load web admin settings: {e}")
        self.worker_id = os.getenv("REMOTE_RENDER_WORKER_ID") or f"worker-{os.getpid()}"
        self.poll_interval = int(os.getenv("REMOTE_RENDER_POLL_INTERVAL", "10"))
        self.use_gpu = os.getenv("USE_GPU_RENDER", "true").lower() == "true"
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
            drive_file = google_drive_service.upload_file(
                output_path,
                token_path=self.google_token_path or None,
                folder_id=self.output_folder_id or None,
                mimetype="video/mp4",
                description=f"Picadiri remote render result for queue job {job_id}",
                make_public=False,
            )
            if not drive_file or not drive_file.get("id"):
                raise RuntimeError("Failed to upload rendered video to Google Drive.")

            self.update_job(
                job_id,
                status="completed",
                progress=100,
                message="Remote Drive API render completed.",
                result_file_id=drive_file.get("id"),
                result_file_name=drive_file.get("name"),
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


if __name__ == "__main__":
    RemoteDriveWorker().run_forever()
