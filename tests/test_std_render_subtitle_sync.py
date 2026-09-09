from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STD_RENDER_QUEUE = (ROOT / "auth-web" / "lib" / "stdRenderQueue.ts").read_text(encoding="utf-8")
REMOTE_RENDER = (ROOT / "services" / "remote_render_service.py").read_text(encoding="utf-8")


def test_render_queue_uses_saved_subtitles_and_requests_worker_sync():
    assert "function buildRenderSubtitles(project: any, scenes: any[])" in STD_RENDER_QUEUE
    assert "project?.project_payload?.subtitles" in STD_RENDER_QUEUE
    assert "const subtitles = buildRenderSubtitles(project, scenes)" in STD_RENDER_QUEUE
    assert "subtitle_sync_mode: 'audio_duration_weighted'" in STD_RENDER_QUEUE


def test_remote_worker_retimes_subtitles_to_the_final_audio_duration():
    assert "def _sync_subtitle_timings_to_audio_duration(subtitles, audio_duration):" in REMOTE_RENDER
    assert "weights = [max(1, len(re.sub" in REMOTE_RENDER
    assert "subs = _sync_subtitle_timings_to_audio_duration(subs, audio_duration)" in REMOTE_RENDER
    assert "음성 길이 기준 자막 싱크 보정 중..." in REMOTE_RENDER
