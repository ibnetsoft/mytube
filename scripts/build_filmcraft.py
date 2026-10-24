"""Build the optional FilmCraft editor and headless renderer independently of AIR workers."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN = json.loads((ROOT / 'tools/filmcraft/source.json').read_text(encoding='utf-8'))
GPU_PATCH = ROOT / 'tools/filmcraft/gpu-receipt.patch'


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--source', type=Path, default=ROOT / '.codex-temp/filmcraft-src')
    args = parser.parse_args()
    source = args.source.resolve()

    def run(command, **kwargs):
        return subprocess.run(command, check=True, **kwargs)

    def git(*args):
        return subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()

    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        run(['git', 'clone', '--no-checkout', PIN['repository'], str(source)])
        run(['git', '-C', str(source), 'checkout', '--detach', PIN['revision']])
    expected_patch = GPU_PATCH.read_text(encoding='utf-8').strip()
    def patched_source():
        return git('diff', '--binary') == expected_patch and not git('ls-files', '--others', '--exclude-standard')
    if git('status', '--porcelain') and not patched_source():
        raise RuntimeError('FilmCraft source has local changes; preserve them before building')
    if git('rev-parse', 'HEAD') != PIN['revision']:
        run(['git', '-C', str(source), 'fetch', '--depth', '1', 'origin', PIN['revision']])
        run(['git', '-C', str(source), 'checkout', '--detach', PIN['revision']])
    if not git('status', '--porcelain'):
        run(['git', '-C', str(source), 'apply', str(GPU_PATCH)])
    if not patched_source():
        raise RuntimeError('Source must match exactly the maintained GPU receipt patch')
    env = os.environ.copy()
    cargo = shutil.which('cargo')
    if not cargo:
        cargo = str(ROOT / '.codex-temp/cargo/bin' / ('cargo.exe' if os.name == 'nt' else 'cargo'))
        if not Path(cargo).is_file():
            raise RuntimeError('Rust 1.95 or later is required to build FilmCraft')
        env.setdefault('CARGO_HOME', str(ROOT / '.codex-temp/cargo'))
        env.setdefault('RUSTUP_HOME', str(ROOT / '.codex-temp/rustup'))
    run([cargo, 'build', '--release', '--locked', '-p', 'filmcraft-cli', '-p', 'filmcraft',
         '--jobs', str(max(1, min(8, args.jobs)))], cwd=source, env=env)
    if not patched_source():
        raise RuntimeError('Build changed upstream source; inspect before packaging')
    target = ROOT / 'output/filmcraft' / (platform.system().lower() + '-' + platform.machine().lower())
    target.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name in ('filmcraft-cli', 'filmcraft'):
        filename = name + ('.exe' if os.name == 'nt' else '')
        built = source / 'target/release' / filename
        if not built.is_file():
            raise RuntimeError('Build artifact missing: ' + str(built))
        if not (target / filename).is_file() or sha(built) != sha(target / filename):
            shutil.copy2(built, target / filename)
        hashes[filename] = sha(target / filename)
    for name in ('LICENSE-MIT', 'LICENSE-APACHE', 'NOTICE', 'ATTRIBUTION.md'):
        shutil.copy2(source / name, target / name)
    for parent in ('assets', 'docs/brand'):
        for file in (source / parent).rglob('*'):
            if file.is_file() and (file.name.startswith(('OFL', 'LICENSE')) or file.suffix == '.attribution'):
                destination = target / file.relative_to(source)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, destination)
    manifest = {**PIN, 'platform': platform.system(), 'architecture': platform.machine(),
                'binaries': hashes, 'gpu_receipt_patch_sha256': sha(GPU_PATCH),
                'render_validation': 'not_run'}
    (target / 'build-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'directory': str(target), 'manifest': manifest}), flush=True)


if __name__ == '__main__':
    main()
