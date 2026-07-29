"""
[AIR-0227E-P2-14] Local update / atomic-swap / rollback simulation for the
AIR Worker onedir install layout.

Adapts the exact pattern already proven in
packaging/windows/launcher/AIRUpdater.py (AIR Studio's own atomic-swap
updater, AIR-0215 hardened) rather than inventing a new one: rename the
live install dir to a backup name, rename the staged new version into its
place, and if the second rename fails, restore the backup. `os.rename()` on
the same NTFS volume is atomic, so at no point does a partially-swapped
directory exist under the live name - either the old or the new version is
there, never a half-copied mix.

This is a standalone simulation script (not wired into the real installer -
that integration is future work), run against a throwaway copy of an
AIRWorker onedir build so it never touches a real install:

    python _dev/simulate_worker_update.py --root <dir containing AIRWorker/> [--fail-swap]

`--fail-swap` deliberately corrupts the staged new version (deletes its
AIRWorker.exe) to exercise the rollback path instead of the happy path.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path


def _atomic_rename(src: Path, dst: Path) -> None:
    os.rename(src, dst)  # same-volume rename is atomic on NTFS


def _safe_rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def simulate(root: Path, fail_swap: bool) -> int:
    live = root / "AIRWorker"
    staged_new = root / "AIRWorker_new"
    backup = root / "AIRWorker_backup"

    if not live.exists():
        print(f"ERROR: expected an existing install at {live}")
        return 1

    print(f"[1/5] Staging 'new version' by copying {live} -> {staged_new}")
    _safe_rmtree(staged_new)
    shutil.copytree(live, staged_new)
    # Mark it so we can tell the two apart after the swap.
    (staged_new / "VERSION_MARKER.txt").write_text("staged-new-version\n", encoding="utf-8")

    if fail_swap:
        print("[FAULT INJECTION] Deleting staged AIRWorker.exe to force a failure mid-swap")
        (staged_new / "AIRWorker.exe").unlink(missing_ok=True)

    print(f"[2/5] Atomic swap: {live} -> {backup}")
    _safe_rmtree(backup)
    _atomic_rename(live, backup)

    try:
        print(f"[3/5] Atomic swap: {staged_new} -> {live}")
        if fail_swap:
            # Simulate a failure detected right after the rename would have
            # happened (e.g. a post-swap integrity check finding the exe
            # missing) - same recovery path AIRUpdater.py takes if promotion
            # of app_new fails.
            if not (staged_new / "AIRWorker.exe").exists():
                raise RuntimeError("staged new version is missing AIRWorker.exe - refusing to promote it")
            _atomic_rename(staged_new, live)
        else:
            _atomic_rename(staged_new, live)
    except Exception as e:
        print(f"[ROLLBACK] Swap failed ({e}) - restoring backup: {backup} -> {live}")
        if not live.exists() and backup.exists():
            _atomic_rename(backup, live)
        marker = live / "VERSION_MARKER.txt"
        print(f"[4/5] Post-rollback state: live install marker exists = {marker.exists()} (should be False - original had none)")
        print("[5/5] Result: ROLLED BACK to previous version, live install untouched in net effect")
        _safe_rmtree(staged_new)
        return 2

    print(f"[4/5] Removing old backup: {backup}")
    _safe_rmtree(backup)
    marker = live / "VERSION_MARKER.txt"
    print(f"[5/5] Result: SWAP SUCCEEDED - live install now the 'new version' (marker exists = {marker.exists()}, should be True)")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help="Directory containing an AIRWorker/ onedir install to experiment on (use a throwaway copy)")
    parser.add_argument("--fail-swap", action="store_true", help="Inject a failure to exercise the rollback path instead of the happy path")
    args = parser.parse_args()
    sys.exit(simulate(Path(args.root), args.fail_swap))
