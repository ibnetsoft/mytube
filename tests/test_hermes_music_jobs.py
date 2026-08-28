import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

import hermes_worker  # noqa: E402


def test_music_trend_payload_defaults_to_thailand_playlist_shape():
    target_market, playlist_concept, track_count, track_duration_seconds, source_summary = (
        hermes_worker._validate_music_trend_payload({})
    )

    assert target_market == "Thailand"
    assert "Thai" in playlist_concept
    assert track_count == 60
    assert track_duration_seconds == 180
    assert source_summary == {}


def test_music_prompt_pack_normalizer_fills_missing_tracks_with_safe_defaults():
    result = hermes_worker._normalize_music_prompt_pack_result(
        {
            "playlist_concept": "Relaxing Thai cafe lofi for work and study",
            "popular_genres": ["lofi", "thai pop ballad"],
            "core_moods": ["calm", "rainy"],
            "tracks": [
                {
                    "title": "Rainy Bangkok Cafe",
                    "genre": "lofi jazz",
                    "mood": "calm, rainy, warm",
                    "prompt": "Original instrumental lo-fi jazz track with soft piano.",
                }
            ],
        },
        target_market="Thailand",
        playlist_concept="Relaxing Thai cafe lofi for work and study",
        track_count=3,
        track_duration_seconds=180,
    )

    assert result["target_market"] == "Thailand"
    assert result["generation_language"] == "th"
    assert len(result["tracks"]) == 3
    assert result["tracks"][0]["title"] == "Rainy Bangkok Cafe"
    assert result["tracks"][1]["title"]
    assert result["tracks"][1]["duration_seconds"] == 180
    assert "no copyrighted melody" in result["tracks"][1]["negative_rules"]


def test_music_trend_normalizer_keeps_conservative_fallback_summary():
    result = hermes_worker._normalize_music_trend_result(
        {},
        target_market="Global",
        playlist_concept="Relaxing instrumental lofi and ambient mix for deep focus",
        track_count=60,
        track_duration_seconds=180,
    )

    assert result["target_market"] == "Global"
    assert result["popular_genres"]
    assert result["core_moods"]
    assert "longform music demand" in result["trend_summary"]


def test_worker_auth_declares_music_job_types():
    source = (ROOT / "auth-web" / "lib" / "workerAuth.ts").read_text(encoding="utf-8")

    assert "'music_trend_analyze'" in source
    assert "'music_prompt_pack_generate'" in source


def test_music_prompt_pack_uses_notion_music_learning_memory():
    source = (ROOT / "worker" / "hermes_worker.py").read_text(encoding="utf-8")
    helper = (ROOT / "worker" / "notion_learning.py").read_text(encoding="utf-8")

    assert "fetch_music_learning_rows" in helper
    assert "create_music_learning_row" in helper
    assert "fetch_music_learning_rows(target_market, genre" in source
    assert "Notion music learning memory JSON" in source
    assert "notion_music_learning_count" in source
    assert "create_music_learning_row" in source
