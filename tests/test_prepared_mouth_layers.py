import copy
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'worker'))
import ae_mouth
import prepared_mouth_layers as prepared


def test_reviewed_patches_reused_only_for_identical_source_and_geometry(tmp_path, monkeypatch):
    monkeypatch.setattr(prepared, 'ROOT', tmp_path / 'cache')
    image = tmp_path / 'source.png'
    image.write_bytes(b'original')
    from test_mouth_geometry import speaker as verified_speaker
    speaker = verified_speaker(); speaker['speaker'] = 'Mother'
    speaker['mouth_geometry']['source_sha256'] = ae_mouth.digest(image)
    geometry = {'state': 'ready', 'source_sha256': ae_mouth.digest(image), 'speakers': [speaker]}
    calls = []
    def generate(generator, image, row, directory):
        calls.append('generate')
        directory.mkdir(parents=True, exist_ok=True)
        row['mouth_box'] = [.33, .42, .47, .52]
        row['coverage_version'] = 2
        paths = {}
        for pose in ae_mouth.POSES:
            path = directory / (pose + '.png')
            path.write_bytes(pose.encode())
            paths[pose] = str(path)
        return paths
    monkeypatch.setattr(ae_mouth, 'mouth_layers', generate)
    monkeypatch.setattr(ae_mouth, 'review_layers', lambda *args: calls.append('review'))
    prepared.prepare_scene(image, geometry, runner=object(), generator=object())
    prepared.prepare_scene(image, geometry, runner=object(), generator=object())
    assert calls == ['generate', 'review']
    assert speaker['mouth_box'] == [.35, .44, .45, .5]  # Stored geometry is untouched.
    row = copy.deepcopy(speaker)
    assert prepared.reuse_prepared(image, row)
    assert row['mouth_box'] == [.33, .42, .47, .52]
    changed = {**speaker, 'mouth_box': [.36, .44, .45, .5]}
    assert not prepared.reuse_prepared(image, changed)
    pathlib.Path(row['layers']['open']).write_bytes(b'corrupted')
    assert not prepared.reuse_prepared(image, copy.deepcopy(speaker))
    image.write_bytes(b'new source')
    assert not prepared.reuse_prepared(image, copy.deepcopy(speaker))


def test_failed_visual_review_never_publishes_reusable_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(prepared, 'ROOT', tmp_path / 'cache')
    image = tmp_path / 'source.png'
    image.write_bytes(b'original')
    from test_mouth_geometry import speaker as verified_speaker
    speaker = verified_speaker(); speaker['speaker'] = 'Mother'
    speaker['mouth_geometry']['source_sha256'] = ae_mouth.digest(image)
    geometry = {'state': 'ready', 'source_sha256': ae_mouth.digest(image), 'speakers': [speaker]}
    monkeypatch.setattr(ae_mouth, 'mouth_layers', lambda *args: {})
    def fail(*args):
        raise ValueError('visual review failed')
    monkeypatch.setattr(ae_mouth, 'review_layers', fail)
    with pytest.raises(ValueError, match='visual review'):
        prepared.prepare_scene(image, geometry, runner=object(), generator=object())
    assert not prepared.reuse_prepared(image, speaker)
