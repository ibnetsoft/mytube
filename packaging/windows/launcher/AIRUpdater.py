import argparse
import json
import shutil
import subprocess
import time
import zipfile
from pathlib import Path


APP_EXE = "AIRStudio.exe"


def wait_for_app_to_exit(timeout_seconds: int = 30) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {APP_EXE}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if APP_EXE.lower() not in result.stdout.lower():
            return
        time.sleep(1)


def copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def find_app_payload(extract_dir: Path) -> Path:
    direct = extract_dir / "app"
    if direct.exists():
        return direct
    nested = list(extract_dir.glob("*/app"))
    if nested:
        return nested[0]
    return extract_dir


def update(root: Path, package: Path, version: str) -> None:
    wait_for_app_to_exit()
    extract_dir = package.parent / "extract"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(package, "r") as zf:
        zf.extractall(extract_dir)

    payload = find_app_payload(extract_dir)
    copy_tree(payload, root / "app")
    (root / "current.json").write_text(
        json.dumps({"version": version}, indent=2),
        encoding="utf-8",
    )


def launch(root: Path) -> None:
    exe = root / "app" / APP_EXE
    if exe.exists():
        subprocess.Popen([str(exe)], cwd=str(exe.parent), close_fds=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    package = Path(args.package).resolve()
    update(root, package, args.version)
    launch(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
