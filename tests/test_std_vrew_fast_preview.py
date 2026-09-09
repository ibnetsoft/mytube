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


def test_vrew_word_progress_is_shown_only_in_the_subtitle_editor():
    assert "const vrewActiveTokenAtPlaybackTime" in STD_PAGE
    assert "? vrewActiveTokenAtPlaybackTime(currentSub, playbackTime)" in STD_PAGE
    assert "const highlightTime = Math.min(end, time + 0.06)" in STD_PAGE
    assert "setInterval(syncPlaybackProgress, 33)" in STD_PAGE
    assert "const renderPreviewSubtitleText" not in STD_PAGE
    preview_overlay = STD_PAGE.split("{/* 실시간 폰트/스타일 자막 오버레이", 1)[1].split("{/* 커스텀 플레이어 바 */}", 1)[0]
    assert "{currentSub.text}" in preview_overlay
    assert "text-cyan-200" not in preview_overlay
    assert "/tts/cache-segment" in STD_PAGE
    assert "upload_mode: 'fast_preview_background_cache'" in SEGMENT_CACHE
    assert "kind: 'vrew_segment_tts'" in SEGMENT_CACHE
    assert ".eq('metadata->>cache_key', cacheKey)" in SEGMENT_CACHE


def test_vrew_cached_preview_fetches_authenticated_audio_before_playback():
    assert "isSameOriginApiAudioUrl(audioUrl)" in STD_PAGE
    assert "fetchVrewAudioBlobUrl(audioUrl)" in STD_PAGE
    assert "...authedJsonHeaders" in STD_PAGE
    assert "Accept: 'audio/mpeg'" in STD_PAGE
    assert "return URL.createObjectURL(audioBlob)" in STD_PAGE


def test_vrew_cached_preview_regenerates_when_cached_drive_audio_fails():
    assert "const bypassSegmentCache = Boolean(body?.bypass_cache)" in TTS_GENERATE
    assert "segmentCacheKey && !bypassSegmentCache" in TTS_GENERATE
    assert "bypass_cache: bypassCache" in STD_PAGE
    assert "if (!payload?.cached) throw error" in STD_PAGE
    assert "vrewBypassCachedSegmentAudioRef.current = true" in STD_PAGE
    assert "requestSegmentAudio(vrewBypassCachedSegmentAudioRef.current)" in STD_PAGE
    assert "payload = await requestSegmentAudio(true)" in STD_PAGE


def test_vrew_preview_deduplicates_requests_and_prefetches_upcoming_segments():
    assert "vrewAudioPromiseRef" in STD_PAGE
    assert "return await inFlightRequest" in STD_PAGE
    assert "for (let offset = 1; offset <= 3; offset += 1)" in STD_PAGE
    assert "prefetchVrewSegment(selectedSubIndex)" in STD_PAGE


def test_vrew_playback_syncs_the_current_scene_video():
    assert "const vrewPreviewVideoRef = useRef<HTMLVideoElement | null>(null)" in STD_PAGE
    assert "vrewPreviewVideoRef.current?.pause()" in STD_PAGE
    assert "const currentPreviewSceneNumber" in STD_PAGE
    assert "void video.play().catch(() => {})" in STD_PAGE
    assert "ref={vrewPreviewVideoRef}" in STD_PAGE
    assert "playsInline" in STD_PAGE


def test_vrew_preview_falls_back_to_the_current_scene_media_when_subtitle_media_is_stale():
    assert "const currentSubImageUrl = currentSubVisual.image_url" in STD_PAGE
    assert "|| runtimeAssetUrl(currentSub?.image_url || currentSub?.image)" in STD_PAGE
    assert "const currentSubVideoCandidate = currentSubVisual.video_url" in STD_PAGE
    assert "|| runtimeAssetUrl(currentSub?.video_url || currentSub?.video)" in STD_PAGE


def test_vrew_preview_uses_scene_image_when_video_is_a_google_drive_view_link():
    assert "const isPlayablePreviewVideoUrl" in STD_PAGE
    assert "parsed.hostname.toLowerCase() === 'drive.google.com'" in STD_PAGE
    assert "const currentSubVideoCandidate" in STD_PAGE
    assert "const currentSubVideoUrl = isPlayablePreviewVideoUrl(currentSubVideoCandidate)" in STD_PAGE


def test_elevenlabs_subscription_checks_use_a_short_server_cache():
    assert "ELEVENLABS_KEY_INSPECTION_TTL_MS = 60_000" in TTS_GENERATE
    assert "elevenLabsKeyInspectionCache.get(cacheKey)" in TTS_GENERATE
    assert "elevenLabsKeyInspectionCache.set(cacheKey" in TTS_GENERATE


def test_std_drive_folder_checks_are_reused_for_background_segment_saves():
    assert "STD_FOLDER_CACHE_TTL_MS = 5 * 60_000" in STD_DRIVE
    assert "stdProjectFolderCache.get(cacheKey)" in STD_DRIVE
    assert STD_DRIVE.count("stdProjectFolderCache.set(cacheKey") == 2


def test_background_cache_accepts_topic_queue_project_ids():
    assert "topicIdFromProjectParam" in SEGMENT_CACHE
    assert ".eq('topic_queue_id', topicQueueId)" in SEGMENT_CACHE
    assert "loadStdProject(" in SEGMENT_CACHE


def test_background_cache_omits_non_uuid_fallback_uploader_ids():
    assert "uploaded_by: UUID_RE.test(String(auth.requester.user.id || ''))" in SEGMENT_CACHE
