from pathlib import Path


ROUTER_SOURCE = Path("app/routers/tts.py").read_text(encoding="utf-8")


def test_tts_router_falls_back_to_default_elevenlabs_voice():
    assert 'DEFAULT_ELEVENLABS_VOICE_ID = "4JJwo477JUAx3HV0T7n7"' in ROUTER_SOURCE
    assert 'base_voice_id = (str(req.voice_id or "").strip() or DEFAULT_ELEVENLABS_VOICE_ID)' in ROUTER_SOURCE
    assert 'req.text, base_voice_id, result_filename, voice_settings=el_voice_settings' in ROUTER_SOURCE


def test_tts_router_uses_service_voice_lookup():
    assert "elevenlabs_voices = await tts_service.get_elevenlabs_voices()" in ROUTER_SOURCE
