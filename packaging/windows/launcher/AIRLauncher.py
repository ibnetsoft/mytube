"""
AIRLauncher.py — AIR Studio launcher with update check (AIR-0215 hardened).

Boot sequence:
  1. Set up logging → %APPDATA%/AIRStudio/logs/launcher.log
  2. Auto-recover: if app/ absent and app_backup/ present, restore app_backup/ → app/
  3. Clean up leftover update artefacts (app_new/, extract/; app_backup/ only if app/ exists)
  4. Read local version: current.json → app/version.json → exe VersionInfo → 0.0.0
  5. Fetch remote manifest; if newer version available:
       a. [EVENT] download_started
       b. Download ZIP to temp dir
       c. [EVENT] download_completed
       d. Verify SHA256
       e. [EVENT] sha256_verified
       f. Spawn AIRUpdater.exe with --sha256 and --build args, then exit
  6. If no update (or update check fails), launch app/AIRStudio.exe
"""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


APP_EXE = "AIRStudio.exe"
CONFIG_FILE = "update_config.json"
VERSION_FILE = "current.json"
VERSION_FILE_APP = "version.json"   # embedded inside app/ by build script


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logging() -> logging.Logger:
    log_dir = Path(os.environ.get("APPDATA", "~")).expanduser() / "AIRStudio" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "launcher.log"

    logger = logging.getLogger("AIRLauncher")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(fh)

        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(sh)

    return logger


log = _setup_logging()


def _event(name: str, **kwargs) -> None:
    """Write a structured [EVENT] marker — machine-parseable for monitoring."""
    extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
    log.info("[EVENT] %s%s", name, f" {extra}" if extra else "")


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent
    return Path(__file__).resolve().parents[3]


def launcher_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

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


def _exe_version(exe_path: Path) -> str:
    """
    Read FileVersion from a Windows PE executable via PowerShell.
    Returns empty string if unavailable or on non-Windows platforms.
    Normalises "2.0.0.0" (4-part) → "2.0.0" (3-part).
    """
    if not exe_path.exists():
        return ""
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile", "-NonInteractive", "-Command",
                f"(Get-Item '{exe_path}').VersionInfo.FileVersion",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        raw = result.stdout.strip()
        if not raw:
            return ""
        # Normalise: "2.0.0.0" or "2, 0, 0, 0" → "2.0.0"
        parts = raw.replace(",", ".").split(".")
        normalized = ".".join(p.strip() for p in parts[:3] if p.strip().isdigit())
        return normalized
    except Exception:
        return ""


def current_version(root: Path) -> str:
    """
    Read local installed version.
    Priority:
      1. root/current.json          → version field
      2. root/app/version.json      → version field
      3. root/app/AIRStudio.exe     → PE FileVersion resource
      4. "0.0.0"
    """
    ver = str(read_json(root / VERSION_FILE).get("version") or "").strip()
    if ver:
        log.debug("Version from current.json: %s", ver)
        return ver

    ver = str(read_json(root / "app" / VERSION_FILE_APP).get("version") or "").strip()
    if ver:
        log.debug("Version from app/version.json: %s", ver)
        return ver

    ver = _exe_version(root / "app" / APP_EXE)
    if ver:
        log.debug("Version from exe VersionInfo: %s", ver)
        return ver

    log.debug("Version unknown — defaulting to 0.0.0")
    return "0.0.0"


def manifest_url() -> str:
    env_url = os.environ.get("AIR_UPDATE_MANIFEST_URL", "").strip()
    if env_url:
        return env_url
    data = read_json(launcher_dir() / CONFIG_FILE)
    return str(data.get("manifest_url") or "").strip()


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Startup recovery
# ---------------------------------------------------------------------------

def _recover_app_if_needed(root: Path) -> None:
    """
    If app/ is absent but app_backup/ exists, restore the backup.

    This handles the rare case where AIRUpdater's own rollback succeeded
    (renamed app_backup/ back to app/) but the machine rebooted or the
    process was killed before the launcher was aware of it — leaving
    app_backup/ as the only valid copy of the app.
    """
    app_dir = root / "app"
    app_backup = root / "app_backup"
    if not app_dir.exists() and app_backup.exists():
        log.warning(
            "app/ is missing but app_backup/ found — recovering from backup."
        )
        try:
            os.rename(app_backup, app_dir)
            log.info("Recovery successful: app_backup/ restored as app/.")
        except Exception as exc:
            log.critical(
                "Recovery FAILED: %s. Manual intervention required: "
                "rename '%s' to '%s' manually.",
                exc, app_backup, app_dir,
            )


