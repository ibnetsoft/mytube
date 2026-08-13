"""GitHub Releases based updater for the packaged AIR Studio app."""

import hashlib
import os
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
from typing import Optional

import requests
from packaging import version

from config import config


RELEASES_API_URL = "https://api.github.com/repos/ibnetsoft/AIR-releases/releases/latest"
APP_EXE_NAME = "AIRStudio.exe"


class UpdaterService:
    def __init__(self):
        self.is_downloading = False
        self.download_progress = 0
        self.download_error = None
        self.download_path: Optional[Path] = None
        self.expected_sha256: Optional[str] = None
        self.release_info = None
        self.is_applying = False
        self._lock = threading.Lock()

    @property
    def current_version(self) -> str:
        """Read the version record installed beside the frozen executable."""
        return str(config.APP_VERSION or "0.0.0").strip() or "0.0.0"

    @property
    def can_apply_update(self) -> bool:
        """Only a packaged one-dir app can replace itself in place."""
        return bool(getattr(sys, "frozen", False))

    @property
    def _update_dir(self) -> Path:
        path = Path(config.LOCAL_APP_DATA_DIR) / "update"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def _app_dir(self) -> Path:
        if not self.can_apply_update:
            return Path(config.BASE_DIR).resolve()
        return Path(sys.executable).resolve().parent

    @staticmethod
    def _wait_for_helper_ready(ready_path: Path, timeout_seconds: float = 8.0) -> bool:
        """Do not terminate the app until the scheduled update helper is alive."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if ready_path.exists():
                return True
            time.sleep(0.05)
        return ready_path.exists()

    @staticmethod
    def _schtasks_path() -> str:
        path = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "schtasks.exe"
        return str(path) if path.exists() else "schtasks.exe"

    @classmethod
    def _run_schtasks(cls, arguments: list[str]) -> tuple[bool, str]:
        try:
            completed = subprocess.run(
                [cls._schtasks_path(), *arguments],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except OSError as exc:
            return False, str(exc)
        return completed.returncode == 0, (completed.stdout or "").strip()

    @classmethod
    def _delete_scheduled_task(cls, task_name: str) -> None:
        cls._run_schtasks(["/Delete", "/TN", task_name, "/F"])

    def check_for_update(self):
        """Read the latest public GitHub release when in-place updates work."""
        current_version = self.current_version

        # A `python main.py` server is frequently used while developing or
        # diagnosing a local install. It cannot replace its own source tree,
        # so never present an update modal that will inevitably loop.
        if not self.can_apply_update:
            return {
                "has_update": False,
                "can_apply_update": False,
                "current_version": current_version,
                "latest_version": current_version,
            }

        try:
            response = requests.get(
                RELEASES_API_URL,
                headers={"Accept": "application/vnd.github+json"},
                timeout=10,
            )
            response.raise_for_status()
            release = response.json()
            tag = str(release.get("tag_name", "")).strip()
            latest_version = tag[1:] if tag.lower().startswith("v") else tag
            if not latest_version:
                return {
                    "has_update": False,
                    "can_apply_update": True,
                    "current_version": current_version,
                    "error": "Invalid release version",
                }

            asset = next(
                (
                    item
                    for item in release.get("assets", [])
                    if item.get("name") == f"AIRStudio-{latest_version}-win-x64.zip"
                ),
                None,
            )
            if not asset:
                return {
                    "has_update": False,
                    "can_apply_update": True,
                    "current_version": current_version,
                    "latest_version": latest_version,
                    "error": "No Windows ZIP asset in the latest release",
                }

            has_update = version.parse(latest_version) > version.parse(current_version)
            digest = str(asset.get("digest", ""))
            if digest.startswith("sha256:"):
                digest = digest.split(":", 1)[1]
            info = {
                "has_update": has_update,
                "can_apply_update": True,
                "current_version": current_version,
                "latest_version": latest_version,
                "download_url": asset.get("browser_download_url"),
                "asset_name": asset.get("name"),
                "sha256": digest or None,
                "release_url": release.get("html_url"),
            }
            self.release_info = info
            return info
        except Exception as exc:
            return {
                "has_update": False,
                "can_apply_update": True,
                "current_version": current_version,
                "error": str(exc),
            }

    def start_download(self, url: str, expected_sha256: Optional[str] = None) -> bool:
        with self._lock:
            if not self.can_apply_update:
                self.download_error = "In-place updates are only available in the installed AIR Studio app."
                return False
            if self.is_downloading:
                return False
            self.is_downloading = True
            self.download_progress = 0
            self.download_error = None
            self.expected_sha256 = expected_sha256
            self.download_path = self._update_dir / "AIRStudio-update.zip"

        thread = threading.Thread(target=self._download_worker, args=(url,), daemon=True)
        thread.start()
        return True

    def _download_worker(self, url: str):
        try:
            assert self.download_path is not None
            temporary_path = self.download_path.with_suffix(".download")
            response = requests.get(url, stream=True, timeout=(15, 120))
            response.raise_for_status()
            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0
            digest = hashlib.sha256()
            with temporary_path.open("wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    if not chunk:
                        continue
                    output.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    self.download_progress = int(downloaded * 100 / total_size) if total_size else 0

            actual_sha256 = digest.hexdigest()
            if self.expected_sha256 and actual_sha256.lower() != self.expected_sha256.lower():
                raise ValueError("Downloaded file did not pass SHA256 verification.")
            temporary_path.replace(self.download_path)
            self.download_progress = 100
        except Exception as exc:
            self.download_error = str(exc)
            self.download_progress = 0
        finally:
            self.is_downloading = False

    def apply_update_and_restart(self):
        if not self.can_apply_update:
            return False, "In-place updates are only available in the installed AIR Studio app."
        if self.is_applying:
            return False, "The update is already being applied."
        if not self.download_path or not self.download_path.exists() or self.download_progress != 100:
            return False, "The downloaded update package is not ready."
        if not zipfile.is_zipfile(self.download_path):
            return False, "The downloaded update package is invalid."

        try:
            with zipfile.ZipFile(self.download_path) as archive:
                names = {item.filename.replace("\\", "/") for item in archive.infolist()}
                if APP_EXE_NAME not in names or "version.json" not in names:
                    return False, "The update package does not contain a complete AIR Studio app."
        except (OSError, zipfile.BadZipFile) as exc:
            return False, f"Unable to validate the update package: {exc}"

        script_path = self._update_dir / "apply_update.ps1"
        extract_dir = self._update_dir / "extracted"
        log_path = self._update_dir / "apply_update.log"
        ready_path = self._update_dir / "apply_update.ready"
        pid = os.getpid()
        task_name = f"AIRStudioUpdate-{pid}-{int(time.time() * 1000)}"
        app_dir = self._app_dir
        zip_path = self.download_path
        exe_path = app_dir / APP_EXE_NAME
        restart_environment = {
            name: value
            for name in ("HOST", "PORT", "LOCALAPPDATA")
            if (value := os.environ.get(name))
        }
        restart_environment_lines = "\n".join(
            f"$env:{name} = '{value.replace("'", "''")}'"
            for name, value in restart_environment.items()
        )
        try:
            ready_path.unlink(missing_ok=True)
        except OSError as exc:
            return False, f"Unable to prepare the update helper: {exc}"

        script = f"""$ErrorActionPreference = 'Stop'
