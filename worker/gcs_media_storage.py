"""GCS-only binary media publishing shared by local image workers."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote
import requests
DEFAULT_BUCKET = "air-studio-prod"
_GCS_CREDENTIALS_CACHE: tuple[Any, str] | None = None

def _gcs_credentials():
    global _GCS_CREDENTIALS_CACHE
    client_email = os.getenv("GCS_CLIENT_EMAIL") or os.getenv("GOOGLE_CLIENT_EMAIL") or ""
    private_key = os.getenv("GCS_PRIVATE_KEY") or os.getenv("GOOGLE_PRIVATE_KEY") or ""
    project_id = os.getenv("GCS_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "air-studio-prod"
    bucket = os.getenv("GCS_BUCKET_NAME") or DEFAULT_BUCKET
    if not (client_email and private_key and bucket):
        raise RuntimeError("GCS credentials are required for scene image publishing")
    if _GCS_CREDENTIALS_CACHE is not None:
        cached_credentials, cached_bucket = _GCS_CREDENTIALS_CACHE
        if cached_bucket == bucket and cached_credentials.valid:
            return cached_credentials, bucket
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
    _GCS_CREDENTIALS_CACHE = (creds, bucket)
    return creds, bucket


def _upload_gcs_file(file_path: Path, object_path: str, mime_type: str) -> tuple[str, str, str]:
    creds, bucket = _gcs_credentials()
    clean_path = str(object_path or "").strip().replace("\\", "/").lstrip("/")
    if not clean_path:
        raise RuntimeError("GCS object path is empty")
    with file_path.open("rb") as handle:
        response = requests.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{quote(bucket, safe='')}/o"
            f"?uploadType=media&name={quote(clean_path, safe='')}",
            headers={"Authorization": f"Bearer {creds.token}", "Content-Type": mime_type},
            data=handle,
            timeout=300,
        )
    if response.status_code not in (200, 201):
        raise RuntimeError(f"GCS scene image upload failed ({response.status_code}): {response.text[:300]}")
    return bucket, clean_path, f"/api/std/assets/gcs-file?bucket={quote(bucket, safe='')}&path={quote(clean_path, safe='')}"


