"""Open the optional FilmCraft editor, inspect a native project, or render it to a new file."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def binary(editor=False):
    directory = ROOT / 'output/filmcraft' / (platform.system().lower() + '-' + platform.machine().lower())
    manifest = json.loads((directory / 'build-manifest.json').read_text(encoding='utf-8'))
    pin = json.loads((ROOT / 'tools/filmcraft/source.json').read_text(encoding='utf-8'))
    if any(manifest.get(key) != pin[key] for key in ('repository', 'revision', 'version')):
        raise ValueError('FilmCraft build does not match the pinned source; rebuild it')
    path = directory / (('filmcraft' if editor else 'filmcraft-cli') + ('.exe' if os.name == 'nt' else ''))
    if manifest.get('binaries', {}).get(path.name) != sha(path):
        raise ValueError('FilmCraft binary hash differs from its build receipt; rebuild it')
    return path, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    editor = commands.add_parser('editor')
    editor.add_argument('project', type=Path, nargs='?')
    inspect = commands.add_parser('inspect')
    inspect.add_argument('project', type=Path)
    render = commands.add_parser('render')
    render.add_argument('project', type=Path)
    render.add_argument('output', type=Path)
    render.add_argument('--gpu-rendering', choices=('auto', 'off'), default='auto')
    args = parser.parse_args()
    executable, manifest = binary(args.command == 'editor')
    project = args.project.resolve() if args.project else None
    if project and (not project.is_file() or project.suffix.lower() != '.fcproj'):
        parser.error('An existing native .fcproj project is required')
    if args.command == 'editor':
        # A visible editor is intentional: this subcommand is explicitly user-invoked.
        subprocess.Popen([str(executable), *([str(project)] if project else [])], cwd=executable.parent)
        return
    command = [str(executable), '--project', str(project), '--compact']
    if args.command == 'inspect':
        subprocess.run(command + ['inspect'], check=True)
        return
    output = args.output.resolve()
    if output.suffix.lower() != '.mp4':
        parser.error('This rendering option exports H.264/AAC MP4; choose an .mp4 output')
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path = output.with_suffix('.filmcraft.json')
    # Reserve both destinations before exporting, never overwrite another render or receipt.
    with output.open('xb'):
        pass
    try:
        with receipt_path.open('x', encoding='utf-8') as receipt:
            project_hash = sha(project)
            result = subprocess.run(command + ['export', str(output), '--format', 'h264',
                                               '--gpu-rendering', args.gpu_rendering],
                                    capture_output=True, text=True, encoding='utf-8', errors='replace')
            completed = result.returncode == 0 and output.is_file() and output.stat().st_size > 0
            record = {'engine': 'filmcraft', 'revision': manifest['revision'],
                      'project': str(project), 'project_sha256': project_hash,
                      'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
                      'review_status': 'rendered_requires_actual_review' if completed else 'failed'}
            if output.is_file() and output.stat().st_size:
                record['output_sha256'] = sha(output)
            json.dump(record, receipt, ensure_ascii=False, indent=2)
            if not completed:
                raise RuntimeError('FilmCraft export failed; see ' + str(receipt_path))
    except Exception:
        if output.is_file() and output.stat().st_size == 0:
            output.unlink()
        raise
    print(json.dumps({'output': str(output), 'receipt': str(receipt_path)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
