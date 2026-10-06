"""Build a source-only worker archive without credentials or project assets."""
from pathlib import Path
import argparse
import zipfile
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {'.py', '.js', '.html', '.css', '.txt'}

def files(root=ROOT):
    for directory in ['worker', 'services', 'utils']:
        base = root / directory
        if not base.exists():
            continue
        for path in sorted(base.rglob('*')):
            excluded = {'__pycache__', 'node_modules', '.venv', 'fixture', 'output', 'config', 'cache', 'logs', 'state'}
            if not path.is_file() or excluded.intersection(path.relative_to(base).parts):
                continue
            if path.suffix in ALLOWED:
                yield path
    for name in ['config.py', 'db.py', 'database.py', 'remote_drive_worker.py',
                 'worker/connection.env.example', 'docs/리페어프로세스.md',
                 'docs/신규생성프로세스.md', 'docs/worker-installation.md',
                 'scripts/install_script_worker.ps1', 'worker/codex_console/modern_japan_watercolor.json']:
        path = root / name
        if path.is_file():
            yield path

def build(target, root=ROOT):
    target.parent.mkdir(parents=True, exist_ok=True)
    paths = sorted(set(files(root)))
    manifest = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path in paths:
            bundle.write(path, path.relative_to(root).as_posix())
        bundle.writestr('bundle-manifest.json', json.dumps({'role': 'script', 'files': manifest}, indent=2))
    return len(paths)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(ROOT / 'output/worker-distribution/AIR-script-worker.zip'))
    args = parser.parse_args()
    target = Path(args.output).resolve()
    print(f'Created {target}: {build(target)} source files; no environment or user asset files')
