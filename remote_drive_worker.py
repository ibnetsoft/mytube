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
import hashlib
from urllib.parse import quote

import requests

from config import config
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
            print(f"[GcsRenderWorker] FFmpeg configured: {ffmpeg_path}")
    except Exception as e:
        print(f"[GcsRenderWorker] FFmpeg setup warning: {e}")


class RemoteDriveWorker:
    def __init__(self):
        _configure_ffmpeg_for_worker()
        try:
            config.load_remote_keys_from_supabase()
        except Exception as e:
            print(f"[GcsRenderWorker] Failed to load web admin settings: {e}")
        self.worker_id = os.getenv("REMOTE_RENDER_WORKER_ID") or f"worker-{os.getpid()}"
        self.poll_interval = int(os.getenv("REMOTE_RENDER_POLL_INTERVAL", "10"))
        # This render PC has a verified NVENC path. Operators can still set
        # USE_GPU_RENDER=false when diagnosing a graphics-driver issue.
        self.use_gpu = os.getenv("USE_GPU_RENDER", "true").lower() == "true"
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
            "render_mode": "eq.gcs_api",
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
            "render_mode": "eq.gcs_api",
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
        print("[GcsRenderWorker] Configuration check")
        print(f"  worker_id: {self.worker_id}")
        print(f"  supabase_url: {self.supabase_url or '(missing)'}")
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

    def _refresh_gcs_settings(self):
        config.load_remote_keys_from_supabase()

    def _safe_manifest_path(self, relative_path):
        normalized = str(relative_path or "").replace("\\", "/").strip("/")
        parts = [part for part in normalized.split("/") if part]
        if not parts or any(part in {".", ".."} for part in parts):
            raise RuntimeError(f"잘못된 렌더 파일 경로입니다: {relative_path}")
        return os.path.join(*parts)

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
            print(f"[GcsRenderWorker] GCS credentials setup failed: {e}")
            return None

    def _download_from_gcs_storage(self, source, destination_path):
        """Fetch a GCS object with atomic local write."""
        if not isinstance(source, dict):
            return False
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

    def _upload_to_gcs_storage(self, file_path, object_path, mime_type="video/mp4"):
        """Upload a file to Google Cloud Storage."""
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
                media_url = f"https://storage.googleapis.com/{quote(bucket, safe='')}/{quote(clean_path, safe='/')}"
                signed_url = self._generate_gcs_signed_url(creds, bucket, clean_path)
                return {
                    "bucket": bucket,
                    "path": clean_path,
                    "public_url": signed_url or media_url,
                    "signed_url": signed_url,
                    "media_url": media_url,
                }
            else:
                print(f"[GcsRenderWorker] GCS upload failed with status {res.status_code}: {res.text[:200]}")
        except Exception as e:
            print(f"[GcsRenderWorker] GCS upload error: {e}")
        return None

    def _generate_gcs_signed_url(self, creds, bucket, object_path, expires_seconds=60 * 60 * 24 * 7):
        """Create a V4 signed URL for private GCS render outputs."""
        try:
            if not creds or not getattr(creds, "signer", None):
                return None
            now = datetime.datetime.now(datetime.timezone.utc)
            datestamp = now.strftime("%Y%m%d")
            timestamp = now.strftime("%Y%m%dT%H%M%SZ")
            credential_scope = f"{datestamp}/auto/storage/goog4_request"
            client_email = getattr(creds, "service_account_email", "") or os.getenv("GCS_CLIENT_EMAIL", "")
            if not client_email:
                return None

            canonical_uri = f"/{quote(bucket, safe='')}/{quote(object_path, safe='/')}"
            credential = f"{client_email}/{credential_scope}"
            query_params = {
                "X-Goog-Algorithm": "GOOG4-RSA-SHA256",
                "X-Goog-Credential": credential,
                "X-Goog-Date": timestamp,
                "X-Goog-Expires": str(int(expires_seconds)),
                "X-Goog-SignedHeaders": "host",
            }
            canonical_query = "&".join(
                f"{quote(k, safe='')}={quote(v, safe='')}"
                for k, v in sorted(query_params.items())
            )
            canonical_headers = "host:storage.googleapis.com\n"
            signed_headers = "host"
            payload_hash = "UNSIGNED-PAYLOAD"
            canonical_request = "\n".join([
                "GET",
                canonical_uri,
                canonical_query,
                canonical_headers,
                signed_headers,
                payload_hash,
            ])
            request_hash = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
            string_to_sign = "\n".join([
                "GOOG4-RSA-SHA256",
                timestamp,
                credential_scope,
                request_hash,
            ])
            signature = creds.signer.sign(string_to_sign.encode("utf-8")).hex()
            return f"https://storage.googleapis.com{canonical_uri}?{canonical_query}&X-Goog-Signature={signature}"
        except Exception as e:
            print(f"[GcsRenderWorker] GCS signed URL generation failed: {e}")
            return None

    def _download_asset_with_fallback(self, job_id, _legacy_file_id, destination_path, *, storage_source=None, label):
        """Read render assets from GCS only."""
        if storage_source and self._download_from_gcs_storage(storage_source, destination_path):
            return "gcs_storage"

        raise RuntimeError(f"에셋 다운로드 실패 (GCS 저장소에서 찾을 수 없음): {label}")

    def _prepare_gcs_manifest_job(self, job_id, job, temp_dir, config_file_id):
        config_path = os.path.join(temp_dir, "config.json")
        self.update_job(job_id, progress=5, message="GCS에서 렌더 설정 파일 다운로드 중...")
        metadata = job.get("metadata") or {}
        gcs_cfg = metadata.get("gcs_config") or {}
        config_storage_source = {
            "gcs_bucket": gcs_cfg.get("bucket"),
            "gcs_path": gcs_cfg.get("path"),
            "gcs_signed_url": gcs_cfg.get("signed_url"),
        }
        if not config_storage_source["gcs_bucket"] and not config_storage_source["gcs_signed_url"]:
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
            relative_path = item.get("path")
            has_storage = (
                item.get("gcs_signed_url")
                or (item.get("gcs_bucket") and item.get("gcs_path"))
            )
            if (not has_storage) or not relative_path:
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
                "gcs_bucket": item.get("gcs_bucket"),
                "gcs_path": item.get("gcs_path"),
                "gcs_signed_url": item.get("gcs_signed_url"),
            }
            if not storage_source["gcs_bucket"] and not storage_source["gcs_signed_url"]:
                storage_source = None
            self._download_asset_with_fallback(
                job_id,
                None,
                local_path,
                storage_source=storage_source,
                label=relative_path,
            )

    def process_job(self, job):
        self._refresh_gcs_settings()
        job_id = job["id"]
        asset_file_id = job.get("asset_file_id")
        if not asset_file_id:
            raise RuntimeError("큐 작업에 asset_file_id가 없습니다.")

        temp_dir = tempfile.mkdtemp(prefix=f"gcs_api_render_{job_id}_")
        zip_path = os.path.join(temp_dir, "asset_package.zip")
        try:
            metadata = job.get("metadata") or {}
            if (
                metadata.get("package_transport") in ("gcs_config", "gcs_manifest", "gcs_folder")
                or metadata.get("config_file_id")
                or metadata.get("gcs_config")
            ):
                config_file_id = metadata.get("config_file_id") or asset_file_id
                self._prepare_gcs_manifest_job(job_id, job, temp_dir, config_file_id)
            else:
                self.update_job(job_id, progress=5, message="GCS API 저장소에서 에셋 패키지 다운로드 중...")
                self._download_asset_with_fallback(
                    job_id,
                    asset_file_id,
                    zip_path,
                    storage_source=metadata.get("gcs_asset_package"),
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

            self.update_job(job_id, progress=92, message="렌더링된 영상을 GCS API 저장소에 업로드 중...")
            result_filename = self._build_result_filename(job)

            gcs_render_path = f"std-renders/{job_id}/{result_filename}"
            gcs_video = self._upload_to_gcs_storage(
                output_path,
                object_path=gcs_render_path,
                mime_type="video/mp4",
            )
            if gcs_video:
                print(f"[GcsRenderWorker] GCS API 저장소 영상 업로드 성공: {gcs_render_path}")

            if not gcs_video:
                raise RuntimeError("렌더링된 영상을 GCS API 저장소에 업로드하지 못했습니다.")

            thumbnail_filename = None
            packaged_thumbnail = None
            upload_metadata = {}
            gcs_thumb = None
            config_path = os.path.join(temp_dir, "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f_conf:
                    packaged_config = json.load(f_conf)
                thumbnail_filename = packaged_config.get("thumbnail_filename")
                if thumbnail_filename:
                    packaged_thumbnail = os.path.join(temp_dir, thumbnail_filename)
                if packaged_thumbnail and os.path.exists(packaged_thumbnail):
                    thumb_mime = "image/png" if thumbnail_filename.lower().endswith(".png") else "image/jpeg"
                    gcs_thumb = self._upload_to_gcs_storage(
                        packaged_thumbnail,
                        object_path=f"std-renders/{job_id}/{thumbnail_filename}",
                        mime_type=thumb_mime,
                    )

                queue_metadata = job.get("metadata") or {}
                upload_metadata = dict(packaged_config.get("project_upload_metadata") or {})
                provenance_path = os.path.join(temp_dir, "audio_provenance.json")
                if os.path.isfile(provenance_path):
                    with open(provenance_path, encoding="utf-8") as provenance_file:
                        upload_metadata["audio_provenance"] = json.load(provenance_file)
                upload_metadata.update({
                    "employee_email": job.get("email") or upload_metadata.get("employee_email") or "",
                    "video_file": result_filename,
                    "thumbnail_file": thumbnail_filename,
                    "gcs_video_path": (gcs_video or {}).get("path"),
                    "gcs_thumbnail_path": (gcs_thumb or {}).get("path"),
                    "gcs_video_url": (gcs_video or {}).get("public_url"),
                    "gcs_thumbnail_url": (gcs_thumb or {}).get("public_url"),
                    "render_mode": "gcs_api",
                })
                for key in ("track_count", "track_durations", "total_duration_seconds", "app_mode", "render_style", "queue_type"):
                    if queue_metadata.get(key) is not None:
                        upload_metadata[key] = queue_metadata.get(key)
                metadata_path = os.path.join(temp_dir, "metadata.json")
                with open(metadata_path, "w", encoding="utf-8") as f_meta:
                    json.dump(upload_metadata, f_meta, ensure_ascii=False, indent=2)

                self._upload_to_gcs_storage(
                    metadata_path,
                    object_path=f"std-renders/{job_id}/metadata.json",
                    mime_type="application/json",
                )

            result_public_url = (gcs_video or {}).get("public_url")
            result_file_id = result_public_url or gcs_render_path
            storage_provider = "gcs"
            storage_summary = []
            if gcs_video:
                storage_summary.append("GCS API")

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
                    "storage_bucket": (gcs_video or {}).get("bucket"),
                    "storage_path": (gcs_video or {}).get("path"),
                    "result_public_url": result_public_url,
                    "gcs_bucket": (gcs_video or {}).get("bucket"),
                    "gcs_path": (gcs_video or {}).get("path"),
                    "gcs_public_url": (gcs_video or {}).get("public_url"),
                    "gcs_thumbnail_url": (gcs_thumb or {}).get("public_url"),
                    "result_video_file_id": None,
                    "result_thumbnail_file_id": None,
                    "result_metadata_file_id": None,
                    "audio_provenance": upload_metadata.get("audio_provenance"),
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
        print(f"[GcsRenderWorker] Started as {self.worker_id}")
        while True:
            try:
                job = self.fetch_next_job()
                if not job:
                    time.sleep(self.poll_interval)
                    continue
                claimed = self.claim_job(job)
                if not claimed:
                    continue
                print(f"[GcsRenderWorker] Processing job {claimed['id']}")
                self.process_job(claimed)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"[GcsRenderWorker] Error: {e}")
                time.sleep(self.poll_interval)

    def run_once(self):
        print(f"[GcsRenderWorker] Running one polling cycle as {self.worker_id}")
        job = self.fetch_next_job()
        if not job:
            print("[GcsRenderWorker] No pending GCS API job.")
            return 0
        claimed = self.claim_job(job)
        if not claimed:
            print("[GcsRenderWorker] Job was already claimed by another worker.")
            return 0
        print(f"[GcsRenderWorker] Processing job {claimed['id']}")
        self.process_job(claimed)
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIR GCS API render worker")
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
