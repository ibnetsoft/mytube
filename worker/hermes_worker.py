"""
[AIR-0227E-P3] Real Hermes Worker Process - topic_research jobs only.

Replaces hermes_worker_mock.py as the process the Manager actually spawns
for the "hermes_worker" role (hermes_worker_mock.py is kept, unmodified, as
a test-only fixture - _dev/ QA scripts that want a fast, API-key-free
Hermes still import it directly; production execution never starts it,
see air_worker_entry.py).

Scope (explicitly limited by this Task): topic research only - given a
keyword/category, call an AI provider and return a list of candidate
topics. No agentic multi-step research, no content generation, no new
Supabase tables/central API - this worker only ever talks to (a) the local
job_store (same SQLite file render_worker.py already uses) and (b) an AI
provider via services/ai_router.py, exactly like the rendering pipeline's
own script-generation calls elsewhere in this codebase.

Job source: worker/job_store.py, job_type='topic_research'. Submitted via
the existing generic POST /jobs/submit on the Local API (job_type is
already a free-form column - no schema change needed there).

State machine reuse: job_store.TRANSITIONS is shaped for rendering
(CLAIMED -> PREPARING -> RENDERING -> UPLOADING -> COMPLETED). Rather than
extending that table (which render_worker.py also depends on - a change
there is exactly the kind of "existing render contract" risk the task
explicitly forbids), this worker walks the identical, unmodified state
sequence with topic-research-appropriate progress messages:
  CLAIMED -> PREPARING  ("프롬프트 준비")
  PREPARING -> RENDERING ("AI 호출 중")
  RENDERING -> UPLOADING ("결과 저장 중")
  UPLOADING -> COMPLETED
job_store.py itself is not touched by this Task.

AI provider key: GEMINI_API_KEY / CLAUDE_API_KEY are read from the local
process environment on the render PC (config.py's existing os.getenv
fallback) - no web-admin fetch, no service_role on this machine. Model
selection reuses the existing config.TOPIC_GENERATION_MODEL knob so an
operator can point Hermes at Claude by setting that env var to a
claude-prefixed model name; services/ai_router.py's Claude->Gemini fallback
then applies unchanged.

[AIR-0230] Added a second job_type: topic_benchmark_analyze. This is the
"which real, high-performing YouTube video should inform this category's
topics" step that used to only exist as a PRO-only manual feature in the
desktop user app (templates/pages/topic.html: search -> sort by views-vs-
subscribers -> pick one -> analyze). It runs here instead of in that app or
in auth-web because (a) transcript extraction depends on
youtube_transcript_api, a Python-only scraping library with no Next.js/
Vercel equivalent, and (b) this worker process is already always-running on
the render PC with a Python environment and network access. It reuses
existing, unmodified app functions rather than reimplementing them:
  - app/routers/youtube.py's search/videos/channels call shape (ported here
    as plain httpx calls since those are FastAPI route handlers, not
    importable service functions)
  - services/source_service.py::extract_text_from_youtube() for transcripts
  - services/gemini_service.py::analyze_comments() /
    extract_success_strategy() for the analysis + generalized-pattern
    extraction
Result is still always written to the local RESULTS_DIR first (unconditionally,
matching topic_research), and ADDITIONALLY reported to the central server via
central_client.complete_job(..., result_payload=...) when
AIRWORKER_CENTRAL_SERVER_URL is configured and this job came from a remote
claim - see the REMOTE_ENABLED / _try_remote_claim() additions below, which
mirror render_worker.py's dual local-vs-central job source pattern exactly
(same central_client.py, same job_store.py remote-ack bookkeeping - nothing
job-type-specific needed changing in either shared module). The web-admin
trigger itself (creating remote_hermes_queue rows) is a separate, still-open
follow-up - see docs/AIR_0230_HERMES_BENCHMARK_WORKER_ARCHITECTURE.md §2b.
"""
import asyncio
import json
import os
import re
import signal
import sys
import threading
import time
from pathlib import Path

import central_client
import job_store
from logging_setup import get_job_logger, get_logger
from shutdown_flag import clear_shutdown_flag, is_shutdown_requested
from worker_config import OUTPUT_DIR, STATE_DIR, WORKER_ID, WORKER_INSTANCE_ID, ensure_project_root_on_path

STATE_FILE = STATE_DIR / "hermes_worker.json"
PAUSE_FLAG_FILE = STATE_DIR / "hermes_worker.pause"
RESULTS_DIR = OUTPUT_DIR / "hermes_results"
AUDIT_DIR = OUTPUT_DIR / "hermes_audit"
logger = get_logger("hermes_worker")

_shutdown_requested = False
SUPPORTED_JOB_TYPES = ["topic_research", "topic_benchmark_analyze", "web_research", "script_plan_generate", "script_generate"]
DEFAULT_COUNT = 10
MAX_COUNT = 30

# [AIR-0230] Same dual-mode pattern as render_worker.py: local job_store is
# always tried first (dev/test convenience, no service_role needed); central
# claim only engages when this env var is set, and only for jobs that came
# from a remote claim (job_store.create_from_remote_claim tags them with
# source='central_server' + remote_job_id/lease_id - see _is_remote below).
LEASE_RENEW_INTERVAL_SECONDS = 3.0
REMOTE_ENABLED = bool(os.environ.get("AIRWORKER_CENTRAL_SERVER_URL"))
REMOTE_HEARTBEAT_INTERVAL_SECONDS = 30.0

# [AIR-0230] topic_benchmark_analyze tuning. Kept deliberately small - each
# analyzed candidate costs one YouTube search + a videos.list/channels.list
# call + (optional) transcript scrape + a comments.list call + two AI calls
# (analyze_comments, extract_success_strategy), so this is far more
# expensive per job than plain topic_research.
DEFAULT_BENCHMARK_CANDIDATES = 1
MAX_BENCHMARK_CANDIDATES = 3
DEFAULT_SEARCH_POOL_SIZE = 15
MAX_SEARCH_POOL_SIZE = 30
DEFAULT_COMMENT_SAMPLE_SIZE = 50
MAX_AUDIT_TRANSCRIPT_CHARS = 40000
MAX_AUDIT_COMMENT_CHARS = 3000


