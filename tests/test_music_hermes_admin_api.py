from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_music_hermes_route_supports_pipeline_and_both_job_types():
    source = (ROOT / "auth-web" / "app" / "api" / "admin" / "music-hermes" / "route.ts").read_text(encoding="utf-8")

    assert "enqueueMusicTrendAnalyzeJob" in source
    assert "enqueueMusicPromptPackGenerateJob" in source
    assert "enqueueMusicPromptPackFromTrendJob" in source
    assert "dispatchMusicPromptPackToStdQueue" in source
    assert "findThaiMusicQueueCandidates" in source
    assert "action === 'pipeline'" in source
    assert "action === 'dispatch'" in source
    assert "queued_after_trend_completion" in source


def test_music_hermes_trigger_uses_remote_hermes_queue_and_queue_key():
    source = (ROOT / "auth-web" / "lib" / "musicHermesTrigger.ts").read_text(encoding="utf-8")

    assert "remote_hermes_queue" in source
    assert "queue_key" in source
    assert "music_trend_analyze" in source
    assert "music_prompt_pack_generate" in source
    assert "enqueue_prompt_pack_on_complete" in source


def test_complete_route_chains_prompt_pack_after_music_trend_completion():
    source = (ROOT / "auth-web" / "app" / "api" / "internal" / "worker" / "jobs" / "[jobId]" / "complete" / "route.ts").read_text(encoding="utf-8")

    assert "syncMusicTrendPromptPack" in source
    assert "music_trend_analyze" in source
    assert "enqueueMusicPromptPackFromTrendJob" in source


def test_music_hermes_std_queue_helper_builds_topics_queue_payload():
    source = (ROOT / "auth-web" / "lib" / "musicHermesStdQueue.ts").read_text(encoding="utf-8")

    assert "Music Hermes Missions" in source
    assert "topics_queue" in source
    assert "user_topic_recommendations" in source
    assert "dispatchMusicPromptPackToStdQueue" in source
    assert "findThaiMusicQueueCandidates" in source
    assert "pregenerated_structure_status: 'ready'" in source
    assert "pregenerated_script_status: 'ready'" in source
