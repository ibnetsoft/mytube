"""
[AIR-0227E / AIR-0227E-P2] Builds AIRWorker from
packaging/windows/AIRWorker.spec (onefile) or
packaging/windows/AIRWorker_onedir.spec (`--onedir`).

[P2 §1 build isolation] onefile and onedir use separate --distpath/--workpath
(dist/onefile + build/onefile vs dist/onedir + build/onedir) so neither
build's PyInstaller cache or output can contaminate the other - both specs
use name="AIRWorker" internally, which would otherwise collide in a shared
build/AIRWorker/ work directory.

Mirrors tools/build_windows.ps1's main-bundle invocation
(`PyInstaller --noconfirm --clean <spec>`) rather than reinventing a
--onefile/--hidden-import CLI call like the older _dev/build_remote_worker.py
did - AIRWorker's hidden-import/datas list is long enough (services/app
submodule collection, moviepy/PIL/pykakasi) that it belongs in the
declarative .spec file, not a growing list of CLI flags.
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SPEC_ONEFILE = os.path.join(ROOT, "packaging", "windows", "AIRWorker.spec")
SPEC_ONEDIR = os.path.join(ROOT, "packaging", "windows", "AIRWorker_onedir.spec")


def build(onedir: bool = False):
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    variant = "onedir" if onedir else "onefile"
    spec = SPEC_ONEDIR if onedir else SPEC_ONEFILE
    distpath = os.path.join(ROOT, "dist", variant)
    workpath = os.path.join(ROOT, "build", variant)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--distpath", distpath,
        "--workpath", workpath,
        spec,
    ]
    print("Executing:", " ".join(cmd))
    t0 = time.time()
    result = subprocess.run(cmd, cwd=ROOT)
    elapsed = time.time() - t0

    record = {
        "variant": variant,
        "command": cmd,
        "exit_code": result.returncode,
        "elapsed_seconds": round(elapsed, 1),
        "distpath": distpath,
        "workpath": workpath,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    record_path = os.path.join(ROOT, "dist", f"build_record_{variant}.json")
    os.makedirs(os.path.dirname(record_path), exist_ok=True)
    with open(record_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    print(f"\nBuild ({variant}) exit_code={result.returncode} elapsed={elapsed:.1f}s")
    if onedir:
        print(f"Output: {distpath}{os.sep}AIRWorker{os.sep}AIRWorker.exe")
    else:
        print(f"Output: {distpath}{os.sep}AIRWorker.exe")
    print(f"Build record: {record_path}")
    return result.returncode


if __name__ == "__main__":
    sys.exit(build(onedir="--onedir" in sys.argv))
