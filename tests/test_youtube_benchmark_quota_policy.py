import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = ROOT / "worker"
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

from services.youtube_data_api import parse_channel_rss_videos
import hermes_worker
from hermes_autopilot import HermesAutopilotManager


RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <yt:videoId>video_001</yt:videoId>
    <yt:channelId>channel_001</yt:channelId>
    <title>첫 번째 영상</title>
    <published>2026-08-14T00:00:00+00:00</published>
    <updated>2026-08-14T01:00:00+00:00</updated>
    <author><name>테스트 채널</name></author>
    <media:group>
      <media:description>설명입니다</media:description>
      <media:thumbnail url="https://example.com/thumb.jpg" />
    </media:group>
  </entry>
</feed>
"""


def test_parse_channel_rss_videos_uses_zero_quota_seed_shape():
    videos = parse_channel_rss_videos(RSS_XML)

    assert videos == [
        {
            "video_id": "video_001",
            "channel_id": "channel_001",
            "title": "첫 번째 영상",
            "channel_title": "테스트 채널",
            "published_at": "2026-08-14T00:00:00+00:00",
            "updated_at": "2026-08-14T01:00:00+00:00",
            "description": "설명입니다",
            "thumbnail_url": "https://example.com/thumb.jpg",
            "url": "https://www.youtube.com/watch?v=video_001",
            "performance_data_source": "youtube_rss_seed",
        }
    ]


def test_load_benchmark_channel_pool_prefers_payload_ids(monkeypatch):
    monkeypatch.delenv("YOUTUBE_BENCHMARK_CHANNELS_JSON", raising=False)

    ids, audit = hermes_worker._load_benchmark_channel_pool(
        {"benchmark_channel_ids": ["UC_payload", "UC_payload"]},
        "옛날이야기",
    )

    assert ids == ["UC_payload"]
    assert audit["source"] == "payload"


def test_load_benchmark_channel_pool_reads_category_env(monkeypatch):
    monkeypatch.setenv(
        "YOUTUBE_BENCHMARK_CHANNELS_JSON",
        json.dumps({"옛날이야기": ["UC_old_story"], "default": ["UC_default"]}, ensure_ascii=False),
    )

    ids, audit = hermes_worker._load_benchmark_channel_pool({}, "옛날이야기")

    assert ids == ["UC_old_story"]
    assert audit["source"] == "env:YOUTUBE_BENCHMARK_CHANNELS_JSON"


def test_search_fallback_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("YOUTUBE_SEARCH_FALLBACK_ENABLED", raising=False)

    with pytest.raises(RuntimeError, match="search fallback is disabled"):
        asyncio.run(hermes_worker._search_candidate_videos("옛날이야기", "ko", "longform", 5, ["민담"]))


def test_old_story_rss_relevance_rejects_modern_and_economy_contamination():
    payload = {
        "category": "옛날이야기",
        "category_name": "옛날이야기",
        "search_keywords": ["조선시대 실화", "한국 민간 전설"],
    }

    assert not hermes_worker._is_relevant_rss_candidate(
        {
            "title": "국정원이 키운 전학생, 학교에 나타나다",
            "description": "흥미로운 이야기",
            "channel_title": "시간실록",
        },
        payload,
        "옛날이야기",
    )
    assert not hermes_worker._is_relevant_rss_candidate(
        {
            "title": "삼성전자 주가 8만원 전망과 코스피 흐름",
            "description": "경제 이야기",
            "channel_title": "경제채널",
        },
        payload,
        "옛날이야기",
    )
    assert hermes_worker._is_relevant_rss_candidate(
        {
            "title": "저승사자가 데려가려던 아이, 이름이 없어 돌아왔다",
            "description": "한국 민간 전설을 바탕으로 한 옛날 이야기",
            "channel_title": "옛이야기",
        },
        payload,
        "옛날이야기",
    )
    assert hermes_worker._is_relevant_rss_candidate(
        {
            "title": "조선시대 나무꾼이 어사또 판결을 뒤집은 날",
            "description": "조선 민담",
            "channel_title": "역사 이야기",
        },
        payload,
        "옛날이야기",
    )


def test_stats_enrichment_uses_batched_list_endpoints(monkeypatch):
    calls = []

    async def fake_list_by_ids(endpoint, ids, *, part, timeout=15.0, max_ids_per_call=50):
        ids = list(ids)
        calls.append((endpoint, ids, part))
        if endpoint == "videos":
            return {
                "items": [{"id": ids[0], "statistics": {"viewCount": "1200"}}],
                "batch_count": 1,
                "responses": [],
            }
        return {
            "items": [{"id": ids[0], "statistics": {"subscriberCount": "100"}}],
            "batch_count": 1,
            "responses": [],
        }

    import services.youtube_data_api as youtube_data_api

    monkeypatch.setattr(youtube_data_api, "async_youtube_list_by_ids", fake_list_by_ids)
    enriched, audit = asyncio.run(
        hermes_worker._fetch_video_and_channel_stats([
            {"video_id": "video_001", "channel_id": "channel_001", "title": "테스트"}
        ])
    )

    assert calls == [
        ("videos", ["video_001"], "statistics"),
        ("channels", ["channel_001"], "statistics"),
    ]
    assert enriched[0]["view_count"] == 1200
    assert enriched[0]["subscriber_count"] == 100
    assert enriched[0]["performance_ratio"] == 12.0
    assert audit["quota_policy"]["videos_list_calls"] == 1


def test_autopilot_auto_discovery_only_when_enabled_and_needed():
    manager = object.__new__(HermesAutopilotManager)
    manager.settings = {
        "benchmark_channel_auto_discovery_enabled": True,
        "benchmark_channel_discovery_max_search_calls": 1,
        "benchmark_channel_discovery_min_channels": 3,
        "benchmark_channel_discovery_interval_hours": 24,
        "benchmark_channel_discovery_last_at": {},
    }

    assert manager._should_discover_benchmark_channels("옛날이야기", ["UC1", "UC2"])
    assert manager._should_discover_benchmark_channels("옛날이야기", ["UC1", "UC2", "UC3"])
    manager.settings["benchmark_channel_discovery_last_at"] = {"옛날이야기": 9999999999}
    assert not manager._should_discover_benchmark_channels("옛날이야기", ["UC1", "UC2", "UC3"])

    manager.settings["benchmark_channel_auto_discovery_enabled"] = False
    assert not manager._should_discover_benchmark_channels("옛날이야기", [])

    manager.settings["benchmark_channel_auto_discovery_enabled"] = True
    manager.settings["benchmark_channel_discovery_max_search_calls"] = 0
    assert not manager._should_discover_benchmark_channels("옛날이야기", [])


def test_old_story_benchmark_keywords_do_not_call_ai_or_use_economy_terms(monkeypatch):
    async def fail_generate_text(*args, **kwargs):
        raise AssertionError("old-story benchmark keyword discovery must use fixed category seeds")

    monkeypatch.setattr("services.ai_router.generate_text", fail_generate_text)

    manager = object.__new__(HermesAutopilotManager)
    keywords = asyncio.run(manager._discover_benchmark_keywords("옛날이야기"))

    assert len(keywords) == 10
    assert "조선시대 야담 실화" in keywords
    assert not any(term in " ".join(keywords) for term in ["금값", "코스피", "환율", "주가", "부동산", "경제"])


def test_economy_keyword_hint_is_category_scoped(monkeypatch):
    manager = object.__new__(HermesAutopilotManager)
    prompts = []

    async def fake_generate_text(prompt, **kwargs):
        prompts.append(prompt)
        return "[]"

    monkeypatch.setattr("hermes_autopilot.ai_router.generate_text", fake_generate_text)

    asyncio.run(manager._discover_benchmark_keywords("한국사연"))
    asyncio.run(manager._discover_benchmark_keywords("경제"))

    assert "gold, oil, stocks" not in prompts[0]
    assert "gold, oil, stocks" in prompts[1]


def test_learning_profile_instruction_includes_script_and_performance_memory():
    instruction = hermes_worker._learning_profile_instruction({
        "learning_profile": {
            "successful_script_patterns": [
                {"central_conflict": "마을의 오해", "turning_point": "보따리의 정체 공개"}
            ],
            "failed_script_patterns": ["hook too slow", "payoff missing"],
            "performance_lessons": [
                {
                    "outcome": "excellent",
                    "score": 91,
                    "summary": "초반 30초에 관계 갈등을 바로 제시한 영상이 유지율이 좋았다.",
                    "recommendations": ["첫 장면에서 갈등을 숨기지 말 것"],
                }
            ],
            "script_generation_rules": {"avoid": ["meta commentary"]},
        }
    })

    assert "LEARNING MEMORY" in instruction
    assert "마을의 오해" in instruction
    assert "hook too slow" in instruction
    assert "초반 30초" in instruction
    assert "never copy" in instruction.lower()
