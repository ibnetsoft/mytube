import os
import sys
import subprocess
import requests
import zipfile
import threading
from packaging import version
from config import config
from version import APP_VERSION

class UpdaterService:
    def __init__(self):
        self.is_downloading = False
        self.download_progress = 0
        self.download_error = None

    def check_for_update(self):
        try:
            latest_version = getattr(config, "LATEST_APP_VERSION", None)
            latest_url = getattr(config, "LATEST_APP_URL", None)

            if not latest_version or not latest_url:
                return {"has_update": False, "error": "No update info on server"}

            if version.parse(latest_version) > version.parse(APP_VERSION):
                return {
                    "has_update": True,
                    "current_version": APP_VERSION,
                    "latest_version": latest_version,
                    "download_url": latest_url
                }
            return {"has_update": False, "current_version": APP_VERSION}
        except Exception as e:
            return {"has_update": False, "error": str(e)}

    def start_download(self, url: str):
        if self.is_downloading:
            return
        
        self.is_downloading = True
        self.download_progress = 0
        self.download_error = None

        thread = threading.Thread(target=self._download_worker, args=(url,), daemon=True)
        thread.start()

    def _download_worker(self, url: str):
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            block_size = 1024 * 8
            downloaded = 0
            
            temp_file = "MyTubeStudio_update.exe"
            with open(temp_file, 'wb') as f:
                for data in response.iter_content(block_size):
                    f.write(data)
                    downloaded += len(data)
                    if total_size > 0:
                        self.download_progress = int((downloaded / total_size) * 100)
            
            self.download_progress = 100
            self.is_downloading = False
        except Exception as e:
            self.download_error = str(e)
            self.is_downloading = False

    def apply_update_and_restart(self):
        if not os.path.exists("MyTubeStudio_update.exe"):
            return False

        # Create batch file to replace executable and restart
        # We use a ping command as a simple sleep to wait for current process to exit
        bat_content = """@echo off
echo Updating MyTubeStudio... Please wait.
ping 127.0.0.1 -n 3 > nul
del /f /q MyTubeStudio.exe
rename MyTubeStudio_update.exe MyTubeStudio.exe
start MyTubeStudio.exe
del "%~f0"
"""
        with open("apply_update.bat", "w") as f:
            f.write(bat_content)

        # Run the batch script detached from this process
        subprocess.Popen(
            "apply_update.bat",
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        
        # Exit current app
        os._exit(0)

updater_service = UpdaterService()