$pidToWait = {pid}
$zip = '{str(zip_path).replace("'", "''")}'
$extract = '{str(extract_dir).replace("'", "''")}'
$app = '{str(app_dir).replace("'", "''")}'
$exe = '{str(exe_path).replace("'", "''")}'
$log = '{str(log_path).replace("'", "''")}'
$ready = '{str(ready_path).replace("'", "''")}'
$task = '{task_name}'
try {{
    Set-Content -LiteralPath $ready -Value "helper-started:$PID" -Encoding ascii
    Add-Content -LiteralPath $log -Value "$(Get-Date -Format o) Update helper started (PID $PID)."
    while (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue) {{ Start-Sleep -Milliseconds 500 }}
    if (Test-Path $extract) {{ Remove-Item $extract -Recurse -Force }}
    New-Item -ItemType Directory -Force -Path $extract | Out-Null
    Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
    if (-not (Test-Path (Join-Path $extract 'AIRStudio.exe'))) {{ throw 'Update package is missing AIRStudio.exe.' }}
    if (-not (Test-Path (Join-Path $extract 'version.json'))) {{ throw 'Update package is missing version.json.' }}
    Copy-Item -Path (Join-Path $extract '*') -Destination $app -Recurse -Force
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    Remove-Item $extract -Recurse -Force -ErrorAction SilentlyContinue
    Add-Content -LiteralPath $log -Value "$(Get-Date -Format o) Update copied successfully."
    {restart_environment_lines}
    Start-Process -FilePath $exe
}} catch {{
    Add-Content -LiteralPath $log -Value "$(Get-Date -Format o) Update failed: $($_ | Out-String)"
    if (Test-Path $exe) {{
        {restart_environment_lines}
        Start-Process -FilePath $exe
    }}
}} finally {{
    Remove-Item $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
    & schtasks.exe /Delete /TN $task /F 2>$null | Out-Null
}}
"""
        try:
            # Windows PowerShell 5.1 reliably reads UTF-8 scripts only with a BOM.
            script_path.write_text(script, encoding="utf-8-sig")
            powershell_path = (
                Path(os.environ.get("SystemRoot", r"C:\Windows"))
                / "System32"
                / "WindowsPowerShell"
                / "v1.0"
                / "powershell.exe"
            )
            powershell_exe = str(powershell_path) if powershell_path.exists() else "powershell.exe"
            task_action = f'"{powershell_exe}" -NoProfile -ExecutionPolicy Bypass -File "{script_path}"'
            schedule_time = time.strftime("%H:%M", time.localtime(time.time() + 60))
            created, create_error = self._run_schtasks(
                [
                    "/Create",
                    "/TN",
                    task_name,
                    "/TR",
                    task_action,
                    "/SC",
                    "ONCE",
                    "/ST",
                    schedule_time,
                    "/RL",
                    "LIMITED",
                    "/F",
                ]
            )
            if not created:
                return False, f"Unable to schedule the updater: {create_error or 'schtasks failed.'}"

            started, start_error = self._run_schtasks(["/Run", "/TN", task_name])
            if not started:
                self._delete_scheduled_task(task_name)
                return False, f"Unable to start the updater: {start_error or 'schtasks failed.'}"
        except OSError as exc:
            self._delete_scheduled_task(task_name)
            return False, f"Unable to start the updater: {exc}"

        if not self._wait_for_helper_ready(ready_path):
            self._delete_scheduled_task(task_name)
            return False, "The update helper did not start. AIR Studio is still running."

        self.is_applying = True
        threading.Thread(target=self._exit_after_response, daemon=True).start()
        return True, None

    @staticmethod
    def _exit_after_response():
        """Stop only after FastAPI has had time to send the success response."""
        time.sleep(2.0)
        os._exit(0)


updater_service = UpdaterService()
