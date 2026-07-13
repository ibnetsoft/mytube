"""
[AIR-0227E] Builds AIRWorker.exe from packaging/windows/AIRWorker.spec.

Mirrors tools/build_windows.ps1's main-bundle invocation
(`PyInstaller --noconfirm --clean <spec>`) rather than reinventing a
--onefile/--hidden-import CLI call like the older _dev/build_remote_worker.py
did - AIRWorker's hidden-import/datas list is long enough (services/app
submodule collection, moviepy/PIL/pykakasi) that it belongs in the
declarative .spec file, not a growing list of CLI flags.
"""
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SPEC = os.path.join(ROOT, "packaging", "windows", "AIRWorker.spec")


def build():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", SPEC]
    print("Executing:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)
    print(f"\nBuild complete: dist{os.sep}AIRWorker.exe")


if __name__ == "__main__":
    build()
