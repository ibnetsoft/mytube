from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REMOTE_RENDER = (ROOT / "services" / "remote_render_service.py").read_text(encoding="utf-8")
TTS_SERVICE = (ROOT / "services" / "tts_service.py").read_text(encoding="utf-8")
AUTOPILOT = (ROOT / "services" / "autopilot_service.py").read_text(encoding="utf-8")


def test_remote_render_normalizes_final_narration_without_shortening_timeline():
    assert "_prepare_narration_audio_for_render(audio_path, temp_dir, audio_ffmpeg_exe)" in REMOTE_RENDER
    remote_prepare = REMOTE_RENDER.split("def _prepare_narration_audio_for_render", 1)[1].split("def _render_std_template_overlay_png", 1)[0]
    assert "silenceremove" not in remote_prepare
    assert "Do not remove internal silence here" in remote_prepare
    assert "loudnorm=I=-16:TP=-1.5:LRA=11" in REMOTE_RENDER


def test_tts_chunks_merge_with_crossfade_instead_of_hard_concat():
    assert "acrossfade=d={fade_seconds}:c1=tri:c2=tri" in TTS_SERVICE
    assert "silenceremove=start_periods=1" in TTS_SERVICE
    assert "ffmpeg crossfade merge failed" in TTS_SERVICE


def test_autopilot_reuses_tts_crossfade_merge():
    assert "tts_service._merge_audio_files(scene_audio_files, final_audio_path)" in AUTOPILOT
    assert "concatenate_audioclips(clips)" not in AUTOPILOT
