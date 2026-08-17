"""
[AIR-0227C Stage 8] Real Google Drive input/output adapter.

Wraps services/google_drive_service.py (unmodified) - the same module the
live Drive-relay feature already uses in production
(services/remote_drive_render_service.py), reusing its OAuth token_path
model rather than inventing a new one. This is a DIFFERENT, narrower kind
of credential than the AIR-0225B service_role incident: a per-user/per-
worker Drive OAuth token scoped (by the token itself, at Google's end) to
whatever the consenting account granted - not an admin master key.

NOT wired to any real Drive account or folder by default. Requires two
pieces of configuration that must be provisioned by CTO/ops, never
committed:
    AIRWORKER_DRIVE_TOKEN_PATH  - path to an existing OAuth token file
                                  (google_drive_service.py's token_path)
    AIRWORKER_DRIVE_FOLDER_ID   - a SPECIFIC, isolated test/working folder
                                  id - never the Drive root, never a real
                                  production content folder without
                                  separate CTO approval (docs/AIR_WORKER_DRIVE_ADAPTER.md)

Live-tested status: NOT live-tested this Task - no isolated test Drive
account/folder/token was available in this environment. Implementation is
complete and reviewed; docs/AIR_WORKER_DRIVE_ADAPTER.md documents exactly
what a CTO-provisioned test folder + token_path would let a future session
verify. LocalCopyUploadAdapter (AIR-0227B) remains the adapter actually
used by the local E2E fixture and this Task's live QA.
"""
import os
import re
import time
from pathlib import Path

MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024  # 500MB - a render input package should never be larger than this
ALLOWED_DOWNLOAD_EXTENSIONS = {".zip"}
ALLOWED_UPLOAD_EXTENSIONS = {".mp4", ".mp3"}
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0

DRIVE_TOKEN_PATH = os.environ.get("AIRWORKER_DRIVE_TOKEN_PATH")
DRIVE_FOLDER_ID = os.environ.get("AIRWORKER_DRIVE_FOLDER_ID")


class DriveAdapterError(Exception):
    pass


def _safe_basename(name: str) -> str:
    """Strips any directory components and rejects traversal sequences -
    a filename coming back from Drive metadata is attacker-influenced (if
    the Drive account/folder were ever compromised) and must never be used
    to build a local path without this check."""
    base = os.path.basename(name or "")
    base = re.sub(r"[^\w.\-]", "_", base)
    if not base or base in (".", "..") :
        raise DriveAdapterError(f"Rejected unsafe filename from Drive: {name!r}")
    return base


def _check_extension(filename: str, allowed: set[str]):
    ext = Path(filename).suffix.lower()
    if ext not in allowed:
        raise DriveAdapterError(f"Rejected file with disallowed extension '{ext}' (allowed: {allowed})")


def _with_retry(fn, description: str):
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            # Never log the exception's raw args if they could contain a
            # token/URL with embedded credentials - google-api-python-client
            # exceptions can include the request URL, which for OAuth flows
            # does not normally carry the token itself (that's in a header),
            # but we still keep this message generic on purpose.
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
    raise DriveAdapterError(f"{description} failed after {MAX_RETRIES} attempts: {type(last_exc).__name__}")


def download_input_package(file_id: str, dest_dir: Path) -> Path:
    """Downloads a render input package (zip) from the configured Drive
    folder, verifying it actually came from that folder (not an arbitrary
    Drive-wide file_id) and passes basic size/extension/name checks before
    handing it back for extraction (render_pipeline_adapter.prepare_temp_dir
    already validates the zip's own contents - this only validates the
    fetch itself)."""
    if not DRIVE_TOKEN_PATH or not DRIVE_FOLDER_ID:
        raise DriveAdapterError("AIRWORKER_DRIVE_TOKEN_PATH / AIRWORKER_DRIVE_FOLDER_ID not configured")

    from services.google_drive_service import google_drive_service

    def _fetch_metadata():
        return google_drive_service.get_file_metadata(file_id, token_path=DRIVE_TOKEN_PATH)

    meta = _with_retry(_fetch_metadata, "Drive metadata fetch")
    if not meta:
        raise DriveAdapterError(f"Drive file not found or inaccessible: {file_id}")
    if DRIVE_FOLDER_ID not in (meta.get("parents") or []):
        raise DriveAdapterError(f"Drive file {file_id} is not inside the configured working folder - refusing (path/scope confinement)")

    size = int(meta.get("size") or 0)
    if size <= 0 or size > MAX_DOWNLOAD_BYTES:
        raise DriveAdapterError(f"Drive file size {size} outside allowed range (1..{MAX_DOWNLOAD_BYTES})")

    safe_name = _safe_basename(meta.get("name") or f"{file_id}.zip")
    _check_extension(safe_name, ALLOWED_DOWNLOAD_EXTENSIONS)

    dest_dir.mkdir(parents=True, exist_ok=True)
    local_path = dest_dir / safe_name

    def _fetch():
        return google_drive_service.download_file(file_id, str(local_path), token_path=DRIVE_TOKEN_PATH)

    result = _with_retry(_fetch, "Drive file download")
    if not result or not local_path.exists():
        raise DriveAdapterError(f"Drive download reported success but file is missing: {local_path}")
    actual_size = local_path.stat().st_size
    if actual_size <= 0 or actual_size > MAX_DOWNLOAD_BYTES:
        local_path.unlink(missing_ok=True)  # clean up a partial/oversized download rather than leaving it around
        raise DriveAdapterError(f"Downloaded file size {actual_size} outside allowed range - discarded")
    return local_path


def upload_output(local_output_path: Path, remote_filename: str) -> str:
    """Uploads a completed render output to the configured Drive working
    folder - render_video's output.mp4.
    Returns the Drive file id (stable reference, cheaper than a webViewLink
    for the central server to store)."""
    if not DRIVE_TOKEN_PATH or not DRIVE_FOLDER_ID:
        raise DriveAdapterError("AIRWORKER_DRIVE_TOKEN_PATH / AIRWORKER_DRIVE_FOLDER_ID not configured")

    safe_name = _safe_basename(remote_filename)
    _check_extension(safe_name, ALLOWED_UPLOAD_EXTENSIONS)
    if not local_output_path.exists() or local_output_path.stat().st_size <= 0:
        raise DriveAdapterError(f"Local output missing or empty, refusing to upload: {local_output_path}")

    from services.google_drive_service import google_drive_service

    mimetype = "audio/mpeg" if safe_name.lower().endswith(".mp3") else "video/mp4"

    def _push():
        return google_drive_service.upsert_file(
            str(local_output_path), token_path=DRIVE_TOKEN_PATH, folder_id=DRIVE_FOLDER_ID,
            filename=safe_name, mimetype=mimetype,
        )

    result = _with_retry(_push, "Drive file upload")
    if not result or not result.get("id"):
        raise DriveAdapterError("Drive upload did not return a file id")
    return result["id"]
