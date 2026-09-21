import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace


def test_gcs_manifest_downloads_config_and_assets_without_legacy_bucket_key(tmp_path):
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'remote_drive_worker.py').read_text(encoding='utf-8'))
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_prepare_gcs_manifest_job')
    namespace = {'os': os, 'json': json}
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<manifest>', 'exec'), namespace)
    seen = []
    def download(job_id, file_id, destination, *, storage_source, label):
        seen.append(storage_source)
        if label == 'config.json':
            Path(destination).write_text(json.dumps({'asset_manifest': {'files': [
                {'path': 'scene.png', 'gcs_bucket': 'media', 'gcs_path': 'scene.png'}
            ]}}), encoding='utf-8')
    worker = SimpleNamespace(update_job=lambda *a, **k: None, _download_asset_with_fallback=download, _safe_manifest_path=lambda p: p)
    namespace['_prepare_gcs_manifest_job'](worker, 'job', {'metadata': {'gcs_config': {'bucket': 'media', 'path': 'config.json'}}}, str(tmp_path), 'config')
    assert [s['gcs_path'] for s in seen] == ['config.json', 'scene.png']