def cleanup_update_artifacts(root: Path) -> None:
    """
    Remove leftover directories from a previous failed/interrupted update.
    Safe to call on every startup — only removes known update temp dirs.

    app_backup/ is only removed if app/ exists, to avoid destroying the
    only remaining copy of the application.
    """
    # app_new and extract are always safe to remove
    for name in ("app_new", "extract"):
        candidate = root / name
        if candidate.exists():
            log.info("Cleaning leftover update artefact: %s", candidate)
            try:
                shutil.rmtree(candidate)
            except Exception as exc:
                log.warning("Could not remove %s: %s", candidate, exc)

    # Remove app_backup only when the live app/ exists
    app_backup = root / "app_backup"
    if app_backup.exists() and (root / "app").exists():
        log.info("Cleaning stale app_backup/...")
        try:
            shutil.rmtree(app_backup)
        except Exception as exc:
            log.warning("Could not remove app_backup: %s", exc)


# ---------------------------------------------------------------------------
# Update check
# ---------------------------------------------------------------------------

def check_for_update(root: Path) -> bool:
    """
    Check GitHub Releases manifest for a newer version.
    Returns True if an update was found, downloaded, verified, and the
    updater was spawned (caller should then exit).
    Returns False in all other cases (no update, unreachable, hash mismatch, etc.).
    """
    url = manifest_url()
    if not url:
        log.info("No manifest URL configured — skipping update check.")
        return False

    _event("update_check_started")
    local_ver = current_version(root)
    log.info("Local version : %s", local_ver)
    log.info("Fetching manifest from %s", url)

    try:
        manifest = fetch_json(url)
        latest = str(manifest.get("version") or "").strip()
        package_url = str(manifest.get("portable_url") or "").strip()
        expected_hash = str(manifest.get("sha256") or "").lower().strip()
        build = int(manifest.get("build") or 0)

        if not latest or not package_url:
            log.warning("Manifest missing version or portable_url — skipping.")
            return False

        log.info("Remote version: %s (build %s)", latest, build)

        if version_tuple(latest) <= version_tuple(local_ver):
            log.info("Already up to date.")
            return False

        log.info("Update available: %s → %s", local_ver, latest)

        # Download
        _event("download_started", version=latest, url=package_url)
        log.info("Downloading %s ...", package_url)
        temp_dir = Path(tempfile.mkdtemp(prefix="air_update_"))
        package_path = temp_dir / f"AIRStudio-{latest}.zip"
        download_file(package_url, package_path)
        file_bytes = package_path.stat().st_size
        _event("download_completed", bytes=file_bytes, file=package_path.name)
        log.info("Download complete: %s (%d bytes)", package_path.name, file_bytes)

        # SHA256 — verify before spawning updater
        if expected_hash:
            actual_hash = sha256(package_path)
            if actual_hash != expected_hash:
                log.error(
                    "SHA256 mismatch — expected %s, got %s. Aborting update.",
                    expected_hash, actual_hash,
                )
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
                return False
            _event("sha256_verified", hash=actual_hash[:16] + "...")
            log.info("SHA256 verified OK.")
        else:
            log.warning("No SHA256 in manifest — skipping hash verification.")

        updater = launcher_dir() / "AIRUpdater.exe"
        if not updater.exists():
            log.error("AIRUpdater.exe not found at %s — cannot apply update.", updater)
            return False

        log.info("Spawning updater: %s", updater)
        subprocess.Popen(
            [
                str(updater),
                "--root",    str(root),
                "--package", str(package_path),
                "--version", latest,
                "--sha256",  expected_hash,  # updater re-verifies independently
                "--build",   str(build),
            ],
            close_fds=True,
        )
        return True

    except Exception as exc:
        log.warning("Update check failed (%s) — continuing with existing app.", exc)
        return False


# ---------------------------------------------------------------------------
# App launch
# ---------------------------------------------------------------------------

def launch_app(root: Path) -> int:
    exe = root / "app" / APP_EXE
    if not exe.exists():
        raise FileNotFoundError(f"Application executable not found: {exe}")
    log.info("Launching %s", exe)
    return subprocess.Popen([str(exe)], cwd=str(exe.parent), close_fds=True).pid


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    log.info("=== AIRLauncher starting ===")
    root = app_root()
    log.info("App root: %s", root)

    # 1. Recover app/ from app_backup/ if needed (must run before cleanup)
    _recover_app_if_needed(root)

    # 2. Remove stale update artefacts (app_new/, extract/; app_backup/ if safe)
    cleanup_update_artifacts(root)

    # 3. Check for update — spawns AIRUpdater and exits if update is available
    if check_for_update(root):
        log.info("Updater spawned — exiting launcher.")
        return 0

    # 4. No update: launch existing app
    try:
        pid = launch_app(root)
        log.info("App launched (pid=%d).", pid)
        return 0
    except FileNotFoundError as exc:
        log.critical("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
