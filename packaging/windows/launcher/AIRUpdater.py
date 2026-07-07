"""
AIRUpdater.py — AIR Studio atomic-swap updater (AIR-0215 hardened).

Invoked by AIRLauncher after it downloads a new release ZIP and spawns this
process.  Applies the update using an atomic-swap strategy so the existing
app/ directory is never left in a partially-written state.

Swap sequence:
  0. Clean leftover artefacts from any prior failed update
  1. SHA256 re-verify downloaded ZIP (abort immediately on mismatch)
  2. Extract ZIP → <root>/app_new/
  3. Guard: AIRLauncher.exe must not be in payload; payload must not be Launcher/
  4. Rename app/     → app_backup/   (old app safely parked; atomic NTFS)
  5. Rename app_new/ → app/          (new app goes live;    atomic NTFS)
  6. Write current.json + app/version.json (full schema: version, installed_at, build)
  7. Remove app_backup/ (cleanup)
  8. Launch app/AIRStudio.exe

On any failure between steps 4–5 the old app is restored from app_backup/.
"""

import argparse
import datetime
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path


APP_EXE = "AIRStudio.exe"
LAUNCHER_EXE = "AIRLauncher.exe"


# ---------------------------------------------------------------------------
# Logging — writes to %APPDATA%\AIRStudio\logs\updater.log
# ---------------------------------------------------------------------------

