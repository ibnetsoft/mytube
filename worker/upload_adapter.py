"""
[AIR-0227B Stage 4/12, AIR-0227C Stage 8] Upload adapter abstraction.

AIR-0227B left GoogleDriveUploadAdapter unimplemented (NotImplementedError)
since real Drive connection was out of that Task's scope. AIR-0227C Stage 8
implements it for real via worker/drive_adapter.py, scoped to a single
configured folder with filename/extension/size validation - see that
module's docstring for the full security rationale. It is NOT live-tested
this Task (no isolated test Drive account/folder/token available in this
environment - docs/AIR_WORKER_DRIVE_ADAPTER.md documents what a
CTO-provisioned test folder would let a future session verify).
LocalCopyUploadAdapter remains the adapter actually used by the local E2E
fixture and all of this Task's live QA.
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
    """[AIR-0227C Stage 8] Real implementation, delegating to
    worker/drive_adapter.py::upload_output. Requires
    AIRWORKER_DRIVE_TOKEN_PATH and AIRWORKER_DRIVE_FOLDER_ID to be
    configured (both provisioned by CTO/ops, never committed) - raises
    DriveAdapterError immediately if either is missing rather than
    silently falling back to some other behavior."""

    def upload(self, local_output_path: Path, job: dict) -> str:
        from drive_adapter import upload_output
        remote_filename = f"{job['job_id']}.mp4"
        return upload_output(local_output_path, remote_filename)
