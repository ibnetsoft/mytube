from pathlib import Path


STD_PAGE = Path("auth-web/app/std/page.tsx").read_text(encoding="utf-8")
STD_LOCAL_MEDIA = Path("auth-web/lib/stdLocalMedia.ts").read_text(encoding="utf-8")
STD_TTS_KEY_ROUTE = Path("auth-web/app/api/std/tts-key/route.ts").read_text(encoding="utf-8")
STD_TTS_GENERATE_ROUTE = Path("auth-web/app/api/std/projects/[projectId]/tts/generate/route.ts").read_text(encoding="utf-8")


def test_std_tts_page_restores_audio_and_exposes_worker_script_restore():
    assert "['image', 'video', 'thumbnail', 'audio']" in STD_PAGE
    assert "let restoredAudioUrl = ''" in STD_PAGE
    assert "setAudioResultUrl(restoredAudioUrl || audioPlaybackEndpoint(projectId, audioAsset) || '')" in STD_PAGE
    assert "const restoreOriginalWorkerScript = async () => {" in STD_PAGE
    assert "onClick={restoreOriginalWorkerScript}" in STD_PAGE
    assert "original_worker_script: projectScript," in STD_PAGE


def test_std_local_media_supports_audio_assets():
    assert "assetType: 'image' | 'video' | 'thumbnail' | 'audio'" in STD_LOCAL_MEDIA
    assert "['image', 'video', 'thumbnail', 'audio'].includes(assetType)" in STD_LOCAL_MEDIA


def test_std_tts_routes_filter_masked_keys_and_retry_elevenlabs_fallbacks():
    assert "function isUsableSecretValue" in STD_TTS_KEY_ROUTE
    assert "function isUsableSecretValue" in STD_TTS_GENERATE_ROUTE
    assert "FALLBACK_ELEVENLABS_MODEL_IDS = ['eleven_v3', 'eleven_multilingual_v2']" in STD_TTS_GENERATE_ROUTE
    assert "shouldRetryElevenLabsWithAlternateModel" in STD_TTS_GENERATE_ROUTE
    assert "DEFAULT_ELEVENLABS_VOICE_ID" in STD_TTS_GENERATE_ROUTE
