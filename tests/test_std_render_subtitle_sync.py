from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STD_RENDER_QUEUE = (ROOT / "auth-web" / "lib" / "stdRenderQueue.ts").read_text(encoding="utf-8")
REMOTE_RENDER = (ROOT / "services" / "remote_render_service.py").read_text(encoding="utf-8")


def test_render_queue_uses_saved_subtitles_and_requests_preserved_timings():
    assert "function buildRenderSubtitles(project: any, scenes: any[])" in STD_RENDER_QUEUE
    assert "project?.project_payload?.subtitles" in STD_RENDER_QUEUE
    assert "const subtitles = buildRenderSubtitles(project, scenes)" in STD_RENDER_QUEUE
    assert "subtitle_sync_mode: 'preserve_subtitle_timings'" in STD_RENDER_QUEUE


def test_remote_worker_preserves_explicit_subtitle_timings():
    assert "def _sync_subtitle_timings_to_audio_duration(subtitles, audio_duration):" in REMOTE_RENDER
    assert "def _subtitles_have_explicit_timings(subtitles):" in REMOTE_RENDER
    assert "weights = [max(1, len(re.sub" in REMOTE_RENDER
    assert "and not _subtitles_have_explicit_timings(subs)" in REMOTE_RENDER
    assert "저장된 자막 타이밍 적용 중..." in REMOTE_RENDER


def test_worker_pauses_only_at_segment_end_and_keeps_speaker_context(tmp_path, monkeypatch):
    import ast
    import os
    import re
    import services.voice_studio as voices
    wanted = {'_voice_id_to_worker_preset', '_maybe_generate_worker_tts'}
    tree = ast.parse(REMOTE_RENDER.lstrip('\ufeff'))
    module = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted], type_ignores=[])
    captured = {}
    class FakeStudio:
        def __init__(self, presets, providers, limits):
            captured['presets'] = presets
        def run(self, segments, directory):
            captured['segments'] = segments
            return {}
    monkeypatch.setattr(voices, 'VoiceStudio', FakeStudio)
    scope = {'os': os, 're': re, 'Path': Path,
             '_retime_subtitles_from_worker_tts': lambda *args: [],
             '_scene_starts_from_subtitles': lambda *args: []}
    exec(compile(module, '<worker-tts>', 'exec'), scope)
    scope['_maybe_generate_worker_tts']({'worker_tts': {
        'enabled': True, 'pause_complete_ms': 260,
        'segments': [
            {'voice_id': 'narrator', 'text': '끝입니다. 등에 작은'},
            {'voice_id': 'narrator', 'text': '보따리를\n졌습니다.'},
            {'voice_id': 'dialogue', 'text': '누구세요?'},
        ],
    }}, str(tmp_path), [])
    a, c = captured['segments']
    assert a['text'] == '끝입니다. 등에 작은 보따리를 졌습니다.'
    assert a['pause_ms'] == 260
    assert 'next_text' not in a and 'previous_text' not in c
    assert all(p['pause_ms'] == 0 for p in captured['presets'].values())
