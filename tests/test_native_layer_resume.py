import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PIL import Image
from worker.manga_layer_generation import NativeCodexLayerGenerator


def generate_stub(command, **kwargs):
    directory = Path(kwargs['cwd'])
    Image.new('RGB', (512, 512), 'white').save(directory / 'source.png')
    (directory / 'response.json').write_text(json.dumps({
        'status': 'ready', 'generator': 'builtin_image_gen', 'image_file': 'source.png',
    }))
    return SimpleNamespace(returncode=0, stdout='')


def test_restart_reuses_verified_same_request(tmp_path):
    reference = tmp_path / 'reference.png'
    Image.new('RGB', (32, 32)).save(reference)
    generator = NativeCodexLayerGenerator()
    with patch('worker.manga_layer_generation.subprocess.run', side_effect=generate_stub) as call:
        first = generator.generate(prompt='closed mouth', role='background', reference=reference, work_dir=tmp_path / 'generation')
        second = generator.generate(prompt='closed mouth', role='background', reference=reference, work_dir=tmp_path / 'generation')
    assert first == second
    assert call.call_count == 1


def test_changed_request_preserves_old_generation(tmp_path):
    legacy = tmp_path / 'generation'
    legacy.mkdir()
    (legacy / 'response.json').write_text('legacy attempt')
    generator = NativeCodexLayerGenerator()
    with patch('worker.manga_layer_generation.subprocess.run', side_effect=generate_stub):
        first = generator.generate(prompt='closed', role='background', reference=None, work_dir=legacy)
        second = generator.generate(prompt='open', role='background', reference=None, work_dir=legacy)
    assert first != second and first.exists() and second.exists()
    assert (legacy / 'response.json').read_text() == 'legacy attempt'


def test_tampered_cache_is_not_reused_or_silently_regenerated(tmp_path):
    generator = NativeCodexLayerGenerator()
    with patch('worker.manga_layer_generation.subprocess.run', side_effect=generate_stub) as call:
        source = generator.generate(prompt='closed', role='background', reference=None, work_dir=tmp_path)
        source.write_bytes(b'corrupt')
        with pytest.raises(FileExistsError):
            generator.generate(prompt='closed', role='background', reference=None, work_dir=tmp_path)
        assert call.call_count == 1