def _clip_audit_text(value: str | None, max_chars: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[truncated: {len(text) - max_chars} chars omitted]"


def _write_audit_payload(job_id: str, payload: dict) -> str:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    audit_path = AUDIT_DIR / f"{job_id}.benchmark_audit.json"
    audit_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(audit_path)


def _handle_signal(signum, frame):
    global _shutdown_requested
    logger.info(f"Received signal {signum}, requesting graceful shutdown")
    _shutdown_requested = True


def _should_stop() -> bool:
    return _shutdown_requested or is_shutdown_requested("hermes_worker")


def is_paused() -> bool:
    return PAUSE_FLAG_FILE.exists()


def write_state(status: str, current_job: dict | None, progress: int, job_id: str | None = None,
                 last_success_at: float | None = None, last_error: str | None = None):
    prev = {}
    if STATE_FILE.exists():
        try:
            prev = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prev = {}
    STATE_FILE.write_text(
        json.dumps(
            {
                "pid": None,
                "status": status,
                "current_job": current_job,
                "current_job_id": job_id,
                "progress": progress,
                "heartbeat_at": time.time(),
                "last_success_at": last_success_at if last_success_at is not None else prev.get("last_success_at"),
                "last_error": last_error if last_error is not None else prev.get("last_error", ""),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _extract_json(text: str) -> dict:
    """AI providers routinely wrap JSON in ```json fences or add a leading
    sentence despite being asked for raw JSON - strip fences first, then
    fall back to the first {...} span so a well-formed payload isn't
    rejected over surrounding chatter."""
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?)\s*```", stripped)
    if fence:
        stripped = fence.group(1).strip()
    start = stripped.find("{")
    if start < 0:
        raise json.JSONDecodeError("JSON object not found", stripped, 0)
    # Gemini may append a second JSON object or prose after the valid object.
    # Decode exactly one complete value and intentionally ignore trailing text.
    decoder = json.JSONDecoder()
    value, _ = decoder.raw_decode(stripped[start:])
    if not isinstance(value, dict):
        raise ValueError("AI response JSON must be an object")
    return value


def _metadata_language_name(language: str) -> str:
    return {
        "ko": "Korean",
        "en": "English",
        "ja": "Japanese",
        "vi": "Vietnamese",
        "th": "Thai",
    }.get(str(language or "").lower(), "Korean")


def _u(text: str) -> str:
    return text.encode("ascii").decode("unicode_escape")


def _fallback_publish_metadata(topic: str, upload_title: str, script: str, language: str) -> dict:
    title = (upload_title or topic or "Untitled").strip()
    script_excerpt = re.sub(r"\s+", " ", (script or "")).strip()
    if len(script_excerpt) > 260:
        script_excerpt = script_excerpt[:260].rstrip() + "..."
    if language == "ko":
        description = "\n\n".join(
            part for part in [
                title,
                script_excerpt,
                _u(r"\ub05d\uae4c\uc9c0 \uc2dc\uccad\ud574 \uc8fc\uc154\uc11c \uac10\uc0ac\ud569\ub2c8\ub2e4."),
            ] if part
        )
        tags = [
            tag for tag in [
                topic,
                _u(r"\ud669\ud63c\uc758 \uc0ac\ub791"),
                _u(r"\ub178\ub144 \uc774\uc57c\uae30"),
                _u(r"\uac00\uc871 \ub4dc\ub77c\ub9c8"),
                _u(r"\uac10\ub3d9 \uc0ac\uc5f0"),
            ] if tag
        ]
        hashtags = [
            _u(r"#\ud669\ud63c\uc758\uc0ac\ub791"),
            _u(r"#\uac00\uc871\ub4dc\ub77c\ub9c8"),
            _u(r"#\uac10\ub3d9\uc0ac\uc5f0"),
        ]
    else:
        description = "\n\n".join(part for part in [title, script_excerpt] if part)
        tags = [tag for tag in [topic, "story", "life", "inspiration"] if tag]
        hashtags = ["#story", "#inspiration"]
    return {
        "titles": [title],
        "description": description,
        "tags": tags[:12],
        "hashtags": hashtags[:10],
        "source": "worker_fallback",
    }


def _looks_corrupt_metadata_text(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if chr(0xFFFD) in text or re.search(r"\?{3,}", text):
        return True
    mojibake_markers = {0x5A9B, 0xF9DE, 0x0080, 0xAFC8, 0xBBC0, 0xB300, 0xC4F0}
    return any(ord(ch) in mojibake_markers for ch in text)


def _clean_metadata_description(description: str, fallback: str) -> str:
    paragraphs = []
    for paragraph in re.split(r"\n{2,}", str(description or "").strip()):
        normalized = paragraph.strip()
        if normalized and not _looks_corrupt_metadata_text(normalized):
            paragraphs.append(normalized)
    cleaned = "\n\n".join(paragraphs).strip()
    return cleaned or fallback


def _clean_metadata_list(values: list, fallback: list[str], *, hashtag: bool = False) -> list[str]:
    cleaned = []
    seen = set()
    for item in values:
        value = str(item or "").strip()
        if not value or _looks_corrupt_metadata_text(value):
            continue
        value = value if hashtag and value.startswith("#") else value.lstrip("#")
        if hashtag and not value.startswith("#"):
            value = f"#{value}"
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(value)
    return cleaned or fallback


def _normalize_publish_metadata(data: dict, topic: str, upload_title: str, script: str, language: str) -> dict:
    fallback = _fallback_publish_metadata(topic, upload_title, script, language)
    if not isinstance(data, dict):
        return fallback

    titles = data.get("titles")
    if not isinstance(titles, list):
        titles = []
    titles = [str(title).strip() for title in titles if str(title or "").strip()]
    primary_title = str(data.get("title") or upload_title or "").strip()
    if primary_title and primary_title not in titles:
        titles.insert(0, primary_title)
    if not titles:
        titles = fallback["titles"]

    tags = data.get("tags")
    if not isinstance(tags, list):
        tags = []
    hashtags = data.get("hashtags")
    if not isinstance(hashtags, list):
        hashtags = []

    description = _clean_metadata_description(str(data.get("description") or ""), fallback["description"])

    return {
        "titles": titles[:5],
        "description": description,
        "tags": _clean_metadata_list(tags, fallback["tags"])[:15],
        "hashtags": _clean_metadata_list(hashtags, fallback["hashtags"], hashtag=True)[:10],
        "source": data.get("source") or "air_worker",
    }


async def _generate_publish_metadata(
    ai_router, model: str, topic: str, upload_title: str, script: str,
    language: str, narrative_blueprint: dict, structure: dict,
) -> dict:
    language_name = _metadata_language_name(language)
    prompt = f"""
You are a YouTube upload metadata editor.

Create upload-ready metadata for this completed longform narration.

Return ONLY JSON:
{{
  "titles": ["5 clickable upload title options"],
  "description": "YouTube description text",
  "tags": ["tag without #"],
  "hashtags": ["#hashtag"]
}}

Rules:
- Write in {language_name}.
- Put the best title first.
- Titles must fit YouTube title style and stay under 100 characters.
- Description must be useful for upload, not a production note.
- Do not mention AI, worker, prompt, benchmark, QA, or internal process.
- Tags should be topical search phrases, not sentences.

TOPIC: {topic}
PRIMARY TITLE: {upload_title}
STORY BLUEPRINT: {json.dumps(narrative_blueprint or {}, ensure_ascii=False)}
SCENE STRUCTURE: {json.dumps(structure or {}, ensure_ascii=False)}
SCRIPT EXCERPT:
{(script or "")[:6000]}
"""
    try:
        raw = await ai_router.generate_text(
            prompt,
            model,
            temperature=0.55,
            max_tokens=2200,
            task_type="hermes_publish_metadata",
        )
        return _normalize_publish_metadata(_extract_json(raw), topic, upload_title, script, language)
    except Exception as e:
        fallback = _fallback_publish_metadata(topic, upload_title, script, language)
        fallback["metadata_error"] = str(e)
        return fallback


def _build_prompt(keyword: str, language: str, country: str, count: int) -> str:
    return (
        f"You are a topic research assistant for a long-form YouTube channel.\n"
        f"Research keyword/category: {keyword}\n"
        f"Target language: {language}\n"
        f"Target country/market: {country}\n"
        f"Generate exactly {count} distinct video topic candidates.\n\n"
        f"Respond with ONLY a JSON object, no markdown fences, no extra text, in this exact shape:\n"
        f'{{"topics": [{{"title": "string", "summary": "string", "sources": ["string", "..."]}}]}}\n'
        f"Each topic's \"sources\" is a short list of the reasoning/evidence behind why it's relevant "
        f"(trend signals, angle rationale) - not necessarily URLs."
    )


def _validate_payload(payload: dict) -> tuple[str, str, str, int]:
    keyword = (payload.get("keyword") or payload.get("topic") or "").strip()
    if not keyword:
        raise ValueError("payload.keyword (or payload.topic) is required for topic_research")
    language = (payload.get("language") or "ko").strip()
    country = (payload.get("country") or payload.get("target_market") or "").strip() or "global"
    count = payload.get("count", DEFAULT_COUNT)
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = DEFAULT_COUNT
    count = max(1, min(count, MAX_COUNT))
    return keyword, language, country, count


def _validate_benchmark_payload(payload: dict) -> tuple[str, str, str, int, int]:
    """[AIR-0230] category_id is deliberately NOT accepted here - the worker
    has no Supabase access (by design, see docs/AIR_WORKER_ARCHITECTURE.md
    §4's central/worker boundary), so whatever creates this job (web-admin,
    manual or scheduled - see the design doc §2b) must resolve the
    category's keywords/language/video_type itself and put the literal
    values in the payload."""
    keyword = (payload.get("keyword") or "").strip()
    if not keyword:
        raise ValueError("payload.keyword is required for topic_benchmark_analyze")
    language = (payload.get("language") or "ko").strip()

    video_type = (payload.get("video_type") or "longform").strip().lower()
    if video_type not in ("longform", "shorts"):
        video_type = "longform"

    max_candidates = payload.get("max_candidates", DEFAULT_BENCHMARK_CANDIDATES)
    try:
        max_candidates = int(max_candidates)
    except (TypeError, ValueError):
        max_candidates = DEFAULT_BENCHMARK_CANDIDATES
    max_candidates = max(1, min(max_candidates, MAX_BENCHMARK_CANDIDATES))

    search_pool_size = payload.get("search_pool_size", DEFAULT_SEARCH_POOL_SIZE)
    try:
        search_pool_size = int(search_pool_size)
    except (TypeError, ValueError):
        search_pool_size = DEFAULT_SEARCH_POOL_SIZE
    search_pool_size = max(max_candidates, min(search_pool_size, MAX_SEARCH_POOL_SIZE))

    raw_keywords = payload.get("search_keywords") or []
    if not isinstance(raw_keywords, list):
        raw_keywords = []
    search_keywords = []
    for item in raw_keywords:
        value = " ".join(str(item or "").split()).strip()
        if value and value != keyword and value not in search_keywords:
            search_keywords.append(value)
    if not search_keywords:
        search_keywords = [keyword]
    return keyword, language, video_type, max_candidates, search_pool_size, search_keywords


async def _youtube_get(path: str, params: dict) -> dict:
    """Same request shape as app/routers/youtube.py's endpoints, called
    directly here rather than through FastAPI (this process has no HTTP
    server of its own for the desktop app's routes, and importing FastAPI
    route handlers as plain functions isn't a supported pattern in that
    router - see its Request-bound signatures)."""
    import httpx
    from config import config

    keys = config.youtube_api_keys()
    if not keys:
        raise RuntimeError("YouTube API key is not configured")

    # A key can be blocked by API restrictions or exhaust its quota while
    # another project key remains healthy. Try the next key only for errors
    # where failover can help, without hiding malformed-request errors.
    retryable_statuses = {403, 429, 500, 502, 503, 504}
    failures = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for index, key in enumerate(keys, start=1):
            response = await client.get(
                f"{config.YOUTUBE_BASE_URL}/{path}",
                params={**params, "key": key},
            )
            try:
                data = response.json()
            except ValueError:
                data = {}
            if response.status_code == 200:
                if index > 1:
                    logger.info("YouTube API failover succeeded on backup key %s for %s", index, path)
                return data

            error_message = (data.get("error") or {}).get("message", "YouTube API Error")
            failures.append(f"key {index}: HTTP {response.status_code} - {error_message}")
            error_lower = str(error_message).lower()
            key_configuration_error = "api key" in error_lower or "apikey" in error_lower
            if response.status_code not in retryable_statuses and not key_configuration_error:
                break

    raise RuntimeError(f"YouTube API error ({path}) after {len(failures)} key(s): " + " | ".join(failures))


async def _search_candidate_videos(
    keyword: str,
    language: str,
    video_type: str,
    max_results: int,
    search_keywords: list[str] | None = None,
) -> tuple[list[dict], dict]:
    """Search several concrete queries and merge unique YouTube videos."""
    queries = []
    for item in [*(search_keywords or []), keyword]:
        value = " ".join(str(item or "").split()).strip()
        if value and value not in queries:
            queries.append(value)
    # Keep the API cost bounded while still exploring multiple interests.
    queries = queries[:10]
    candidates_by_id = {}
    query_audits = []
    per_query_limit = max(3, min(5, max_results))

    for query in queries:
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": per_query_limit,
            "order": "viewCount",
            "relevanceLanguage": language,
        }
        params["videoDuration"] = "short" if video_type == "shorts" else "medium"
        data = await _youtube_get("search", params)
        items = data.get("items", [])
        query_audits.append({"query": query, "params": params, "result_count": len(items)})
        for index, item in enumerate(items, start=1):
            video_id = (item.get("id") or {}).get("videoId")
            snippet = item.get("snippet") or {}
            channel_id = snippet.get("channelId")
            if not video_id or not channel_id or video_id in candidates_by_id:
                continue
            candidates_by_id[video_id] = {
                "search_rank": index,
                "search_query": query,
                "video_id": video_id,
                "channel_id": channel_id,
                "title": snippet.get("title", ""),
                "channel_title": snippet.get("channelTitle", ""),
                "published_at": snippet.get("publishedAt"),
                "description": snippet.get("description", ""),
                "thumbnail_url": ((snippet.get("thumbnails") or {}).get("high") or {}).get("url")
                    or ((snippet.get("thumbnails") or {}).get("default") or {}).get("url"),
            }

    # Keep a bounded pool from every query. Truncating here would make the
    # first query win before YouTube performance data has been compared.
    pool_limit = min(50, max_results * max(1, len(queries)))
    candidates = list(candidates_by_id.values())[:pool_limit]
    return candidates, {
        "endpoint": "search",
        "queries": query_audits,
        "query_count": len(query_audits),
        "result_count": sum(item["result_count"] for item in query_audits),
    }


async def _fetch_video_and_channel_stats(candidates: list[dict]) -> tuple[list[dict], dict]:
    """Adds view_count/subscriber_count/performance_ratio to each candidate.
    performance_ratio mirrors the "성과도(구독자 대비 조회수)" the desktop
    app's topic.html computes client-side only (never sent to a server) -
    here it's the actual ranking signal, not just a display column."""
    if not candidates:
        return [], {"video_ids": [], "channel_ids": [], "videos_response": {}, "channels_response": {}}

    video_ids = ",".join(c["video_id"] for c in candidates)
    channel_ids = ",".join(sorted({c["channel_id"] for c in candidates}))

    videos_data = await _youtube_get("videos", {"part": "statistics", "id": video_ids})
    channels_data = await _youtube_get("channels", {"part": "statistics", "id": channel_ids})
    stats_audit = {
        "video_ids": video_ids.split(",") if video_ids else [],
        "channel_ids": channel_ids.split(",") if channel_ids else [],
        "videos_response": videos_data,
        "channels_response": channels_data,
    }

    view_counts = {
        item["id"]: int((item.get("statistics") or {}).get("viewCount", 0) or 0)
        for item in videos_data.get("items", [])
    }
    subscriber_counts = {
        item["id"]: int((item.get("statistics") or {}).get("subscriberCount", 0) or 0)
        for item in channels_data.get("items", [])
    }

    enriched = []
    for c in candidates:
        views = view_counts.get(c["video_id"], 0)
        subs = subscriber_counts.get(c["channel_id"], 0)
        performance_ratio = round(views / subs, 2) if subs > 0 else 0.0
        enriched.append({
            **c,
            "view_count": views,
            "subscriber_count": subs,
            "performance_ratio": performance_ratio,
        })
    return enriched, stats_audit


def _rank_search_keywords(candidates: list[dict]) -> list[dict]:
    """Rank concrete search phrases from real YouTube candidate performance.

    YouTube Data API does not expose search-volume data. This ranking therefore
    uses observable signals from the returned videos: channel-relative views,
    absolute views, and recency. Log scaling prevents one giant channel from
    overwhelming the other signals.
    """
    from datetime import datetime, timezone
    from math import log1p

    groups: dict[str, list[dict]] = {}
    now = datetime.now(timezone.utc)
    for candidate in candidates:
        query = str(candidate.get("search_query") or "").strip()
        if query:
            groups.setdefault(query, []).append(candidate)

    raw = []
    for query, items in groups.items():
        performance_values = sorted(
            [float(item.get("performance_ratio") or 0) for item in items], reverse=True
        )
        view_values = sorted(
            [int(item.get("view_count") or 0) for item in items], reverse=True
        )
        recent_values = []
        for item in items:
            try:
                published = datetime.fromisoformat(str(item.get("published_at")).replace("Z", "+00:00"))
                age_days = max(0.0, (now - published).total_seconds() / 86400.0)
                recent_values.append(max(0.0, 1.0 - min(age_days, 730.0) / 730.0))
            except (TypeError, ValueError):
                recent_values.append(0.0)

        top_count = min(3, len(items))
        raw.append({
            "query": query,
            "candidate_count": len(items),
            "top_performance_ratio": round(performance_values[0] if performance_values else 0.0, 2),
            "top_view_count": view_values[0] if view_values else 0,
            "recentness": round(sum(recent_values) / len(recent_values), 4) if recent_values else 0.0,
            "_performance_signal": sum(log1p(v) for v in performance_values[:top_count]) / max(1, top_count),
            "_view_signal": sum(log1p(v) for v in view_values[:top_count]) / max(1, top_count),
            "_recent_signal": sum(recent_values) / max(1, len(recent_values)),
        })

    def normalize(values: list[float], value: float) -> float:
        if not values or max(values) == min(values):
            return 0.5
        return (value - min(values)) / (max(values) - min(values))

    performance_values = [item["_performance_signal"] for item in raw]
    view_values = [item["_view_signal"] for item in raw]
    recent_values = [item["_recent_signal"] for item in raw]
    ranked = []
    for item in raw:
        score = (
            normalize(performance_values, item["_performance_signal"]) * 0.50
            + normalize(view_values, item["_view_signal"]) * 0.30
            + normalize(recent_values, item["_recent_signal"]) * 0.20
        )
        ranked.append({
            "query": item["query"],
            "score": round(score * 100, 2),
            "candidate_count": item["candidate_count"],
            "top_performance_ratio": item["top_performance_ratio"],
            "top_view_count": item["top_view_count"],
            "recentness": item["recentness"],
        })
    return sorted(ranked, key=lambda item: item["score"], reverse=True)


async def _fetch_comments_with_audit(video_id: str, max_results: int = DEFAULT_COMMENT_SAMPLE_SIZE) -> tuple[list[str], dict]:
    """Best-effort: comments can be disabled on a video - that should not
    fail the whole job (analyze_comments() already handles an empty list;
    it just leans more on the transcript)."""
    params = {"part": "snippet", "videoId": video_id, "maxResults": max_results, "order": "relevance"}
    try:
        data = await _youtube_get("commentThreads", params)
    except Exception as e:
        return [], {
            "endpoint": "commentThreads",
            "params": params,
            "error": str(e),
            "count": 0,
            "items": [],
        }

    comments = []
    comment_items = []
    for item in data.get("items", []):
        snippet = ((item.get("snippet") or {}).get("topLevelComment") or {}).get("snippet", {})
        text = snippet.get("textDisplay", "")
        if text:
            comments.append(text)
            comment_items.append({
                "author_display_name": snippet.get("authorDisplayName"),
                "like_count": snippet.get("likeCount"),
                "published_at": snippet.get("publishedAt"),
                "updated_at": snippet.get("updatedAt"),
                "text": _clip_audit_text(text, MAX_AUDIT_COMMENT_CHARS),
            })
    return comments, {
        "endpoint": "commentThreads",
        "params": params,
        "count": len(comments),
        "items": comment_items,
        "raw_response": data,
    }


async def _fetch_comments(video_id: str, max_results: int = DEFAULT_COMMENT_SAMPLE_SIZE) -> list[str]:
    comments, _audit = await _fetch_comments_with_audit(video_id, max_results=max_results)
    return comments


def _is_remote(job: dict) -> bool:
    return job.get("source") == "central_server" and bool(job.get("remote_job_id"))


def _start_lease_renewal(job: dict, job_log) -> tuple[threading.Thread, threading.Event] | tuple[None, None]:
    """[AIR-0230] Ported verbatim from render_worker.py - nothing here is
    render-specific, it only touches job_store's generic remote-claim
    fields (remote_job_id/lease_id/job_id) and central_client.renew_lease()
    (job-type-agnostic)."""
    if not _is_remote(job):
        return None, None
    stop_event = threading.Event()

    def _loop():
        while not stop_event.wait(LEASE_RENEW_INTERVAL_SECONDS):
            try:
                result = central_client.renew_lease(job["remote_job_id"], job["lease_id"], WORKER_INSTANCE_ID)
                job_store.update_lease(job["job_id"], result["lease_expires_at"])
                job_log.info(f"Lease renewed, expires_at={result['lease_expires_at']:.1f}")
            except Exception as e:
                job_log.warning(f"Lease renewal failed (non-fatal, will retry next interval): {e}")

    t = threading.Thread(target=_loop, daemon=True, name=f"lease-renew-{job['job_id']}")
    t.start()
    return t, stop_event


def _report_remote_outcome(job: dict, job_log, *, success: bool, output_ref: str = "",
                            result_payload: dict | None = None, error_code: str = "", error_message: str = "") -> None:
    """[AIR-0230] Ported verbatim from render_worker.py's
    _report_remote_outcome (see that function's own comment for the exact
    409-crash bug this structure avoids: central-reporting failure must
    never be allowed to alter/interrupt a local outcome that already
    succeeded or failed on its own terms). Only addition vs. the render
    version: result_payload, forwarded to central_client.complete_job() so
    topic_benchmark_analyze's compact analysis JSON lands in
    remote_hermes_queue.result_payload without a second fetch."""
    if not _is_remote(job):
        return
    idem_key = job["job_id"]
    try:
        if success:
            central_client.complete_job(job["remote_job_id"], job["lease_id"], WORKER_INSTANCE_ID, idem_key, output_ref, result_payload=result_payload)
        else:
            central_client.fail_job(job["remote_job_id"], job["lease_id"], WORKER_INSTANCE_ID, idem_key, error_code, error_message)
        job_store.mark_remote_acked(job["job_id"])
        job_log.info(f"Central server acknowledged {'completion' if success else 'failure'}")
    except central_client.LeaseConflict as e:
        try:
            job_store.mark_remote_ack_abandoned(job["job_id"])
        except Exception:
            pass
        job_log.warning(f"Central server rejected this {'completion' if success else 'failure'} report as stale (lease no longer active) - giving up on this report, NOT retrying: {e}")
    except Exception as e:
        try:
            job_store.mark_remote_ack_pending(job["job_id"])
        except Exception:
            pass
        job_log.warning(f"Could not report {'completion' if success else 'failure'} to central server ({e}) - queued for retry, local status is final regardless")


def _flush_pending_remote_acks() -> None:
    """[AIR-0230] Ported verbatim from render_worker.py - job_store's
    pending-ack bookkeeping is shared/generic, not render-specific."""
    for job in job_store.list_pending_remote_acks():
        job_log = get_job_logger(job["job_id"])
        if job["status"] == job_store.COMPLETED:
            _report_remote_outcome(job, job_log, success=True, output_ref=job.get("output_path") or "")
        else:
            _report_remote_outcome(job, job_log, success=False, error_code=job.get("error_code") or "", error_message=job.get("error_message") or "")


def _try_remote_claim() -> dict | None:
    """[AIR-0230] Ported verbatim from render_worker.py - central_client and
    job_store.create_from_remote_claim are both already job-type-agnostic
    (job_type/payload are passed straight through)."""
    try:
        claimed = central_client.claim_job(WORKER_ID, WORKER_INSTANCE_ID, SUPPORTED_JOB_TYPES)
    except central_client.AuthError as e:
        logger.error(f"Central server rejected our worker token (not retrying this tick): {e}")
        return None
    except central_client.CentralServerUnavailable as e:
        logger.warning(f"Central server unreachable (will retry next tick): {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during central server claim (will retry next tick): {e}")
        return None
    if not claimed:
        return None
    local_job_id = job_store.create_from_remote_claim(
        remote_job_id=claimed["job_id"], job_type=claimed["job_type"], payload=claimed["payload"],
        priority=claimed["priority"], lease_id=claimed["lease_id"], worker_instance_id=WORKER_INSTANCE_ID,
        lease_expires_at=claimed["lease_expires_at"],
    )
    return job_store.get_job(local_job_id)


def _send_remote_heartbeat() -> None:
    try:
        central_client.heartbeat(WORKER_ID, WORKER_INSTANCE_ID)
    except central_client.AuthError as e:
        logger.error(f"Central server rejected heartbeat token (local queue will continue): {e}")
    except central_client.CentralServerUnavailable as e:
        logger.warning(f"Central heartbeat unavailable (local queue will continue): {e}")
    except Exception as e:
        logger.warning(f"Unexpected central heartbeat error (local queue will continue): {e}")


def _process_topic_research(job: dict, job_id: str, job_log) -> tuple[str, dict]:
    """Returns (output_ref, result_payload) - both are forwarded to
    _report_remote_outcome() by process_one_job() when this job came from a
    central claim; harmless/unused for a locally-submitted job."""
    job_store.transition(job_id, job_store.PREPARING, reason="preparing prompt")
    write_state("preparing", job, 0, job_id)
    job_log.info("-> PREPARING (building prompt)")

    keyword, language, country, count = _validate_payload(job["payload"])
    prompt = _build_prompt(keyword, language, country, count)

    job_store.transition(job_id, job_store.RENDERING, reason="calling AI provider")
    write_state("running", job, 30, job_id)
    job_log.info("-> RENDERING (calling AI provider for topic research)")

    ensure_project_root_on_path()
    from config import Config, config
    from services import ai_router
    import asyncio

    Config.refresh_remote_keys_if_stale()

    model = config.TOPIC_GENERATION_MODEL
    raw_text = asyncio.run(
        ai_router.generate_text(
            prompt, model=model, temperature=0.9, max_tokens=4096,
            task_type="hermes_topic_research",
        )
    )
    parsed = _extract_json(raw_text)
    topics = parsed.get("topics")
    if not isinstance(topics, list) or not topics:
        raise ValueError(f"AI response did not contain a non-empty 'topics' list: {raw_text[:300]}")

    job_store.transition(job_id, job_store.UPLOADING, reason="saving result")
    write_state("running", job, 90, job_id)
    job_log.info(f"-> UPLOADING (saving {len(topics)} topic candidates)")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = RESULTS_DIR / f"{job_id}.json"
    completed_at = time.time()
    result_payload = {
        "job_id": job_id,
        "job_type": "topic_research",
        "status": "COMPLETED",
        "topics": topics,
        "model": model,
        "completed_at": completed_at,
        "error": None,
        "_payload_data": job.get("payload", {}),
    }
    result_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    job_store.transition(job_id, job_store.COMPLETED, reason="topic research complete", output_path=str(result_path))
    job_log.info(f"-> COMPLETED, result at {result_path}")
    logger.info(f"Completed job {job_id} -> {result_path}")
    return str(result_path), result_payload


def _process_topic_benchmark_analyze(job: dict, job_id: str, job_log) -> tuple[str, dict]:
    """Returns (output_ref, result_payload) - see _process_topic_research's
    docstring."""
    job_store.transition(job_id, job_store.PREPARING, reason="validating payload")
    write_state("preparing", job, 0, job_id)
    job_log.info("-> PREPARING (validating payload)")

    keyword, language, video_type, max_candidates, search_pool_size, search_keywords = _validate_benchmark_payload(job["payload"])

    job_store.transition(job_id, job_store.RENDERING, reason="searching YouTube for high-performing videos")
    write_state("running", job, 10, job_id)
    job_log.info(f"-> RENDERING (keyword={keyword!r}, video_type={video_type}, pool={search_pool_size}, pick={max_candidates})")

    ensure_project_root_on_path()
    from services.gemini_service import gemini_service
    from services.source_service import source_service
    import asyncio

    async def _run_analysis() -> tuple[list[dict], dict]:
        audit_payload = {
            "job_id": job_id,
            "job_type": "topic_benchmark_analyze",
            "keyword": keyword,
            "language": language,
            "video_type": video_type,
            "max_candidates": max_candidates,
            "search_pool_size": search_pool_size,
            "started_at": time.time(),
            "search": None,
            "stats": None,
            "fallbacks": [],
            "analyzed_candidates": [],
        }

        try:
            candidates, search_audit = await _search_candidate_videos(
                keyword, language, video_type, search_pool_size, search_keywords
            )
            audit_payload["search"] = search_audit
            if not candidates:
                raise ValueError("No candidates returned from YouTube search")
        except Exception as search_e:
            raise RuntimeError(f"YouTube search unavailable; benchmark cannot continue: {search_e}") from search_e
            audit_payload["fallbacks"].append({"stage": "search", "error": str(search_e), "applied_at": time.time()})
            candidates = [
                {
                    "search_rank": 1,
                    "video_id": "dummy_vid_123",
                    "channel_id": "dummy_channel_456",
                    "title": f"[fallback] {keyword} reference video unavailable",
                    "channel_title": "fallback benchmark channel",
                    "published_at": None,
                    "description": "",
                    "thumbnail_url": None,
                }
            ]
            audit_payload["search"] = {
                "endpoint": "search",
                "params": {
                    "part": "snippet",
                    "q": keyword,
                    "type": "video",
                    "maxResults": search_pool_size,
                    "order": "viewCount",
                    "relevanceLanguage": language,
                    "videoDuration": "short" if video_type == "shorts" else "medium",
                },
                "error": str(search_e),
                "result_count": 0,
                "raw_response": None,
            }

        try:
            enriched, stats_audit = await _fetch_video_and_channel_stats(candidates)
            audit_payload["stats"] = stats_audit
        except Exception as stats_e:
            raise RuntimeError(f"YouTube statistics unavailable; benchmark cannot continue: {stats_e}") from stats_e
            audit_payload["fallbacks"].append({"stage": "stats", "error": str(stats_e), "applied_at": time.time()})
            enriched = []
            for c in candidates:
                enriched.append({
                    **c,
                    "view_count": 150000,
                    "subscriber_count": 12000,
                    "performance_ratio": 12.5,
                    "performance_data_source": "fallback",
                })
            audit_payload["stats"] = {
                "video_ids": [c["video_id"] for c in candidates],
                "channel_ids": sorted({c["channel_id"] for c in candidates}),
                "error": str(stats_e),
                "videos_response": None,
                "channels_response": None,
            }

        keyword_ranking = _rank_search_keywords(enriched)
        audit_payload["search"]["keyword_ranking"] = keyword_ranking
        keyword_scores = {item["query"]: item["score"] for item in keyword_ranking}
        for candidate in enriched:
            candidate.setdefault("performance_data_source", "youtube_api")
            candidate["keyword_score"] = keyword_scores.get(candidate.get("search_query"), 0.0)
        enriched.sort(
            key=lambda c: (
                c.get("keyword_score", 0.0),
                c.get("performance_ratio", 0.0),
                c.get("view_count", 0),
            ),
            reverse=True,
        )

        # Preserve keyword diversity when more than one reference video is
        # requested, while still prioritizing the highest-scoring queries.
        top_candidates = []
        used_queries = set()
        for candidate in enriched:
            query = candidate.get("search_query") or ""
            if query in used_queries:
                continue
            top_candidates.append(candidate)
            used_queries.add(query)
            if len(top_candidates) >= max_candidates:
                break
        if len(top_candidates) < max_candidates:
            selected_ids = {candidate.get("video_id") for candidate in top_candidates}
            for candidate in enriched:
                if candidate.get("video_id") in selected_ids:
                    continue
                top_candidates.append(candidate)
                if len(top_candidates) >= max_candidates:
                    break

        for index, candidate in enumerate(top_candidates, start=1):
            video_id = str(candidate.get("video_id") or "")
            if video_id.startswith("dummy_"):
                job_log.warning("REFERENCE_VIDEO unavailable: YouTube search returned a fallback placeholder")
                continue
            job_log.info(
                "REFERENCE_VIDEO #%s title=%r channel=%r views=%s ratio=%s source=%s url=https://www.youtube.com/watch?v=%s",
                index,
                candidate.get("title") or "",
                candidate.get("channel_title") or "",
                candidate.get("view_count") or 0,
                candidate.get("performance_ratio") or 0,
                candidate.get("performance_data_source"),
                video_id,
            )

        results = []
        for candidate in top_candidates:
            video_id = candidate["video_id"]

            transcript = None
            transcript_error = None
            try:
                extracted = await source_service.extract_text_from_youtube(
                    f"https://www.youtube.com/watch?v={video_id}"
                )
                transcript = extracted.get("content")
            except Exception as e:
                # Best-effort: plenty of high-performing videos have no captions.
                job_log.warning(f"Transcript extraction failed for {video_id} (continuing without it): {e}")
                transcript_error = str(e)

            comments, comments_audit = await _fetch_comments_with_audit(video_id)
            analysis = await gemini_service.analyze_comments(
                comments=comments, video_title=candidate["title"], transcript=transcript
            )

            success_strategies = []
            if not analysis.get("error"):
                try:
                    success_strategies = await gemini_service.extract_success_strategy(analysis)
                except Exception as e:
                    job_log.warning(f"Success-strategy extraction failed for {video_id}: {e}")

            results.append({
                **candidate,
                "comment_count_analyzed": len(comments),
                "has_transcript": bool(transcript),
                "analysis": analysis,
                "success_strategies": success_strategies,
            })
            audit_payload["analyzed_candidates"].append({
                "candidate": candidate,
                "transcript": {
                    "has_transcript": bool(transcript),
                    "char_count": len(transcript or ""),
                    "error": transcript_error,
                    "content": _clip_audit_text(transcript, MAX_AUDIT_TRANSCRIPT_CHARS),
                },
                "comments": comments_audit,
                "gemini_analysis": analysis,
                "success_strategies": success_strategies,
                "analyzed_at": time.time(),
            })

        audit_payload["completed_at"] = time.time()
        return results, audit_payload

    results, audit_payload = asyncio.run(_run_analysis())

    job_store.transition(job_id, job_store.UPLOADING, reason="saving result")
    write_state("running", job, 90, job_id)
    job_log.info(f"-> UPLOADING (saving benchmark analysis for {len(results)} video(s))")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = RESULTS_DIR / f"{job_id}.json"
    completed_at = time.time()
    audit_path = _write_audit_payload(job_id, audit_payload)
    analyzed_candidates = audit_payload.get("analyzed_candidates") or []
    audit_summary = {
        "audit_path": audit_path,
        "search_result_count": ((audit_payload.get("search") or {}).get("result_count") or 0),
        "analyzed_video_count": len(analyzed_candidates),
        "stored_comment_count": sum(((c.get("comments") or {}).get("count") or 0) for c in analyzed_candidates),
        "stored_transcript_chars": sum(((c.get("transcript") or {}).get("char_count") or 0) for c in analyzed_candidates),
        "fallbacks": audit_payload.get("fallbacks") or [],
    }
    result_payload = {
        "job_id": job_id,
        "job_type": "topic_benchmark_analyze",
        "status": "COMPLETED",
        "keyword": keyword,
        "language": language,
        "video_type": video_type,
        "candidates": results,
        "audit_path": audit_path,
        "audit_summary": audit_summary,
        "completed_at": completed_at,
        "error": None,
    }
    result_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    job_store.transition(job_id, job_store.COMPLETED, reason="benchmark analysis complete", output_path=str(result_path))
    job_log.info(f"-> COMPLETED, result at {result_path}; audit at {audit_path}")
    logger.info(f"Completed job {job_id} -> {result_path}; audit -> {audit_path}")
    return str(result_path), result_payload

def _process_web_research(job: dict, job_id: str, job_log) -> tuple[str, dict]:
    payload = job.get("payload") or {}
    topic = str(payload.get("topic") or "").strip()
    upload_title = str(payload.get("upload_title") or topic).strip()
    category = str(payload.get("category") or "").strip()
    benchmark_sources = [
        source for source in (payload.get("benchmark_sources") or [])
        if isinstance(source, dict) and source.get("url")
    ]
    if not topic:
        raise ValueError("payload.topic is required for web_research")
    job_store.transition(job_id, job_store.PREPARING, reason="preparing Gemini web research")
    write_state("preparing", job, 0, job_id)
    ensure_project_root_on_path()
    from config import Config, config
    from services.gemini_service import gemini_service
    Config.refresh_remote_keys_if_stale()
    model = config.SCRIPT_PLANNING_MODEL or config.TOPIC_GENERATION_MODEL or "gemini-2.5-flash"
    # Google Search grounding is a Gemini operation. A stale admin setting
    # may contain a Claude model id, which Gemini rejects as "not found".
    if str(model).lower().startswith("claude"):
        model = "gemini-3-flash-preview"
    prompt = f"""Research factual material for a Korean YouTube script.
CATEGORY: {category}
UPLOAD TITLE: {upload_title}
CATEGORY: {topic}

Use Google Search to find reliable context relevant to the upload title and category. Do not invent events, statistics, quotes, people, or sources. For fictional/story categories, research only useful historical, cultural, or real-world context and clearly separate it from creative invention.
Return JSON only:
{{"research_brief":"short factual context", "verified_facts":[{{"claim":"a usable fact", "caution":"scope/date/uncertainty"}}], "story_material":"how these facts can enrich the script without claiming fiction is real", "risk_notes":["facts that must not be overstated"]}}
"""
    job_store.transition(job_id, job_store.RENDERING, reason="Gemini Google Search grounding")
    write_state("running", job, 30, job_id)
    try:
        result = asyncio.run(
            asyncio.wait_for(
                gemini_service.generate_grounded_research(prompt, model=model),
                timeout=75,
            )
        )
    except Exception as exc:
        # Search grounding can hang or be temporarily unavailable. Continue
        # with the real benchmark URLs instead of blocking the whole video.
        if not benchmark_sources:
            raise
        job_log.warning("WEB_RESEARCH fallback to benchmark sources: %s", exc)
        result = {
            "text": "외부 웹 조사는 일시적으로 사용할 수 없어 실제 벤치마크 영상의 제목과 공개 성과 데이터를 근거로 기획을 이어갑니다.",
            "sources": benchmark_sources,
            "search_queries": [],
            "grounding_supports": [],
        }
    if not result.get("sources"):
        if not benchmark_sources:
            raise ValueError("Gemini 웹 조사에서 검증 가능한 출처를 받지 못했습니다.")
        result["sources"] = benchmark_sources
    try:
        research = _extract_json(result.get("text") or "{}")
    except Exception:
        research = {"research_brief": result.get("text") or "", "verified_facts": [], "story_material": "", "risk_notes": []}
    bundle = {
        "topic": topic, "upload_title": upload_title, "category": category,
        "research_brief": research.get("research_brief") or "",
        "verified_facts": research.get("verified_facts") or [],
        "story_material": research.get("story_material") or "",
        "risk_notes": research.get("risk_notes") or [],
        "sources": result["sources"], "search_queries": result.get("search_queries") or [],
        "grounding_supports": result.get("grounding_supports") or [], "researched_at": time.time(),
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = RESULTS_DIR / f"{job_id}.json"
    result_payload = {"job_id": job_id, "job_type": "web_research", "status": "COMPLETED", "research_bundle": bundle}
    result_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    job_store.transition(job_id, job_store.COMPLETED, reason="Gemini web research complete", output_path=str(result_path))
    job_log.info("WEB_RESEARCH complete: %d sources; queries=%r", len(bundle["sources"]), bundle["search_queries"])
    for source in bundle["sources"]:
        job_log.info("WEB_SOURCE title=%r url=%s", source["title"], source["url"])
    return str(result_path), result_payload


def _validate_script_plan_payload(payload: dict) -> tuple[str, str, int, str, str, str, dict | None, str, dict]:
    """[AIR-0230 §2d] topic_queue_id is required (not optional) - unlike
    topic_research/topic_benchmark_analyze, this job's whole purpose is to
    write its result back onto a SPECIFIC topics_queue row (see
    auth-web/app/api/internal/worker/jobs/[jobId]/complete/route.ts's
    sync-back step) - a script plan with nowhere to land is pointless."""
    topic_queue_id = str(payload.get("topic_queue_id") or "").strip()
    if not topic_queue_id:
        raise ValueError("payload.topic_queue_id is required for script_plan_generate")
    topic = str(payload.get("topic") or "").strip()
    if not topic:
        raise ValueError("payload.topic is required for script_plan_generate")
    target_duration = payload.get("target_duration_seconds", 60)
    try:
        target_duration = max(15, int(target_duration))
    except (TypeError, ValueError):
        target_duration = 60
    script_style = str(payload.get("script_style") or "default").strip()
    image_style = str(payload.get("image_style") or "").strip()
    language = str(payload.get("language") or "ko").strip()
    benchmark_analysis = payload.get("benchmark_analysis") if isinstance(payload.get("benchmark_analysis"), dict) else None
    title_generation = payload.get("title_generation") if isinstance(payload.get("title_generation"), dict) else {}
    upload_title = str(payload.get("upload_title") or title_generation.get("generated_title") or "").strip()
    return topic_queue_id, topic, target_duration, script_style, image_style, language, benchmark_analysis, upload_title, title_generation


def _resolve_image_style_directive(image_style: str, image_style_selection: dict | None = None) -> tuple[str, str]:
    """Resolve an image style key into the concrete prompt directive used by
    desktop image generation. Worker pre-generation must honor the same admin
    style choice because STD users now see these prompts immediately."""
    style_key = str(image_style or "realistic").strip().lower() or "realistic"
    style_prompt = ""
    try:
        ensure_project_root_on_path()
        import database as db
        from app.utils import STYLE_PROMPTS

        presets = db.get_style_presets()
        style_data = presets.get(style_key, {}) if isinstance(presets, dict) else {}
        style_prompt = (
            str(style_data.get("prompt_value") or "").strip()
            or str(STYLE_PROMPTS.get(style_key, "")).strip()
        )
    except Exception as e:
        logger.warning(f"Image style resolution failed for {style_key}: {e}")

    if not style_prompt:
        style_prompt = style_key

    # The selection rationale is internal metadata, not a visual instruction.
    # Keeping it out of the generator directive prevents Korean decision text
    # or administrative wording from leaking into the rendered image prompt.
    return style_key, style_prompt


def _select_worker_image_style_for_plan(
    job: dict,
    payload: dict,
    topic: str,
    upload_title: str,
) -> tuple[str, dict | None]:
    explicit_style = str(payload.get("image_style") or "").strip()
    explicit_selection = payload.get("image_style_selection") if isinstance(payload.get("image_style_selection"), dict) else None
    if explicit_style:
        return explicit_style, explicit_selection

    category_id = str(job.get("category_id") or payload.get("category_id") or "").strip()
    category_name = str(payload.get("category") or payload.get("category_name") or "").strip()
    category_default = "realistic"

    if category_id or category_name:
        try:
            ensure_project_root_on_path()
            from services.web_admin_client import web_admin_client

            for category in web_admin_client.fetch_categories("id,name,default_image_style"):
                row_id = str(category.get("id") or "")
                row_name = str(category.get("name") or "").strip()
                if (category_id and row_id == category_id) or (category_name and row_name == category_name):
                    category_name = category_name or row_name
                    category_default = str(category.get("default_image_style") or category_default).strip() or category_default
                    break
        except Exception as e:
            logger.warning(f"Worker image style category lookup failed: {e}")

    try:
        ensure_project_root_on_path()
        from hermes_autopilot import HermesAutopilotManager

        manager = HermesAutopilotManager()
        manual_override = None
        if category_name:
            manual_override = (manager.settings.get("category_image_style_overrides") or {}).get(category_name)
        selection = asyncio.run(
            manager._select_image_style(
                category_name or "uncategorized",
                topic,
                upload_title,
                category_default,
                manual_override,
            )
        )
        selected_style = str(selection.get("assigned_image_style") or category_default or "realistic").strip() or "realistic"
        return selected_style, selection
    except Exception as e:
        logger.warning(f"Worker image style selection failed; using fallback {category_default}: {e}")
        return category_default, {
            "assigned_image_style": category_default,
            "automatic_style": category_default,
            "selection_source": "worker_fallback",
            "reason": "Worker image style selection failed, so the category fallback style was used.",
        }


def _mostly_english(value: str) -> bool:
    letters = re.findall(r"[A-Za-z]", value or "")
    hangul = re.findall(r"[\uac00-\ud7a3]", value or "")
    return len(letters) >= 40 and len(letters) >= len(hangul) * 2


def _validate_media_prompt_quality(media: dict, scene_label: str) -> None:
    image_prompt = str(media.get("image_prompt") or "").strip()
    video_prompt = str(media.get("video_prompt") or "").strip()
    if len(image_prompt) < 220:
        raise ValueError(f"image_prompt too short for scene {scene_label}")
    if len(video_prompt) < 260:
        raise ValueError(f"video_prompt too short for scene {scene_label}")
    if not _mostly_english(image_prompt):
        raise ValueError(f"image_prompt is not English enough for scene {scene_label}")
    if not _mostly_english(video_prompt):
        raise ValueError(f"video_prompt is not English enough for scene {scene_label}")
    generic_terms = ("cinematic scene", "beautiful scene", "high quality image", "camera moves")
    if any(term in image_prompt.lower() for term in generic_terms):
        raise ValueError(f"image_prompt contains generic filler for scene {scene_label}")
    if not re.search(r"\b(push-in|push in|dolly|zoom|pan|tilt|tracking|handheld|crane|pull-back|pull back|rack focus|locked-off|locked off|drift)\b", video_prompt, re.I):
        raise ValueError(f"video_prompt lacks a concrete camera movement for scene {scene_label}")
    positive_audio_patterns = (
        r"\b(with|include|add|generate|create|use)\s+(dialogue|narration|voice-over|voiceover|subtitles|captions|sound effects|music|audio)\b",
        r"\b(dialogue|narration|voice-over|voiceover|subtitles|captions|sound effects|music|audio)\s+(plays|starts|rises|swells|is heard|can be heard)\b",
    )
    if any(re.search(pattern, video_prompt, re.I) for pattern in positive_audio_patterns):
        raise ValueError(f"video_prompt contains positive audio/text instructions for scene {scene_label}")
    discontinuous_positive_patterns = (
        r"\b(hard cut|jump cut)\b",
        r"(?<!\bno\s)\bteleport(?:ation)?\b",
    )
    if any(re.search(pattern, video_prompt, re.I) for pattern in discontinuous_positive_patterns):
        raise ValueError(f"video_prompt contains a discontinuous scene change for scene {scene_label}")


def _generate_scene_media_prompts(
    structure: dict,
    topic: str,
    upload_title: str,
    image_style: str,
    image_style_selection: dict | None,
    language: str,
    job_log,
) -> dict:
    """Attach image/video generation prompts without changing scene boundaries."""
    scenes = structure.get("scenes") if isinstance(structure, dict) else None
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("Cannot generate media prompts without planned scenes")

    from config import Config, config
    from services import ai_router

    Config.refresh_remote_keys_if_stale()
    model = config.IMAGE_PROMPT_MODEL or config.SCRIPT_PLANNING_MODEL or config.SCRIPT_GENERATION_MODEL
    if str(model).lower().startswith("claude"):
        model = "gemini-2.5-flash"
    image_style_key, image_style_directive = _resolve_image_style_directive(image_style, image_style_selection)
    prompt = f"""
You are the visual director for a YouTube video production pipeline.
Create production-ready image and AI-video prompts for every scene below.

TOPIC: {topic}
UPLOAD TITLE: {upload_title}
LANGUAGE OF NARRATION: {language}
ADMIN-SELECTED IMAGE STYLE KEY: {image_style_key}
ADMIN-SELECTED IMAGE STYLE DIRECTIVE:
{image_style_directive}
SCENE PLAN:
{json.dumps(scenes, ensure_ascii=False, indent=2)}

Rules:
1. Return exactly one result for every input scene, preserving scene_id and scene_order.
2. Do not change scene boundaries, duration, story facts, or character identity.
3. Treat the admin-selected image style as the visual language for the whole video. Integrate it naturally into every scene; do not mix incompatible art styles or repeat it as a meaningless keyword list.
4. image_prompt must describe one coherent keyframe with: primary subject, visible action, setting, historically/culturally accurate era and location, foreground/midground/background composition, shot size and angle, facial emotion or readable body language, lighting, color palette, and continuity anchors.
5. For recurring characters, preserve the same age range, facial traits, hairstyle, clothing, accessories, body type, and dominant colors unless the scene explicitly changes them. Preserve recurring locations and important props as well.
6. image_prompt quality guardrails: include "no text, no words, no letters, no labels, no watermarks, no captions"; for human characters include correct anatomy, exactly two arms, exactly two hands, anatomically correct hands, no extra limbs, no fused fingers, no duplicated people.
7. Treat image_prompt as the exact opening keyframe for video_prompt. The first frame must match its subject, pose, location, wardrobe, props, composition, and lighting before motion begins.
8. video_prompt must describe one continuous shot using this flow: opening keyframe, EXACTLY ONE named camera movement, subject motion, ambient/background motion, focus or depth response, and a stable end pose. Do not introduce a new subject, location, outfit, or prop midway through the shot.
9. Use the scene's planned duration. Describe a natural beginning, middle motion, and end state that can fit inside that duration; do not compress multiple actions into a short clip.
10. Keep motion physically plausible and restrained: no rubbery anatomy, duplicated limbs, teleportation, morphing faces, sudden object changes, impossible camera acceleration, or uncontrolled shaking.
11. video_prompt must not request cuts, transitions, dialogue, narration, subtitles, captions, sound effects, music, or audio. It must describe visual motion only.
12. Make each prompt specific to its scene. Do not use generic phrases such as "cinematic scene" without concrete visual details. Do not invent text, logos, brands, or historically impossible objects.
13. Write image_prompt and video_prompt in English for generator compatibility. Keep administrative rationale out of both prompts.
14. Minimum length: image_prompt 220+ characters, video_prompt 260+ characters.

Return ONLY valid JSON in this shape:
{{
  "director_notes": {{"overall_vision": "...", "error": false}},
  "scenes": [
    {{
      "scene_id": "scene001",
      "scene_order": 1,
      "image_prompt": "detailed English image generation prompt",
      "video_prompt": "detailed English single-shot visual motion prompt with timing, one camera movement, subject motion, ambient motion, focus response, and stable end pose",
      "lighting_hint": "specific lighting",
      "visual_style": "specific visual style",
      "shot_hints": [
        {{"camera": "close-up", "composition": "...", "movement": "slow push-in", "emotion": "...", "purpose": "..."}}
      ]
    }}
  ]
}}
"""

    try:
        import asyncio
        raw = asyncio.run(asyncio.wait_for(
            ai_router.generate_text(
                prompt,
                model,
                temperature=0.45,
                max_tokens=16384,
                task_type="scene_media_prompt_generation",
            ),
            timeout=90,
        ))
        generated = _extract_json(raw)
        generated_scenes = generated.get("scenes") if isinstance(generated, dict) else None
        if not isinstance(generated_scenes, list) or len(generated_scenes) != len(scenes):
            raise ValueError(
                f"media prompt count mismatch: expected {len(scenes)}, got "
                f"{len(generated_scenes or [])}"
            )

        by_key = {}
        for item in generated_scenes:
            key = (str(item.get("scene_id") or ""), str(item.get("scene_order") or ""))
            by_key[key] = item

        enriched_scenes = []
        for index, scene in enumerate(scenes, start=1):
            key = (str(scene.get("scene_id") or ""), str(scene.get("scene_order") or index))
            media = by_key.get(key)
            if not media:
                raise ValueError(f"media prompt missing for scene {key[0] or key[1]}")
            if not str(media.get("image_prompt") or "").strip():
                raise ValueError(f"image_prompt missing for scene {key[0] or key[1]}")
            if not str(media.get("video_prompt") or "").strip():
                raise ValueError(f"video_prompt missing for scene {key[0] or key[1]}")
            _validate_media_prompt_quality(media, key[0] or key[1])

            merged = dict(scene)
            for field in ("image_prompt", "video_prompt", "lighting_hint", "visual_style", "shot_hints"):
                if media.get(field) is not None:
                    merged[field] = media[field]
            merged["image_style"] = image_style_key
            merged["media_prompt_status"] = "ready"
            enriched_scenes.append(merged)

        result = dict(structure)
        result["scenes"] = enriched_scenes
        result["image_style"] = image_style_key
        result["image_style_directive"] = image_style_directive
        result["media_prompt_director"] = generated.get("director_notes") or {}
        result["media_prompt_status"] = "ready"
        return result
    except Exception as e:
        # Prompt generation must not strand a valid plan at 65%. Keep the
        # scene plan intact and provide deterministic, generator-ready prompts
        # so the saved result still contains media prompts for every scene.
        job_log.warning(f"Scene media prompt generation fallback: {e}")
        fallback_scenes = []
        for index, scene in enumerate(scenes, start=1):
            scene_id = str(scene.get("scene_id") or f"scene{index:03d}")
            scene_order = scene.get("scene_order") or index
            context = str(
                scene.get("visual_description")
                or scene.get("scene_summary")
                or scene.get("narration")
                or scene.get("description")
                or upload_title
            ).strip()
            # Scene narration may mention editing language such as "cut to";
            # keep that source text from tripping the continuous-shot guard.
            context = re.sub(
                r"\b(cut to|hard cut|jump cut|teleport(?:ation)?)\b",
                "continuous visual change",
                context,
                flags=re.IGNORECASE,
            )
            image_prompt = (
                f"Documentary-style economic explainer keyframe for the scene context: {context}. "
                f"Show the primary subject and visible action in a believable contemporary financial setting, "
                f"with a clear foreground, midground, and background, medium-wide composition, eye-level angle, "
                f"readable body language, restrained {image_style_key} visual language, realistic materials, "
                f"coherent cool-to-warm lighting, controlled contrast, and continuity-friendly wardrobe and props. "
                f"Use accurate office, street, bank, or home details appropriate to the subject. "
                f"No text, no words, no letters, no labels, no watermarks, no captions; correct anatomy, "
                f"exactly two arms, exactly two hands, anatomically correct hands, no extra limbs, no fused fingers."
            )
            video_prompt = (
                f"Start from the exact image keyframe for this scene: {context}. "
                f"Use one continuous shot for the planned duration. Begin with the subject held clearly in frame, "
                f"then use exactly one slow push-in camera movement while the subject performs one restrained, "
                f"physically plausible action related to the economic situation. Let only subtle background activity "
                f"and natural light movement continue. Preserve the same identity, wardrobe, props, location, and "
                f"composition throughout; use a gentle focus response as attention shifts to the subject, then end "
                f"on a stable readable pose. No cuts, no transitions, no morphing, no teleportation, no dialogue, "
                f"no narration, no subtitles, no captions, no sound effects, no music, and no audio instructions."
            )
            media = {
                "scene_id": scene_id,
                "scene_order": scene_order,
                "image_prompt": image_prompt,
                "video_prompt": video_prompt,
                "lighting_hint": "Controlled documentary lighting with restrained contrast and clear subject separation.",
                "visual_style": image_style_key,
                "shot_hints": [{"camera": "medium-wide", "composition": "clear foreground, midground, background", "movement": "slow push-in", "emotion": "focused concern", "purpose": "make the economic consequence readable"}],
            }
            _validate_media_prompt_quality(media, scene_id)
            merged = dict(scene)
            merged.update(media)
            merged["image_style"] = image_style_key
            merged["media_prompt_status"] = "fallback_ready"
            fallback_scenes.append(merged)
        result = dict(structure)
        result["scenes"] = fallback_scenes
        result["image_style"] = image_style_key
        result["image_style_directive"] = image_style_directive
        result["media_prompt_director"] = {"fallback": True, "reason": str(e)}
        result["media_prompt_status"] = "fallback_ready"
        return result


def _build_fallback_scene_plan(
    topic: str,
    upload_title: str,
    target_duration: int,
    script_style: str,
    style_directive: str,
    benchmark_analysis: dict | None,
    title_generation: dict | None,
) -> dict:
    """Create a deterministic scene plan when the AI planner returns no scenes."""
    target_duration = max(60, int(target_duration or 900))
    slots = []
    cursor = 0
    while cursor < target_duration:
        if cursor < 60:
            step = 5
            phase = "opening"
        elif cursor < 300:
            step = 15
            phase = "development"
        elif cursor < 600:
            step = 20
            phase = "explanation"
        else:
            step = 30
            phase = "steady"
        end = min(cursor + step, target_duration)
        slots.append((cursor, end, phase))
        cursor = end

    title = (upload_title or topic or "경제 이슈").strip()
    benchmark_title = ""
    if isinstance(benchmark_analysis, dict):
        benchmark_title = str(benchmark_analysis.get("title") or "").strip()
    scenes = []
    for index, (start, end, phase) in enumerate(slots, start=1):
        duration = end - start
        scene_id = f"scene{index:03d}"
        if phase == "opening":
            summary = f"Opening beat {index}: expose the personal money tension behind '{title}'."
            purpose = "Create immediate curiosity and a concrete household-level stake."
        elif phase == "development":
            summary = f"Development beat {index}: connect the viewer's daily spending pressure to the market signal."
            purpose = "Escalate from a familiar problem into the economic mechanism."
        elif phase == "explanation":
            summary = f"Explanation beat {index}: explain one cause, consequence, or decision point behind '{title}'."
            purpose = "Make the economic logic clear without losing narrative momentum."
        else:
            summary = f"Steady beat {index}: resolve the implication and prepare the next practical insight."
            purpose = "Carry the analysis toward a grounded payoff."
        scenes.append({
            "scene_id": scene_id,
            "scene_order": index,
            "opening_micro_scene": phase == "opening",
            "opening_time_range": f"{start}-{end}s" if phase == "opening" else None,
            "time_range": f"{start}-{end}s",
            "pacing_phase": phase,
            "scene_summary": summary,
            "scene_situation": (
                f"Timed {phase} visual beat for '{title}'. Show a specific economic pressure through "
                f"people, prices, charts, bank screens, market headlines, or household decisions. "
                f"Reference technique from benchmark '{benchmark_title}' without copying its content."
            ),
            "scene_emotion": "focused concern",
            "scene_purpose": purpose,
            "retention_hook": "Leave one clear economic question unresolved into the next beat.",
            "title_promise_link": f"This beat advances the viewer promise of '{title}'.",
            "end_bridge": "Move into the next beat by raising the next cause or consequence.",
            "target_duration": duration,
            "visual_direction": (
                "Documentary economy explainer visuals with realistic Korean urban details, "
                "market screens, receipts, household objects, bank or street context, and restrained motion."
            ),
            "tts_direction": "Calm but urgent Korean narration, clear pacing, no exaggerated shouting.",
        })

    return {
        "topic": topic,
        "upload_title": title,
        "title_promise": f"Explain why '{title}' matters to the viewer's money decisions.",
        "opening_hook": f"Start with the contradiction inside '{title}' and make it personal.",
        "payoff": "Give a grounded explanation of the economic signal and what viewers should watch next.",
        "scene_count": len(scenes),
        "target_duration_seconds": target_duration,
        "global_mood": "urgent economic explainer",
        "scenes": scenes,
        "planner_notes": {
            "strategy": "Fallback deterministic scene plan created because AI planner returned no usable scenes.",
            "error": False,
            "fallback": True,
            "script_style": script_style,
            "style_directive_present": bool(style_directive),
            "title_generation": title_generation or {},
        },
    }


def _fallback_narration_section(
    topic: str,
    upload_title: str,
    scene: dict,
    idx: int,
    total: int,
    min_chars: int,
) -> str:
    title = (upload_title or topic or "이번 경제 이슈").strip()
    summary = str(scene.get("scene_summary") or scene.get("scene_situation") or title).strip()
    purpose = str(scene.get("scene_purpose") or "이 장면의 핵심 경제 신호를 설명합니다.").strip()
    hook = str(scene.get("retention_hook") or "다음 장면에서 더 구체적인 원인을 확인합니다.").strip()
    text = (
        f"{idx + 1}번째 장면입니다. 지금 우리가 봐야 할 핵심은 '{title}'라는 질문이 "
        f"단순한 체감 문제가 아니라 실제 돈의 흐름과 연결되어 있다는 점입니다. "
        f"{summary} {purpose} 화면 속 가격표, 통장 잔액, 시장 지표는 모두 같은 방향을 가리킵니다. "
        f"소득은 천천히 움직이는데 생활비와 자산 가격은 먼저 반응하고, 그 차이가 시청자의 선택을 압박합니다. "
        f"{hook} 그래서 이 장면은 다음 판단으로 넘어가기 전, 왜 지금 이 문제가 개인의 지갑까지 도착했는지 "
        f"분명하게 짚고 넘어갑니다."
    )
    while len(text) < min_chars:
        text += (
            " 이 흐름을 놓치면 숫자는 뉴스 속 이야기로만 보이지만, 실제로는 장보기와 저축, 투자 판단에 "
            "동시에 영향을 주는 신호가 됩니다."
        )
    return text


def _process_script_plan_generate(job: dict, job_id: str, job_log) -> tuple[str, dict]:
    """[AIR-0230 §2d] Pre-bakes a scene structure for one topics_queue row
    ahead of any user claiming it - reuses app/services/scene_planner.py's
    plan_scenes() verbatim (same function the live claim-and-plan flow uses,
    app/routers/gemini.py::generate_script_structure_api()), so a pre-baked
    structure is indistinguishable in shape from one generated live."""
    job_store.transition(job_id, job_store.PREPARING, reason="validating payload")
    write_state("preparing", job, 0, job_id)
    job_log.info("-> PREPARING (validating payload)")

    topic_queue_id, topic, target_duration, script_style, image_style, language, benchmark_analysis, upload_title, title_generation = _validate_script_plan_payload(job["payload"])
    image_style, image_style_selection = _select_worker_image_style_for_plan(job, job["payload"], topic, upload_title)

    job_store.transition(job_id, job_store.RENDERING, reason="planning scene structure")
    write_state("running", job, 30, job_id)
    job_log.info(f"-> RENDERING (planning scenes for topic_queue_id={topic_queue_id})")

    ensure_project_root_on_path()
    from services.script_style_resolver import resolve_script_style_directive
    from app.services.scene_planner import scene_planner_service
    import asyncio

    # Relies on this worker PC's local script_style_presets being in sync
    # with the web-admin (same assumption every other desktop install
    # already depends on for this function - not new to this job type).
    style_directive = resolve_script_style_directive(script_style)

    structure = asyncio.run(
        scene_planner_service.plan_scenes(
            topic=topic,
            target_duration=target_duration,
            style_directive=style_directive,
            benchmark_analysis=benchmark_analysis,
            upload_title=upload_title,
            title_generation=title_generation,
        )
    )

    planner_notes = structure.get("planner_notes") or {}
    if planner_notes.get("error"):
        planner_error = planner_notes.get("error_message") or "scene_planner_service.plan_scenes() failed"
        job_log.warning(f"Scene planner fallback activated: {planner_error}")
        structure = _build_fallback_scene_plan(
            topic=topic,
            upload_title=upload_title,
            target_duration=target_duration,
            script_style=script_style,
            style_directive=style_directive,
            benchmark_analysis=benchmark_analysis,
            title_generation=title_generation,
        )
    research_bundle = (benchmark_analysis or {}).get("web_research")
    if isinstance(research_bundle, dict):
        structure["research_bundle"] = research_bundle

    job_store.update_progress(job_id, 65, "generating scene image and video prompts")
    write_state("running", job, 65, job_id)
    job_log.info(f"-> GENERATING MEDIA PROMPTS (scene_count={structure.get('scene_count')})")
    job_log.info(
        f"-> IMAGE STYLE SELECTED BY WORKER (style={image_style}, "
        f"source={(image_style_selection or {}).get('selection_source')})"
    )
    structure = _generate_scene_media_prompts(
        structure=structure,
        topic=topic,
        upload_title=upload_title,
        image_style=image_style,
        image_style_selection=image_style_selection,
        language=language,
        job_log=job_log,
    )

    job_store.transition(job_id, job_store.UPLOADING, reason="saving result")
    write_state("running", job, 90, job_id)
    job_log.info(f"-> UPLOADING (scene_count={structure.get('scene_count')})")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = RESULTS_DIR / f"{job_id}.json"
    completed_at = time.time()
    result_payload = {
        "job_id": job_id,
        "job_type": "script_plan_generate",
        "status": "COMPLETED",
        "topic_queue_id": topic_queue_id,
        "upload_title": upload_title,
        "title_generation": title_generation,
        "structure": structure,
        "completed_at": completed_at,
        "error": None,
    }
    result_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    job_store.transition(job_id, job_store.COMPLETED, reason="script plan complete", output_path=str(result_path))
    job_log.info(f"-> COMPLETED, result at {result_path}")
    logger.info(f"Completed job {job_id} -> {result_path}")
    return str(result_path), result_payload


# =====================================================================
# [AIR-0230 §2d] script_generate - full narration text pre-generation.
#
# Ported from templates/pages/script_gen.html::generateScript() (client
# JS), section by section, with ONE deliberate correction found while
# porting: the live client reads section.title/section.key_points, but
# scene_planner_service.plan_scenes() (the only structure source since
# AIR-0209 "Scene Source of Truth") produces scene_summary/scene_situation/
# scene_purpose/scene_emotion/tts_direction - there is no title/key_points
# field anywhere in that schema, and no normalization step exists between
# them (confirmed by exhaustive search of script_gen.html and the DB
# round-trip in database.py::get_full_project). This means the LIVE app
# has been sending "제목: undefined" / "주요 내용: 자유롭게 작성" into every
# single section prompt since AIR-0209 - the detailed per-scene planning
# scene_planner produces has never actually reached script generation.
# This port uses the real scene fields instead (see _build_section_prompt).
# The live script_gen.html itself is a separate, not-yet-done fix - see
# docs/AIR_0230_HERMES_BENCHMARK_WORKER_ARCHITECTURE.md §2d.
#
# Also adds one thing script_gen.html never had at all: an explicit
# language instruction (script_gen.html fetches project.language into an
# unused variable and always writes Korean prompts regardless) - since
# this path already threads topic language through from topics_queue, it
# costs nothing to do this correctly here.
# =====================================================================

SCRIPT_GEN_LANGUAGE_INSTRUCTIONS = {
    "ko": "반드시 자연스러운 한국어로 작성하세요.",
    "en": "You MUST write the entire output in natural, fluent English.",
    "ja": "必ず自然な日本語で作成してください。",
}

# Keep language instructions explicit. The legacy values above were corrupted
# by an earlier encoding conversion and can cause the model to ignore Korean.
SCRIPT_GEN_LANGUAGE_INSTRUCTIONS = {
    "ko": "전체 대본을 자연스럽고 유창한 한국어로 작성하세요. 번역투와 어색한 직역을 피하세요.",
    "en": "You MUST write the entire output in natural, fluent English.",
    "ja": "出力全体を自然で流暢な日本語で書いてください。直訳調の不自然な表現は避けてください。",
}

# Regexes ported 1:1 from script_gen.html's inline JS (see module comment above).
_CLEANUP_BRACKET_PATTERN = re.compile(r"\[[^\]]*\]")
# Non-raw string so \uXXXX resolves to real Hangul-range characters before
# re.compile sees them - a raw string would hand re the literal backslash-u
# sequence instead, which Python's re engine does not reliably expand.
_CLEANUP_ALLOWED_PATTERN = re.compile(
    "[^\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318Fa-zA-Z0-9\\s,.\\?\\!\"'\\.:\\(\\)]"
)
_SPEAKER_STRIP_PATTERN = re.compile(r"^[가-힣\w\s]+[ \t]*:[ \t]*", re.MULTILINE)
_SPEAKER_LINE_REGEX = re.compile(r"^\s*(?:([^\s:\[\]()]+)(?:\(.*\))?[:：]|([^\s:\[\]()]+)[)）\]])")
_SPEAKER_NAME_STRIP_PATTERN = re.compile(r"[\*_#\[\]\{\}()]")


def _clean_section_text(text: str, is_multi: bool) -> str:
    text = _CLEANUP_BRACKET_PATTERN.sub("", text)
    text = text.replace("*", "")
    text = _CLEANUP_ALLOWED_PATTERN.sub("", text)
    if not is_multi:
        text = _SPEAKER_STRIP_PATTERN.sub("", text)
    return text.strip()


def _extract_speaker_names(text: str) -> list[str]:
    names = []
    seen = set()
    for line in (text or "").split("\n"):
        m = _SPEAKER_LINE_REGEX.match(line.strip())
        if not m:
            continue
        raw = m.group(1) or m.group(2)
        if not raw:
            continue
        clean = _SPEAKER_NAME_STRIP_PATTERN.sub("", raw).strip()
        if clean and clean not in seen:
            seen.add(clean)
            names.append(clean)
    return names


def _script_gen_length_instruction(duration_seconds: int, is_shorts: bool) -> tuple[float, str]:
    if is_shorts:
        total_target_chars = duration_seconds * 7.5
        length_instruction = (
            f"[매우 중요] 이 대본은 {duration_seconds}초 숏폼(Shorts) 영상용입니다. "
            f"전체 대본이 매우 짧아야 합니다. 군더더기 없이 핵심만 빠르게 전달하세요."
        )
    else:
        total_target_chars = (duration_seconds / 60) * 450
        length_instruction = f"이 영상은 약 {duration_seconds // 60}분 {duration_seconds % 60}초 길이입니다."
    return total_target_chars, length_instruction


def _script_gen_mode_instruction(is_multi: bool, known_characters: list[str], is_dramatic_single: bool = False) -> str:
    if is_multi:
        known_chars_line = ""
        if known_characters:
            known_chars_line = (
                "\n[이미 등장한 인물 - 이 파트에서 같은 인물이 다시 말하면 반드시 이 이름을 그대로 "
                "재사용하세요. 새 인물은 스토리 전개상 꼭 필요할 때만 추가하세요]\n"
                f"{', '.join(known_characters)}\n"
            )
        return f"""
1. **기본은 나레이터의 서술**입니다. 인물의 행동이나 상황은 나레이터가 설명하듯 전달하세요 (예: "철수는 화를 내며 소리쳤다").
2. 인물이 **직접 한 말을 그대로 전달할 필요가 있는 대목에서만** 그 인물 이름으로 화자를 전환하세요. (예: "철수: 당장 나가!") 그 외에는 전부 나레이터입니다.
3. 나레이터 화자 이름은 "나레이터:"로 표시하세요.
4. 한 문장짜리 대사 때문에 새로운 이름을 만들지 마세요 - 비중이 작은 인물의 말은 나레이터가 요약해서 전달하는 쪽을 우선하세요.
5. 이 파트에서 실제로 등장인물이 몇 명 필요한지는 스토리 전개가 결정합니다 - 인위적으로 늘리거나 줄이지 마세요. 단, 같은 인물은 항상 같은 이름을 쓰세요.{known_chars_line}
"""
    if is_dramatic_single:
        return """
1. Write as a single narrator-led dramatic narration. The narrator carries the story; do NOT write screenplay format.
2. You MAY include short direct quotes at decisive emotional moments, but embed them naturally inside the narration.
3. Do NOT use speaker labels such as "철수:" or "사부:". If a line is spoken, write it as quoted speech within the paragraph.
4. Keep dialogue sparse and purposeful: roughly 5-15% of the section. Use it only for betrayal, confession, threat, realization, or final payoff.
5. Maintain one consistent narrative voice. Do not switch into a multi-character roleplay script.
6. Make every quote reveal character, raise tension, or pay off the title promise. No casual filler dialogue.
"""
    return """
1. 반드시 **독백(Monologue) 또는 나레이션(Narration) 형식**으로 작성하세요. (대화체 절대 금지)
2. 화자는 **무조건 딱 1명(성우 1인)**으로 제한합니다. 대화 형식으로 역할을 나누지 마세요.
5. 화자(이름) 표시 금지 (예: 나:, 상사: 처럼 누가 말하는지 적지 말 것)
"""


def _build_section_prompt(
    topic: str, scene: dict, is_shorts: bool, is_multi: bool, known_characters: list[str],
    length_instruction: str, min_chars: int, max_chars: int, language: str,
    upload_title: str = "", structure_context: dict | None = None,
    narrative_blueprint: dict | None = None, previous_context: dict | None = None,
    narration_mode: str = "single",
) -> str:
    # [FIX][AIR-0230] scene_planner.py's actual schema - see module comment
    # above for why this replaces script_gen.html's title/key_points reads.
    scene_summary = scene.get("scene_summary") or "이 장면"
    detail_lines = [v for v in (scene.get("scene_situation"), scene.get("scene_purpose")) if v]
    key_points_text = ", ".join(detail_lines) if detail_lines else "자유롭게 작성"
    emotion = scene.get("scene_emotion") or ""
    tts_direction = scene.get("tts_direction") or ""
    retention_hook = scene.get("retention_hook") or ""
    title_promise_link = scene.get("title_promise_link") or ""
    end_bridge = scene.get("end_bridge") or ""
    structure_context = structure_context or {}
    title_promise = structure_context.get("title_promise") or ""
    opening_hook = structure_context.get("opening_hook") or ""
    payoff = structure_context.get("payoff") or ""
    narrative_blueprint = narrative_blueprint or {}
    previous_context = previous_context or {}

    is_dramatic_single = narration_mode == "dramatic_single"
    mode_instruction = _script_gen_mode_instruction(is_multi, known_characters, is_dramatic_single=is_dramatic_single)
    language_instruction = SCRIPT_GEN_LANGUAGE_INSTRUCTIONS.get(language, SCRIPT_GEN_LANGUAGE_INSTRUCTIONS["ko"])
    extra_context = ""
    if emotion:
        extra_context += f"- 감정/분위기: {emotion}\n"
    if tts_direction:
        extra_context += f"- 성우 연기 지침: {tts_direction}\n"

    for label, value in (
        ("Retention hook", retention_hook),
        ("Title promise link", title_promise_link),
        ("End bridge to next scene", end_bridge),
    ):
        if value:
            extra_context += f"- {label}: {value}\n"

    title_contract = ""
    if upload_title:
        title_contract = f"""
[UPLOAD TITLE CONTRACT]
- Upload title: {upload_title}
- Title promise: {title_promise or "infer it from the upload title and topic"}
- Opening hook to honor: {opening_hook or "make the first section immediately prove the title is worth staying for"}
- Final payoff required: {payoff or "the script must resolve the curiosity raised by the title"}
- Every paragraph must serve the clicked title. Do not drift into meta commentary, content strategy, or storytelling lessons unless the title explicitly asks for that.
"""

    blueprint_section = ""
    if narrative_blueprint:
        scene_order = scene.get("scene_order") or scene.get("order")
        beats = narrative_blueprint.get("scene_beats") or []
        scene_beat = None
        if isinstance(beats, list):
            for beat in beats:
                if str(beat.get("scene_order") or "") == str(scene_order or ""):
                    scene_beat = beat
                    break
        blueprint_section = f"""
[STORY BLUEPRINT]
{json.dumps({
    "logline": narrative_blueprint.get("logline"),
    "protagonist": narrative_blueprint.get("protagonist"),
    "desire": narrative_blueprint.get("desire"),
    "central_conflict": narrative_blueprint.get("central_conflict"),
    "stakes": narrative_blueprint.get("stakes"),
    "hidden_information": narrative_blueprint.get("hidden_information"),
    "turning_point": narrative_blueprint.get("turning_point"),
    "final_payoff": narrative_blueprint.get("final_payoff"),
    "current_scene_beat": scene_beat,
}, ensure_ascii=False)}
"""

    research_section = ""
    research_bundle = structure_context.get("research_bundle") or {}
    if research_bundle:
        facts = research_bundle.get("verified_facts") or []
        research_section = f"""
[GEMINI WEB RESEARCH]
{research_bundle.get("research_brief") or ""}
Verified facts: {json.dumps(facts[:8], ensure_ascii=False)}
Risk notes: {json.dumps(research_bundle.get("risk_notes") or [], ensure_ascii=False)}
- Use a fact only when it is relevant to this scene. Do not invent facts, quotations, figures, or real people.
- For fictional stories, use research as context only; never present invented plot events as factual.
"""

    continuity_section = ""
    if previous_context:
        continuity_section = f"""
[CONTINUITY FROM PREVIOUS SCENES]
{json.dumps(previous_context, ensure_ascii=False)}
- Continue from this emotional state. Do not restart the story.
- Carry unresolved questions forward unless this scene is explicitly paying one off.
"""

    clean_prompt = f"""You are an expert {'Shorts' if is_shorts else 'YouTube long-form'} narration writer. Write the body for this planned scene so a real viewer wants to keep listening.

[TOPIC]
{topic}
{title_contract}
{blueprint_section}
{research_section}
{continuity_section}

[CURRENT SCENE]
- Summary: {scene_summary}
- Situation and purpose: {key_points_text}
{extra_context}

[WRITING RULES]
0. {length_instruction}
{mode_instruction}
3. {language_instruction}
4. Output body text only. Do not output a scene title, scene number, headings, markdown, timecodes, camera directions, or sound-effect labels.
5. Target {min_chars} to {max_chars} characters. Do not pad by repeating information.
6. Build the scene around its retention hook, and end with the supplied end bridge as an unresolved question, reveal, or emotional turn that pulls into the next scene.
7. Keep the title promise, story blueprint, character motivation, and current scene purpose aligned. Do not drift into meta commentary, content strategy, or a lesson about storytelling.
8. Write for the ear: vary sentence length, use concrete details, and make each paragraph move the situation, emotion, or information forward.

Output only the narration body."""
    return clean_prompt

    return f"""당신은 {'유튜브 쇼츠(Shorts)' if is_shorts else '유튜브'} 대본 작가입니다. 아래 주제에 대한 "{scene_summary}" 파트를 작성해주세요.

[영상 주제]
{topic}
{title_contract}
{blueprint_section}
{research_section}
{continuity_section}

[현재 섹션]
- 제목: {scene_summary}
- 주요 내용: {key_points_text}
{extra_context}
[작성 지침]
0. {length_instruction}
{mode_instruction}
3. 자연스럽고 몰입감 있는 대본을 작성하세요. {language_instruction}
4. 섹션 제목은 출력하지 말고, 본문만 작성하세요.
5. 이 파트의 분량은 **약 {min_chars}자 ~ {max_chars}자** 내외로 작성하세요. (절대적으로 지킬 것)
6. {'문장을 짧고 간결하게 끊어주세요. 호흡을 짧게 가져가세요.' if is_shorts else '문장을 자연스럽게 이어주세요.'}

**[작성 및 감정/톤 지침]**
1. 반드시 대본의 구문 앞이나 중간중간에 괄호를 사용하여 말의 톤이나 분위기를 표시하세요. (예: "(차분하게)", "(슬프게)", "(진지하게)")
2. 음악, 효과음 등 상황 설명용 괄호(예: (음악), (상황), (웃음))는 금지합니다. 오직 성우의 목소리 톤/감정만 괄호로 표시하세요.
3. 시간 표시 금지 (예: [0-5초], ** 등 타임스탬프 금지)
4. 이모티콘 및 꾸밈 기호 금지 (예: 🤣, ✨, 🔥 등 특수문자 금지)

본문만 출력하세요:"""


def _short_script_excerpt(text: str, max_chars: int = 1400) -> str:
    value = (text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


def _fallback_narrative_blueprint(topic: str, upload_title: str, structure: dict) -> dict:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    scene_beats = []
    for idx, scene in enumerate(scenes or [], start=1):
        scene_beats.append({
            "scene_order": scene.get("scene_order") or idx,
            "beat": scene.get("scene_summary") or f"Scene {idx}",
            "tension": scene.get("retention_hook") or scene.get("scene_purpose") or "",
            "turn": scene.get("end_bridge") or "",
        })
    return {
        "logline": upload_title or topic,
        "protagonist": "the person at the center of the clicked story",
        "desire": "resolve the promise raised by the title",
        "central_conflict": structure.get("title_promise") or topic,
        "stakes": structure.get("opening_hook") or "viewer curiosity must keep rising",
        "hidden_information": "reveal new information gradually instead of explaining everything upfront",
        "turning_point": "a late middle reversal that changes what the viewer believes",
        "final_payoff": structure.get("payoff") or "emotionally resolve the title promise",
        "scene_beats": scene_beats,
        "fallback": True,
    }


async def _generate_narrative_blueprint(
    ai_router, model: str, topic: str, upload_title: str, structure: dict,
    title_generation: dict, language: str, style_directive: str,
) -> dict:
    prompt = f"""
You are a senior story editor for retention-focused Korean YouTube longform narration.

Before writing the script, create a STORY BLUEPRINT. This is not the script.
It must force a real story arc: hook, character desire, conflict, rising tension,
midpoint turn, withheld information, emotional payoff.

LANGUAGE: {language}
TOPIC: {topic}
UPLOAD TITLE: {upload_title}
TITLE GENERATION: {json.dumps(title_generation or {}, ensure_ascii=False)}
SCENE STRUCTURE: {json.dumps(structure or {}, ensure_ascii=False)}
STYLE DIRECTIVE: {style_directive or "none"}

Return ONLY JSON:
{{
  "logline": "one-sentence story premise",
  "protagonist": "who the viewer follows",
  "desire": "what they want or need",
  "central_conflict": "main obstacle or tension",
  "stakes": "why it matters emotionally",
  "hidden_information": "what must be delayed for curiosity",
  "turning_point": "middle or late reversal",
  "final_payoff": "what the ending must resolve",
  "scene_beats": [
    {{
      "scene_order": 1,
      "beat": "what changes in this scene",
      "tension": "question or pressure held in this scene",
      "turn": "new reveal or emotional move",
      "must_include": ["specific story detail"],
      "must_avoid": ["filler, explanation, meta commentary"]
    }}
  ]
}}
"""
    try:
        raw = await ai_router.generate_text(
            prompt, model, temperature=0.45, max_tokens=4096,
            task_type="hermes_script_blueprint",
        )
        parsed = _extract_json(raw)
        if not isinstance(parsed.get("scene_beats"), list):
            raise ValueError("blueprint.scene_beats missing")
        return parsed
    except Exception:
        return _fallback_narrative_blueprint(topic, upload_title, structure)


def _fallback_script_quality_report(script: str, upload_title: str) -> dict:
    text = script or ""
    issues = []
    score = 70
    if len(text) < 3500:
        score -= 18
        issues.append("script_too_short_for_longform")
    if "섹션 생성 실패" in text or "generation failed" in text:
        score -= 35
        issues.append("failed_section_placeholder_present")
    if upload_title and upload_title[:8] not in text:
        score -= 4
        issues.append("title_not_directly_echoed")
    if any(term in text for term in ("스토리텔링 비법", "콘텐츠 전략", "조회수 분석")):
        score -= 18
        issues.append("meta_commentary_present")
    return {
        "score": max(0, min(100, score)),
        "verdict": "pass" if score >= 72 and not issues else "revise",
        "critical_issues": issues,
        "strengths": [],
        "revision_notes": issues,
        "fallback": True,
    }


async def _evaluate_script_quality(
    ai_router, model: str, topic: str, upload_title: str, narrative_blueprint: dict,
    structure: dict, script: str, language: str,
) -> dict:
    prompt = f"""
You are a ruthless Korean YouTube story QA editor.

Score this generated narration script for whether real viewers would keep watching/listening.

Evaluate:
1. first 30 seconds hook
2. title promise fulfillment
3. clear protagonist/central conflict
4. rising tension and curiosity gaps
5. scene-to-scene continuity
6. midpoint turn or reveal
7. emotional payoff
8. absence of filler/meta commentary
9. natural spoken narration

LANGUAGE: {language}
TOPIC: {topic}
UPLOAD TITLE: {upload_title}
STORY BLUEPRINT: {json.dumps(narrative_blueprint or {}, ensure_ascii=False)}
SCENE STRUCTURE: {json.dumps(structure or {}, ensure_ascii=False)}
SCRIPT:
{script}

Return ONLY JSON:
{{
  "score": 0,
  "verdict": "pass|revise",
  "hook_score": 0,
  "structure_score": 0,
  "retention_score": 0,
  "payoff_score": 0,
  "naturalness_score": 0,
  "critical_issues": ["specific issue"],
  "strengths": ["specific strength"],
  "revision_notes": ["specific instruction for revision"]
}}
"""
    try:
        raw = await ai_router.generate_text(
            prompt, model, temperature=0.2, max_tokens=3000,
            task_type="hermes_script_quality_qa",
        )
        report = _extract_json(raw)
        report["score"] = max(0, min(100, round(float(report.get("score") or 0))))
        if report.get("score", 0) < 78 and report.get("verdict") == "pass":
            report["verdict"] = "revise"
        return report
    except Exception as e:
        report = _fallback_script_quality_report(script, upload_title)
        report["qa_error"] = str(e)
        return report


def _script_needs_revision(report: dict) -> bool:
    if not isinstance(report, dict):
        return True
    if report.get("verdict") == "revise":
        return True
    if int(report.get("score") or 0) < 78:
        return True
    return bool(report.get("critical_issues"))


async def _revise_full_script(
    ai_router, model: str, topic: str, upload_title: str, narrative_blueprint: dict,
    structure: dict, script: str, quality_report: dict, language: str,
) -> str:
    prompt = f"""
You are a senior Korean YouTube script doctor.

Rewrite the FULL narration script once, using the QA report below.
Keep the core story and scene order, but fix weak hook, filler, flat tension,
unclear character motivation, missing payoff, and title-promise drift.

Rules:
- Output only the revised script body.
- Do not add markdown headings.
- Do not mention QA, strategy, content, algorithm, storytelling, or analysis.
- Keep natural spoken narration.
- Preserve the upload title promise and final payoff.
- Keep length within roughly +/-20% of the original.

LANGUAGE: {language}
TOPIC: {topic}
UPLOAD TITLE: {upload_title}
STORY BLUEPRINT: {json.dumps(narrative_blueprint or {}, ensure_ascii=False)}
SCENE STRUCTURE: {json.dumps(structure or {}, ensure_ascii=False)}
QA REPORT: {json.dumps(quality_report or {}, ensure_ascii=False)}

ORIGINAL SCRIPT:
{script}
"""
    revised = await ai_router.generate_text(
        prompt, model, temperature=0.55, max_tokens=12000,
        task_type="hermes_script_rewrite",
    )
    return _clean_section_text(revised.strip(), False)


def _validate_script_generate_payload(payload: dict) -> tuple[str, str, list, dict, str, str, str, int, str, dict]:
    topic_queue_id = str(payload.get("topic_queue_id") or "").strip()
    if not topic_queue_id:
        raise ValueError("payload.topic_queue_id is required for script_generate")
    topic = str(payload.get("topic") or "").strip()
    if not topic:
        raise ValueError("payload.topic is required for script_generate")

    structure = payload.get("structure")
    scenes = (structure or {}).get("scenes") if isinstance(structure, dict) else None
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("payload.structure.scenes (non-empty list) is required for script_generate")

    script_style = str(payload.get("script_style") or "default").strip()
    language = str(payload.get("language") or "ko").strip()
    if language not in SCRIPT_GEN_LANGUAGE_INSTRUCTIONS:
        language = "ko"
    narration_mode = str(payload.get("narration_mode") or "dramatic_single").strip().lower()
    if narration_mode not in ("single", "dramatic_single", "multi"):
        narration_mode = "dramatic_single"

    duration_seconds = payload.get("target_duration_seconds", 60)
    try:
        duration_seconds = max(15, int(duration_seconds))
    except (TypeError, ValueError):
        duration_seconds = 60

    title_generation = payload.get("title_generation") if isinstance(payload.get("title_generation"), dict) else {}
    upload_title = str(payload.get("upload_title") or title_generation.get("generated_title") or "").strip()

    return topic_queue_id, topic, scenes, structure or {}, script_style, language, narration_mode, duration_seconds, upload_title, title_generation


def _process_script_generate(job: dict, job_id: str, job_log) -> tuple[str, dict]:
    job_store.transition(job_id, job_store.PREPARING, reason="validating payload")
    write_state("preparing", job, 0, job_id)
    job_log.info("-> PREPARING (validating payload)")

    topic_queue_id, topic, scenes, structure, script_style, language, narration_mode, duration_seconds, upload_title, title_generation = _validate_script_generate_payload(job["payload"])
    is_multi = narration_mode == "multi"
    is_shorts = duration_seconds <= 60

    job_store.transition(job_id, job_store.RENDERING, reason="generating narration section by section")
    write_state("running", job, 10, job_id)
    job_log.info(f"-> RENDERING (topic_queue_id={topic_queue_id}, {len(scenes)} scenes, mode={narration_mode})")

    ensure_project_root_on_path()
    from config import Config, config
    from services import ai_router
    from services.script_style_resolver import resolve_script_style_directive
    import asyncio

    Config.refresh_remote_keys_if_stale()

    # Mirrors /api/script/generate's own model selection
    # (app/routers/gemini.py::script_generate) so pre-baked and live-generated
    # narration use the same model choice.
    model = config.SCRIPT_GENERATION_MODEL or config.SCRIPT_PLANNING_MODEL
    style_directive = resolve_script_style_directive(script_style)
    total_target_chars, length_instruction = _script_gen_length_instruction(duration_seconds, is_shorts)
    chars_per_section = round(total_target_chars / len(scenes))
    min_chars = max(20, round(chars_per_section * 0.7)) if is_shorts else max(50, round(chars_per_section * 0.8))
    max_chars = round(chars_per_section * 1.2)

    async def _run_generation() -> tuple[str, dict, dict, dict, int, dict]:
        narrative_blueprint = await _generate_narrative_blueprint(
            ai_router, model, topic, upload_title, structure, title_generation, language, style_directive
        )
        final_parts = []
        known_characters: list[str] = []
        unresolved_threads = [
            narrative_blueprint.get("hidden_information"),
            narrative_blueprint.get("central_conflict"),
        ]
        for idx, scene in enumerate(scenes):
            previous_context = {}
            if final_parts:
                previous_context = {
                    "previous_scene_count": len(final_parts),
                    "previous_script_excerpt": _short_script_excerpt(final_parts[-1], 1200),
                    "known_characters": known_characters,
                    "unresolved_threads": [t for t in unresolved_threads if t],
                }
            prompt = _build_section_prompt(
                topic, scene, is_shorts, is_multi, known_characters,
                length_instruction, min_chars, max_chars, language,
                upload_title=upload_title,
                structure_context=structure,
                narrative_blueprint=narrative_blueprint,
                previous_context=previous_context,
                narration_mode=narration_mode,
            )
            if style_directive:
                prompt = f"{prompt}\n\n{style_directive}"

            try:
                raw_text = await ai_router.generate_text(
                    prompt, model, temperature=0.7, max_tokens=8192,
                    task_type="hermes_script_generate",
                )
                section_text = _clean_section_text(raw_text.strip(), is_multi)
                if not section_text:
                    raise ValueError("model returned an empty section")
                if is_multi:
                    for name in _extract_speaker_names(section_text):
                        if name not in known_characters:
                            known_characters.append(name)
            except Exception as e:
                job_log.warning(f"Section {idx + 1}/{len(scenes)} generation fallback: {e}")
                section_text = _fallback_narration_section(
                    topic, upload_title, scene, idx, len(scenes), min_chars
                )

            final_parts.append(section_text)
            if scene.get("end_bridge"):
                unresolved_threads.append(scene.get("end_bridge"))
            progress = int(10 + 60 * (idx + 1) / len(scenes))
            job_store.update_progress(job_id, progress, f"section {idx + 1}/{len(scenes)} complete")
            write_state("running", job, progress, job_id)

            if idx < len(scenes) - 1:
                await asyncio.sleep(0.5)  # same inter-section pacing script_gen.html uses

        draft_script = "\n\n".join(p for p in final_parts if p).strip()
        job_store.update_progress(job_id, 78, "script QA")
        write_state("running", job, 78, job_id)
        initial_quality = await _evaluate_script_quality(
            ai_router, model, topic, upload_title, narrative_blueprint, structure, draft_script, language
        )
        final_script = draft_script
        final_quality = initial_quality
        revision_count = 0

        if _script_needs_revision(initial_quality):
            job_log.info(
                f"Script QA requested revision (score={initial_quality.get('score')}, verdict={initial_quality.get('verdict')})"
            )
            job_store.update_progress(job_id, 84, "script rewrite")
            write_state("running", job, 84, job_id)
            try:
                revised = await _revise_full_script(
                    ai_router, model, topic, upload_title, narrative_blueprint,
                    structure, draft_script, initial_quality, language,
                )
                if revised and len(revised) >= max(500, int(len(draft_script) * 0.55)):
                    revised_quality = await _evaluate_script_quality(
                        ai_router, model, topic, upload_title, narrative_blueprint, structure, revised, language
                    )
                    revised_score = int(revised_quality.get("score") or 0)
                    revised_passed = (
                        revised_quality.get("verdict") == "pass"
                        and not revised_quality.get("critical_issues")
                        and revised_score >= 78
                    )
                    if revised_passed and revised_score >= int(initial_quality.get("score") or 0) - 3:
                        final_script = revised
                        final_quality = revised_quality
                        revision_count = 1
            except Exception as e:
                job_log.warning(f"Script rewrite failed (keeping draft): {e}")

        job_store.update_progress(job_id, 90, "publish metadata")
        write_state("running", job, 90, job_id)
        publish_metadata = await _generate_publish_metadata(
            ai_router, config.TITLE_GENERATION_MODEL or model, topic, upload_title,
            final_script, language, narrative_blueprint, structure,
        )

        return final_script, narrative_blueprint, initial_quality, final_quality, revision_count, publish_metadata

    final_script, narrative_blueprint, initial_quality, final_quality, revision_count, publish_metadata = asyncio.run(_run_generation())
    if not final_script:
        raise ValueError("Generated script was empty after all sections were processed")
    if _script_needs_revision(final_quality):
        job_log.warning(
            "Generated script did not pass story QA after revision; saving draft with QA warning: "
            f"score={final_quality.get('score')}, "
            f"issues={final_quality.get('critical_issues') or final_quality.get('revision_notes') or []}"
        )
        final_quality["saved_with_warning"] = True

    job_store.transition(job_id, job_store.UPLOADING, reason="saving result")
    write_state("running", job, 95, job_id)
    char_count = len(final_script)
    job_log.info(f"-> UPLOADING (char_count={char_count})")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = RESULTS_DIR / f"{job_id}.json"
    completed_at = time.time()
    result_payload = {
        "job_id": job_id,
        "job_type": "script_generate",
        "status": "COMPLETED",
        "topic_queue_id": topic_queue_id,
        "topic": topic,
        "script": final_script,
        "upload_title": upload_title,
        "title_generation": title_generation,
        "publish_metadata": publish_metadata,
        "narrative_blueprint": narrative_blueprint,
        "initial_script_quality_report": initial_quality,
        "script_quality_report": final_quality,
        "revision_count": revision_count,
        "char_count": char_count,
        "read_time_seconds": (char_count + 414) // 415,  # matches script_gen.html's Math.ceil(charCount / 415)
        "narration_mode": narration_mode,
        "completed_at": completed_at,
        "error": None,
    }
    result_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    job_store.transition(job_id, job_store.COMPLETED, reason="script generation complete", output_path=str(result_path))
    job_log.info(f"-> COMPLETED, result at {result_path}")
    logger.info(f"Completed job {job_id} -> {result_path}")
    return str(result_path), result_payload


def _save_result_to_supabase(job_type: str, result_payload: dict, job_log) -> None:
    """Save generated content to Supabase topics_queue table.

    Uses the same direct REST pattern as dispatcher_service.py — service_role
    key gives full PostgREST access.  Failures are logged but never propagated
    (the local result file is already the authoritative copy).
    """
    supabase_url = (os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not supabase_url or not supabase_key:
        job_log.info("Supabase not configured — skipping cloud save")
        return

    import requests as _req

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    try:
        if job_type == "topic_research":
            topics = result_payload.get("topics", [])
            payload_data = result_payload.get("_payload_data")
            if not topics:
                job_log.warning("No topics in result_payload — skipping Supabase insert")
                return
            # Insert each topic as a pending row (mirrors dispatcher_service.py)
            category_id = (payload_data or {}).get("category_id")
            language = (payload_data or {}).get("language", "ko")
            assigned_email = (payload_data or {}).get("assigned_employee_email", "")
            if not assigned_email:
                # Derive a fallback so the NOT NULL column is satisfied
                assigned_email = "hermes_worker@local"
            for topic_item in topics:
                title = topic_item.get("title", "") if isinstance(topic_item, dict) else str(topic_item)
                if not title:
                    continue
                row = {
                    "topic": title,
                    "assigned_employee_email": assigned_email,
                    "language": language,
                    "status": "pending",
                    "is_auto_generated": True,
                }
                if category_id:
                    row["category_id"] = category_id
                r = _req.post(
                    f"{supabase_url}/rest/v1/topics_queue",
                    json=row, headers=headers, timeout=10,
                )
                if r.status_code in (200, 201):
                    job_log.info(f"Supabase: inserted topic '{title[:60]}'")
                else:
                    job_log.warning(f"Supabase insert failed: {r.status_code} {r.text[:200]}")

        elif job_type == "script_generate":
            tq_id = result_payload.get("topic_queue_id")
            if not tq_id:
                job_log.info("No topic_queue_id in script result - skipping Supabase update")
                return
            patch_data = {
                # Keep pre-generated topics claimable. The queue row becomes
                # completed only when the user claims it.
                "status": "pending",
                "pregenerated_script": result_payload.get("script"),
                "pregenerated_script_status": "ready",
                "publish_metadata": result_payload.get("publish_metadata"),
                "progress_payload": {"publish_metadata": result_payload.get("publish_metadata")},
                "narrative_blueprint": result_payload.get("narrative_blueprint"),
                "script_quality_report": result_payload.get("script_quality_report"),
            }
            r = _req.patch(
                f"{supabase_url}/rest/v1/topics_queue?id=eq.{tq_id}",
                headers={**headers, "Prefer": "return=minimal"},
                json=patch_data,
                timeout=10,
            )
            if r.status_code not in (200, 204):
                fallback = {
                    k: v for k, v in patch_data.items()
                    if k not in ("narrative_blueprint", "script_quality_report", "publish_metadata")
                }
                r = _req.patch(
                    f"{supabase_url}/rest/v1/topics_queue?id=eq.{tq_id}",
                    headers={**headers, "Prefer": "return=minimal"},
                    json=fallback,
                    timeout=10,
                )
            if r.status_code in (200, 204):
                job_log.info(f"Supabase: marked topics_queue#{tq_id} as completed")
            else:
                job_log.warning(f"Supabase patch failed: {r.status_code} {r.text[:200]}")

        elif job_type == "script_plan_generate":
            tq_id = result_payload.get("topic_queue_id")
            if not tq_id:
                job_log.info("No topic_queue_id in plan result — skipping Supabase update")
                return
            structure = result_payload.get("structure", {})
            scene_count = structure.get("scene_count")
            patch_data = {
                "pregenerated_structure": structure,
                "pregenerated_structure_status": "ready",
            }
            if scene_count:
                patch_data["total_scenes"] = scene_count
            if patch_data:
                r = _req.patch(
                    f"{supabase_url}/rest/v1/topics_queue?id=eq.{tq_id}",
                    headers={**headers, "Prefer": "return=minimal"},
                    json=patch_data,
                    timeout=10,
                )
                if r.status_code not in (200, 204):
                    # Older deployments may not yet have the optional plan
                    # metadata columns. Preserve the scene count at minimum.
                    fallback = {"total_scenes": scene_count} if scene_count else {}
                    if fallback:
                        r = _req.patch(
                            f"{supabase_url}/rest/v1/topics_queue?id=eq.{tq_id}",
                            headers={**headers, "Prefer": "return=minimal"},
                            json=fallback,
                            timeout=10,
                        )
                if r.status_code in (200, 204):
                    job_log.info(f"Supabase: updated topics_queue#{tq_id} with plan data")
                else:
                    job_log.warning(f"Supabase patch failed: {r.status_code} {r.text[:200]}")

        # topic_benchmark_analyze — no Supabase table to write to; results are
        # consumed by subsequent script_plan_generate / script_generate jobs.

    except Exception as e:
        job_log.warning(f"Supabase save failed (non-fatal): {e}")


def process_one_job(job: dict) -> None:
    job_id = job["job_id"]
    job_type = job.get("job_type") or "topic_research"
    job_log = get_job_logger(job_id)
    job_log.info(f"Claimed {job_type} job (source={job.get('source')}, remote_job_id={job.get('remote_job_id')}), payload={job['payload']}")
    logger.info(f"Claimed job {job_id} ({job_type})")

    # [AIR-0230] Lease renewal + central outcome reporting, ported from
    # render_worker.py's process_one_job - see _start_lease_renewal /
    # _report_remote_outcome docstrings for why this wraps the whole
    # dispatch rather than living inside each _process_topic_* function.
    renew_thread, renew_stop = _start_lease_renewal(job, job_log)
    _last_success_at = None
    _last_error = None
    try:
        # A running worker must not keep a stale model choice after an
        # operator changes the web-admin setting. Keep this inside the job
        # boundary so a bad setting is recorded, retried, and reported rather
        # than leaving a claimed job stranded.
        ensure_project_root_on_path()
        from config import Config

        Config.refresh_remote_keys_if_stale()
        invalid_models = Config.validate_generation_models()
        if invalid_models:
            raise RuntimeError(f"Invalid generation model settings: {', '.join(invalid_models)}")

        if job_type == "topic_benchmark_analyze":
            output_ref, result_payload = _process_topic_benchmark_analyze(job, job_id, job_log)
        elif job_type == "web_research":
            output_ref, result_payload = _process_web_research(job, job_id, job_log)
        elif job_type == "script_plan_generate":
            output_ref, result_payload = _process_script_plan_generate(job, job_id, job_log)
        elif job_type == "script_generate":
            output_ref, result_payload = _process_script_generate(job, job_id, job_log)
        else:
            output_ref, result_payload = _process_topic_research(job, job_id, job_log)

        _report_remote_outcome(job, job_log, success=True, output_ref=output_ref, result_payload=result_payload)
        _save_result_to_supabase(job_type, result_payload, job_log)
        _last_success_at = time.time()

    except job_store.InvalidTransitionError as e:
        logger.warning(f"Job {job_id} state changed externally mid-run, aborting our own processing: {e}")
        job_log.warning(f"Aborted: externally transitioned ({e})")
    except Exception as e:
        error_message = str(e)
        job_store.transition(job_id, job_store.FAILED, reason=error_message, error_code="HERMES_EXCEPTION", error_message=error_message)
        job_log.error(f"FAILED: [HERMES_EXCEPTION] {error_message}")
        refreshed = job_store.get_job(job_id)
        if refreshed["retry_count"] < refreshed["max_retries"]:
            job_store.transition(job_id, job_store.QUEUED, reason=f"auto-retry after failure ({refreshed['retry_count'] + 1}/{refreshed['max_retries']})")
            job_log.info(f"Re-queued for retry {refreshed['retry_count'] + 1}/{refreshed['max_retries']}")
        _report_remote_outcome(job, job_log, success=False, error_code="HERMES_EXCEPTION", error_message=error_message)
        _last_error = error_message
    finally:
        if renew_stop:
            renew_stop.set()
        # Clear last_error if the job completed successfully (last_success_at is set)
        _last_err_val = _last_error if _last_error is not None else ("" if _last_success_at is not None else None)
        write_state("idle", None, 0, last_success_at=_last_success_at, last_error=_last_err_val)


def run_forever():
    clear_shutdown_flag("hermes_worker")
    logger.info(f"Hermes Worker (real) starting, pid={os.getpid()}, worker_instance_id={WORKER_INSTANCE_ID}, remote_enabled={REMOTE_ENABLED}")
    # A fresh process start is a recovery boundary. Do not surface the
    # previous process's failure as if it were a current error.
    write_state("idle", None, 0, last_error="")
    next_remote_heartbeat_at = 0.0

    try:
        if REMOTE_ENABLED:
            try:
                central_client.register(WORKER_ID, WORKER_INSTANCE_ID, SUPPORTED_JOB_TYPES)
            except Exception as exc:
                logger.warning(f"Central worker registration failed; claims will retry: {exc}")
        while not _should_stop():
            try:
                # Checkpoint: don't even start a new job while the render
                # priority policy has paused us (docs/AIR_WORKER_RESOURCE_POLICY.md
                # §2, manager.py::_apply_resource_policy) - a job already in
                # flight is never interrupted mid-call, only the NEXT claim
                # is held back.
                while is_paused() and not _should_stop():
                    write_state("paused", None, 0)
                    time.sleep(1)
                if _should_stop():
                    break

                # [AIR-0230] Local job_store is tried first (dev/test, no
                # service_role needed); central claim only engages when
                # AIRWORKER_CENTRAL_SERVER_URL is set - mirrors
                # render_worker.py's run_forever() exactly.
                _flush_pending_remote_acks()

                if REMOTE_ENABLED and time.time() >= next_remote_heartbeat_at:
                    _send_remote_heartbeat()
                    next_remote_heartbeat_at = time.time() + REMOTE_HEARTBEAT_INTERVAL_SECONDS

                # Production Hermes must service the central queue first.
                # Local jobs are retained for development/offline recovery,
                # but must not starve user-facing pre-generation work.
                job = _try_remote_claim() if REMOTE_ENABLED else None
                if not job:
                    job = job_store.claim_next_job(SUPPORTED_JOB_TYPES, os.getpid())
                if not job:
                    write_state("idle", None, 0)
                    time.sleep(1.0)
                    continue
                process_one_job(job)
            except Exception as e:
                logger.error(f"Unexpected error in main loop iteration (non-fatal, continuing): {e}")
                write_state("idle", None, 0, last_error=str(e))
                time.sleep(1.0)
    finally:
        write_state("stopped", None, 0)
        logger.info("Hermes Worker stopped")


def main():
    signal.signal(signal.SIGINT, _handle_signal)
    try:
        signal.signal(signal.SIGTERM, _handle_signal)
    except (AttributeError, ValueError):
        pass
    run_forever()


if __name__ == "__main__":
    if "--crash-now" in sys.argv:
        logger.info("--crash-now flag set, exiting with non-zero status immediately")
        sys.exit(1)
    main()