def _setup_logging() -> logging.Logger:
    log_dir = Path(os.environ.get("APPDATA", "~")).expanduser() / "AIRStudio" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "updater.log"

    logger = logging.getLogger("AIRUpdater")
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
# SHA256
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    """Return lowercase hex SHA256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def wait_for_app_to_exit(timeout_seconds: int = 30) -> None:
    """Poll tasklist until AIRStudio.exe is no longer running."""
    log.info("Waiting for %s to exit (timeout %ds)...", APP_EXE, timeout_seconds)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {APP_EXE}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if APP_EXE.lower() not in result.stdout.lower():
            log.info("%s has exited.", APP_EXE)
            return
        time.sleep(1)
    log.warning("Timed out waiting for %s to exit — proceeding anyway.", APP_EXE)


def find_app_payload(extract_dir: Path) -> Path:
    """Return the app/ subdirectory inside an extracted ZIP, or extract_dir itself."""
    direct = extract_dir / "app"
    if direct.exists():
        return direct
    nested = list(extract_dir.glob("*/app"))
    if nested:
        return nested[0]
    return extract_dir


def _safe_rmtree(path: Path) -> None:
    """Remove a directory tree, logging but not raising on failure."""
    try:
        if path.exists():
            shutil.rmtree(path)
            log.debug("Removed %s", path)
    except Exception as exc:
        log.warning("Could not remove %s: %s", path, exc)


def _atomic_rename(src: Path, dst: Path) -> None:
    """
    Rename src → dst atomically (NTFS MoveFileEx within same volume).
    dst must NOT already exist before calling this.
    """
    if dst.exists():
        raise FileExistsError(f"Destination already exists: {dst}")
    os.rename(src, dst)
    log.debug("Renamed %s → %s", src, dst)


# ---------------------------------------------------------------------------
# Launcher guard
# ---------------------------------------------------------------------------

def _guard_launcher_not_overwritten(app_new: Path, root: Path) -> None:
    """
    Ensure the update payload cannot overwrite Launcher/ or AIRLauncher.exe.

    Rule: Launcher/ at install root is immutable between installer versions.
    Only a new installer .exe replaces it.  The app-payload swap touches
    only install_root/app/ — never install_root/Launcher/.

    Raises ValueError if the payload path is inside Launcher/.
    Removes AIRLauncher.exe from the payload root if present (defensive).
    """
    launcher_dir = (root / "Launcher").resolve()
    app_new_resolved = app_new.resolve()

    # Guard 1: payload must not be inside or equal to Launcher/
    try:
        app_new_resolved.relative_to(launcher_dir)
        raise ValueError(
            f"[GUARD] Payload path '{app_new}' is inside the protected Launcher/ "
            "directory. Only the app/ payload may be updated via this mechanism."
        )
    except ValueError as exc:
        if "[GUARD]" in str(exc):
            raise  # our own guard triggered
        # relative_to raises ValueError when NOT a subpath — this is the safe case

    # Guard 2: remove AIRLauncher.exe from payload root if present
    launcher_in_payload = app_new / LAUNCHER_EXE
    if launcher_in_payload.exists():
        log.warning(
            "[GUARD] %s found in app payload root — removing it. "
            "Launcher/ is never updated by payload swap.",
            LAUNCHER_EXE,
        )
        try:
            launcher_in_payload.unlink()
            log.info("[GUARD] %s removed from payload.", LAUNCHER_EXE)
        except Exception as exc:
            # Fail hard: if we can't remove it, we can't guarantee safety
            log.error("[GUARD] Failed to remove %s from payload: %s. Aborting.", LAUNCHER_EXE, exc)
            raise ValueError(
                f"{LAUNCHER_EXE} in payload could not be removed: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Version record schema
# ---------------------------------------------------------------------------

def _version_record(version: str, build: int) -> dict:
    """Return the canonical version record dict."""
    return {
        "version": version,
        "installed_at": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "build": build,
    }


# ---------------------------------------------------------------------------
# Core update with atomic swap
# ---------------------------------------------------------------------------

def update(root: Path, package: Path, version: str,
           expected_hash: str = "", build: int = 0) -> None:
    """
    Apply the downloaded release ZIP to root using an atomic swap.

    Parameters
    ----------
    root          Install root directory.
    package       Path to the downloaded ZIP.
    version       New version string (e.g. "1.2.3").
    expected_hash Lowercase hex SHA256 of the ZIP.  Empty = skip verification.
    build         Build/task ID (e.g. 215). Written to current.json and version.json.
    """
    _event("update_check_started", version=version, build=build)
    log.info("=== AIRUpdater starting — version: %s, build: %s ===", version, build)
    log.info("Root:    %s", root)
    log.info("Package: %s", package)

    if not package.exists():
        raise FileNotFoundError(f"Package not found: {package}")

    # --- SHA256 verification (before any extraction) ---
    if expected_hash:
        log.info("Verifying SHA256...")
        actual_hash = sha256_file(package)
        if actual_hash != expected_hash:
            log.error(
                "SHA256 mismatch — expected %s, got %s. Aborting update.",
                expected_hash, actual_hash,
            )
            # Clean up the corrupt/tampered package
            try:
                package.unlink()
                _safe_rmtree(package.parent)
            except Exception:
                pass
            raise ValueError(
                f"SHA256 mismatch: expected {expected_hash}, got {actual_hash}. "
                "Update aborted — no changes made."
            )
        _event("sha256_verified", hash=actual_hash[:16] + "...")
        log.info("SHA256 verified OK.")
    else:
        log.warning("No expected_hash provided — SHA256 verification skipped.")

    wait_for_app_to_exit()

    app_dir = root / "app"
    app_new = root / "app_new"
    app_backup = root / "app_backup"

    # --- Step 0: clean up leftover artefacts from a prior failed update ---
    log.info("Cleaning up any leftover update artefacts...")
    _safe_rmtree(app_new)
    _safe_rmtree(app_backup)

    # --- Step 1: extract ZIP → app_new/ ---
    _event("download_completed", package=package.name,
           bytes=package.stat().st_size)
    log.info("Extracting %s → %s", package.name, app_new)
    app_new.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package, "r") as zf:
        zf.extractall(app_new)
    _event("extract_completed", dest=str(app_new))
    log.info("Extraction complete.")

    # --- Step 2: find the app payload inside the ZIP ---
    payload = find_app_payload(app_new)
    log.info("Payload directory: %s", payload)
    if not (payload / APP_EXE).exists():
        _safe_rmtree(app_new)
        raise FileNotFoundError(
            f"{APP_EXE} not found in payload: {payload}. "
            "The ZIP may be malformed or for a different platform."
        )

    # If app_new wraps a subdirectory, promote the inner dir to app_new level
    if payload != app_new:
        promoted = root / "_app_new_promoted"
        _safe_rmtree(promoted)
        os.rename(payload, promoted)
        _safe_rmtree(app_new)
        os.rename(promoted, app_new)
        log.debug("Promoted payload to %s", app_new)

    # --- Step 3: Launcher guard ---
    _guard_launcher_not_overwritten(app_new, root)

    # --- Step 4 & 5: atomic swap ---
    #   app/     → app_backup/    (park old version)
    #   app_new/ → app/           (install new version)
    log.info("Performing atomic swap...")
    try:
        if app_dir.exists():
            _atomic_rename(app_dir, app_backup)
        _atomic_rename(app_new, app_dir)
    except Exception as exc:
        log.error("Atomic swap failed: %s — attempting rollback.", exc)
        _event("rollback_executed", reason=str(exc))
        # Rollback: restore app_backup → app if app/ is missing
        if not app_dir.exists() and app_backup.exists():
            try:
                _atomic_rename(app_backup, app_dir)
                log.info("Rollback successful — old app restored.")
            except Exception as rb_exc:
                log.critical("Rollback FAILED: %s. Manual recovery required.", rb_exc)
        raise

    _event("swap_completed", version=version)
    log.info("Swap complete. New app is live at %s", app_dir)

    # --- Step 6: write full version record ---
    record = _version_record(version, build)
    record_json = json.dumps(record, indent=2)
    (root / "current.json").write_text(record_json, encoding="utf-8")
    (app_dir / "version.json").write_text(record_json, encoding="utf-8")
    log.info("Version record written: version=%s installed_at=%s build=%s",
             record["version"], record["installed_at"], record["build"])

    # --- Step 7: cleanup backup and temp package ---
    log.info("Removing app_backup and temp package...")
    _safe_rmtree(app_backup)
    try:
        package.unlink()
        _safe_rmtree(package.parent)
    except Exception as exc:
        log.warning("Could not clean temp package: %s", exc)

    log.info("=== Update applied successfully ===")


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------

def launch(root: Path) -> None:
    exe = root / "app" / APP_EXE
    if exe.exists():
        log.info("Launching %s", exe)
        subprocess.Popen([str(exe)], cwd=str(exe.parent), close_fds=True)
        _event("app_launched", exe=APP_EXE)
    else:
        log.error("Cannot launch: %s not found after update.", exe)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="AIR Studio atomic updater")
    parser.add_argument("--root",    required=True,  help="Install root directory")
    parser.add_argument("--package", required=True,  help="Path to downloaded ZIP")
    parser.add_argument("--version", required=True,  help="New version string")
    parser.add_argument("--sha256",  default="",     help="Expected SHA256 hex digest of ZIP")
    parser.add_argument("--build",   default=0, type=int, help="Build/task ID (e.g. 215)")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    package = Path(args.package).resolve()

    try:
        update(root, package, args.version,
               expected_hash=args.sha256.lower().strip(),
               build=args.build)
        launch(root)
        return 0
    except Exception as exc:
        log.critical("Update failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
