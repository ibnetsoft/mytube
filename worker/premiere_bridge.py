"""Local CEP handoff for Premiere/Adobe Media Encoder exports."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from adobe_tools import find_premiere

SOURCE = Path(__file__).resolve().parent.parent / "adobe" / "cep" / "air-premiere-bridge"
BRIDGE_ROOT = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "AirStudio" / "premiere_bridge"
QUEUE = BRIDGE_ROOT / "queue"


class PremiereBridgeError(RuntimeError):
    pass


def installed_path() -> Path:
    roaming = Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming")
    return roaming / "Adobe" / "CEP" / "extensions" / "com.airstudio.premiere.bridge"


def install() -> Path:
    """Install only AIR Studio's user-scoped extension; leave other plugins alone."""
    if os.name != "nt":
        raise PremiereBridgeError("Premiere CEP bridge installation requires Windows")
    destination = installed_path()
    destination.mkdir(parents=True, exist_ok=True)
    for source in SOURCE.rglob("*"):
        if source.is_file():
            target = destination / source.relative_to(SOURCE)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    import winreg
    for version in ("12", "13", "14"):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Adobe\CSXS.{version}") as key:
            winreg.SetValueEx(key, "PlayerDebugMode", 0, winreg.REG_SZ, "1")
    return destination


def is_installed() -> bool:
    destination = installed_path()
    return (destination / "CSXS" / "manifest.xml").is_file() and (destination / "bridge.js").is_file()


def submit(script_path: Path, status_path: Path, project_id: str) -> Path:
    if not is_installed():
        raise PremiereBridgeError("Premiere bridge is not installed; run worker/premiere_bridge.py --install")
    QUEUE.mkdir(parents=True, exist_ok=True)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.unlink(missing_ok=True)
    job = {"project_id": project_id, "script_path": str(script_path.resolve()), "status_path": str(status_path.resolve())}
    name = f"{int(time.time())}-{uuid.uuid4().hex}.json"
    pending = QUEUE / (name + ".tmp")
    pending.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    target = QUEUE / name
    pending.replace(target)
    premiere = find_premiere()
    if not premiere or not premiere.is_file():
        target.unlink(missing_ok=True)
        raise PremiereBridgeError("Premiere Pro executable was not found")
    subprocess.Popen([str(premiere)], cwd=str(premiere.parent))
    return target


def wait(status_path: Path, output_path: Path, *, timeout_seconds: int = 3600) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if status_path.is_file():
            status = status_path.read_text(encoding="utf-8", errors="replace").strip()
            if status.startswith("error|"):
                raise PremiereBridgeError(status[6:])
            if status.startswith("complete|"):
                if output_path.is_file() and output_path.stat().st_size >= 1024:
                    return
                raise PremiereBridgeError("AME reported completion without a valid output file")
        time.sleep(1)
    raise PremiereBridgeError(f"Premiere/AME export timed out after {timeout_seconds}s; status={status_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    if args.install:
        print(install())
    else:
        print(json.dumps({"installed": is_installed(), "path": str(installed_path())}))
