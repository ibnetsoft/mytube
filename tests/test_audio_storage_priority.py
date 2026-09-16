import ast
from pathlib import Path
from types import SimpleNamespace


def test_storage_audio_never_attempts_drive():
    source = Path('remote_drive_worker.py').read_text(encoding='utf-8-sig')
    tree = ast.parse(source)
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_download_asset_with_fallback')
    namespace = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<audio-worker>', 'exec'), namespace)
    calls = []
    worker = SimpleNamespace(_download_from_supabase_storage=lambda source, path: calls.append((source, path)) or True)
    result = namespace[method.name](worker, 'job', None, 'audio.mp3', storage_source={'bucket': 'content-assets', 'path': 'voice.mp3'}, label='voice')
    assert result == 'supabase_storage'
    assert len(calls) == 1


def test_storage_failure_without_drive_reports_failure():
    import pytest
    source = Path('remote_drive_worker.py').read_text(encoding='utf-8-sig')
    method = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == '_download_asset_with_fallback')
    namespace = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<audio-worker>', 'exec'), namespace)
    worker = SimpleNamespace(_download_from_supabase_storage=lambda *args: False)
    with pytest.raises(RuntimeError, match='Supabase'):
        namespace[method.name](worker, 'job', None, 'audio.mp3', storage_source={'bucket': 'b', 'path': 'p'}, label='voice')
