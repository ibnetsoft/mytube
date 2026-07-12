"""
[AIR-0227B Stage 4/12] Upload adapter abstraction.

Stage 1 re-verification of services/google_drive_service.py found upload
(upsert_file) and download (download_file) both require a per-user OAuth
token_path, not a service_role/admin credential - a materially different
(and much narrower) kind of secret than the AIR-0225B incident's exposed
key. Wiring the real Drive adapter into a worker running on an
operator-controlled remote PC is still explicitly out of this Task's scope
(local E2E fixture only, per the task's own "가짜 업로드 또는 로컬 copy
adapter" instruction) - GoogleDriveUploadAdapter below is documented but
deliberately left unimplemented (NotImplementedError) so nothing here can
accidentally reach a real Drive account.
"""
import shutil
import time
from pathlib import Path


class UploadAdapter:
    def upload(self, local_output_path: Path, job: dict) -> str:
        raise NotImplementedError


class LocalCopyUploadAdapter(UploadAdapter):
    """[AIR-0227B Stage 12 E2E fixture] Copies the rendered output.mp4 into
    a local 'delivered' folder instead of uploading anywhere - this is the
    adapter actually used by the local E2E test and by default until a real
    upload target is approved."""

    def __init__(self, delivered_dir: Path):
        self.delivered_dir = Path(delivered_dir)
        self.delivered_dir.mkdir(parents=True, exist_ok=True)

    def upload(self, local_output_path: Path, job: dict) -> str:
        job_id = job["job_id"]
        dest = self.delivered_dir / f"{job_id}.mp4"
        shutil.copy2(local_output_path, dest)
        return str(dest)


class GoogleDriveUploadAdapter(UploadAdapter):
    """[Documented, NOT wired up this Task] Would call
    services/google_drive_service.py::upsert_file(...) using a per-project
    Drive OAuth token_path, mirroring remote_drive_worker.py's existing
    upload step. Left unimplemented until a real production connection is
    explicitly approved (docs/AIR_WORKER_ARCHITECTURE.md §0)."""

    def upload(self, local_output_path: Path, job: dict) -> str:
        raise NotImplementedError(
            "GoogleDriveUploadAdapter is a design placeholder only - "
            "not connected in AIR-0227B (local E2E fixture uses LocalCopyUploadAdapter)."
        )
