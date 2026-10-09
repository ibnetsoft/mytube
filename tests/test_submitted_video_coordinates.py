import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
import submitted_video_coordinates as video_coordinates
from test_ae_video_tracking import clip


@pytest.fixture
def submitted(monkeypatch, tmp_path):
    video, reference, speakers = clip(tmp_path)
    speakers[0].update(confidence=.99, reason='visible face and lips')
    store = {'video.mp4': video.read_bytes(), 'manual.png': reference.read_bytes()}
    assets, calls = [], []
    scene = {'number': 12, 'start': 0, 'end': 1.2, 'text': 'A speaks', 'image': None,
             'original_video': {'id': 'v12', 'metadata': {'gcs_bucket': 'bucket', 'gcs_path': 'video.mp4'}}}
    rows = [{'kind': 'dialogue', 'speaker': 'A', 'text': 'Hello', 'start': 0, 'end': 1.2}]
    class Runner:
        def _stage(self, identity, stage, context, task):
            calls.append(context)
            assert Path(context['_local_image_paths'][0]).is_file()
            return {'speakers': copy.deepcopy(speakers)}
    monkeypatch.setattr(video_coordinates.ae, '_supabase', lambda: ('https://db', {}))
    monkeypatch.setattr(video_coordinates, 'load_project_assets', lambda *a: copy.deepcopy(assets))
    def download(ref, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(store[ref.path])
    def upload(file, path, mime):
        store[path] = file.read_bytes()
        return 'bucket', path, 'url'
    def request(method, url, headers, json):
        assert method == 'POST'
        asset = {**copy.deepcopy(json), 'id': str(len(assets))}
        assets.append(asset)
        return SimpleNamespace(json=lambda: [asset])
    monkeypatch.setattr(video_coordinates.ae, '_download_gcs_file', download)
    monkeypatch.setattr(video_coordinates.ae, '_upload_gcs_file', upload)
    monkeypatch.setattr(video_coordinates.ae, '_request', request)
    def execute(**kw):
        return video_coordinates.prepare_submitted_video(Runner(), 'p', scene, rows, {}, tmp_path/'work', lambda: None, **kw)
    return scene, speakers, store, assets, calls, execute


def test_submission_extracts_analyzes_tracks_persists_and_reuses_without_codex(submitted):
    scene, speakers, store, assets, calls, execute = submitted
    result = execute()
    assert len(calls) == 1 and len(assets) == 1
    metadata = assets[0]['metadata']
    assert metadata['kind'] == 'submitted_video_coordinates'
    assert metadata['state'] == 'ready'
    saved = json.loads(store[metadata['gcs_path']])
    track = saved['speakers'][0]['tracking']
    assert len(track) == 18
    assert track[-1]['mouth_box'][0] - track[0]['mouth_box'][0] == pytest.approx(17/256, abs=.01)
    assert track[-1]['face_box'][0] > track[0]['face_box'][0]
    assert saved['report']['video_sha256'] == video_coordinates.digest(result[0])
    again = execute(allow_analyze=False)
    assert again[3] == result[3] and len(calls) == 1 and len(assets) == 1


def test_manual_seed_is_preserved_and_never_reclassified(submitted):
    scene, speakers, store, assets, calls, execute = submitted
    scene['image'] = {'id': 'manual', 'metadata': {'gcs_bucket': 'bucket', 'gcs_path': 'manual.png'}}
    scene['speaker_regions'] = {'image_id': 'manual', 'source_sha256': video_coordinates.hashlib.sha256(store['manual.png']).hexdigest(), 'speakers': copy.deepcopy(speakers)}
    execute()
    assert calls == [] and assets[0]['metadata']['manual_seed_used'] is True
    assert scene['speaker_regions']['speakers'] == speakers


def test_cannot_reanalyze_after_direction_approval_or_reuse_changed_video(submitted):
    scene, speakers, store, assets, calls, execute = submitted
    with pytest.raises(ValueError, match='승인된'):
        execute(allow_analyze=False)
    execute()
    store['video.mp4'] += b'changed source'
    with pytest.raises(ValueError, match='승인된'):
        execute(allow_analyze=False)
    assert len(calls) == 1


def test_first_frame_absence_does_not_claim_whole_video_offscreen(submitted):
    scene, speakers, store, assets, calls, execute = submitted
    speakers[0]['status'] = 'offscreen'
    with pytest.raises(ValueError, match='첫 프레임'):
        execute()
    assert assets == []


def test_corrupt_persisted_coordinates_are_not_used(submitted):
    scene, speakers, store, assets, calls, execute = submitted
    execute()
    store[assets[0]['metadata']['gcs_path']] = b'{}'
    with pytest.raises(ValueError, match='파일'):
        execute(allow_analyze=False)
