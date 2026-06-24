import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


APP_EXE = "AIRStudio.exe"
CONFIG_FILE = "update_config.json"
VERSION_FILE = "current.json"


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent
    return Path(__file__).resolve().parents[3]


def launcher_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def version_tuple(value: str) -> tuple:
    parts = []
    for piece in str(value or "0").replace("v", "").split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def current_version(root: Path) -> str:
    data = read_json(root / VERSION_FILE)
    return str(data.get("version") or "0.0.0")


def manifest_url() -> str:
    env_url = os.environ.get("AIR_UPDATE_MANIFEST_URL", "").strip()
    if env_url:
        return env_url
    data = read_json(launcher_dir() / CONFIG_FILE)
    return str(data.get("manifest_url") or "").strip()


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def download_file(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=120) as response:
        with dest.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def check_for_update(root: Path) -> None:
    url = manifest_url()
    if not url:
        return

    try:
        manifest = fetch_json(url)
        latest = str(manifest.get("version") or "")
        package_url = str(manifest.get("portable_url") or "")
        expected_hash = str(manifest.get("sha256") or "").lower()
        if not latest or not package_url:
            return
        if version_tuple(latest) <= version_tuple(current_version(root)):
            return

        temp_dir = Path(tempfile.mkdtemp(prefix="air_update_"))
        package_path = temp_dir / f"AIRStudio-{latest}.zip"
        download_file(package_url, package_path)
        if expected_hash and sha256(package_path) != expected_hash:
            return

        updater = launcher_dir() / "AIRUpdater.exe"
        if not updater.exists():
            return
        subprocess.Popen([
            str(updater),
            "--root", str(root),
            "--package", str(package_path),
            "--version", latest,
        ], close_fds=True)
        sys.exit(0)
    except Exception:
        return


def launch_app(root: Path) -> int:
    exe = root / "app" / APP_EXE
    if not exe.exists():
        raise FileNotFoundError(f"Application executable not found: {exe}")
    return subprocess.Popen([str(exe)], cwd=str(exe.parent), close_fds=True).pid


def main() -> int:
    root = app_root()
    check_for_update(root)
    launch_app(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
