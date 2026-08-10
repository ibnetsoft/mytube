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
from version import APP_VERSION


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
        self._lock = threading.Lock()

    @property
    def _update_dir(self) -> Path:
        path = Path(config.LOCAL_APP_DATA_DIR) / "update"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def _app_dir(self) -> Path:
        if not getattr(sys, "frozen", False):
            return Path(config.BASE_DIR).resolve()
        return Path(sys.executable).resolve().parent

    def check_for_update(self):
        """Read the latest public GitHub release; no server-side setting is needed."""
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
                return {"has_update": False, "current_version": APP_VERSION, "error": "Invalid release version"}

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
                    "current_version": APP_VERSION,
                    "latest_version": latest_version,
                    "error": "No Windows ZIP asset in the latest release",
                }

            has_update = version.parse(latest_version) > version.parse(APP_VERSION)
            digest = str(asset.get("digest", ""))
            if digest.startswith("sha256:"):
                digest = digest.split(":", 1)[1]
            info = {
                "has_update": has_update,
                "current_version": APP_VERSION,
                "latest_version": latest_version,
                "download_url": asset.get("browser_download_url"),
                "asset_name": asset.get("name"),
                "sha256": digest or None,
                "release_url": release.get("html_url"),
            }
            self.release_info = info
            return info
        except Exception as exc:
            return {"has_update": False, "current_version": APP_VERSION, "error": str(exc)}

    def start_download(self, url: str, expected_sha256: Optional[str] = None):
        with self._lock:
            if self.is_downloading:
                return
            self.is_downloading = True
            self.download_progress = 0
            self.download_error = None
            self.expected_sha256 = expected_sha256
            self.download_path = self._update_dir / "AIRStudio-update.zip"

        thread = threading.Thread(target=self._download_worker, args=(url,), daemon=True)
        thread.start()

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
                raise ValueError("다운로드 파일의 SHA256 검증에 실패했습니다.")
            temporary_path.replace(self.download_path)
            self.download_progress = 100
        except Exception as exc:
            self.download_error = str(exc)
            self.download_progress = 0
        finally:
            self.is_downloading = False

    def apply_update_and_restart(self):
        if not getattr(sys, "frozen", False):
            return False, "개발 모드에서는 자동 교체를 실행하지 않습니다."
        if not self.download_path or not self.download_path.exists() or self.download_progress != 100:
            return False, "다운로드된 업데이트 파일이 없습니다."

        script_path = self._update_dir / "apply_update.ps1"
        extract_dir = self._update_dir / "extracted"
        pid = os.getpid()
        app_dir = self._app_dir
        zip_path = self.download_path
        exe_path = app_dir / APP_EXE_NAME
        script = f"""$ErrorActionPreference = 'Stop'
$pidToWait = {pid}
$zip = '{str(zip_path).replace("'", "''")}'
$extract = '{str(extract_dir).replace("'", "''")}'
$app = '{str(app_dir).replace("'", "''")}'
$exe = '{str(exe_path).replace("'", "''")}'
while (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue) {{ Start-Sleep -Milliseconds 500 }}
if (Test-Path $extract) {{ Remove-Item $extract -Recurse -Force }}
New-Item -ItemType Directory -Force -Path $extract | Out-Null
Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
Copy-Item -Path (Join-Path $extract '*') -Destination $app -Recurse -Force
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Remove-Item $extract -Recurse -Force -ErrorAction SilentlyContinue
Start-Process -FilePath $exe
Remove-Item $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
"""
        script_path.write_text(script, encoding="utf-8")
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            close_fds=True,
        )
        os._exit(0)


updater_service = UpdaterService()
