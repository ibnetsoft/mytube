from pathlib import Path


STD_PAGE = Path("auth-web/app/std/page.tsx").read_text(encoding="utf-8")
STD_LOCAL_MEDIA = Path("auth-web/lib/stdLocalMedia.ts").read_text(encoding="utf-8")
STD_TTS_KEY_ROUTE = Path("auth-web/app/api/std/tts-key/route.ts").read_text(encoding="utf-8")
STD_TTS_GENERATE_ROUTE = Path("auth-web/app/api/std/projects/[projectId]/tts/generate/route.ts").read_text(encoding="utf-8")
STD_VOICES_ROUTE = Path("auth-web/app/api/std/voices/route.ts").read_text(encoding="utf-8")
STD_GOOGLE_DRIVE = Path("auth-web/lib/stdGoogleDrive.ts").read_text(encoding="utf-8")


def test_std_tts_page_restores_audio_and_exposes_worker_script_restore():
    assert "['image', 'video', 'thumbnail', 'audio']" in STD_PAGE
    assert "let restoredAudioUrl = ''" in STD_PAGE
    assert "setAudioResultUrl(restoredAudioUrl || audioPlaybackEndpoint(projectId, audioAsset) || '')" in STD_PAGE
    assert "const restoreOriginalWorkerScript = async () => {" in STD_PAGE
    assert "onClick={restoreOriginalWorkerScript}" in STD_PAGE
    assert "original_worker_script: projectScript," in STD_PAGE


def test_std_tts_page_displays_actual_audio_metadata_duration_after_generation():
    assert "const [audioDurationSeconds, setAudioDurationSeconds] = useState(0)" in STD_PAGE
    assert 'preload="metadata"' in STD_PAGE
    assert "onLoadedMetadata={event =>" in STD_PAGE
    assert "setAudioDurationSeconds(Number.isFinite(duration) && duration > 0 ? duration : 0)" in STD_PAGE
    assert "? `실제 ${formattedActualAudioDuration}`" in STD_PAGE
    assert "selectedVoice.startsWith('google_') ? 330 : 420" in STD_PAGE


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
    assert "selectUsableElevenLabsKeys(apiKeys, largestChunkChars)" in STD_TTS_GENERATE_ROUTE
    assert "inspectElevenLabsKey" in STD_TTS_GENERATE_ROUTE
    assert "잔여 ${item.remaining.toLocaleString('ko-KR')}자 < 청크 필요" in STD_TTS_GENERATE_ROUTE
    assert "DEFAULT_ELEVENLABS_VOICE_ID" in STD_TTS_GENERATE_ROUTE
    assert "voiceId: DEFAULT_ELEVENLABS_VOICE_ID" not in STD_TTS_GENERATE_ROUTE
    assert "등록된 다음 백업 키를 확인합니다" in STD_TTS_GENERATE_ROUTE
    assert "const keySlot = typeof keyCandidate === 'string' ? keyIndex + 1 : keyCandidate.keySlot" in STD_TTS_GENERATE_ROUTE
    assert "elevenlabs_key_slots: elevenLabsTrace?.keySlots || []" in STD_TTS_GENERATE_ROUTE
    assert "[STD TTS] ElevenLabs generation trace" in STD_TTS_GENERATE_ROUTE
    assert "ElevenLabs 키 ${usedKeySlots.join(', ')}번 사용" in STD_PAGE


def test_std_tts_failures_are_logged_with_chunk_and_key_context():
    assert "recordStdTtsFailure" in STD_TTS_GENERATE_ROUTE
    assert "task_type: 'std_tts_generate'" in STD_TTS_GENERATE_ROUTE
    assert "prompt_summary: `project=${input.project?.id || '-'} text=${input.textLength || 0} chunks=${input.chunkCount || 0} stage=${input.stage}`" in STD_TTS_GENERATE_ROUTE
    assert "[STD TTS] generation failed" in STD_TTS_GENERATE_ROUTE
    assert "elevenlabs_key_preflight: ttsDebug.keyInspections" in STD_TTS_GENERATE_ROUTE


def test_std_tts_uses_inline_audio_when_drive_playback_auth_fails():
    assert "MAX_INLINE_AUDIO_BYTES" in STD_TTS_GENERATE_ROUTE
    assert "audio_url: inlineAudioUrl || audioUrl" in STD_TTS_GENERATE_ROUTE
    assert "persisted_audio_url: audioUrl" in STD_TTS_GENERATE_ROUTE
    assert "for (let attempt = 0; attempt < 2; attempt += 1)" in STD_GOOGLE_DRIVE
    assert "if (res.status !== 401) break" in STD_GOOGLE_DRIVE


def test_std_tts_hides_custom_voices_unavailable_to_current_primary_key():
    assert "const accessibleVoiceIds = new Set(apiVoices.map" in STD_VOICES_ROUTE
    assert "customVoices.filter(voice => accessibleVoiceIds.has" in STD_VOICES_ROUTE
    assert "for (const cv of availableCustomVoices)" in STD_VOICES_ROUTE
    assert "for (const cv of customVoices)" not in STD_VOICES_ROUTE
    assert "voiceId: DEFAULT_ELEVENLABS_VOICE_ID" not in STD_TTS_GENERATE_ROUTE
