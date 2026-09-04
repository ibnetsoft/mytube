from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STD_PAGE = (ROOT / "auth-web" / "app" / "std" / "page.tsx").read_text(encoding="utf-8")
TTS_GENERATE = (ROOT / "auth-web" / "app" / "api" / "std" / "projects" / "[projectId]" / "tts" / "generate" / "route.ts").read_text(encoding="utf-8")
SEGMENT_CACHE = (ROOT / "auth-web" / "app" / "api" / "std" / "projects" / "[projectId]" / "tts" / "cache-segment" / "route.ts").read_text(encoding="utf-8")
STD_DRIVE = (ROOT / "auth-web" / "lib" / "stdGoogleDrive.ts").read_text(encoding="utf-8")


def test_vrew_preview_returns_generated_audio_before_drive_persistence():
    assert "mode: 'vrew_segment_preview_fast'" in STD_PAGE
    assert "const fastSegmentPreview = body?.mode === 'vrew_segment_preview_fast'" in TTS_GENERATE
    fast_return = TTS_GENERATE.index("if (fastSegmentPreview)")
    drive_persistence = TTS_GENERATE.index("stage = 'ensure_drive_folders'", fast_return)
    assert fast_return < drive_persistence
    assert "persistence_pending: true" in TTS_GENERATE
    assert "audio_url: `data:audio/mpeg;base64,${audioBuffer.toString('base64')}`" in TTS_GENERATE


def test_vrew_preview_persists_the_same_audio_in_background():
    assert "persistVrewSegmentAudio(audioBlob, payload, subtitle, index, voiceId)" in STD_PAGE
    assert "/tts/cache-segment" in STD_PAGE
    assert "upload_mode: 'fast_preview_background_cache'" in SEGMENT_CACHE
    assert "kind: 'vrew_segment_tts'" in SEGMENT_CACHE
    assert ".eq('metadata->>cache_key', cacheKey)" in SEGMENT_CACHE


def test_vrew_preview_deduplicates_requests_and_prefetches_upcoming_segments():
    assert "vrewAudioPromiseRef" in STD_PAGE
    assert "return await inFlightRequest" in STD_PAGE
    assert "for (let offset = 1; offset <= 3; offset += 1)" in STD_PAGE
    assert "prefetchVrewSegment(selectedSubIndex)" in STD_PAGE


def test_elevenlabs_subscription_checks_use_a_short_server_cache():
    assert "ELEVENLABS_KEY_INSPECTION_TTL_MS = 60_000" in TTS_GENERATE
    assert "elevenLabsKeyInspectionCache.get(cacheKey)" in TTS_GENERATE
    assert "elevenLabsKeyInspectionCache.set(cacheKey" in TTS_GENERATE


def test_std_drive_folder_checks_are_reused_for_background_segment_saves():
    assert "STD_FOLDER_CACHE_TTL_MS = 5 * 60_000" in STD_DRIVE
    assert "stdProjectFolderCache.get(cacheKey)" in STD_DRIVE
    assert STD_DRIVE.count("stdProjectFolderCache.set(cacheKey") == 2
