"""Pinned FilmCraft exports for the web's isolated FilmCraft submission queue.

Original sources, editable keys, native captions and audio are placed directly on
FilmCraft timelines. Actual GPU composition counts are required for success.
PSD rigs require an explicitly prepared video, never a fallback to another engine.
"""
from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path
from scripts.filmcraft import sha

ROOT = Path(__file__).resolve().parents[1]
PIN = json.loads((ROOT/'auth-web/lib/filmcraftSource.json').read_text(encoding='utf-8'))
CONTRACT = json.loads((ROOT/'auth-web/lib/filmcraftNativeContract.json').read_text(encoding='utf-8'))
VERSION = CONTRACT['adapter']
TICKS = 254016000000


def binary():
    from scripts.filmcraft import binary as installed
    path, manifest = installed()
    if manifest['revision'] != PIN['revision'] or manifest.get('gpu_receipt_patch_sha256') != sha(ROOT/'tools/filmcraft/gpu-receipt.patch'):
        raise ValueError('FilmCraft web/worker source revisions differ; rebuild the selected engine')
    return path


def execute(cli, arguments, directory, stage):
    directory = Path(directory).resolve()
    env = {k:v for k,v in os.environ.items() if k != 'AIR_WORKER_ENV_FILE' and not any(
        s in k.upper() for s in ('TOKEN','SECRET','PASSWORD','API_KEY','CREDENTIAL','SUPABASE','GOOGLE','OPENAI','GEMINI','ANTHROPIC'))}
    with (directory/(stage+'.stdout.json')).open('w', encoding='utf-8') as out, (directory/(stage+'.stderr.log')).open('w', encoding='utf-8') as err:
        result = subprocess.run([str(cli),'--data-dir',str(directory/'engine-config'),'--compact',*map(str,arguments)],
            cwd=directory,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,timeout=3600,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        raise ValueError('FilmCraft '+stage+' failed; source, project and diagnostic logs were preserved')
    raw=(directory/(stage+'.stdout.json')).read_text(encoding='utf-8')
    try:response=json.loads(raw)
    except json.JSONDecodeError:response=[json.loads(line) for line in raw.splitlines() if line.strip()]
    rows=response if isinstance(response,list) else [response]
    if any(isinstance(row,dict) and (row.get('error') or row.get('ok') is False) for row in rows):
        raise ValueError('FilmCraft command rejected: '+stage)
    return response



def render_scene(*args, **kwargs):
    from filmcraft_native import render_scene as render
    return render(*args, **kwargs)


def render_master(*args, **kwargs):
    from filmcraft_native import render_master as render
    return render(*args, **kwargs)
