from pathlib import Path


STD_PAGE = Path("auth-web/app/std/page.tsx").read_text(encoding="utf-8")
STD_LOCAL_MEDIA = Path("auth-web/lib/stdLocalMedia.ts").read_text(encoding="utf-8")
STD_TTS_KEY_ROUTE = Path("auth-web/app/api/std/tts-key/route.ts").read_text(encoding="utf-8")
STD_TTS_GENERATE_ROUTE = Path("auth-web/app/api/std/projects/[projectId]/tts/generate/route.ts").read_text(encoding="utf-8")
STD_GOOGLE_DRIVE = Path("auth-web/lib/stdGoogleDrive.ts").read_text(encoding="utf-8")


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


def test_std_local_media_reuses_existing_folder_for_permission_reconnect():
    assert "export async function reconnectStdLocalDirectory()" in STD_LOCAL_MEDIA
    assert "const handle = await getRootHandle()" in STD_LOCAL_MEDIA
    assert "return await selectStdLocalDirectory()" in STD_LOCAL_MEDIA
    assert "? await reconnectStdLocalDirectory()" in STD_PAGE
    assert "? '권한 재연결'" in STD_PAGE


def test_std_tts_routes_filter_masked_keys_and_retry_elevenlabs_fallbacks():
    assert "getConfiguredElevenLabsKeys" in STD_TTS_KEY_ROUTE
    assert "getConfiguredElevenLabsKeys" in STD_TTS_GENERATE_ROUTE
    assert "FALLBACK_ELEVENLABS_MODEL_IDS = ['eleven_v3', 'eleven_multilingual_v2']" in STD_TTS_GENERATE_ROUTE
    assert "shouldRetryElevenLabsWithAlternateModel" in STD_TTS_GENERATE_ROUTE
    assert "DEFAULT_ELEVENLABS_VOICE_ID" in STD_TTS_GENERATE_ROUTE


def test_std_tts_uses_inline_audio_when_drive_playback_auth_fails():
    assert "MAX_INLINE_AUDIO_BYTES" in STD_TTS_GENERATE_ROUTE
    assert "audio_url: inlineAudioUrl || audioUrl" in STD_TTS_GENERATE_ROUTE
    assert "persisted_audio_url: audioUrl" in STD_TTS_GENERATE_ROUTE
    assert "for (let attempt = 0; attempt < 2; attempt += 1)" in STD_GOOGLE_DRIVE
    assert "if (res.status !== 401) break" in STD_GOOGLE_DRIVE
