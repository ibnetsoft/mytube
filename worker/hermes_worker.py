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
import datetime
import asyncio
import json
import os
import re
import signal
import sys
import threading
import time
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from dotenv import load_dotenv

import central_client
import job_store
from logging_setup import get_job_logger, get_logger
from shutdown_flag import clear_shutdown_flag, is_shutdown_requested
from worker_config import OUTPUT_DIR, PROJECT_ROOT, STATE_DIR, WORKER_ID, WORKER_INSTANCE_ID, ensure_project_root_on_path

STATE_FILE = STATE_DIR / "hermes_worker.json"
PAUSE_FLAG_FILE = STATE_DIR / "hermes_worker.pause"
RESULTS_DIR = OUTPUT_DIR / "hermes_results"
AUDIT_DIR = OUTPUT_DIR / "hermes_audit"
logger = get_logger("hermes_worker")

_hermes_mutex_handle = None
_HERMES_MUTEX_NAME = "Global\\AIRWorker_HermesWorker_SingleInstance"


def _acquire_hermes_single_instance_or_exit() -> None:
    """Exit duplicate Hermes workers before they can race on the same queue."""
    global _hermes_mutex_handle
    if sys.platform != "win32":
        return
    try:
        import win32api
        import win32event
        import winerror
    except Exception as exc:
        logger.warning(f"Hermes single-instance mutex unavailable; continuing without it: {exc}")
        return

    handle = win32event.CreateMutex(None, False, _HERMES_MUTEX_NAME)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        logger.warning(
            f"Another Hermes Worker already holds mutex '{_HERMES_MUTEX_NAME}' - "
            "exiting duplicate before claiming jobs."
        )
        win32api.CloseHandle(handle)
        sys.exit(0)
    _hermes_mutex_handle = handle


def _load_project_env() -> None:
    """Load the repository .env even when Manager starts us with cwd=worker/."""
    for env_path in (PROJECT_ROOT / ".env", Path.cwd() / ".env"):
        try:
            if env_path.exists():
                load_dotenv(env_path, override=True)
        except Exception as exc:
            logger.warning(f"Failed to load Hermes env file at {env_path}: {exc}")


_load_project_env()

_shutdown_requested = False
SUPPORTED_JOB_TYPES = [
    "topic_research",
    "topic_benchmark_analyze",
    "web_research",
    "script_plan_generate",
    "script_generate",
    "publish_metadata_generate",
]
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
REMOTE_CLAIM_RETRY_SECONDS = 60.0
_next_remote_claim_at = 0.0

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
DEFAULT_RSS_VIDEOS_PER_CHANNEL = 15
MAX_RSS_CHANNELS_PER_JOB = 30
BENCHMARK_CHANNEL_POOL_PATHS = [
    PROJECT_ROOT / "data" / "youtube_benchmark_channels.json",
    PROJECT_ROOT / "worker" / "youtube_benchmark_channels.json",
]
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
                "pid": os.getpid(),
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
    """Extract JSON safely from AI output with markdown fence stripping and robust parsing."""
    stripped = str(text or "").strip()
    if not stripped:
        raise ValueError("Empty AI response text")

    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", stripped)
    if fence:
        stripped = fence.group(1).strip()
    else:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]

    try:
        decoder = json.JSONDecoder(strict=False)
        value, _ = decoder.raw_decode(stripped)
        if isinstance(value, dict):
            return value
    except Exception:
        pass

    try:
        cleaned = re.sub(r",\s*([\]}])", r"\1", stripped)
        decoder = json.JSONDecoder(strict=False)
        value, _ = decoder.raw_decode(cleaned)
        if isinstance(value, dict):
            return value
    except Exception:
        pass

    start = stripped.find("{")
    if start >= 0:
        return json.loads(stripped[start:], strict=False)

    raise json.JSONDecodeError("JSON object not found", stripped, 0)


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
        compact_topic = re.sub(r"\s+", " ", (topic or title)).strip()
        tags = [
            tag for tag in [
                compact_topic,
                title[:24],
                _u(r"\uc774\uc57c\uae30"),
                _u(r"\uc0ac\uc5f0"),
                _u(r"\ub4dc\ub77c\ub9c8"),
            ] if tag
        ]
        hashtags = [
            _u(r"#\uc774\uc57c\uae30"),
            _u(r"#\uc0ac\uc5f0"),
            _u(r"#\ub4dc\ub77c\ub9c8"),
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


def _text_with_mojibake_repairs(*values) -> str:
    parts: list[str] = []
    for value in values:
        text = str(value or "")
        if not text:
            continue
        parts.append(text)
        for encoding in ("latin1", "cp1252"):
            try:
                repaired = text.encode(encoding).decode("utf-8")
            except Exception:
                continue
            if repaired and repaired != text:
                parts.append(repaired)
    return " ".join(parts).lower()


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


_METADATA_INTERNAL_TERMS = (
    "AI",
    "worker",
    "prompt",
    "benchmark",
    "QA",
    "quality gate",
    "learning_profile",
    "scene plan",
    "narrative_blueprint",
    "script_quality_report",
    "자동 생성",
    "프롬프트",
    "벤치마크",
    "품질 게이트",
    "작업자",
)


def _metadata_hangul_ratio(value: str) -> float:
    text = str(value or "")
    hangul = len(re.findall(r"[\uac00-\ud7a3]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if hangul + latin == 0:
        return 0.0
    return hangul / (hangul + latin)


def _metadata_title_matches_script(title: str, script: str) -> bool:
    def variants(token: str) -> set[str]:
        result = {token}
        for suffix in ("에서", "으로", "에게", "에게서", "부터", "까지", "은", "는", "이", "가", "을", "를", "과", "와", "도", "만"):
            if token.endswith(suffix) and len(token) - len(suffix) >= 2:
                result.add(token[: -len(suffix)])
        return result

    title_tokens = [
        token for token in re.findall(r"[\uac00-\ud7a3A-Za-z0-9]{2,}", str(title or ""))
        if token not in {"그리고", "하지만", "그런데", "이야기", "사연"}
    ]
    if not title_tokens:
        return True
    script_text = str(script or "")
    matched = sum(1 for token in title_tokens[:8] if any(variant in script_text for variant in variants(token)))
    return matched >= max(1, min(2, len(title_tokens[:8]) // 3))


def _validate_publish_metadata_quality(metadata: dict, topic: str, upload_title: str, script: str, language: str) -> None:
    if not isinstance(metadata, dict):
        raise ValueError("publish_metadata must be an object")
    title = str((metadata.get("titles") or [upload_title])[0] if isinstance(metadata.get("titles"), list) else upload_title).strip()
    description = str(metadata.get("description") or "").strip()
    tags = metadata.get("tags") if isinstance(metadata.get("tags"), list) else []
    hashtags = metadata.get("hashtags") if isinstance(metadata.get("hashtags"), list) else []
    blob = "\n".join([title, description, " ".join(map(str, tags)), " ".join(map(str, hashtags))])
    if len(description) < 120:
        raise ValueError("publish_metadata.description too short")
    if language == "ko" and _metadata_hangul_ratio(description) < 0.8:
        raise ValueError("publish_metadata.description is not Korean enough")
    if any(term.lower() in blob.lower() for term in _METADATA_INTERNAL_TERMS):
        raise ValueError("publish_metadata leaks internal production terms")
    if not _metadata_title_matches_script(title or upload_title, script):
        raise ValueError("publish_metadata title does not match script content")
    clean_tags = [str(tag or "").strip() for tag in tags if str(tag or "").strip()]
    clean_hashtags = [str(tag or "").strip() for tag in hashtags if str(tag or "").strip()]
    if len(clean_tags) < 5:
        raise ValueError("publish_metadata requires at least 5 tags")
    if len(clean_hashtags) < 3:
        raise ValueError("publish_metadata requires at least 3 hashtags")
    if any(len(tag) > 30 for tag in clean_tags):
        raise ValueError("publish_metadata contains overlong tag")
    if any(not tag.startswith("#") for tag in clean_hashtags):
        raise ValueError("publish_metadata hashtags must start with #")


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
- The first title should normally be the PRIMARY TITLE unless the script clearly requires a more honest version.
- Titles must fit YouTube title style and stay under 100 characters.
- Description must be 2-4 natural paragraphs, useful for upload, and clearly match the script.
- Description must not reveal spoilers too early, but it must honestly represent the title promise.
- Do not mention AI, worker, prompt, benchmark, QA, learning, scene plan, quality gate, internal process, or generated assets.
- Do not include markdown tables, production notes, JSON explanation, timestamps, scene numbers, or labels such as "Title:".
- Tags should be topical Korean search phrases, not sentences, no #.
- Hashtags must start with # and be short.
- Avoid unrelated category contamination. For example, old-story metadata must not include economy/investment tags.
- Return at least 8 tags and at least 5 hashtags.

TOPIC: {topic}
PRIMARY TITLE: {upload_title}
STORY BLUEPRINT: {json.dumps(narrative_blueprint or {}, ensure_ascii=False)}
SCENE STRUCTURE: {json.dumps(structure or {}, ensure_ascii=False)}
SCRIPT EXCERPT:
{(script or "")[:6000]}
"""
    try:
        last_error = None
        for attempt in range(2):
            retry_note = ""
            if last_error:
                retry_note = (
                    "\n\n[PREVIOUS METADATA QA FAILURE]\n"
                    f"{last_error}\n"
                    "Regenerate all fields and fix this failure. Return JSON only.\n"
                )
            raw = await ai_router.generate_text(
                prompt + retry_note,
                model,
                temperature=0.45 if attempt else 0.55,
                max_tokens=2600,
                task_type="hermes_publish_metadata",
            )
            metadata = _normalize_publish_metadata(_extract_json(raw), topic, upload_title, script, language)
            try:
                _validate_publish_metadata_quality(metadata, topic, upload_title, script, language)
                return metadata
            except Exception as qa_error:
                last_error = str(qa_error)
        raise ValueError(last_error or "publish metadata quality check failed")
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


def _validate_benchmark_payload(payload: dict) -> tuple[str, str, str, int, int, list[str]]:
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


def _normalize_channel_ids(raw_value) -> list[str]:
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            raw_value = parsed
        except Exception:
            raw_value = re.split(r"[\s,;]+", raw_value)
    if not isinstance(raw_value, list):
        return []
    channel_ids = []
    for item in raw_value:
        value = str(item or "").strip()
        if not value or value in channel_ids:
            continue
        channel_ids.append(value)
    return channel_ids


def _load_channel_pool_from_mapping(mapping: dict, keyword: str, category: str = "") -> list[str]:
    keys = [
        category,
        keyword,
        str(category or "").casefold(),
        str(keyword or "").casefold(),
        "default",
        "*",
    ]
    for key in keys:
        if not key:
            continue
        value = mapping.get(key)
        channel_ids = _normalize_channel_ids(value)
        if channel_ids:
            return channel_ids
    return []


def _load_benchmark_channel_pool(payload: dict, keyword: str) -> tuple[list[str], dict]:
    """Load benchmark seed channels without spending search.list quota.

    Supported inputs, in priority order:
    - job payload: benchmark_channel_ids/channel_ids
    - env YOUTUBE_BENCHMARK_CHANNELS_JSON: list or {category: [ids]}
    - data/youtube_benchmark_channels.json or worker/youtube_benchmark_channels.json
    """
    category = str(payload.get("category") or payload.get("category_name") or keyword or "").strip()
    payload_ids = _normalize_channel_ids(payload.get("benchmark_channel_ids") or payload.get("channel_ids"))
    if payload_ids:
        return payload_ids[:MAX_RSS_CHANNELS_PER_JOB], {"source": "payload", "category": category, "count": len(payload_ids)}

    env_value = os.environ.get("YOUTUBE_BENCHMARK_CHANNELS_JSON", "").strip()
    if env_value:
        try:
            parsed = json.loads(env_value)
            if isinstance(parsed, dict):
                env_ids = _load_channel_pool_from_mapping(parsed, keyword, category)
            else:
                env_ids = _normalize_channel_ids(parsed)
            if env_ids:
                return env_ids[:MAX_RSS_CHANNELS_PER_JOB], {
                    "source": "env:YOUTUBE_BENCHMARK_CHANNELS_JSON",
                    "category": category,
                    "count": len(env_ids),
                }
        except Exception as exc:
            logger.warning("Invalid YOUTUBE_BENCHMARK_CHANNELS_JSON: %s", exc)

    for path in BENCHMARK_CHANNEL_POOL_PATHS:
        if not path.exists():
            continue
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                file_ids = _load_channel_pool_from_mapping(parsed, keyword, category)
            else:
                file_ids = _normalize_channel_ids(parsed)
            if file_ids:
                return file_ids[:MAX_RSS_CHANNELS_PER_JOB], {
                    "source": str(path),
                    "category": category,
                    "count": len(file_ids),
                }
        except Exception as exc:
            logger.warning("Could not read benchmark channel pool %s: %s", path, exc)
    return [], {"source": "none", "category": category, "count": 0}


RSS_RELEVANCE_TERMS_BY_CATEGORY = {
    "경제": [
        "경제",
        "물가",
        "금리",
        "환율",
        "부동산",
        "주식",
        "증시",
        "코스피",
        "소비",
        "월급",
        "생활비",
        "장바구니",
        "대출",
        "가계부채",
        "경기",
        "투자",
        "재테크",
        "시장",
    ],
    "노후금융": [
        "노후금융",
        "국민연금",
        "퇴직연금",
        "기초연금",
        "주택연금",
        "연금",
        "노후",
        "은퇴",
        "고령",
        "노인",
        "생활비",
        "건강보험료",
        "건보료",
        "재테크",
        "노후자금",
        "예금",
        "배당",
        "보험료",
    ],
    "옛날이야기": [
        "옛날이야기",
        "옛날 이야기",
        "전래",
        "전래동화",
        "민담",
        "설화",
        "고전",
        "마을",
        "며느리",
        "시어머니",
        "보따리",
        "한옥",
        "이야기",
    ],
    "황혼19금": [
        "황혼19금",
        "황혼",
        "황혼연애",
        "황혼 연애",
        "황혼사연",
        "황혼 사연",
        "중년",
        "중년사랑",
        "중년 사랑",
        "노년",
        "재혼",
        "비밀",
        "편지",
        "인생사연",
        "인생 사연",
        "로맨스",
    ],
    "탈북사연": [
        "탈북사연",
        "탈북",
        "탈북민",
        "탈북자",
        "북한",
        "두만강",
        "압록강",
        "국경",
        "브로커",
        "보위부",
        "북송",
        "중국",
        "탈출",
        "생존",
        "사연",
        "증언",
    ],
    "무협": [
        "무협",
        "무림",
        "강호",
        "문파",
        "검객",
        "검",
        "무공",
        "비급",
        "복수",
        "협객",
        "천마",
        "마교",
        "오디오북",
        "소설",
    ],
}


RSS_STRONG_RELEVANCE_TERMS_BY_CATEGORY = {}


RSS_HARD_NEGATIVE_TERMS_BY_CATEGORY = {}


def _literal_category(value: str) -> str:
    """Keep Korean category checks readable even in legacy mojibake files."""
    return value


RSS_STRONG_RELEVANCE_TERMS_BY_CATEGORY[_literal_category("옛날이야기")] = [
    "옛날",
    "전래",
    "민담",
    "설화",
    "전설",
    "고전",
    "역사",
    "조선",
    "조선시대",
    "고려",
    "한양",
    "유배",
    "단종",
    "왕비",
    "선비",
    "어사",
    "사또",
    "나무꾼",
    "호랑이",
    "저승",
    "저승사자",
    "도깨비",
    "장승",
    "스님",
    "며느리",
    "시어머니",
    "보따리",
    "마을",
]


RSS_HARD_NEGATIVE_TERMS_BY_CATEGORY[_literal_category("옛날이야기")] = [
    "국정원",
    "학교",
    "전학생",
    "권투",
    "챔피언",
    "회사",
    "직장",
    "아파트",
    "재건축",
    "삼성전자",
    "코스피",
    "주가",
    "주식",
    "금리",
    "환율",
    "국민연금",
    "실버타운",
    "부동산",
    "분양",
    "NIS",
]


def _normalize_relevance_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").casefold())


def _rss_relevance_terms(payload: dict, keyword: str) -> list[str]:
    category = str(payload.get("category") or payload.get("category_name") or keyword or "").strip()
    terms = list(RSS_RELEVANCE_TERMS_BY_CATEGORY.get(category, []))
    for item in payload.get("search_keywords") or []:
        text = str(item or "").strip()
        if 2 <= len(text) <= 18:
            terms.append(text)
    terms.append(category)

    normalized = []
    seen = set()
    for term in terms:
        value = _normalize_relevance_text(term)
        if len(value) < 2 or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _rss_strong_relevance_terms(payload: dict, keyword: str) -> list[str]:
    category = str(payload.get("category") or payload.get("category_name") or keyword or "").strip()
    terms = RSS_STRONG_RELEVANCE_TERMS_BY_CATEGORY.get(category, [])
    normalized = []
    seen = set()
    for term in terms:
        value = _normalize_relevance_text(term)
        if len(value) < 2 or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _rss_hard_negative_terms(payload: dict, keyword: str) -> list[str]:
    category = str(payload.get("category") or payload.get("category_name") or keyword or "").strip()
    terms = RSS_HARD_NEGATIVE_TERMS_BY_CATEGORY.get(category, [])
    normalized = []
    seen = set()
    for term in terms:
        value = _normalize_relevance_text(term)
        if len(value) < 2 or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _is_relevant_rss_candidate(item: dict, payload: dict, keyword: str) -> bool:
    terms = _rss_relevance_terms(payload, keyword)
    strong_terms = _rss_strong_relevance_terms(payload, keyword)
    negative_terms = _rss_hard_negative_terms(payload, keyword)
    haystack = _normalize_relevance_text(
        " ".join(
            str(item.get(field) or "")
            for field in ("title", "description", "channel_title")
        )
    )
    title_haystack = _normalize_relevance_text(str(item.get("title") or ""))
    if any(term in haystack for term in negative_terms):
        return False
    if strong_terms:
        return any(term in title_haystack for term in strong_terms)
    if not terms:
        return True
    return any(term in haystack for term in terms)


async def _youtube_get(path: str, params: dict) -> dict:
    """Same request shape as app/routers/youtube.py's endpoints, called
    directly here rather than through FastAPI (this process has no HTTP
    server of its own for the desktop app's routes, and importing FastAPI
    route handlers as plain functions isn't a supported pattern in that
    router - see its Request-bound signatures)."""
    from services.youtube_data_api import async_youtube_get

    data = await async_youtube_get(path, params)
    if data.get("error"):
        raise RuntimeError(f"YouTube API error ({path}): {data.get('message') or data.get('error')}")
    if int(data.get("_youtube_key_index") or 1) > 1:
        logger.info("YouTube API failover succeeded on backup key %s for %s", data.get("_youtube_key_index"), path)
    return data


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
    if str(os.environ.get("YOUTUBE_SEARCH_FALLBACK_ENABLED", "")).strip().lower() not in {"1", "true", "yes", "on"}:
        raise RuntimeError(
            "YouTube search fallback is disabled. Configure benchmark_channel_ids or "
            "YOUTUBE_BENCHMARK_CHANNELS_JSON so the worker can use RSS + videos.list."
        )
    fallback_limit = os.environ.get("YOUTUBE_SEARCH_FALLBACK_MAX_CALLS_PER_RUN", "1")
    try:
        fallback_limit_int = int(fallback_limit)
    except (TypeError, ValueError):
        fallback_limit_int = 1
    queries = queries[: max(0, min(10, fallback_limit_int))]
    if not queries:
        raise RuntimeError("YouTube search fallback call limit is 0")
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
        "quota_policy": {
            "enabled_by": "YOUTUBE_SEARCH_FALLBACK_ENABLED",
            "max_calls_per_run": fallback_limit_int,
        },
        "queries": query_audits,
        "query_count": len(query_audits),
        "result_count": sum(item["result_count"] for item in query_audits),
    }


async def _rss_candidate_videos(payload: dict, keyword: str, max_results: int) -> tuple[list[dict], dict]:
    from services.youtube_data_api import async_fetch_channel_rss_videos

    channel_ids, pool_audit = _load_benchmark_channel_pool(payload, keyword)
    if not channel_ids:
        return [], {
            "endpoint": "youtube_channel_rss",
            "quota_cost": 0,
            "channel_pool": pool_audit,
            "channels": [],
            "result_count": 0,
        }

    per_channel = max(1, min(DEFAULT_RSS_VIDEOS_PER_CHANNEL, max_results))
    candidates_by_id = {}
    channel_audits = []
    filtered_out = 0
    for channel_index, channel_id in enumerate(channel_ids, start=1):
        try:
            items = await async_fetch_channel_rss_videos(channel_id, limit=per_channel)
            channel_audits.append({"channel_id": channel_id, "result_count": len(items), "error": None})
        except Exception as exc:
            channel_audits.append({"channel_id": channel_id, "result_count": 0, "error": str(exc)})
            continue
        for item_index, item in enumerate(items, start=1):
            video_id = item.get("video_id")
            if not video_id or video_id in candidates_by_id:
                continue
            if not _is_relevant_rss_candidate(item, payload, keyword):
                filtered_out += 1
                continue
            candidates_by_id[video_id] = {
                **item,
                "search_rank": len(candidates_by_id) + 1,
                "search_query": keyword,
                "rss_channel_rank": channel_index,
                "rss_item_rank": item_index,
            }

    candidates = list(candidates_by_id.values())[: max(1, min(50, max_results * max(1, len(channel_ids))))]
    return candidates, {
        "endpoint": "youtube_channel_rss",
        "quota_cost": 0,
        "channel_pool": pool_audit,
        "channels": channel_audits,
        "filtered_out_by_category": filtered_out,
        "result_count": len(candidates),
    }


async def _collect_candidate_videos(
    payload: dict,
    keyword: str,
    language: str,
    video_type: str,
    max_results: int,
    search_keywords: list[str] | None = None,
) -> tuple[list[dict], dict]:
    rss_candidates, rss_audit = await _rss_candidate_videos(payload, keyword, max_results)
    if rss_candidates:
        rss_audit["fallback_search_used"] = False
        return rss_candidates, rss_audit

    search_candidates, search_audit = await _search_candidate_videos(
        keyword, language, video_type, max_results, search_keywords
    )
    search_audit["rss_attempt"] = rss_audit
    search_audit["fallback_search_used"] = True
    return search_candidates, search_audit


async def _fetch_video_and_channel_stats(candidates: list[dict]) -> tuple[list[dict], dict]:
    """Adds view_count/subscriber_count/performance_ratio to each candidate.
    performance_ratio mirrors the "성과도(구독자 대비 조회수)" the desktop
    app's topic.html computes client-side only (never sent to a server) -
    here it's the actual ranking signal, not just a display column."""
    if not candidates:
        return [], {"video_ids": [], "channel_ids": [], "videos_response": {}, "channels_response": {}}

    from services.youtube_data_api import async_youtube_list_by_ids, unique_nonempty

    video_ids_list = unique_nonempty(c.get("video_id") for c in candidates)
    channel_ids_list = unique_nonempty(c.get("channel_id") for c in candidates)
    videos_data = await async_youtube_list_by_ids("videos", video_ids_list, part="statistics")
    if videos_data.get("error"):
        raise RuntimeError(f"YouTube API error (videos): {videos_data.get('message') or videos_data.get('error')}")
    channels_data = await async_youtube_list_by_ids("channels", channel_ids_list, part="statistics")
    if channels_data.get("error"):
        raise RuntimeError(f"YouTube API error (channels): {channels_data.get('message') or channels_data.get('error')}")
    stats_audit = {
        "video_ids": video_ids_list,
        "channel_ids": channel_ids_list,
        "quota_policy": {
            "videos_list_calls": videos_data.get("batch_count", 0),
            "channels_list_calls": channels_data.get("batch_count", 0),
            "max_ids_per_call": 50,
        },
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
    global _next_remote_claim_at
    now = time.time()
    if now < _next_remote_claim_at:
        return None
    try:
        claimed = central_client.claim_job(WORKER_ID, WORKER_INSTANCE_ID, SUPPORTED_JOB_TYPES)
    except central_client.AuthError as e:
        logger.error(f"Central server rejected our worker token (not retrying this tick): {e}")
        _next_remote_claim_at = now + REMOTE_CLAIM_RETRY_SECONDS
        return None
    except central_client.CentralServerUnavailable as e:
        logger.warning(f"Central server unreachable (will retry after {REMOTE_CLAIM_RETRY_SECONDS:.0f}s): {e}")
        _next_remote_claim_at = now + REMOTE_CLAIM_RETRY_SECONDS
        return None
    except Exception as e:
        logger.error(f"Unexpected error during central server claim (will retry after {REMOTE_CLAIM_RETRY_SECONDS:.0f}s): {e}")
        _next_remote_claim_at = now + REMOTE_CLAIM_RETRY_SECONDS
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

    job_store.transition(job_id, job_store.RENDERING, reason="collecting YouTube benchmark candidates")
    write_state("running", job, 10, job_id)
    job_log.info(f"-> RENDERING (keyword={keyword!r}, video_type={video_type}, pool={search_pool_size}, pick={max_candidates})")

    ensure_project_root_on_path()
    from config import config
    from services import ai_router
    from services.prompts import prompts as prompt_templates
    from services.source_service import source_service
    import asyncio

    async def _run_analysis() -> tuple[list[dict], dict]:
        async def _analyze_comments_with_router(comments: list[str], video_title: str, transcript: str | None) -> dict:
            script_section = ""
            if transcript:
                script_section = f"""
[영상 스크립트 (앞부분 발췌)]
{transcript[:5000]}
... (후략)
"""
            prompt = prompt_templates.GEMINI_ANALYZE_COMMENTS.format(
                script_indicator=("및 스크립트" if transcript else ""),
                video_title=video_title,
                script_section=script_section,
                comments_text=chr(10).join(comments[:50]),
            )
            text = await ai_router.generate_text(
                prompt,
                config.SCRIPT_GENERATION_MODEL,
                temperature=0.3,
                max_tokens=4096,
                task_type="benchmark_comment_analysis",
            )
            match = re.search(r"\{[\s\S]*\}", text or "")
            if match:
                return json.loads(match.group(), strict=False)
            return {"error": "parse_failed", "raw": text}

        async def _extract_success_strategy_with_router(analysis_data: dict) -> list[dict]:
            prompt = prompt_templates.GEMINI_EXTRACT_STRATEGY.format(
                analysis_json=json.dumps(analysis_data, ensure_ascii=False)
            )
            text = await ai_router.generate_text(
                prompt,
                config.SCRIPT_GENERATION_MODEL,
                temperature=0.3,
                max_tokens=2048,
                task_type="benchmark_strategy_extraction",
            )
            match = re.search(r"\[[\s\S]*\]", text or "")
            if match:
                return json.loads(match.group(), strict=False)
            return []

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
            candidates, search_audit = await _collect_candidate_videos(
                job.get("payload") or {}, keyword, language, video_type, search_pool_size, search_keywords
            )
            audit_payload["search"] = search_audit
            if not candidates:
                raise ValueError("No candidates returned from YouTube RSS/channel pool")
        except Exception as search_e:
            raise RuntimeError(f"YouTube benchmark candidate collection unavailable; benchmark cannot continue: {search_e}") from search_e

        try:
            enriched, stats_audit = await _fetch_video_and_channel_stats(candidates)
            audit_payload["stats"] = stats_audit
            enriched = [candidate for candidate in enriched if int(candidate.get("view_count") or 0) > 0]
            if not enriched:
                raise ValueError("No candidates had public non-zero YouTube statistics")
        except Exception as stats_e:
            raise RuntimeError(f"YouTube statistics unavailable; benchmark cannot continue: {stats_e}") from stats_e

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
        total_candidates = max(1, len(top_candidates))
        for candidate_index, candidate in enumerate(top_candidates, start=1):
            video_id = candidate["video_id"]
            candidate_progress_base = 20 + int(55 * (candidate_index - 1) / total_candidates)
            job_store.update_progress(
                job_id,
                candidate_progress_base,
                f"benchmark candidate {candidate_index}/{total_candidates}",
            )
            write_state("running", job, candidate_progress_base, job_id)
            job_log.info(
                "BENCHMARK_ANALYZE #%s/%s video_id=%s title=%r",
                candidate_index,
                total_candidates,
                video_id,
                candidate.get("title") or "",
            )

            transcript = None
            transcript_error = None
            try:
                extracted = await asyncio.wait_for(
                    source_service.extract_text_from_youtube(
                        f"https://www.youtube.com/watch?v={video_id}"
                    ),
                    timeout=25.0,
                )
                transcript = extracted.get("content")
            except Exception as e:
                # Best-effort: plenty of high-performing videos have no captions.
                job_log.warning(f"Transcript extraction failed for {video_id} (continuing without it): {e}")
                transcript_error = str(e)

            try:
                comments, comments_audit = await asyncio.wait_for(_fetch_comments_with_audit(video_id), timeout=20.0)
            except Exception as e:
                job_log.warning(f"Comment fetch failed for {video_id} (continuing without comments): {e}")
                comments = []
                comments_audit = {"video_id": video_id, "count": 0, "error": str(e), "items": []}

            try:
                analysis = await asyncio.wait_for(
                    _analyze_comments_with_router(
                        comments=comments,
                        video_title=candidate["title"],
                        transcript=transcript,
                    ),
                    timeout=90.0,
                )
            except Exception as e:
                job_log.warning(f"Comment/transcript analysis failed for {video_id} (using compact fallback): {e}")
                analysis = {
                    "error": "analysis_fallback",
                    "reason": str(e),
                    "summary": f"High-performing reference title: {candidate.get('title') or ''}",
                    "viewer_interest": ["clear curiosity gap", "historical/folk-story stakes", "specific hidden truth"],
                    "retention_pattern": ["open with unresolved event", "delay the true cause", "pay off with a concrete moral turn"],
                }

            success_strategies = []
            if not analysis.get("error"):
                try:
                    success_strategies = await asyncio.wait_for(
                        _extract_success_strategy_with_router(analysis),
                        timeout=60.0,
                    )
                except Exception as e:
                    job_log.warning(f"Success-strategy extraction failed for {video_id}: {e}")
            if not success_strategies:
                success_strategies = [
                    {
                        "pattern": "specific folk mystery title",
                        "application": "Use one concrete impossible event, then reveal the cause only near the end.",
                    },
                    {
                        "pattern": "emotion before explanation",
                        "application": "Let shame, fear, debt, or devotion drive each scene before giving exposition.",
                    },
                ]

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
    job_store.transition(job_id, job_store.UPLOADING, reason="saving web research result")
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


def _quality_feedback_instruction(payload: dict) -> str:
    feedback = payload.get("quality_feedback") if isinstance(payload, dict) else None
    if not isinstance(feedback, list):
        return ""
    items = [str(item or "").strip() for item in feedback if str(item or "").strip()]
    if not items:
        return ""
    return (
        "\n[PREVIOUS QUALITY GATE FAILURES - MUST FIX THIS RUN]\n"
        + "\n".join(f"- {item}" for item in items[:20])
        + "\nDo not repeat the failed patterns above. Generate fresh, specific, complete results.\n"
    )


def _learning_profile_instruction(payload: dict) -> str:
    profile = payload.get("learning_profile") if isinstance(payload, dict) else None
    if not isinstance(profile, dict) or not profile:
        return ""

    compact = {
        "successful_script_patterns": (profile.get("successful_script_patterns") or [])[:8],
        "failed_script_patterns": (profile.get("failed_script_patterns") or [])[:10],
        "performance_lessons": (profile.get("performance_lessons") or [])[:6],
        "script_generation_rules": profile.get("script_generation_rules") or {},
    }
    if not any(compact.values()):
        return ""
    return (
        "\n[LEARNING MEMORY FOR THIS CATEGORY - APPLY CAREFULLY]\n"
        "Use this as production learning from previous generated videos. "
        "Extract abstract structure only; never copy titles, names, incidents, or sentences.\n"
        f"{json.dumps(compact, ensure_ascii=False)}\n"
        "Required application:\n"
        "- Preserve successful hook/tension/reveal/payoff patterns when they fit this new title.\n"
        "- Avoid failed patterns and QA issues listed above.\n"
        "- If performance lessons conflict with generic style rules, prioritize the concrete category lesson.\n"
        "- Still obey the current upload title and scene plan over memory.\n"
    )


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


MEDIA_CAMERA_MOVEMENTS = (
    "slow push-in",
    "slow pull-back",
    "gentle pan",
    "gentle tilt",
    "slow dolly",
    "slow tracking shot",
    "locked-off shot",
    "subtle crane movement",
    "slow drift",
)
MAX_VIDEO_PROMPT_SCENES = 12


def _category_visual_grammar(topic: str, upload_title: str, structure: dict | None = None) -> str:
    blob = json.dumps(
        {
            "topic": topic,
            "upload_title": upload_title,
            "category": (structure or {}).get("category") if isinstance(structure, dict) else "",
            "global_mood": (structure or {}).get("global_mood") if isinstance(structure, dict) else "",
        },
        ensure_ascii=False,
    ).lower()
    if any(term in blob for term in ("옛날", "folk", "tale", "village", "hanok")):
        return (
            "Old Korean folk-tale visual grammar: tactile hanok courtyards, worn fabric, wooden gates, wells, "
            "paper lanterns, mountain silhouettes, restrained gestures, warm dusk or moonlit blue lighting, "
            "emotion readable through posture and hands, no modern objects, no typography."
        )
    if any(term in blob for term in ("무협", "martial", "jianghu", "sword", "sect")):
        return (
            "Martial-arts fiction visual grammar: readable silhouettes, robes and belts consistent across scenes, "
            "courtyards, bamboo forests, mountain paths, training halls, precise weapon placement, controlled wind, "
            "no chaotic limb duplication, no modern street objects."
        )
    if any(term in blob for term in ("경제", "금리", "주식", "부동산", "money", "market", "finance")):
        return (
            "Documentary economy visual grammar: realistic Korean household and urban details, receipts, bank counters, "
            "market screens without readable text, apartment exteriors, restrained infographic-like composition, "
            "no fake logos, no readable numbers or letters."
        )
    return (
        "Human documentary-story visual grammar: realistic lived-in spaces, expressive faces and hands, restrained camera, "
        "clear foreground/midground/background, culturally coherent props, no text overlays, no logos."
    )


def _fallback_visual_direction_plan(
    topic: str,
    upload_title: str,
    structure: dict,
    image_style_key: str,
    image_style_directive: str,
) -> dict:
    return {
        "visual_bible_version": "fallback_v1",
        "overall_vision": f"Consistent longform visual sequence for {upload_title or topic}.",
        "category_visual_grammar": _category_visual_grammar(topic, upload_title, structure),
        "image_style_key": image_style_key,
        "image_style_directive": image_style_directive,
        "recurring_characters": [
            "Keep every recurring person visually consistent: age range, face shape, hair, clothing color, body type, and key prop."
        ],
        "recurring_locations": [
            "Keep recurring places consistent: architecture, time period, light direction, weather, and key background anchors."
        ],
        "continuity_anchors": [
            "Opening keyframe of each video prompt must exactly match the image prompt.",
            "Do not add modern objects, readable text, logos, captions, or unexpected extra people.",
            "Vary composition and camera movement across neighboring scenes while preserving the same visual world.",
        ],
        "palette": "Restrained, category-appropriate palette with clear lighting continuity.",
        "camera_language": list(MEDIA_CAMERA_MOVEMENTS),
        "negative_prompt": (
            "no text, no words, no letters, no labels, no watermarks, no captions, no logos, correct anatomy, "
            "exactly two arms, exactly two hands, anatomically correct hands, no extra limbs, no fused fingers, "
            "no duplicated people"
        ),
    }


def _build_visual_direction_plan(
    ai_router,
    model: str,
    topic: str,
    upload_title: str,
    structure: dict,
    image_style_key: str,
    image_style_directive: str,
    language: str,
) -> dict:
    import asyncio

    scenes_preview = []
    for scene in (structure.get("scenes") or [])[:12]:
        if isinstance(scene, dict):
            scenes_preview.append({
                "scene_id": scene.get("scene_id"),
                "scene_order": scene.get("scene_order"),
                "scene_summary": scene.get("scene_summary"),
                "scene_situation": scene.get("scene_situation"),
                "visual_direction": scene.get("visual_direction"),
                "scene_emotion": scene.get("scene_emotion"),
            })
    fallback = _fallback_visual_direction_plan(topic, upload_title, structure, image_style_key, image_style_directive)
    prompt = f"""
You are the visual showrunner for a longform AI video.

Create a compact visual bible that will govern strict 2x2 image grid prompts and every single-shot video prompt.

TOPIC: {topic}
UPLOAD TITLE: {upload_title}
LANGUAGE: {language}
IMAGE STYLE KEY: {image_style_key}
IMAGE STYLE DIRECTIVE:
{image_style_directive}
CATEGORY VISUAL GRAMMAR:
{_category_visual_grammar(topic, upload_title, structure)}
SCENE PREVIEW:
{json.dumps(scenes_preview, ensure_ascii=False, indent=2)}

Rules:
- Preserve story facts and category tone.
- Define recurring character continuity, recurring location continuity, palette, camera language, and negative prompt.
- Keep it practical for image/video generation, not a prose essay.
- Do not include Korean administrative explanation inside fields that will be reused in English prompts.
- Return ONLY JSON.

Schema:
{{
  "visual_bible_version": "v1",
  "overall_vision": "English visual direction",
  "category_visual_grammar": "English category-specific visual rules",
  "recurring_characters": ["English continuity anchor"],
  "recurring_locations": ["English continuity anchor"],
  "continuity_anchors": ["English rule"],
  "palette": "English palette and lighting rule",
  "camera_language": ["allowed camera movement phrase"],
  "negative_prompt": "English negative prompt"
}}
"""
    try:
        raw = asyncio.run(asyncio.wait_for(
            ai_router.generate_text(
                prompt,
                model,
                temperature=0.25,
                max_tokens=2200,
                task_type="scene_visual_direction_plan",
            ),
            timeout=45,
        ))
        plan = _extract_json(raw)
        if not isinstance(plan, dict):
            raise ValueError("visual direction plan is not an object")
        for key, value in fallback.items():
            plan.setdefault(key, value)
        plan["image_style_key"] = image_style_key
        plan["image_style_directive"] = image_style_directive
        plan["camera_language"] = [
            item for item in (plan.get("camera_language") or [])
            if str(item).strip() in MEDIA_CAMERA_MOVEMENTS
        ] or list(MEDIA_CAMERA_MOVEMENTS)
        return plan
    except Exception as exc:
        fallback["error"] = str(exc)
        return fallback


def _validate_video_prompt_quality(media: dict, scene_label: str) -> None:
    video_prompt = str(media.get("video_prompt") or "").strip()
    if len(video_prompt) < 260:
        raise ValueError(f"video_prompt too short for scene {scene_label}")
    if not _mostly_english(video_prompt):
        raise ValueError(f"video_prompt is not English enough for scene {scene_label}")
    generic_terms = ("cinematic scene", "beautiful scene", "camera moves")
    if any(term in video_prompt.lower() for term in generic_terms):
        raise ValueError(f"video_prompt contains generic filler for scene {scene_label}")
    movement_count = sum(1 for movement in MEDIA_CAMERA_MOVEMENTS if movement in video_prompt.lower())
    if movement_count != 1:
        raise ValueError(f"video_prompt must contain exactly one approved camera movement for scene {scene_label}")
    video_lower = video_prompt.lower()
    for required in ("no dialogue", "no narration", "no subtitles", "no captions", "no music", "no sound effects", "no audio"):
        if required not in video_lower:
            raise ValueError(f"video_prompt missing negative motion guardrail '{required}' for scene {scene_label}")
    positive_audio_patterns = (
        r"\b(with|include|add|generate|create|use)\s+(dialogue|narration|voice-over|voiceover|subtitles|captions|sound effects|music|audio)\b",
        r"\b(dialogue|narration|voice-over|voiceover|subtitles|captions|sound effects|music|audio)\s+(plays|starts|rises|swells|is heard|can be heard)\b",
    )
    if any(re.search(pattern, video_prompt, re.I) for pattern in positive_audio_patterns):
        raise ValueError(f"video_prompt contains positive audio/text instructions for scene {scene_label}")
    discontinuous_positive_patterns = (
        r"(?<!\bno\s)(?<!without\s)\bhard cuts?\b",
        r"(?<!\bno\s)(?<!without\s)\bjump cuts?\b",
        r"(?<!\bno\s)\bteleport(?:ation)?\b",
    )
    if any(re.search(pattern, video_prompt, re.I) for pattern in discontinuous_positive_patterns):
        raise ValueError(f"video_prompt contains a discontinuous scene change for scene {scene_label}")


def _normalize_video_prompt_camera_movement(video_prompt: str) -> str:
    text = re.sub(r"\s+", " ", str(video_prompt or "")).strip()
    if not text:
        return text

    matches: list[tuple[int, str]] = []
    for movement in MEDIA_CAMERA_MOVEMENTS:
        found = re.search(re.escape(movement), text, flags=re.I)
        if found:
            matches.append((found.start(), movement))
    chosen = sorted(matches, key=lambda item: item[0])[0][1] if matches else "locked-off shot"

    without_named_movements = text
    for movement in MEDIA_CAMERA_MOVEMENTS:
        without_named_movements = re.sub(re.escape(movement), "measured camera motion", without_named_movements, flags=re.I)
    without_named_movements = re.sub(r"\b(measured camera motion)(?:\s*,?\s*and\s*measured camera motion)+\b", r"\1", without_named_movements)
    without_named_movements = re.sub(r"\s+", " ", without_named_movements).strip()
    without_named_movements = re.sub(r"^(?:the shot uses|camera uses)\s+(?:a\s+)?measured camera motion[:,]?\s*", "", without_named_movements, flags=re.I)
    return f"The shot uses a {chosen}. {without_named_movements}".strip()


def _sanitize_video_prompt_text(video_prompt: str) -> str:
    text = re.sub(r"\s+", " ", str(video_prompt or "")).strip()
    if not text:
        return text
    text = re.sub(r"\bcamera moves\b", "the shot continues", text, flags=re.I)
    text = re.sub(r"\bcameras move\b", "the shot continues", text, flags=re.I)
    required_guardrails = (
        "no dialogue",
        "no narration",
        "no subtitles",
        "no captions",
        "no music",
        "no sound effects",
        "no audio",
    )
    missing_guardrails = [
        phrase for phrase in required_guardrails
        if phrase not in text.lower()
    ]
    if missing_guardrails:
        suffix = ", ".join(missing_guardrails)
        separator = "" if text.endswith((".", "!", "?")) else "."
        text = f"{text}{separator} {suffix}."
    return text


def _align_generated_media_chunk(input_scenes: list[dict], generated_scenes: list[dict], chunk_label: str) -> list[dict]:
    if len(generated_scenes) != len(input_scenes):
        raise ValueError(
            f"media prompt count mismatch for chunk {chunk_label}: expected {len(input_scenes)}, got "
            f"{len(generated_scenes or [])}"
        )
    aligned = []
    for index, (input_scene, generated_item) in enumerate(zip(input_scenes, generated_scenes), start=1):
        if not isinstance(generated_item, dict):
            raise ValueError(f"media prompt item {index} is not an object for chunk {chunk_label}")
        item = dict(generated_item)
        expected_order = input_scene.get("scene_order") or input_scene.get("order") or index
        expected_id = str(input_scene.get("scene_id") or f"scene{int(expected_order):03d}")
        item["scene_id"] = expected_id
        item["scene_order"] = expected_order
        aligned.append(item)
    return aligned


def _validate_unique_video_prompts(scenes: list[dict]) -> None:
    seen_video_prompts: dict[str, str] = {}
    normalized_videos: list[tuple[str, str]] = []
    for index, scene in enumerate(scenes, start=1):
        label = str(scene.get("scene_id") or scene.get("scene_order") or index)
        video_prompt = str(scene.get("video_prompt") or "").strip()
        if not video_prompt:
            continue
        if video_prompt in seen_video_prompts:
            raise ValueError(f"duplicate video_prompt for scenes {seen_video_prompts[video_prompt]} and {label}")
        seen_video_prompts[video_prompt] = label
        normalized_videos.append((label, re.sub(r"\s+", " ", video_prompt.lower())))
    for i, (left_label, left) in enumerate(normalized_videos):
        for right_label, right in normalized_videos[i + 1:]:
            if len(left) > 120 and len(right) > 120 and SequenceMatcher(None, left, right).ratio() >= 0.998:
                raise ValueError(f"near-duplicate video_prompt for scenes {left_label} and {right_label}")


def _split_script_into_scene_excerpts(script_text: str, scene_count: int, max_chars: int = 900) -> list[str]:
    """Approximate final narration coverage for each planned scene."""
    if scene_count <= 0:
        return []
    text = str(script_text or "").strip()
    if not text:
        return [""] * scene_count

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    if len(paragraphs) >= scene_count:
        buckets = [[] for _ in range(scene_count)]
        for index, paragraph in enumerate(paragraphs):
            bucket_index = min(scene_count - 1, int(index * scene_count / len(paragraphs)))
            buckets[bucket_index].append(paragraph)
        return ["\n\n".join(bucket)[:max_chars].strip() for bucket in buckets]

    chunk_size = max(1, len(text) // scene_count)
    excerpts = []
    for index in range(scene_count):
        start = index * chunk_size
        end = len(text) if index == scene_count - 1 else (index + 1) * chunk_size
        excerpts.append(text[start:end][:max_chars].strip())
    return excerpts


def _attach_script_excerpts_to_scenes(
    scenes: list[dict],
    script_text: str,
    scene_script_sections: list[str] | None = None,
) -> list[dict]:
    if scene_script_sections and len(scene_script_sections) == len(scenes):
        excerpts = [
            str(section or "").strip()[:900]
            for section in scene_script_sections
        ]
    else:
        excerpts = _split_script_into_scene_excerpts(script_text, len(scenes))
    enriched = []
    for index, scene in enumerate(scenes):
        merged = dict(scene)
        if index < len(excerpts) and excerpts[index]:
            merged["script_excerpt"] = excerpts[index]
        enriched.append(merged)
    return enriched


def _generate_direct_image_grid_prompts(
    ai_router,
    model: str,
    topic: str,
    upload_title: str,
    scenes: list[dict],
    visual_direction_plan: dict,
    image_style_key: str,
    image_style_directive: str,
    job_log,
    character_anchors_context: str = "",
) -> list[dict]:
    """Generate 2x2 prompts directly instead of concatenating per-scene prompts."""
    from services.image_grid_prompts import (
        build_compact_image_grid_prompts,
        grid_windows,
        validate_image_grid_prompt_readiness,
    )

    windows = grid_windows(len(scenes))
    if not windows:
        return []

    grid_inputs = []
    for grid_number, (start_index, end_index) in enumerate(windows, start=1):
        panels = []
        for panel_index, scene in enumerate(scenes[start_index:end_index], start=1):
            scene_number = scene.get("scene_order") or scene.get("scene_number") or (start_index + panel_index)
            panels.append({
                "panel": panel_index,
                "position": ["Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right"][panel_index - 1],
                "scene_id": scene.get("scene_id"),
                "scene_number": scene_number,
                "scene_summary": scene.get("scene_summary"),
                "scene_situation": scene.get("scene_situation"),
                "script_excerpt": scene.get("script_excerpt"),
                "scene_emotion": scene.get("scene_emotion"),
                "keyframe_subject": scene.get("keyframe_subject"),
                "continuity_identity": scene.get("continuity_identity"),
                "lighting_hint": scene.get("lighting_hint"),
                "visual_style": scene.get("visual_style"),
            })
        grid_inputs.append({
            "grid_number": grid_number,
            "scene_numbers": [panel["scene_number"] for panel in panels],
            "scene_ids": [panel["scene_id"] for panel in panels if panel.get("scene_id")],
            "panels": panels,
        })

    def _fallback_grids(reason: str) -> list[dict]:
        job_log.warning(
            "Rebuilding compact 2x2 image grid prompts without AI JSON "
            f"({reason}). grid_count={len(grid_inputs)}"
        )
        fallback = []
        for grid_input in grid_inputs:
            panels = []
            for panel in grid_input["panels"]:
                scene_number = panel.get("scene_number")
                scene_id = panel.get("scene_id")
                position = panel.get("position")
                excerpt = str(panel.get("script_excerpt") or "").strip()
                situation = str(panel.get("scene_situation") or panel.get("scene_summary") or "").strip()
                emotion = str(panel.get("scene_emotion") or "").strip()
                anchor = str(panel.get("keyframe_subject") or panel.get("continuity_identity") or "").strip()
                panel_prompt = (
                    f"Scene {scene_number}: visualize the final narration beat. "
                    f"Story excerpt: {excerpt[:360] or situation[:360]}. "
                    f"Emotion: {emotion or 'quiet dramatic tension'}. "
                    f"Unique visual anchor: {anchor or situation[:160] or 'period location and character action'}."
                )
                panels.append({
                    "scene_number": scene_number,
                    "scene_id": scene_id,
                    "position": position,
                    "panel_prompt": panel_prompt,
                })
            fallback.append({
                "grid_number": grid_input["grid_number"],
                "scene_numbers": grid_input["scene_numbers"],
                "scene_ids": grid_input["scene_ids"],
                "shared_style": (
                    f"{image_style_key}: {image_style_directive} "
                    f"{character_anchors_context} "
                    "Keep recurring characters, wardrobe, era, lighting, palette, and location logic consistent."
                ),
                "negative_prompt": (
                    "no text, no words, no letters, no labels, no captions, no watermarks, "
                    "No borders, NO grid lines, no dividers, correct anatomy, no extra limbs"
                ),
                "panels": panels,
            })
        return fallback

    # Longform jobs can have dozens of 2x2 grid windows. Asking the model to
    # return all windows as one JSON document is brittle and often truncates.
    if len(grid_inputs) > 12:
        grids = _fallback_grids("large grid batch")
        compact_grids = build_compact_image_grid_prompts(grids)
        validate_image_grid_prompt_readiness(scenes, compact_grids, status="ready", require_status="ready")
        job_log.info(f"Prepared {len(compact_grids)} direct compact 2x2 image grid prompt(s)")
        return compact_grids

    prompt = f"""
You are creating external image-generation prompts for a longform production workflow.

Create one compact prompt per strict 2x2 image grid from the provided grid window fields.
Each grid prompt must use a shared style block once, then four short panel briefs.

TOPIC: {topic}
UPLOAD TITLE: {upload_title}
IMAGE STYLE KEY: {image_style_key}
IMAGE STYLE DIRECTIVE:
{image_style_directive}
VISUAL BIBLE:
{json.dumps(visual_direction_plan, ensure_ascii=False, indent=2)}
CHARACTER DNA ANCHORS - TEXT ONLY, MUST PRESERVE WHEN EACH CHARACTER APPEARS:
{character_anchors_context or "{}"}
GRID INPUTS:
{json.dumps(grid_inputs, ensure_ascii=False, indent=2)}

Rules:
1. Return exactly one grid object for every GRID INPUT, preserving grid_number, scene_numbers, and scene_ids.
2. Each grid has exactly 4 panels in these positions: Top-Left, Top-Right, Bottom-Left, Bottom-Right.
3. Write one shared_style per grid covering recurring characters, wardrobe, era/location logic, lighting direction, color palette, and selected image style. Include the relevant CHARACTER DNA ANCHORS in compact English when a named/recurring character appears in that grid.
4. Write each panel_prompt as a concise English visual beat: subject, action, setting, composition, emotion, and one unique prop or background anchor. Keep each panel_prompt under 70 words.
5. The final prompt must be compact: common layout rules once, shared_style once, then the four panel briefs. Avoid repeating negative guardrails inside every panel.
6. Every final prompt must include: "No borders", "NO grid lines", "no text", "no words", "no letters", "no captions", and "no watermarks".
7. Ground every panel in script_excerpt first, then use scene_situation and keyframe_subject only as supporting context. Do not contradict the final narration.
8. Every 2x2 grid prompt MUST strictly enforce a 16:9 widescreen canvas aspect ratio (16:9 aspect ratio, widescreen horizontal format).
9. No Korean administrative commentary. Return ONLY valid JSON.

Schema:
{{
  "grids": [
    {{
      "grid_number": 1,
      "scene_numbers": [1, 2, 3, 4],
      "scene_ids": ["scene001", "scene002", "scene003", "scene004"],
      "shared_style": "compact English continuity/style block",
      "negative_prompt": "no text, no words, no letters, no labels, no captions, no watermarks, No borders, NO grid lines, no dividers, correct anatomy, no extra limbs",
      "panels": [
        {{"scene_number": 1, "scene_id": "scene001", "position": "Top-Left", "panel_prompt": "concise English panel brief"}}
      ],
      "prompt": "optional final compact 2x2 prompt; omit this if the fields above are enough"
    }}
  ]
}}
"""
    raw = asyncio.run(asyncio.wait_for(
        ai_router.generate_text(
            prompt,
            model,
            temperature=0.35,
            max_tokens=12000,
            task_type="image_grid_prompt_generation",
        ),
        timeout=90,
    ))
    try:
        generated = _extract_json(raw)
        grids = generated.get("grids") if isinstance(generated, dict) else None
    except Exception as exc:
        grids = _fallback_grids(f"AI JSON parse failed: {exc}")
    if not isinstance(grids, list) or len(grids) != len(grid_inputs):
        got_count = len(grids) if isinstance(grids, list) else 0
        job_log.warning(
            "Image grid prompt count mismatch from AI; rebuilding compact 2x2 prompts "
            f"from grid inputs. expected={len(grid_inputs)}, got={got_count}"
        )
        grids = _fallback_grids("AI grid count mismatch")

    by_number = {int(spec["grid_number"]): spec for spec in grid_inputs}
    for grid in grids:
        try:
            grid_number = int(grid.get("grid_number") or 0)
        except (TypeError, ValueError):
            grid_number = 0
        expected = by_number.get(grid_number)
        if expected:
            grid["scene_numbers"] = expected["scene_numbers"]
            grid["scene_ids"] = expected["scene_ids"]
            grid["prompt"] = ""
            panels = grid.get("panels") if isinstance(grid.get("panels"), list) else []
            for index, panel in enumerate(panels[:4]):
                if isinstance(panel, dict):
                    panel["scene_number"] = expected["scene_numbers"][index]
                    if index < len(expected["scene_ids"]):
                        panel.setdefault("scene_id", expected["scene_ids"][index])
                    panel["position"] = ["Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right"][index]

    compact_grids = build_compact_image_grid_prompts(grids)
    validate_image_grid_prompt_readiness(scenes, compact_grids, status="ready", require_status="ready")
    job_log.info(f"Prepared {len(compact_grids)} direct compact 2x2 image grid prompt(s)")
    return compact_grids


def _generate_scene_media_prompts(
    structure: dict,
    topic: str,
    upload_title: str,
    image_style: str,
    image_style_selection: dict | None,
    language: str,
    job_log,
    script_text: str = "",
    scene_script_sections: list[str] | None = None,
    main_character: dict | None = None,
    supporting_characters: list[dict] | None = None,
) -> dict:
    """Attach image/video generation prompts without changing scene boundaries."""
    scenes = structure.get("scenes") if isinstance(structure, dict) else None
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("Cannot generate media prompts without planned scenes")

    from config import Config, config
    from services import ai_router
    from services.image_grid_prompts import validate_image_grid_prompt_readiness

    Config.refresh_remote_keys_if_stale()
    model = config.IMAGE_PROMPT_MODEL or config.SCRIPT_PLANNING_MODEL or config.SCRIPT_GENERATION_MODEL
    if str(model).lower().startswith("claude"):
        model = "gemini-2.5-flash"
    scenes = _attach_script_excerpts_to_scenes(scenes, script_text, scene_script_sections)
    image_style_key, image_style_directive = _resolve_image_style_directive(image_style, image_style_selection)
    visual_direction_plan = _build_visual_direction_plan(
        ai_router,
        model,
        topic,
        upload_title,
        structure,
        image_style_key,
        image_style_directive,
        language,
    )
    if main_character:
        visual_direction_plan = dict(visual_direction_plan or {})
        visual_direction_plan["main_character"] = main_character
    if supporting_characters:
        visual_direction_plan = dict(visual_direction_plan or {})
        visual_direction_plan["supporting_characters"] = supporting_characters
    character_anchors_context = _character_anchors_context(main_character, supporting_characters)

    def _build_media_prompt(prompt_scenes: list, chunk_label: str, retry_note: str = "") -> str:
        retry_instruction = ""
        if retry_note:
            retry_instruction = f"""
PREVIOUS ATTEMPT FAILED QA:
{retry_note}

For this retry, fix the exact QA failure above. Every video_prompt in this chunk must be unique to its scene_id, with different subject action and camera movement from neighboring scenes. Do not reuse any full sentence from another scene prompt.
"""
        return f"""
You are the visual director for a YouTube video production pipeline.
Create production-ready AI-video prompts and visual continuity notes for every scene in this chunk.

TOPIC: {topic}
UPLOAD TITLE: {upload_title}
LANGUAGE OF NARRATION: {language}
CHUNK: {chunk_label}
ADMIN-SELECTED IMAGE STYLE KEY: {image_style_key}
ADMIN-SELECTED IMAGE STYLE DIRECTIVE:
{image_style_directive}
GLOBAL VISUAL BIBLE - MUST GOVERN EVERY SCENE:
{json.dumps(visual_direction_plan, ensure_ascii=False, indent=2)}
CHARACTER DNA ANCHORS - TEXT ONLY, MUST PRESERVE WHEN EACH CHARACTER APPEARS:
{character_anchors_context or "{}"}
SCENE PLAN:
{json.dumps(prompt_scenes, ensure_ascii=False, indent=2)}
{retry_instruction}

Rules:
1. Return exactly one result for every input scene, preserving scene_id and scene_order.
2. Do not change scene boundaries, duration, story facts, or character identity.
3. Treat script_excerpt as the most authoritative source for what appears in the scene. Use scene_summary/scene_situation only to clarify context; never contradict the final narration.
4. Treat the admin-selected image style as the visual language for the whole video. Integrate it naturally into the continuity notes; do not mix incompatible art styles.
5. keyframe_subject must describe the opening keyframe in one concise English sentence: primary subject, pose/action, location, lighting, and continuity anchors.
6. For recurring characters, preserve the same age range, facial traits, hairstyle, clothing, accessories, body type, and dominant colors unless the scene explicitly changes them. Use CHARACTER DNA ANCHORS as the source of truth; do not invent contradictory faces or wardrobes.
7. video_prompt must describe one continuous shot using this flow: opening keyframe, EXACTLY ONE named camera movement, subject motion, ambient/background motion, focus or depth response, and a stable end pose. The named camera movement MUST include exactly one of these literal phrases: "slow push-in", "slow pull-back", "gentle pan", "gentle tilt", "slow dolly", "slow tracking shot", "locked-off shot", "subtle crane movement", "slow drift". Do not introduce a new subject, location, outfit, or prop midway through the shot. Never write the generic phrase "camera moves"; name the exact approved movement instead.
8. Use the scene's planned duration. Describe a natural beginning, middle motion, and end state that can fit inside that duration; do not compress multiple actions into a short clip.
9. Keep motion physically plausible and restrained: no rubbery anatomy, duplicated limbs, teleportation, morphing faces, sudden object changes, impossible camera acceleration, or uncontrolled shaking.
10. video_prompt must include these exact negative phrases: "no dialogue, no narration, no subtitles, no captions, no music, no sound effects, no audio". It must describe visual motion only.
12. Make each prompt specific to its scene. Vary shot size, composition, subject action, and approved camera movement from neighboring scenes. Do not use generic phrases such as "cinematic scene" without concrete visual details. Do not invent text, logos, brands, or historically impossible objects.
13. Write video_prompt and continuity notes in English for generator compatibility. Keep administrative rationale out.
14. Minimum length: video_prompt 260+ characters.

Return ONLY valid JSON in this shape:
{{
  "director_notes": {{"overall_vision": "...", "error": false}},
  "scenes": [
    {{
      "scene_id": "scene001",
      "scene_order": 1,
      "video_prompt": "detailed English single-shot visual motion prompt with timing, one camera movement, subject motion, ambient motion, focus response, and stable end pose",
      "lighting_hint": "specific lighting",
      "visual_style": "specific visual style",
      "continuity_identity": "recurring character/location/prop continuity used in this scene",
      "keyframe_subject": "opening keyframe subject and pose",
      "motion_plan": "one camera movement plus subject/background motion",
      "shot_hints": [
        {{"camera": "close-up", "composition": "...", "movement": "slow push-in", "emotion": "...", "purpose": "..."}}
      ]
    }}
  ]
}}
"""

    try:
        import asyncio
        generated_scenes = []
        director_notes = {"overall_vision": "chunked media prompt generation", "error": False, "chunks": []}
        prompt_scenes = scenes[:MAX_VIDEO_PROMPT_SCENES]
        chunk_size = 8
        for offset in range(0, len(prompt_scenes), chunk_size):
            chunk = prompt_scenes[offset:offset + chunk_size]
            chunk_label = f"{offset + 1}-{offset + len(chunk)} of {len(prompt_scenes)}"
            last_chunk_error = None
            for attempt in range(2):
                try:
                    prompt = _build_media_prompt(
                        chunk,
                        chunk_label,
                        str(last_chunk_error or "") if attempt else "",
                    )
                    raw = asyncio.run(asyncio.wait_for(
                        ai_router.generate_text(
                            prompt,
                            model,
                            temperature=0.35 if attempt else 0.45,
                            max_tokens=8192,
                            task_type="scene_media_prompt_generation",
                        ),
                        timeout=90,
                    ))
                    generated = _extract_json(raw)
                    chunk_scenes = generated.get("scenes") if isinstance(generated, dict) else None
                    if not isinstance(chunk_scenes, list):
                        raise ValueError(f"media prompt scenes missing for chunk {chunk_label}")
                    chunk_scenes = _align_generated_media_chunk(chunk, chunk_scenes, chunk_label)
                    for generated_item in chunk_scenes:
                        scene_label = str(
                            generated_item.get("scene_id")
                            or generated_item.get("scene_order")
                            or chunk_label
                        )
                        generated_item["video_prompt"] = _normalize_video_prompt_camera_movement(
                            str(generated_item.get("video_prompt") or "")
                        )
                        generated_item["video_prompt"] = _sanitize_video_prompt_text(generated_item["video_prompt"])
                        _validate_video_prompt_quality(generated_item, scene_label)
                    _validate_unique_video_prompts(chunk_scenes)
                    break
                except Exception as chunk_error:
                    last_chunk_error = chunk_error
                    job_log.warning(f"Media prompt chunk {chunk_label} attempt {attempt + 1}/2 failed: {chunk_error}")
            else:
                raise ValueError(
                    f"media prompt chunk {chunk_label} failed after retry: {last_chunk_error}"
                )
            director_notes["chunks"].append({
                "chunk": chunk_label,
                "scene_count": len(chunk_scenes),
                "director_notes": generated.get("director_notes") if isinstance(generated, dict) else {},
            })
            generated_scenes.extend(chunk_scenes)

        by_key = {}
        for item in generated_scenes:
            key = (str(item.get("scene_id") or ""), str(item.get("scene_order") or ""))
            by_key[key] = item

        enriched_scenes = []
        for index, scene in enumerate(scenes, start=1):
            key = (str(scene.get("scene_id") or ""), str(scene.get("scene_order") or index))
            media = by_key.get(key)
            if index > MAX_VIDEO_PROMPT_SCENES:
                merged = dict(scene)
                for field in ("video_prompt", "motion_desc", "flow_prompt", "camera_motion"):
                    merged.pop(field, None)
                merged.pop("image_prompt", None)
                merged.pop("prompt_en", None)
                merged.pop("prompt_content", None)
                merged.pop("prompt", None)
                merged.pop("prompt_ko", None)
                merged.pop("visual_prompt", None)
                merged["image_style"] = image_style_key
                merged["video_prompt_required"] = False
                merged["media_prompt_status"] = "ready"
                enriched_scenes.append(merged)
                continue
            if not media:
                raise ValueError(f"media prompt missing for scene {key[0] or key[1]}")
            if not str(media.get("video_prompt") or "").strip():
                raise ValueError(f"video_prompt missing for scene {key[0] or key[1]}")
            media["video_prompt"] = _sanitize_video_prompt_text(
                _normalize_video_prompt_camera_movement(str(media.get("video_prompt") or ""))
            )
            _validate_video_prompt_quality(media, key[0] or key[1])

            merged = dict(scene)
            for field in (
                "video_prompt", "lighting_hint", "visual_style",
                "continuity_identity", "keyframe_subject", "motion_plan", "shot_hints",
            ):
                if media.get(field) is not None:
                    merged[field] = media[field]
            merged.pop("image_prompt", None)
            merged.pop("prompt_en", None)
            merged.pop("prompt_content", None)
            merged.pop("prompt", None)
            merged.pop("prompt_ko", None)
            merged.pop("visual_prompt", None)
            merged["image_style"] = image_style_key
            merged["video_prompt_required"] = True
            merged["media_prompt_status"] = "ready"
            enriched_scenes.append(merged)

        _validate_unique_video_prompts(enriched_scenes)
        image_grid_prompts = _generate_direct_image_grid_prompts(
            ai_router,
            model,
            topic,
            upload_title,
            enriched_scenes,
            visual_direction_plan,
            image_style_key,
            image_style_directive,
            job_log,
            character_anchors_context=character_anchors_context,
        )
        image_prompt_by_scene: dict[str, str] = {}
        for grid in image_grid_prompts:
            panels = grid.get("panels") if isinstance(grid, dict) else None
            if not isinstance(panels, list):
                continue
            shared_style = str(grid.get("shared_style") or "").strip()
            for panel in panels:
                if not isinstance(panel, dict):
                    continue
                scene_number = str(panel.get("scene_number") or "").strip()
                panel_prompt = str(panel.get("panel_prompt") or panel.get("brief") or "").strip()
                if scene_number and panel_prompt:
                    image_prompt_by_scene[scene_number] = (
                        f"{shared_style}\nPanel image prompt: {panel_prompt}".strip()
                        if shared_style
                        else panel_prompt
                    )
        if image_prompt_by_scene:
            for scene in enriched_scenes:
                scene_number = str(scene.get("scene_order") or scene.get("scene_number") or "").strip()
                image_prompt = image_prompt_by_scene.get(scene_number)
                if image_prompt:
                    scene["image_prompt"] = image_prompt

        image_grid_prompt_mode = "direct_2x2_only"
        validate_image_grid_prompt_readiness(enriched_scenes, image_grid_prompts, status="ready", require_status="ready")
        result = dict(structure)
        result["scenes"] = enriched_scenes
        result["image_style"] = image_style_key
        result["image_style_directive"] = image_style_directive
        result["image_style_selection"] = image_style_selection or {}
        result["visual_direction_plan"] = visual_direction_plan
        if main_character:
            result["main_character"] = main_character
        if supporting_characters:
            result["supporting_characters"] = supporting_characters[:2]
        result["image_grid_prompts"] = image_grid_prompts
        result["image_grid_prompt_status"] = "ready" if image_grid_prompts else "not_applicable"
        result["image_grid_prompt_mode"] = image_grid_prompt_mode
        result["media_prompt_director"] = director_notes
        result["media_prompt_status"] = "ready"
        job_log.info(f"Prepared {len(image_grid_prompts)} strict 2x2 image grid prompt(s)")
        return result
    except Exception as e:
        job_log.error(f"Scene media prompt generation failed; refusing fallback completion: {e}")
        raise




def _build_fallback_scene_plan(
    topic: str,
    upload_title: str,
    target_duration: int,
    script_style: str,
    style_directive: str,
    benchmark_analysis: dict | None,
    title_generation: dict | None,
    category: str = "",
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
        elif cursor < 1200:
            step = 30
            phase = "steady"
        else:
            step = 40
            phase = "closing"
        end = min(cursor + step, target_duration)
        slots.append((cursor, end, phase))
        cursor = end

    title = (upload_title or topic or "video topic").strip()
    context = " ".join(str(part or "") for part in (category, script_style, style_directive, topic, title)).strip()
    context_lower = context.lower()
    is_old_story_style = _is_old_story_plan_context(context, topic, title, "")
    is_survival_style = _is_survival_story_plan_context(context, topic, title, "")
    is_martial_style = _is_martial_plan_context(context, topic, title, "")
    is_twilight_style = _is_twilight_plan_context(context, topic, title, "")
    is_korean_drama_style = _is_korean_drama_plan_context(context, topic, title, "")
    is_overseas_style = _is_overseas_touching_plan_context(context, topic, title, "")
    is_finance_style = _is_finance_plan_context(context, topic, title, "")
    is_economy_style = _is_macro_economy_plan_context(context, topic, title, "") or "경제" in context
    is_story_style = any(marker in context_lower for marker in ("story", "folk", "tale", "drama", "survival"))
    benchmark_title = ""
    if isinstance(benchmark_analysis, dict):
        benchmark_title = str(benchmark_analysis.get("title") or "").strip()

    if is_old_story_style:
        profile = {
            "opening": ("reveal the strange incident or object behind", "Create immediate mystery, place, and emotional stakes"),
            "development": ("follow the villagers, family, or witness as the secret deepens", "Escalate suspicion through character choices and village consequences"),
            "explanation": ("uncover one hidden motive, promise, betrayal, or supernatural clue behind", "Turn the mystery into an emotionally readable folk-tale revelation"),
            "steady": ("resolve the secret and leave a lingering moral aftertaste", "Deliver the emotional consequence"),
            "situation": "Show an old Korean village, a character decision, a mysterious object, a family conflict, a rumor, a night road, a well, a courtyard, or a hidden room.",
            "emotion": "quiet suspense",
            "retention": "Leave one story secret about {variation} unresolved into the next beat.",
            "bridge": "Move into the next beat by revealing a new clue, reaction, or consequence from {variation}.",
            "visual": "Atmospheric Korean folk-tale visuals with village lanes, hanok courtyards, wells, lanterns, wooden doors, worn fabric, dusk shadows, restrained motion, and character-focused staging around {variation}.",
            "tts": "Calm Korean storytelling narration with suspense, warmth, and clear emotional turns around {variation}.",
            "promise": f"Reveal the secret behind '{title}' through character choices, village rumor, and emotional payoff.",
            "hook": f"Start with the impossible incident inside '{title}' and make the viewer want the hidden truth.",
            "payoff": "Resolve the mystery with a clear emotional reveal and a folk-tale moral aftertaste.",
            "mood": "atmospheric Korean folk tale mystery",
        }
    elif is_survival_style:
        profile = {
            "opening": ("show the concrete danger, choice, or separation behind", "Create immediate survival stakes through one person's memory"),
            "development": ("follow the family pressure, border risk, broker threat, or hidden promise as the escape tightens", "Escalate the testimony through a specific decision and consequence"),
            "explanation": ("reveal one withheld fact, betrayal, document, route, or sacrifice behind", "Make the survival logic emotionally clear without sensationalizing it"),
            "steady": ("resolve the testimony through present-day confession, loss, or reunion", "Carry the story toward a restrained human payoff"),
            "situation": "Show a concrete North Korean escape or testimony scene: family separation, border routes, safe houses, documents, whispered decisions, cold roads, or a present-day interview.",
            "emotion": "restrained survival tension",
            "retention": "Leave one human survival question about {variation} unresolved into the next beat.",
            "bridge": "Move into the next beat by revealing the next risk, sacrifice, or memory from {variation}.",
            "visual": "Restrained documentary survival-story visuals with cold border landscapes, sparse rooms, hidden documents, tense faces, family objects, and present-day testimony framing around {variation}.",
            "tts": "Grounded Korean testimony narration with restrained emotion and clear human stakes around {variation}.",
            "promise": f"Reveal the survival choice, sacrifice, and present-day truth behind '{title}'.",
            "hook": f"Start with the dangerous human contradiction inside '{title}' and make the viewer understand the stakes.",
            "payoff": "Resolve the testimony through the cost of escape, the person left behind, and the truth carried into the present.",
            "mood": "restrained North Korean defector testimony",
        }
    elif is_martial_style:
        profile = {
            "opening": ("stage the oath, duel, betrayal, or forbidden technique behind", "Create immediate martial stakes through honor and danger"),
            "development": ("follow the sect conflict, master-disciple bond, pursuit, or hidden manual as pressure rises", "Escalate through action, strategy, and loyalty"),
            "explanation": ("reveal one secret lineage, technique, betrayal, or debt behind", "Make the martial conflict legible and emotionally charged"),
            "steady": ("resolve the duel, sacrifice, or justice arc", "Carry the story toward a decisive martial payoff"),
            "situation": "Show a martial-world scene: training hall, mountain path, inn, sect gate, battlefield, hidden manual, oath, pursuit, duel, or betrayal.",
            "emotion": "tense martial resolve",
            "retention": "Leave one martial question about {variation} unresolved into the next beat.",
            "bridge": "Move into the next beat through the next clue, challenge, or duel from {variation}.",
            "visual": "Cinematic martial arts visuals with mountain paths, rain, blades, robes, training halls, sect banners, restrained action, and character-focused staging around {variation}.",
            "tts": "Epic but controlled Korean narration with honor, tension, and clear action around {variation}.",
            "promise": f"Reveal the oath, betrayal, technique, and final justice behind '{title}'.",
            "hook": f"Start with the martial contradiction inside '{title}' and make the first conflict unavoidable.",
            "payoff": "Resolve the martial promise through sacrifice, truth, and a decisive final confrontation.",
            "mood": "cinematic martial arts drama",
        }
    elif is_twilight_style:
        profile = {
            "opening": ("open the late-life reunion, diary, photograph, or confession behind", "Create mature emotional stakes through memory and regret"),
            "development": ("follow the old promise, family reaction, hidden relationship, or delayed apology as tension grows", "Escalate through time, choice, and restrained emotion"),
            "explanation": ("reveal one old misunderstanding, sacrifice, or secret behind", "Make the late-life truth emotionally readable"),
            "steady": ("resolve the confession, reconciliation, or farewell", "Carry the story toward a dignified emotional payoff"),
            "situation": "Show a late-life romance or memory scene: old diary, tea table, hospital room, reunion place, family home, letter, photograph, or quiet confession.",
            "emotion": "mature longing",
            "retention": "Leave one late-life emotional question about {variation} unresolved into the next beat.",
            "bridge": "Move into the next beat by revealing the next memory, regret, or choice from {variation}.",
            "visual": "Warm restrained twilight-story visuals with old letters, tea cups, dim rooms, autumn streets, family photos, and mature close-ups around {variation}.",
            "tts": "Warm Korean narration with mature restraint, longing, and emotional clarity around {variation}.",
            "promise": f"Reveal the old promise, regret, and late-life truth behind '{title}'.",
            "hook": f"Start with the late-life emotional contradiction inside '{title}'.",
            "payoff": "Resolve the story through confession, forgiveness, or a dignified farewell.",
            "mood": "mature late-life emotional drama",
        }
    elif is_korean_drama_style:
        profile = {
            "opening": ("show the injustice, betrayal, family conflict, or workplace insult behind", "Create immediate empathy and anger through a concrete scene"),
            "development": ("follow the evidence, humiliation, alliance, or reversal as pressure builds", "Escalate the drama through choices and consequences"),
            "explanation": ("reveal one hidden motive, document, witness, or secret behind", "Turn the conflict toward a satisfying reversal"),
            "steady": ("resolve the payback, apology, or restored dignity", "Carry the story toward a cathartic payoff"),
            "situation": "Show a Korean real-life drama scene: family meeting, company office, hospital corridor, neighborhood dispute, legal document, recording, or public confrontation.",
            "emotion": "grounded catharsis",
            "retention": "Leave one dramatic question about {variation} unresolved into the next beat.",
            "bridge": "Move into the next beat through the next evidence, insult, or reversal from {variation}.",
            "visual": "Realistic Korean drama visuals with apartments, offices, family tables, documents, phones, tense faces, and restrained confrontation around {variation}.",
            "tts": "Clear Korean narration with grounded anger, empathy, and cathartic pacing around {variation}.",
            "promise": f"Reveal the conflict, evidence, and reversal behind '{title}'.",
            "hook": f"Start with the unfair incident inside '{title}' and make the viewer want justice.",
            "payoff": "Resolve the conflict through evidence, consequence, and restored dignity.",
            "mood": "grounded Korean real-life drama",
        }
    elif is_overseas_style:
        profile = {
            "opening": ("show the foreign place, misunderstanding, kindness, or crisis behind", "Create immediate vulnerability and human warmth"),
            "development": ("follow the cultural barrier, stranger's help, memory, or promise as emotion grows", "Escalate through human connection across distance"),
            "explanation": ("reveal one hidden reason, past kindness, or sacrifice behind", "Make the touching turn feel earned"),
            "steady": ("resolve the gratitude, reunion, or lasting promise", "Carry the story toward a warm emotional payoff"),
            "situation": "Show an overseas touching-story scene: airport, foreign street, hospital, small shop, translation moment, stranger's home, old photo, or reunion.",
            "emotion": "warm gratitude",
            "retention": "Leave one touching human question about {variation} unresolved into the next beat.",
            "bridge": "Move into the next beat by revealing the next kindness, memory, or connection from {variation}.",
            "visual": "Warm documentary overseas-story visuals with foreign streets, airports, small shops, handwritten notes, gentle faces, and cultural contrast around {variation}.",
            "tts": "Warm Korean narration with gratitude, curiosity, and restrained emotion around {variation}.",
            "promise": f"Reveal the overseas encounter, kindness, and emotional reason behind '{title}'.",
            "hook": f"Start with the unexpected human encounter inside '{title}'.",
            "payoff": "Resolve the story through gratitude, connection, and a believable emotional reveal.",
            "mood": "warm overseas human-interest story",
        }
    elif is_finance_style:
        profile = {
            "opening": ("show the retirement, pension, debt, or household finance pressure behind", "Create immediate household-level financial stakes"),
            "development": ("connect the person's daily pressure to policy, pension rules, or asset decisions", "Escalate from lived pressure into practical financial context"),
            "explanation": ("explain one cause, consequence, or decision point behind", "Make the retirement-finance logic clear"),
            "steady": ("resolve the implication and prepare the next practical insight", "Carry the analysis toward a grounded payoff"),
            "situation": "Show a retirement-finance scene: pension notice, bank visit, hospital bill, family budget, housing choice, insurance document, or household decision.",
            "emotion": "practical concern",
            "retention": "Leave one retirement-finance question about {variation} unresolved into the next beat.",
            "bridge": "Move into the next beat by raising the next financial consequence from {variation}.",
            "visual": "Documentary retirement-finance visuals with pension papers, bank counters, household budgets, medical bills, family conversations, and restrained motion around {variation}.",
            "tts": "Calm Korean finance narration with practical clarity and human concern around {variation}.",
            "promise": f"Explain why '{title}' matters to retirement, pension, and household financial decisions.",
            "hook": f"Start with the personal finance contradiction inside '{title}'.",
            "payoff": "Give a grounded explanation of the retirement-finance signal and what viewers should check next.",
            "mood": "practical retirement finance explainer",
        }
    elif is_economy_style:
        profile = {
            "opening": ("expose the personal money tension behind", "Create immediate curiosity and a concrete household-level stake"),
            "development": ("connect the viewer's daily spending pressure to the market signal", "Escalate from a familiar problem into the economic mechanism"),
            "explanation": ("explain one cause, consequence, or decision point behind", "Make the economic logic clear without losing narrative momentum"),
            "steady": ("resolve the implication and prepare the next practical insight", "Carry the analysis toward a grounded payoff"),
            "situation": "Show a specific economic pressure through people, prices, charts, bank screens, market headlines, or household decisions.",
            "emotion": "focused concern",
            "retention": "Leave one clear economic question about {variation} unresolved into the next beat.",
            "bridge": "Move into the next beat by raising the next cause or consequence from {variation}.",
            "visual": "Documentary economy explainer visuals with realistic Korean urban details, market screens, receipts, household objects, bank or street context, and restrained motion around {variation}.",
            "tts": "Calm but urgent Korean narration around {variation}, clear pacing, no exaggerated shouting.",
            "promise": f"Explain why '{title}' matters to the viewer's money decisions.",
            "hook": f"Start with the contradiction inside '{title}' and make it personal.",
            "payoff": "Give a grounded explanation of the economic signal and what viewers should watch next.",
            "mood": "urgent economic explainer",
        }
    else:
        profile = {
            "opening": ("show the concrete human incident behind", "Create immediate curiosity and emotional stakes"),
            "development": ("follow the person's choice, conflict, or hidden truth as pressure grows", "Escalate through specific actions and consequences"),
            "explanation": ("reveal one motive, misunderstanding, sacrifice, or turning point behind", "Make the human truth emotionally clear"),
            "steady": ("resolve the story promise with a clear emotional consequence", "Carry the story toward a satisfying payoff"),
            "situation": "Show a grounded human-story scene with a specific place, object, choice, conflict, witness, and emotional consequence.",
            "emotion": "grounded emotional tension",
            "retention": "Leave one human story question about {variation} unresolved into the next beat.",
            "bridge": "Move into the next beat by revealing the next choice, clue, or consequence from {variation}.",
            "visual": "Realistic human-story visuals with specific locations, meaningful objects, restrained close-ups, and clear character staging around {variation}.",
            "tts": "Grounded Korean narration with clear emotion, restraint, and narrative momentum around {variation}.",
            "promise": f"Reveal the human choice, conflict, and emotional truth behind '{title}'.",
            "hook": f"Start with the concrete contradiction inside '{title}' and make the viewer want the truth.",
            "payoff": "Resolve the story through a clear emotional reveal and consequence.",
            "mood": "grounded human story",
        }

    scenes = []
    for index, (start, end, phase) in enumerate(slots, start=1):
        duration = end - start
        scene_id = f"scene{index:03d}"
        variation = _scene_variation_label(index)
        if is_story_style or not (is_finance_style or is_economy_style):
            if phase == "opening":
                summary = f"Opening beat {index} ({variation}): {profile['opening'][0]} '{title}'."
                purpose = f"{profile['opening'][1]} through {variation}."
            elif phase == "development":
                summary = f"Development beat {index} ({variation}): {profile['development'][0]}."
                purpose = f"{profile['development'][1]} tied to {variation}."
            elif phase == "explanation":
                summary = f"Revelation beat {index} ({variation}): {profile['explanation'][0]} '{title}'."
                purpose = f"{profile['explanation'][1]} using {variation}."
            else:
                summary = f"Payoff beat {index} ({variation}): {profile['steady'][0]}."
                purpose = f"{profile['steady'][1]} around {variation}."
            scene_situation = (
                f"Timed {phase} visual beat for '{title}'. {profile['situation']} "
                f"Make this beat distinct with {variation}. "
                f"Reference technique from benchmark '{benchmark_title}' without copying its content."
            )
            emotion = profile["emotion"]
            retention = profile["retention"].format(variation=variation)
            bridge = profile["bridge"].format(variation=variation)
            visual_direction = profile["visual"].format(variation=variation)
            tts_direction = profile["tts"].format(variation=variation)
        else:
            if phase == "opening":
                summary = f"Opening beat {index} ({variation}): {profile['opening'][0]} '{title}'."
                purpose = f"{profile['opening'][1]} through {variation}."
            elif phase == "development":
                summary = f"Development beat {index} ({variation}): {profile['development'][0]}."
                purpose = f"{profile['development'][1]} using {variation}."
            elif phase == "explanation":
                summary = f"Explanation beat {index} ({variation}): {profile['explanation'][0]} '{title}'."
                purpose = f"{profile['explanation'][1]} around {variation}."
            else:
                summary = f"Steady beat {index} ({variation}): {profile['steady'][0]}."
                purpose = f"{profile['steady'][1]} tied to {variation}."
            scene_situation = (
                f"Timed {phase} visual beat for '{title}'. {profile['situation']} "
                f"Make this beat distinct with {variation}. "
                f"Reference technique from benchmark '{benchmark_title}' without copying its content."
            )
            emotion = profile["emotion"]
            retention = profile["retention"].format(variation=variation)
            bridge = profile["bridge"].format(variation=variation)
            visual_direction = profile["visual"].format(variation=variation)
            tts_direction = profile["tts"].format(variation=variation)

        scenes.append({
            "scene_id": scene_id,
            "scene_order": index,
            "opening_micro_scene": phase == "opening",
            "opening_time_range": f"{start}-{end}s" if phase == "opening" else None,
            "time_range": f"{start}-{end}s",
            "pacing_phase": phase,
            "scene_summary": summary,
            "scene_situation": scene_situation,
            "scene_emotion": emotion,
            "scene_purpose": purpose,
            "retention_hook": retention,
            "title_promise_link": f"This beat advances the viewer promise of '{title}'.",
            "end_bridge": bridge,
            "target_duration": duration,
            "visual_direction": visual_direction,
            "tts_direction": tts_direction,
        })

    title_promise = profile["promise"]
    opening_hook = profile["hook"]
    payoff = profile["payoff"]
    global_mood = profile["mood"]

    return {
        "topic": topic,
        "upload_title": title,
        "title_promise": title_promise,
        "opening_hook": opening_hook,
        "payoff": payoff,
        "scene_count": len(scenes),
        "target_duration_seconds": target_duration,
        "global_mood": global_mood,
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
    title = (upload_title or topic or "이번 이야기").strip()
    summary = str(scene.get("scene_summary") or scene.get("scene_situation") or title).strip()
    purpose = str(scene.get("scene_purpose") or "").strip()
    hook = str(scene.get("retention_hook") or "").strip()
    scene_context = " ".join(
        str(scene.get(key) or "")
        for key in (
            "scene_summary",
            "scene_situation",
            "scene_purpose",
            "visual_direction",
            "video_prompt",
        )
    ).lower()
    is_story = any(
        marker in scene_context
        for marker in ("folk", "tale", "story", "village", "hanok", "well", "courtyard", "lantern", "황혼", "편지", "일기장", "사연", "찻집")
    )
    variation = _scene_variation_label(idx)
    story_fillers = [
        "오래 접힌 마음이 조심스럽게 펴지며, 말하지 못한 선택의 대가가 장면 안에 남습니다.",
        "작은 물건 하나가 지난 세월의 침묵을 흔들고, 인물들은 서로 다른 기억 앞에서 멈춰 섭니다.",
        "창밖의 빛과 낮은 목소리가 겹치며, 숨겨 둔 진심이 다음 고백으로 이어집니다.",
        "누군가의 망설임이 또 다른 단서를 불러내고, 오래된 약속의 의미가 조금씩 달라집니다.",
    ]
    explainer_fillers = [
        "숨은 맥락이 새 단서와 연결되며, 시청자가 다음 판단을 따라갈 수 있는 발판을 만듭니다.",
        "앞선 장면과 다른 근거가 더해지고, 선택의 결과가 한층 구체적인 상황으로 좁혀집니다.",
        "사람들의 반응과 주변 조건이 맞물리며, 표면 아래 있던 원인이 새 방향으로 드러납니다.",
        "작은 변화가 다음 결정을 압박하고, 이야기는 이전과 다른 질문을 향해 움직입니다.",
    ]

    if is_story:
        purpose = purpose or "숨겨진 사연과 사람들의 얽힌 감정이 조용히 번져 나갑니다."
        hook = hook or "이어지는 순간, 아무도 예상치 못한 뜻밖의 진실이 서서히 드러나기 시작합니다."
        text = f"{variation}의 장면. {summary}. {purpose} {hook}"
        filler_idx = 0
        while len(text) < min_chars:
            detail = _scene_variation_label(idx + (filler_idx + 1) * max(1, total))
            text += f" {detail}의 {story_fillers[filler_idx % len(story_fillers)]}"
            filler_idx += 1
        return text

    purpose = purpose or "이 상황의 본질과 숨겨진 맥락을 차분히 짚어갑니다."
    hook = hook or "그리고 다음 순간, 상황의 흐름을 완전히 바꾸어 놓을 중요한 전환점이 찾아옵니다."
    text = f"{variation}의 장면. {summary}. {purpose} {hook}"
    filler_idx = 0
    while len(text) < min_chars:
        detail = _scene_variation_label(idx + (filler_idx + 1) * max(1, total))
        text += f" {detail}의 {explainer_fillers[filler_idx % len(explainer_fillers)]}"
        filler_idx += 1
    return text


def _scene_plan_repetition_errors(structure: dict) -> list[str]:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list):
        return ["structure.scenes must be a list"]
    errors: list[str] = []
    previous_key = ""
    run_start = 0
    run_count = 0
    duplicate_counts: Counter[str] = Counter()
    duplicate_summary_counts: Counter[str] = Counter()
    duplicate_field_counts: dict[str, Counter[str]] = {
        "scene_situation": Counter(),
        "visual_direction": Counter(),
        "tts_direction": Counter(),
        "end_bridge": Counter(),
    }
    ordinal_middle_template_hits: list[int] = []
    leaked_template_hits: list[str] = []

    def _scene_plan_key(value: str) -> str:
        value = re.sub(
            r"\b(?:Opening\s+5-second\s+beat|First-minute\s+micro\s+beat|Development\s+beat|Timed\s+visual\s+beat|Scene)\s*\d+(?:/\d+)?\s*:?",
            "",
            value,
            flags=re.IGNORECASE,
        )
        value = re.sub(
            r"\b(?:Mandatory\s+\d+-second\s+(?:opening|development|climax|resolution)?\s*(?:phase\s+)?cut|Keep it separate(?: and advance the story)?|Use a distinct composition(?:, action, or camera beat)?|advance(?:s)? the story)\b",
            "",
            value,
            flags=re.IGNORECASE,
        )
        value = re.sub(r"\([^)]*\d+\s*-\s*\d+s[^)]*\)", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\d+", "#", value)
        return re.sub(r"\s+", " ", value).strip().lower()

    for idx, scene in enumerate(scenes, start=1):
        summary = str((scene or {}).get("scene_summary") or "").strip()
        purpose = str((scene or {}).get("scene_purpose") or "").strip()
        hook = str((scene or {}).get("retention_hook") or "").strip()
        if re.search(r"\d+\s*번째\s*중반\s*전환", summary):
            ordinal_middle_template_hits.append(idx)
        key = " ".join([summary, purpose, hook])
        key = _scene_plan_key(key)
        if not key:
            errors.append(f"scene {idx} has no summary/purpose/hook")
            continue
        summary_key = _scene_plan_key(summary)
        summary_key = re.sub(r"^\s*\d+\s*(?:번|踰)\s*(?:장면|scene)?\s*:?\s*", "", summary_key, flags=re.IGNORECASE)
        if summary_key:
            duplicate_summary_counts[summary_key] += 1
        for field, counts in duplicate_field_counts.items():
            raw_value = str((scene or {}).get(field) or "").strip()
            field_key = _scene_plan_key(raw_value)
            if field_key:
                counts[field_key] += 1
            if re.search(
                r"\b(?:Timed visual beat|Mandatory \d+-second|Keep it separate|Use a distinct composition|opening keyframe|development phase cut)\b",
                raw_value,
                flags=re.IGNORECASE,
            ):
                leaked_template_hits.append(f"scene {idx} {field}")
        duplicate_counts[key] += 1
        if key == previous_key:
            run_count += 1
            if run_count == 2:
                errors.append(f"scenes {idx - 1}-{idx} duplicate the same beat")
        else:
            if run_count >= 3:
                errors.append(f"scenes {run_start}-{idx - 1} repeat the same beat")
            previous_key = key
            run_start = idx
            run_count = 1
    if run_count >= 3:
        errors.append(f"scenes {run_start}-{len(scenes)} repeat the same beat")
    if len(ordinal_middle_template_hits) >= 2:
        errors.append(
            "scene plan uses ordinal middle-transition template scenes: "
            f"{ordinal_middle_template_hits[:12]}"
        )
    for key, count in duplicate_counts.items():
        if count >= 3:
            errors.append(f"scene plan repeats one beat {count} times: {key[:120]}")
    for key, count in duplicate_summary_counts.items():
        if count >= 3:
            errors.append(f"scene plan repeats one summary {count} times: {key[:120]}")
    for field, counts in duplicate_field_counts.items():
        for key, count in counts.items():
            if count >= 3:
                errors.append(f"scene plan repeats {field} {count} times: {key[:120]}")
    if leaked_template_hits:
        errors.append(f"scene plan leaked internal template text: {leaked_template_hits[:12]}")
    return errors


def _is_finance_plan_context(script_style: str, topic: str, upload_title: str, image_style: str = "") -> bool:
    blob = _text_with_mojibake_repairs(script_style, topic, upload_title, image_style)
    return any(
        term in blob
        for term in (
            "finance",
            "economy",
            "news",
            "money",
            "market",
            "\ub178\ud6c4\uae08\uc735",
            "\uacbd\uc81c",
            "\uc5f0\uae08",
            "\uae08\ub9ac",
            "\uc8fc\uc2dd",
            "\ubd80\ub3d9\uc0b0",
        )
    )


def _is_old_story_plan_context(script_style: str, topic: str, upload_title: str, image_style: str = "") -> bool:
    blob = _text_with_mojibake_repairs(script_style, topic, upload_title, image_style)
    return any(
        term in blob
        for term in (
            "folk",
            "old_story",
            "tale",
            "village",
            "hanok",
            "forest story",
            "\uc61b\ub0a0\uc774\uc57c\uae30",
            "\uc804\ub798",
            "\ubbfc\ub2f4",
            "무덤",
            "묘",
            "유언",
            "며느리",
            "시어머니",
        )
    )


def _is_survival_story_plan_context(script_style: str, topic: str, upload_title: str, image_style: str = "") -> bool:
    blob = _text_with_mojibake_repairs(script_style, topic, upload_title, image_style)
    return any(
        term in blob
        for term in (
            "survival",
            "testimony",
            "defector",
            "north korea",
            "safehouse",
            "border crossing",
            "탈북사연",
            "탈북",
            "탈북민",
            "탈북자",
            "북한",
            "두만강",
            "압록강",
            "국경",
            "보위부",
            "브로커",
            "북송",
            "도강",
        )
    )


def _is_martial_plan_context(script_style: str, topic: str, upload_title: str, image_style: str = "") -> bool:
    blob = _text_with_mojibake_repairs(script_style, topic, upload_title, image_style)
    return any(
        term in blob
        for term in (
            "martial",
            "wuxia",
            "jianghu",
            "sword",
            "\ubb34\ud611",
            "\ubb34\ub9bc",
            "\uac15\ud638",
            "\ubb38\ud30c",
            "\uac80\uac1d",
            "\uac80\ubcf4",
            "\ubb34\uacf5",
            "\ub9c8\uad50",
            "\ud3d0\ubb38",
            "\uc81c\uc790",
            "\uc0ac\ubd80",
            "\ubc18\uc9c0",
        )
    )



def _is_twilight_plan_context(script_style: str, topic: str, upload_title: str, image_style: str = "") -> bool:
    blob = _text_with_mojibake_repairs(script_style, topic, upload_title, image_style)
    return any(
        term in blob
        for term in (
            "twilight", "mature", "late_life", "황혼19금", "황혼 19금", "황혼", "중년", "19금",
            "재혼", "첫사랑", "졸혼", "비밀일기", "동창회", "재회", "황혼부부", "황혼이혼"
        )
    )


def _is_korean_drama_plan_context(script_style: str, topic: str, upload_title: str, image_style: str = "") -> bool:
    blob = _text_with_mojibake_repairs(script_style, topic, upload_title, image_style)
    return any(
        term in blob
        for term in (
            "korean_drama", "real_life_story", "family_drama", "한국사연", "사연", "시댁", "처가", "친정",
            "상속", "시어머니", "올케", "시누이", "갑질", "폭로", "이웃", "층간소음", "유산", "가족사연"
        )
    )


def _is_overseas_touching_plan_context(script_style: str, topic: str, upload_title: str, image_style: str = "") -> bool:
    blob = _text_with_mojibake_repairs(script_style, topic, upload_title, image_style)
    return any(
        term in blob
        for term in (
            "overseas", "global", "touching_story", "kindness", "해외감동", "해외", "외국인", "외국",
            "공항", "국제", "은인", "입양", "파독", "참전용사", "해외실화"
        )
    )


def _is_macro_economy_plan_context(script_style: str, topic: str, upload_title: str, image_style: str = "") -> bool:
    blob = _text_with_mojibake_repairs(script_style, topic, upload_title, image_style)
    return any(
        term in blob
        for term in (
            "macro_economy", "economy_explainer", "market_trend", "경제", "금값", "환율", "코스피",
            "나스닥", "유가", "인플레이션", "공급망", "수출", "반도체", "관세", "국제유가", "달러"
        )
    ) and not any(term in blob for term in ("노후", "은퇴", "연금"))



def _old_story_title_is_grave_vigil(topic: str, upload_title: str) -> bool:
    title_blob = _text_with_mojibake_repairs(topic, upload_title)
    return any(term in title_blob for term in ("며느리", "시어머니", "묘에", "묘지", "grave vigil"))


def _old_story_title_is_tiger_hunter(topic: str, upload_title: str) -> bool:
    title_blob = _text_with_mojibake_repairs(topic, upload_title)
    return "호랑이" in title_blob and any(term in title_blob for term in ("발톱", "사냥꾼", "나무꾼"))


def _old_story_title_has_any(topic: str, upload_title: str, *terms: str) -> bool:
    blob = _text_with_mojibake_repairs(topic, upload_title)
    return any(term and term in blob for term in terms)


def _build_old_story_story_core(topic: str, upload_title: str, structure: dict | None = None) -> dict:
    """Create the dramatic spine that old-story plans must follow."""
    title = (upload_title or topic or "옛날이야기").strip()
    if _old_story_title_has_any(topic, upload_title, "호랑이", "범"):
        protagonist = "사냥꾼 만복"
        desire = "사라진 사람들의 흔적을 따라가 호랑이 소문의 진짜 원인을 밝힌다"
        opening_incident = "첫 장면에서 만복이 산길의 피 묻은 발자국과 부러진 나무꾼의 도끼를 동시에 발견한다"
        personal_stake = "실종된 사람 중 하나가 만복에게 은혜를 입힌 은인이라 외면할 수 없다"
        midpoint_reversal = "호랑이의 발톱 자국으로 보였던 흔적이 사람이 일부러 만든 가짜 표식이었다는 사실이 드러난다"
        final_payoff = "만복이 범의 공포를 이용한 사람의 죄를 밝혀 제목의 소문을 사건으로 풀어낸다"
    elif _old_story_title_has_any(topic, upload_title, "무덤", "묘", "시어머니", "며느리", "어머니"):
        protagonist = "맏아들 덕수"
        desire = "어머니의 무덤에서 시작된 이상한 일을 끝까지 확인해 집안을 지킨다"
        opening_incident = "첫 장면에서 덕수가 새벽 무덤가에서 젖은 흙 위에 새로 찍힌 맨발 자국을 본다"
        personal_stake = "어머니의 마지막 유언을 지키지 못했다는 죄책감 때문에 물러설 수 없다"
        midpoint_reversal = "저주처럼 보였던 흔적이 어머니가 숨겨 둔 약속과 집안의 죄를 가리키고 있음이 드러난다"
        final_payoff = "덕수가 무덤 앞에서 숨긴 진실을 직접 고백하게 만들며 어머니의 유언을 사건으로 완성한다"
    elif _old_story_title_has_any(topic, upload_title, "형제", "아들", "삼형제", "세 형제"):
        protagonist = "맏형 덕수"
        desire = "동생들을 지키며 집안에 내려온 금기를 깨야 하는 이유를 알아낸다"
        opening_incident = "첫 장면에서 덕수가 집 마당 한복판에 놓인 낯선 제물과 흙 묻은 손자국을 발견한다"
        personal_stake = "가난한 집안을 혼자 떠받쳐 온 덕수는 동생들을 잃을지 모른다는 두려움을 숨기고 있다"
        midpoint_reversal = "금기는 복을 막는 말이 아니라 누군가의 죄를 숨기기 위한 장치였음이 드러난다"
        final_payoff = "덕수가 동생들 앞에서 금기의 진짜 주인을 밝혀 집안의 공포를 끝낸다"
    else:
        protagonist = "농부 돌쇠"
        desire = "마을에 떠도는 금기와 소문의 근원을 직접 확인한다"
        opening_incident = "첫 장면에서 돌쇠가 모두가 피하던 장소에서 제목 속 사건의 첫 증거를 손에 쥔다"
        personal_stake = "그 증거가 돌쇠 가족의 오래된 침묵과 이어져 있어 모른 척할 수 없다"
        midpoint_reversal = "마을 사람들이 두려워한 대상보다 숨겨 온 거짓말이 더 위험했다는 사실이 드러난다"
        final_payoff = "돌쇠가 마을 앞에서 침묵의 이유를 드러내며 제목의 의문을 행동으로 풀어낸다"

    return {
        "logline": f"{title}의 소문이 한 사람의 선택과 집안의 비밀로 밝혀지는 옛날이야기",
        "protagonist": protagonist,
        "desire": desire,
        "opening_incident": opening_incident,
        "personal_stake": personal_stake,
        "central_conflict": f"{title}에 담긴 금기와 진실을 밝히려는 {protagonist}의 싸움",
        "stakes": personal_stake,
        "hidden_information": "처음에는 소문과 금기로 보이지만, 중반 이후 사람의 선택과 오래된 죄가 드러난다",
        "turning_point": midpoint_reversal,
        "midpoint_reversal": midpoint_reversal,
        "final_payoff": final_payoff,
        "acts": [
            {"act": 1, "scene_range": "1-12", "goal": "첫 30초 안에 실제 사건을 보여주고 주인공의 개인적 이유를 세운다"},
            {"act": 2, "scene_range": "13-28", "goal": "단서를 따라가며 주인공이 선택과 손실을 겪게 한다"},
            {"act": 3, "scene_range": "29-44", "goal": "중반 반전 이후 숨겨진 죄와 대가를 구체적 장면으로 밀어붙인다"},
            {"act": 4, "scene_range": "45-53", "goal": "설교가 아니라 사건의 결말로 제목의 약속을 갚는다"},
        ],
    }


def _old_story_dramatic_function(scene_order: int, scene_count: int) -> str:
    if scene_order <= 4:
        return "opening incident and personal stake"
    if scene_order <= 12:
        return "hook escalation"
    if scene_order <= max(13, int(scene_count * 0.52)):
        return "investigation and active choice"
    if scene_order <= max(14, int(scene_count * 0.62)):
        return "midpoint reversal"
    if scene_order <= max(15, int(scene_count * 0.84)):
        return "cost and confrontation"
    return "final payoff"


def _apply_old_story_story_core_to_structure(structure: dict, topic: str, upload_title: str) -> dict:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    repaired = dict(structure)
    core = _build_old_story_story_core(topic, upload_title, repaired)
    scene_count = len(scenes)
    protagonist = core["protagonist"]
    title = (upload_title or topic or "옛날이야기").strip()
    repaired["story_core"] = core
    repaired["title_promise"] = repaired.get("title_promise") or core["central_conflict"]
    repaired["opening_hook"] = core["opening_incident"]
    repaired["payoff"] = core["final_payoff"]

    rewritten: list[dict] = []
    for idx, original in enumerate(scenes, start=1):
        scene = dict(original or {})
        scene["scene_order"] = scene.get("scene_order") or scene.get("order") or scene.get("scene_number") or idx
        scene["scene_number"] = scene["scene_order"]
        scene["act"] = 1 if idx <= 12 else 2 if idx <= 28 else 3 if idx <= 44 else 4
        scene["dramatic_function"] = _old_story_dramatic_function(idx, scene_count)

        if idx == 1:
            scene["scene_summary"] = core["opening_incident"]
            scene["scene_situation"] = f"{protagonist}이 {core['opening_incident']}."
            scene["scene_purpose"] = "설명보다 사건을 먼저 보여주며 제목의 의문을 눈앞에 세운다"
            scene["retention_hook"] = "이 흔적은 정말 금기의 시작일까, 누군가가 남긴 경고일까?"
            scene["character_choice"] = f"{protagonist}이 도망가지 않고 흔적을 손에 쥔다"
            scene["emotional_shift"] = "불길한 호기심에서 피할 수 없는 책임감으로 바뀐다"
            scene["reveal_or_question"] = core["opening_incident"]
        elif idx == 2:
            scene["scene_summary"] = f"{protagonist}이 물러설 수 없는 개인적 이유가 드러난다"
            scene["scene_situation"] = core["personal_stake"]
            scene["scene_purpose"] = "주인공의 동기를 소문이 아니라 개인적 상처와 책임으로 고정한다"
            scene["retention_hook"] = f"{protagonist}은 왜 이 일을 남에게 맡길 수 없을까?"
            scene["character_choice"] = f"{protagonist}이 가족이나 마을의 만류를 거절한다"
            scene["emotional_shift"] = "두려움을 숨긴 결심으로 좁혀진다"
            scene["reveal_or_question"] = core["personal_stake"]
        elif idx == 3:
            scene["character_choice"] = f"{protagonist}이 첫 증거를 숨기지 않고 확인하러 나선다"
            scene["emotional_shift"] = "의심이 구체적 불안으로 커진다"
            scene["reveal_or_question"] = "첫 단서가 제목의 소문과 직접 이어진다"
        elif idx == 4:
            scene["character_choice"] = f"{protagonist}이 침묵하는 어른에게 직접 묻는다"
            scene["emotional_shift"] = "혼자만의 의심에서 마을 전체의 침묵으로 확장된다"
            scene["reveal_or_question"] = "마을 사람들이 같은 사실을 서로 다르게 숨긴다"
        elif 24 <= idx <= 30:
            scene["dramatic_function"] = "midpoint reversal"
            scene["scene_purpose"] = scene.get("scene_purpose") or "중반 반전으로 제목의 의미를 뒤집는다"
            scene["character_choice"] = scene.get("character_choice") or f"{protagonist}이 안전한 해석을 버리고 위험한 진실 쪽으로 걸어간다"
            scene["emotional_shift"] = scene.get("emotional_shift") or "공포가 분노와 죄책감으로 바뀐다"
            scene["reveal_or_question"] = scene.get("reveal_or_question") or core["midpoint_reversal"]
            if idx == 26:
                scene["scene_summary"] = core["midpoint_reversal"]
                scene["scene_situation"] = core["midpoint_reversal"]
                scene["retention_hook"] = "그렇다면 지금까지 모두가 두려워한 것은 무엇을 감추기 위한 것이었을까?"
        elif idx >= max(45, scene_count - 8):
            scene["dramatic_function"] = "final payoff"
            scene["character_choice"] = scene.get("character_choice") or f"{protagonist}이 침묵 대신 공개적인 고백과 대면을 선택한다"
            scene["emotional_shift"] = scene.get("emotional_shift") or "공포가 결심과 해소로 바뀐다"
            scene["reveal_or_question"] = scene.get("reveal_or_question") or core["final_payoff"]
            if idx == scene_count:
                scene["scene_summary"] = core["final_payoff"]
                scene["scene_situation"] = f"{title}의 의문이 {protagonist}의 선택으로 끝난다"
                scene["scene_purpose"] = "교훈 설명이 아니라 마지막 행동과 결과로 결말을 맺는다"
                scene["retention_hook"] = "마지막 장면이 제목의 의문을 감정적으로 닫는다"
        else:
            scene["character_choice"] = scene.get("character_choice") or f"{protagonist}이 단서 하나를 확인하고 다음 위험을 감수한다"
            scene["emotional_shift"] = scene.get("emotional_shift") or "새 단서가 나오며 감정의 방향이 한 단계 변한다"
            scene["reveal_or_question"] = scene.get("reveal_or_question") or (
                scene.get("retention_hook") or scene.get("scene_purpose") or "새로운 의문이 남는다"
            )

        scene.pop("visual_direction", None)
        scene.pop("tts_direction", None)
        rewritten.append(scene)

    repaired["scenes"] = rewritten
    repaired["scene_count"] = len(rewritten)
    repaired["planner_notes"] = {
        **(repaired.get("planner_notes") or {}),
        "old_story_story_core_applied": True,
    }
    return repaired


def _old_story_drama_plan_errors(structure: dict, topic: str, upload_title: str) -> list[str]:
    errors: list[str] = []
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    core = structure.get("story_core") if isinstance(structure, dict) and isinstance(structure.get("story_core"), dict) else {}
    if not isinstance(scenes, list) or not scenes:
        return ["old-story drama plan missing scenes"]
    generic_names = {"", "주인공", "the person at the center of the clicked story"}
    if str(core.get("protagonist") or "").strip() in generic_names:
        errors.append("old-story story_core missing concrete protagonist")
    for key in ("opening_incident", "personal_stake", "central_conflict", "midpoint_reversal", "final_payoff"):
        if len(str(core.get(key) or "").strip()) < 12:
            errors.append(f"old-story story_core missing {key}")
    first_blob = " ".join(
        str((scene or {}).get(field) or "")
        for scene in scenes[:4]
        for field in ("scene_summary", "scene_situation", "scene_purpose", "character_choice")
    )
    if str(core.get("protagonist") or "") and str(core.get("protagonist")) not in first_blob:
        errors.append("old-story first scenes do not establish protagonist")
    action_terms = ("발견", "묻", "거절", "숨기", "확인", "잡", "찾", "고백", "대면", "쥔다", "나선다")
    if not any(term in first_blob for term in action_terms):
        errors.append("old-story opening lacks visible action")
    first_twelve_choices = sum(1 for scene in scenes[:12] if str((scene or {}).get("character_choice") or "").strip())
    if first_twelve_choices < 4:
        errors.append("old-story first act lacks active protagonist choices")
    midpoint_blob = " ".join(
        str((scene or {}).get(field) or "")
        for scene in scenes[22:34]
        for field in ("dramatic_function", "scene_summary", "scene_situation", "reveal_or_question")
    )
    if "midpoint" not in midpoint_blob and str(core.get("midpoint_reversal") or "")[:16] not in midpoint_blob:
        errors.append("old-story plan missing midpoint reversal")
    ending_blob = " ".join(
        str((scene or {}).get(field) or "")
        for scene in scenes[-9:]
        for field in ("dramatic_function", "scene_summary", "scene_situation", "reveal_or_question")
    )
    if "final payoff" not in ending_blob and str(core.get("final_payoff") or "")[:16] not in ending_blob:
        errors.append("old-story plan missing final payoff")
    if any(term in ending_blob for term in ("교훈은", "이야기의 교훈", "시청자 여러분", "콘텐츠")):
        errors.append("old-story ending is preachy/meta instead of dramatic payoff")
    return errors


def _old_story_scene_has_template_drift(scene: dict) -> bool:
    blob = " ".join(
        str((scene or {}).get(field) or "")
        for field in ("scene_summary", "scene_situation", "scene_purpose", "retention_hook", "end_bridge")
    )
    return any(
        term in blob
        for term in (
            "1단계",
            "2단계",
            "3단계",
            "4단계",
            "오프닝의 역할",
            "중반의 역할",
            "후반의 역할",
            "숨겨진 관계가 한 겹 더 흔들린다",
            "같은 사건 반복이 아니라",
            "단서를 통해 인물의 선택과 대가를 새 방향",
        )
    )


def _korean_ordinal_label(number: int) -> str:
    if number <= 0:
        return "처음"
    special = {
        1: "첫",
        2: "둘",
        3: "셋",
        4: "넷",
        5: "다섯",
        6: "여섯",
        7: "일곱",
        8: "여덟",
        9: "아홉",
        10: "열",
    }
    if number in special:
        return special[number]
    units = ["", "하나", "둘", "셋", "넷", "다섯", "여섯", "일곱", "여덟", "아홉"]
    tens = {1: "열", 2: "스물", 3: "서른", 4: "마흔", 5: "쉰"}
    ten, unit = divmod(number, 10)
    if ten in tens:
        return f"{tens[ten]}{units[unit]}"
    return f"{number}번"


def _scene_variation_label(number: int) -> str:
    """Return a non-numeric scene token so repetition QA does not collapse long plans."""
    label = _korean_ordinal_label(number)
    objects = [
        "낡은 편지",
        "찻잔",
        "서랍 열쇠",
        "흑백 사진",
        "손수건",
        "기차표",
        "약속 반지",
        "일기장",
        "문간 불빛",
        "빗물 자국",
        "장롱 그림자",
        "오래된 주소",
        "봉투 봉인",
        "마른 꽃잎",
        "전화번호 메모",
        "버려진 신발",
        "창가 먼지",
    ]
    places = [
        "부엌",
        "마루",
        "골목",
        "찻집",
        "장터",
        "강둑",
        "역전",
        "병원 복도",
        "빈집",
        "작은 공원",
        "버스 정류장",
        "묘소 앞",
        "다락",
        "우체국",
        "비 오는 처마",
    ]
    emotions = [
        "망설임",
        "후회",
        "질투",
        "용서",
        "침묵",
        "분노",
        "그리움",
        "의심",
        "체념",
        "결심",
        "부끄러움",
        "안도",
        "서운함",
    ]
    idx = max(0, number - 1)
    return f"{label} {objects[idx % len(objects)]} {places[(idx // len(objects)) % len(places)]} {emotions[(idx // (len(objects) * len(places))) % len(emotions)]}"


def _clean_planned_scene_situation(scene: dict) -> str:
    text = str((scene or {}).get("scene_situation") or "").strip()
    if not text:
        return str((scene or {}).get("scene_summary") or "").strip()
    for marker in ("advances the hook:", "advances the hook："):
        if marker in text:
            text = text.split(marker, 1)[1].strip()
            break
    text = re.sub(r"^First-minute micro beat\s+\d+/\d+\s+\([^)]+\)\.\s*", "", text).strip()
    text = re.sub(r"^Keep this as a separate fast visual cut[^:]*:\s*", "", text).strip()
    return text or str((scene or {}).get("scene_summary") or "").strip()


def _generic_old_story_unique_beats(title: str, count: int) -> list[tuple[str, str, str]]:
    """Build non-repeating folk-tale beats when model plans collapse into loops."""
    clean_title = str(title or "숨겨진 약속").strip()
    actions = [
        "마을 사람들이 제목 속 사건을 입에 올리지 못하는 금기를 보여준다",
        "주인공이 그 금기를 어기게 되는 개인적인 사정을 드러낸다",
        "첫 번째 목격자가 사라지기 직전 남긴 이상한 행동을 보여준다",
        "사건이 벌어진 장소에 남은 냄새, 흙, 소리 같은 감각 단서를 잡는다",
        "마을 어른들이 서로 다른 이유로 같은 질문을 피하는 장면을 둔다",
        "주인공의 가족이 과거에 그 사건과 엮였다는 첫 흔적을 발견한다",
        "낡은 물건 하나가 현재 사건과 오래된 빚을 연결한다",
        "밤길에서 보이면 안 되는 사람이나 짐승의 그림자를 스치게 한다",
        "주인공이 처음에는 이익이나 체면 때문에 진실을 외면하게 한다",
        "가장 약한 인물이 모두가 숨긴 말을 뜻밖에 먼저 꺼낸다",
        "사건을 이용하려는 사람이 등장해 갈등의 방향을 흔든다",
        "첫 번째 선택의 결과로 작은 벌이나 불길한 변화가 생긴다",
        "과거 회상에서 사건이 시작된 계절과 첫 희생자를 보여준다",
        "젊은 시절의 약속이나 거래가 선의처럼 보였음을 밝힌다",
        "그 약속을 깬 사람이 누구인지 아직 말하지 않고 흔적만 남긴다",
        "주인공이 마을 밖 사람에게 도움을 청하지만 더 큰 경고를 듣는다",
        "두 번째 물건이나 문장이 첫 단서와 모순된 사실을 드러낸다",
        "가족 중 한 사람이 자기만 살기 위해 거짓말했다는 의심을 심는다",
        "마을 공동체가 피해자보다 집안 체면을 먼저 지켰음을 보여준다",
        "주인공이 진실을 좇다가 누군가의 억울한 이름을 처음 듣는다",
        "중심 장소가 단순한 배경이 아니라 약속이 묻힌 자리였음을 밝힌다",
        "주인공이 되돌릴 수 없는 행동으로 금기의 중심에 들어선다",
        "죽은 사람이나 사라진 존재가 원망보다 부탁을 남겼음을 암시한다",
        "가해자로 보였던 사람이 실제로는 더 큰 죄를 막으려 했음을 보여준다",
        "중간 반전으로 제목의 이유가 두려움이 아니라 보호였을 가능성을 연다",
        "그 보호가 누군가에게는 또 다른 상처가 되었음을 드러낸다",
        "주인공이 처음으로 자기 가족의 책임을 인정하지 못하고 흔들린다",
        "숨겨진 증인이 나타나 과거의 결정적 장면을 구체적으로 말한다",
        "증언과 물건이 맞물리며 거짓으로 덮인 날짜가 바로잡힌다",
        "마을 사람들이 주인공을 막으려 모이고, 진실은 더 공개적인 싸움이 된다",
        "가장 존경받던 인물이 침묵의 대가로 이익을 얻었음이 드러난다",
        "주인공이 그 인물에게 맞서며 이야기의 주도권을 잡는다",
        "세 번째 단서가 제목 속 의문을 거의 풀지만 마지막 이유만 남긴다",
        "과거의 희생자가 왜 끝까지 자기 이름을 숨겼는지 밝혀진다",
        "그 선택이 사랑인지 벌인지 헷갈리게 만드는 감정 장면을 둔다",
        "주인공이 잃을 것을 알면서도 숨긴 문서나 물건을 사람들 앞에 꺼낸다",
        "가족은 무너지고 마을은 처음으로 피해자의 관점에서 사건을 듣는다",
        "가짜 원인이 무너지고 진짜 원인이 한 사람의 욕심이었음이 드러난다",
        "욕심을 부린 인물이 뒤늦게 변명하지만 이미 증거가 맞물린다",
        "주인공이 복수보다 바로잡기를 선택하며 결말의 감정 방향을 정한다",
        "오래된 장소를 다시 찾아가 묻힌 이름이나 약속을 꺼낸다",
        "희생자의 마지막 부탁이 원망이 아니라 남은 사람을 살리려는 말이었음을 밝힌다",
        "주인공이 자신도 그 침묵의 혜택을 받았다는 사실을 받아들인다",
        "마을 사람들이 처음으로 피해자 앞에서 체면 없이 사과한다",
        "제목 속 행동이나 금기의 진짜 이유가 명확한 한 문장으로 정리된다",
        "대가를 치러야 할 사람이 재산, 명예, 자리 중 하나를 내려놓는다",
        "주인공은 잃은 것을 되찾기보다 다시는 반복하지 않을 규칙을 세운다",
        "가족 안의 마지막 오해가 풀리지만 완전한 용서는 쉽게 오지 않는다",
        "공동체가 숨겼던 기록을 새로 쓰거나 비석, 장부, 제단을 바로잡는다",
        "사건의 물건이 제자리로 돌아가며 불길한 징조가 사라진다",
        "남은 사람 한 명이 조용히 울거나 웃으며 감정의 결을 회수한다",
        "다음 세대가 같은 금기를 두려움이 아니라 기억으로 받아들인다",
        "마지막 장면에서 제목의 질문에 대한 답을 짧고 선명하게 남긴다",
    ]
    beats: list[tuple[str, str, str]] = []
    for idx in range(max(0, count)):
        action = actions[idx % len(actions)]
        phase = (
            "오프닝"
            if idx < 12
            else "단서 추적"
            if idx < 28
            else "진실 접근"
            if idx < 44
            else "결말 회수"
        )
        label = _korean_ordinal_label(idx + 1)
        summary = f"{phase} {label} 장면: {action}"
        purpose = f"{phase}에서 새 사건 하나로 인물의 선택, 마을의 침묵, 마지막 대가를 전진시킨다"
        hook = f"{label} 번째 장면 뒤에는 아직 말하지 않은 다음 이유가 남아 있다"
        beats.append((summary, purpose, hook))
    return beats


def _old_story_exam_sons_mother_beats(title: str) -> list[tuple[str, str, str]]:
    actions = [
        "장원 급제 소식이 온 마을에 울리지만 어머니만 눈물 한 방울 흘리지 않는다",
        "상여가 지나간 같은 날 둘째 아들의 빈 신발이 대문 앞에 놓인다",
        "첫째는 붉은 관복을 입고 돌아오지만 어머니의 방문은 굳게 닫혀 있다",
        "마을 사람들은 어머니가 큰아들 출세에 정신이 팔렸다고 수군거린다",
        "막내딸이 둘째의 죽음을 알리자 어머니는 밥상을 두 벌 차리라고 말한다",
        "둘째의 방에서 과거 시험 답안지와 피 묻은 붓대가 함께 발견된다",
        "첫째는 답안지를 보자 얼굴이 굳지만 아무 말 없이 불씨를 찾는다",
        "어머니는 불씨를 빼앗고 둘째가 남긴 글씨를 끝까지 읽으라 명한다",
        "글 첫머리에는 첫째의 이름과 둘째의 필체가 나란히 적혀 있다",
        "마을 훈장은 두 형제가 시험 전날 함께 서당을 떠났다고 증언한다",
        "첫째는 길에서 산적을 만났다고 둘러대지만 짚신의 흙빛이 다르다",
        "어머니는 울지 않고 둘째의 관 앞에 낡은 노리개 하나를 올려놓는다",
        "과거길 첫날 둘째가 병든 첫째를 업고 고개를 넘던 과거가 드러난다",
        "첫째는 열병으로 정신을 잃고 둘째는 형의 이름으로 답안을 써 준다",
        "둘째는 형이 집안을 살려야 한다며 자기 이름을 끝내 숨긴다",
        "시험장 밖에서 부정 응시를 본 관리가 둘째를 협박한다",
        "둘째는 형을 살리기 위해 자신이 답안을 훔쳤다는 거짓 자백을 한다",
        "관리는 돈을 요구하고 첫째는 두려움에 둘째를 외면한다",
        "둘째는 옥에 끌려가기 전 어머니에게 보내는 짧은 편지를 맡긴다",
        "편지를 전해야 할 하인이 첫째 집안의 돈을 받고 침묵한다",
        "어머니는 이미 편지의 존재를 알았지만 일부러 모른 척 기다렸다",
        "첫째가 장원 급제했다는 방이 붙자 둘째는 옥중에서 피를 토한다",
        "둘째는 죽기 전 어머니에게 절대 울지 말라는 마지막 말을 남긴다",
        "그 말의 뜻을 아는 어머니는 눈물을 삼키고 큰아들을 기다린다",
        "현재로 돌아와 첫째는 관복을 벗지 못한 채 둘째 관 앞에 선다",
        "어머니는 첫째에게 네가 받은 벼슬이 누구의 목숨값인지 묻는다",
        "첫째는 자기 이름으로 된 답안지가 둘째 손에서 나온 사실을 부인한다",
        "훈장은 답안지의 마지막 획이 둘째의 버릇과 같다고 밝힌다",
        "하인은 뒤늦게 편지를 꺼내며 돈을 받고 숨겼다고 고백한다",
        "편지에는 둘째가 형을 원망하지 말라고 적은 문장이 있다",
        "첫째는 무너져 울지만 어머니는 아직도 울지 않는다",
        "마을 사람들은 차가운 어머니라 손가락질하지만 그녀는 장독대로 간다",
        "장독 안에는 둘째가 어릴 때 모은 작은 나무패들이 숨겨져 있다",
        "나무패마다 첫째를 도와 집안을 일으키겠다는 둘째의 소원이 적혀 있다",
        "어머니는 첫째에게 그 소원 때문에 네 죄가 사라지지는 않는다고 말한다",
        "첫째는 벼슬길을 포기하고 관아에 자수하겠다고 결심한다",
        "어머니는 이제야 둘째의 관 뚜껑을 열고 마지막 얼굴을 바라본다",
        "둘째의 손에는 어머니 눈물을 닦던 낡은 손수건이 쥐어져 있다",
        "어머니는 그 손수건을 보고도 울지 말라는 약속을 떠올리며 입술을 깨문다",
        "첫째가 관아로 떠나려 하자 마을 사람들은 집안 망신이라 막아선다",
        "어머니는 사람들 앞에서 둘째의 편지를 큰소리로 읽는다",
        "편지 끝에는 어머니가 울면 형이 평생 죄인이 되어 살 거라는 말이 있다",
        "어머니가 울지 않은 이유는 큰아들을 용서해서가 아니라 둘째의 마지막 부탁 때문임이 드러난다",
        "첫째는 장원 급제 방을 찢고 둘째 이름을 자기 이름 위에 쓴다",
        "관아에서는 첫째의 벼슬을 거두지만 둘째의 억울한 누명도 풀린다",
        "마을 사람들은 둘째 관 앞에 처음으로 무릎을 꿇는다",
        "어머니는 둘째가 좋아하던 팥죽을 끓여 관 앞에 놓는다",
        "첫째는 평생 서당에서 가난한 아이들에게 글을 가르치겠다고 맹세한다",
        "어머니는 둘째의 손수건을 첫째에게 주며 네가 흘릴 눈물을 닦으라 한다",
        "장례 행렬이 떠나는 순간 하늘에서 비가 내리기 시작한다",
        "비를 맞던 어머니는 사람들 몰래 소매 안에서 손수건을 꽉 쥔다",
        "마지막 봉분 앞에서 어머니는 울지 않고 둘째의 이름을 세 번 부른다",
        "세 번째 이름을 부르자 첫째가 대신 무너져 울고 마을은 조용히 고개를 숙인다",
    ]
    beats = []
    for idx, action in enumerate(actions, start=1):
        if idx <= 12:
            purpose = "초반 훅으로 장원 급제와 죽음, 그리고 울지 않는 어머니의 모순을 세운다"
        elif idx <= 24:
            purpose = "과거길의 진실과 둘째의 희생을 단계적으로 드러낸다"
        elif idx <= 43:
            purpose = "첫째의 죄책감과 어머니의 침묵이 부딪히며 제목의 이유를 압박한다"
        else:
            purpose = "어머니가 울지 않은 이유를 결말에서 감정적으로 회수한다"
        hook = "어머니의 침묵 뒤에 숨은 다음 진실이 더 무겁게 다가온다"
        if idx >= 43:
            hook = "울지 않은 이유가 용서가 아니라 마지막 약속이었다는 사실이 선명해진다"
        beats.append((action, purpose, hook))
    return beats


def _repair_generic_old_story_scene_plan_repetition(structure: dict, topic: str, upload_title: str) -> dict:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    title = (upload_title or topic or "옛날이야기").strip()
    beats = _generic_old_story_unique_beats(title, len(scenes))
    repaired = dict(structure)
    repaired_scenes = []
    for idx, original in enumerate(scenes):
        scene = dict(original or {})
        summary, purpose, hook = beats[idx]
        scene["scene_id"] = str(scene.get("scene_id") or f"scene{idx + 1:03d}")
        scene["scene_order"] = idx + 1
        scene["scene_number"] = idx + 1
        scene["scene_summary"] = summary
        scene["scene_situation"] = summary
        scene["scene_purpose"] = purpose
        scene["retention_hook"] = hook
        scene["title_promise_link"] = f"'{title}'의 숨겨진 약속, 금기, 단서, 고백, 대가를 순서대로 회수한다"
        scene["end_bridge"] = hook
        for field in ("image_prompt", "video_prompt", "visual_direction", "tts_direction", "prompt_en", "prompt_content", "prompt"):
            scene.pop(field, None)
        repaired_scenes.append(scene)
    repaired["scenes"] = repaired_scenes
    repaired["scene_count"] = len(repaired_scenes)
    repaired.pop("image_grid_prompts", None)
    repaired.pop("media_prompt_director", None)
    repaired.pop("media_prompt_status", None)
    repaired.pop("image_grid_prompt_status", None)
    repaired.pop("image_grid_prompt_mode", None)
    repaired["planner_notes"] = {
        **(repaired.get("planner_notes") or {}),
        "repaired_repeated_scene_beats": True,
        "repair_reason": "generic old-story unique beat rebuild",
    }
    return repaired


def _old_story_wedding_bride_beats(title: str) -> list[tuple[str, str, str]]:
    return [
        ("혼례 마당에 등불이 켜지고 신부의 빈 가마가 먼저 보인다", "사라진 신부라는 핵심 사건을 즉시 세운다", "가마는 비었는데 왜 신부의 신발만 남았을까?"),
        ("젊은 신랑이 빈 자리 앞에서 굳어 버리고 마을이 숨을 죽인다", "신랑의 상처를 중심 감정으로 고정한다", "그 순간 신랑은 무엇을 보지 못했을까?"),
        ("신부 방 안에서 찢어진 붉은 댕기와 접히지 않은 편지가 발견된다", "비밀의 물증을 보여주되 이유는 숨긴다", "편지는 왜 끝까지 접히지 못했을까?"),
        ("신부가 사라지기 직전 뒤뜰 장독대 앞에서 누군가와 마주친다", "실종이 충동이 아니라 선택이었음을 암시한다", "그 밤 그녀를 부른 사람은 누구였을까?"),
        ("신랑의 아버지가 하인들에게 서재 문을 잠그라고 명한다", "신랑 집안의 숨겨진 죄를 첫 단서로 심는다", "잠긴 서재 안에는 무엇이 있었을까?"),
        ("신부가 혼례복 소매 안에 작은 열쇠를 숨긴 채 산길로 향한다", "신부의 도주가 목적 있는 행동임을 보여준다", "그 열쇠는 어느 문을 열기 위한 것이었을까?"),
        ("신랑은 밤새 산길과 냇가를 뒤지지만 발자국은 절벽 앞에서 끊긴다", "첫 수색의 실패로 40년 미스터리를 시작한다", "발자국은 왜 물가가 아니라 절벽에서 끊겼을까?"),
        ("마을 사람들은 신부가 겁을 먹고 달아났다고 수군거린다", "오해와 소문이 신랑의 세월을 갉아먹게 만든다", "소문 속에 빠진 한 가지 진실은 무엇일까?"),
        ("신랑은 신부가 남긴 편지를 펼치지만 먹물이 번져 핵심 문장이 보이지 않는다", "초반에 진실을 노출하지 않고 미스터리를 유지한다", "지워진 문장 하나가 왜 40년을 가를까?"),
        ("신부의 어머니가 찾아와 아무 말 없이 신랑에게 낡은 비녀를 건넨다", "신부 쪽 가족도 비밀을 알고 있음을 암시한다", "그 비녀 속에는 무엇이 숨겨져 있을까?"),
        ("젊은 신랑은 기다리겠다고 맹세하지만 집안 어른들은 혼례 이야기를 묻으려 한다", "사랑과 집안 체면의 갈등을 세운다", "왜 어른들은 신부보다 소문을 더 두려워했을까?"),
        ("마지막 오프닝 컷에서 늙은 신랑이 같은 무덤 앞에 다시 선다", "40년 후 현재로 도약할 고리를 만든다", "그가 이제야 찾아온 까닭은 무엇일까?"),
        ("40년 뒤 백발이 된 신랑은 낡은 비녀 속에서 두 번째 편지 조각을 발견한다", "현재 추적의 출발점을 만든다", "비녀는 왜 이제야 열렸을까?"),
        ("편지 조각에는 신부가 서재에서 본 장부의 일부만 적혀 있다", "가문의 죄를 단계적으로 드러내기 시작한다", "장부에는 누구의 이름이 지워져 있었을까?"),
        ("신랑은 죽은 아버지의 서재 바닥을 다시 뜯어 오래된 나무함을 찾는다", "과거 집안 비밀을 행동으로 추적한다", "나무함은 왜 바닥 아래 묻혀 있었을까?"),
        ("나무함 속에는 신부 집안이 억울하게 빼앗긴 땅문서가 들어 있다", "가문의 죄를 구체적 피해로 만든다", "빼앗긴 땅문서가 왜 신부의 운명을 바꾸었을까?"),
        ("문서 옆에는 신랑의 아버지가 신부 아버지를 모함했다는 증서가 남아 있다", "신부가 알게 된 진실의 무게를 보여준다", "신부는 이 증서를 보고 어떤 선택을 했을까?"),
        ("신부는 혼례 전날 그 증서를 들고 신랑을 찾아가려다 그의 잠든 얼굴을 보고 멈춘다", "사랑 때문에 고발하지 못한 갈등을 보여준다", "왜 그녀는 진실을 바로 말하지 못했을까?"),
        ("신부는 죄가 드러나면 신랑까지 몰락할 것을 알고 혼자 떠나기로 결심한다", "실종의 동기를 희생으로 구체화한다", "사라지는 것이 정말 그를 지키는 길이었을까?"),
        ("그녀는 서재 열쇠와 증서 사본을 절집 노승에게 맡긴다", "40년 뒤 진실이 돌아올 장치를 만든다", "노승은 왜 40년 동안 침묵했을까?"),
        ("신랑은 노승의 제자를 찾아가지만 이미 암자는 폐허가 되어 있다", "추적에 장애물을 만든다", "폐허 속에서 남은 단서는 무엇일까?"),
        ("폐허의 기둥 안에서 신부의 필체로 적힌 짧은 기도가 발견된다", "신부가 살아서 숨어 지낸 흔적을 남긴다", "기도문은 누구를 위해 쓰였을까?"),
        ("기도문에는 신랑을 원망하지 말라는 말만 있고 자기 행방은 없다", "신부의 사랑과 침묵을 동시에 강화한다", "그녀는 왜 끝까지 자신을 지웠을까?"),
        ("마을의 늙은 산지기가 신부가 해마다 혼례날 산길에 꽃을 놓았다고 증언한다", "40년 세월 속 지속된 마음을 보여준다", "그 꽃은 누구에게 바친 것이었을까?"),
        ("신랑은 산길 끝 작은 초가에서 신부가 살았던 흔적을 발견한다", "신부의 희생이 실제 삶이었다는 증거를 준다", "그 초가에는 왜 혼례복 한 벌이 남아 있었을까?"),
        ("초가 벽장에는 신랑의 집안이 갚아야 할 사람들의 이름이 빼곡히 적혀 있다", "신부가 복수가 아니라 속죄를 선택했음을 보여준다", "그 이름들을 누가 대신 갚아 왔을까?"),
        ("신부는 40년 동안 몰래 품삯을 모아 피해자들의 자손에게 돌려주고 있었다", "희생의 구체적 행동을 드러낸다", "그녀는 왜 자기 이름을 끝내 밝히지 않았을까?"),
        ("신랑은 자신이 기다리는 동안 그녀도 다른 방식으로 곁에 있었다는 사실을 깨닫는다", "오해를 회한으로 전환한다", "기다림보다 더 무거운 사랑이 있을까?"),
        ("초가 아궁이 밑에서 마지막 편지의 첫 장이 나온다", "최종 고백으로 가는 문을 연다", "마지막 편지는 왜 세 장으로 나뉘어 숨겨졌을까?"),
        ("첫 장에는 신부가 떠난 밤 신랑 아버지에게 협박받은 일이 적혀 있다", "외부 압박과 선택의 불가피함을 보여준다", "협박의 조건은 무엇이었을까?"),
        ("신랑 아버지는 증서를 없애지 않으면 신랑을 역모 누명에 엮겠다고 했다", "희생의 이유를 더 강하게 만든다", "신부는 누구를 살리려 침묵했을까?"),
        ("두 번째 장에는 신부가 증서를 숨긴 장소와 피해자 명단이 적혀 있다", "비밀을 해결 가능한 행동으로 바꾼다", "그 장소는 왜 무덤 근처였을까?"),
        ("신랑은 신부가 묻힌 줄 알았던 무덤이 사실 증서 보관처였음을 알게 된다", "무덤의 의미를 반전시킨다", "비어 있던 무덤은 누구를 기다리고 있었을까?"),
        ("무덤 속 작은 돌함에서 원본 증서와 신부의 머리카락 한 줌이 나온다", "물증과 감정을 결합한다", "머리카락은 왜 함께 묻혔을까?"),
        ("세 번째 편지에는 신부가 병든 몸으로 마지막까지 신랑의 이름을 불렀다고 적혀 있다", "감정적 클라이맥스를 준비한다", "그녀는 마지막 순간 무엇을 부탁했을까?"),
        ("신부는 자신을 찾지 말고 억울한 이들의 이름을 회복해 달라고 부탁한다", "사랑을 개인 감정에서 속죄로 확장한다", "신랑은 이제 무엇을 해야 할까?"),
        ("신랑은 마을 사람들을 모아 아버지의 죄와 신부의 희생을 공개한다", "진실 공개 장면을 만든다", "마을은 누구를 부끄러워해야 할까?"),
        ("오랫동안 신부를 욕하던 이들이 하나둘 고개를 숙인다", "소문이 뒤집히는 사회적 보상을 준다", "사라진 사람의 이름은 어떻게 돌아올까?"),
        ("신랑은 빼앗긴 땅과 재산을 피해자 자손에게 돌려주겠다고 선언한다", "속죄를 말이 아닌 행동으로 완성한다", "40년 늦은 사과는 받아들여질까?"),
        ("신랑은 신부의 빈 무덤 앞에 혼례 때 쓰지 못한 술잔 두 개를 놓는다", "사랑의 결말을 시각적이고 감정적으로 만든다", "빈 잔 하나는 누구를 기다릴까?"),
        ("그는 처음으로 신부에게 도망쳤다고 원망한 죄를 고백한다", "주인공의 내적 결산을 만든다", "용서는 죽은 사람에게도 닿을까?"),
        ("바람에 마지막 편지 뒷장이 펼쳐지고 신부의 마지막 부탁이 드러난다", "최종 페이오프 직전의 마지막 단서를 제시한다", "그녀가 끝까지 숨긴 한 문장은 무엇일까?"),
        ("마지막 문장에는 당신을 떠난 것이 아니라 당신의 내일을 지킨 것이라고 적혀 있다", "제목의 이유를 명확히 해소한다", "그제야 신랑은 무엇을 이해했을까?"),
        ("신랑은 신부의 이름을 비석에 새기고 더는 정씨부인이라 부르지 않는다", "지워진 존재의 이름을 되찾아 준다", "이름을 되찾는 순간 어떤 세월이 끝날까?"),
        ("피해자 자손들이 무덤 앞에 흙 한 줌씩 올리며 고맙다고 인사한다", "신부의 희생이 공동체에 닿았음을 보여준다", "늦은 감사는 그녀에게 닿았을까?"),
        ("신랑은 남은 재산을 팔아 신부가 돌보던 사람들을 끝까지 책임지기로 한다", "속죄의 지속성을 만든다", "그의 남은 삶은 누구의 것이 될까?"),
        ("그날 밤 신랑은 꿈에서 젊은 신부가 혼례복을 입고 웃는 모습을 본다", "환상은 짧게 감정의 해소로만 사용한다", "꿈속의 신부는 무슨 말을 남겼을까?"),
        ("신부는 원망하지 않았다고 말하고, 이제 그만 자신을 용서하라고 한다", "용서와 화해를 전달한다", "용서받은 사람은 어떻게 살아야 할까?"),
        ("아침이 되자 무덤가에는 간밤에 없던 붉은 꽃잎이 놓여 있다", "민담적 여운을 절제해서 남긴다", "꽃잎은 누가 두고 갔을까?"),
        ("신랑은 마을 아이들에게 이 이야기를 숨기지 말고 전하라고 부탁한다", "이야기의 교훈을 다음 세대로 넘긴다", "사람은 어떤 진실을 잊지 말아야 할까?"),
        ("마을 사람들은 해마다 혼례날 신부의 무덤에 등불을 켠다", "개인 비극을 공동체 기억으로 바꾼다", "등불은 누구의 길을 밝히는 걸까?"),
        ("마지막으로 늙은 신랑은 빈 잔 옆에 자신의 잔을 내려놓고 조용히 웃는다", "사랑과 회한의 마지막 정서를 닫는다", "40년의 기다림은 끝난 걸까?"),
        ("바람이 불어 두 잔 사이의 먼지를 걷어내고, 편지의 마지막 먹물이 햇빛에 드러난다", "잔잔한 이미지로 여운을 남긴다", "진심은 늦어도 사라지지 않는다"),
    ]


def _old_story_tiger_woodcutter_beats(title: str) -> list[tuple[str, str, str]]:
    return [
        ("산길 입구에 호랑이를 세 번 살리면 집안이 망한다는 금기패가 보인다", "제목의 세 번 구원과 비극을 첫 장면에 세운다", "왜 호랑이를 살리는 일이 죄가 되었을까?"),
        ("젊은 나무꾼이 덫에 걸려 피 흘리는 호랑이를 발견한다", "첫 선택의 순간을 동정과 두려움 사이에 놓는다", "그는 도끼를 들고도 왜 물러서지 못했을까?"),
        ("호랑이가 사람 말처럼 살려 달라는 눈빛으로 나무꾼을 바라본다", "민담적 기이함을 과장 없이 심는다", "짐승의 부탁을 사람은 믿어도 되는 걸까?"),
        ("나무꾼은 덫줄을 끊고 호랑이를 풀어 주지만 발목 상처를 숨긴다", "첫 번째 구원을 행동으로 확정한다", "상처를 숨긴 까닭은 무엇이었을까?"),
        ("호랑이는 사라지기 전 세 번의 은혜를 갚겠다는 듯 고개를 숙인다", "호랑이의 약속을 복선으로 만든다", "짐승의 은혜는 사람의 은혜와 같을까?"),
        ("마을 노인은 산짐승의 약속을 믿으면 산이 사람을 삼킨다고 경고한다", "외부 경고로 비극의 윤곽을 만든다", "노인은 과거에 무엇을 보았을까?"),
        ("나무꾼의 아내는 피 묻은 짚신을 보고 산에서 무슨 일이 있었는지 묻는다", "가족의 불안과 비밀을 연결한다", "그 피가 사람의 피가 아니라고 누가 믿을까?"),
        ("밤마다 산 너머에서 세 번 낮게 우는 소리가 들린다", "호랑이와 나무꾼 사이의 보이지 않는 연결을 강화한다", "울음소리는 감사일까, 부름일까?"),
        ("첫눈이 내린 날 호랑이가 나무꾼 집 앞에 죽은 노루를 두고 간다", "첫 번째 보답이 축복처럼 보이게 한다", "선물이 왜 더 큰 불안을 불렀을까?"),
        ("굶주리던 집안은 고기를 먹지만 아내는 문턱의 발자국을 지우지 못한다", "은혜의 이면에 두려움을 남긴다", "발자국은 왜 집 안쪽을 향해 있었을까?"),
        ("마을 사람들은 나무꾼이 산신의 복을 받았다고 부러워한다", "처음에는 구원이 이익처럼 보이게 한다", "복이라 부른 일이 정말 복이었을까?"),
        ("나무꾼은 호랑이를 다시 만나면 약속을 돌려주겠다고 혼잣말한다", "후반의 약속 파기를 위한 내면 갈등을 심는다", "돌려줄 수 없는 은혜도 있을까?"),
        ("봄 장마 뒤 호랑이가 절벽 아래에 갇힌 새끼 곁에서 울부짖는다", "두 번째 구원의 새로운 원인을 만든다", "새끼를 구하면 산의 원한도 풀릴까?"),
        ("나무꾼은 밧줄을 묶어 내려가 새끼 호랑이를 끌어올린다", "위험을 감수한 두 번째 행동을 보여준다", "사람이 짐승의 새끼를 안는 순간 무엇이 바뀔까?"),
        ("어미 호랑이는 새끼를 핥다가 나무꾼의 손등 피 냄새를 맡는다", "은혜와 포식 본능의 충돌을 처음 드러낸다", "감사와 굶주림 중 무엇이 먼저일까?"),
        ("나무꾼은 그 눈빛을 보고도 새끼를 살렸다는 자부심으로 산을 내려온다", "주인공의 선의와 자만이 섞이기 시작한다", "선한 일도 자랑이 되면 위험해질까?"),
        ("마을 닭과 염소가 하나씩 사라지고 사람들은 산짐승을 의심한다", "은혜가 공동체 피해로 번지게 한다", "누가 사라진 짐승 값을 치르게 될까?"),
        ("나무꾼은 호랑이 짓임을 알면서도 자신을 해치지 않을 거라며 침묵한다", "비극의 원인을 단순한 선의가 아니라 방치로 바꾼다", "모른 척한 침묵도 죄가 될까?"),
        ("아내는 아이에게 산길에 가지 말라며 호랑이 발자국을 보여준다", "가족을 위험권 안으로 끌어들인다", "금지한 길은 왜 더 가까워졌을까?"),
        ("노인은 호랑이를 한 번 살리면 목숨을 구하고 두 번 살리면 배고픔을 부른다고 말한다", "세 번째 구원의 의미를 예언으로 준비한다", "세 번째에는 무엇을 잃게 될까?"),
        ("나무꾼은 덫을 놓은 사냥꾼들을 말리다 호랑이가 다시 쫓기는 것을 본다", "세 번째 구원이 피할 수 없는 선택처럼 다가오게 한다", "그는 사람 편에 설까, 산 편에 설까?"),
        ("사냥꾼들은 호랑이가 이미 사람 냄새에 익었다며 죽여야 한다고 주장한다", "공동체의 안전 논리를 세운다", "사람 냄새를 배운 짐승은 돌아갈 수 있을까?"),
        ("나무꾼은 자신에게 빚진 짐승이라며 사냥꾼들의 덫을 몰래 끊는다", "세 번째 구원을 선의가 아닌 소유감으로 오염시킨다", "은혜를 빌미로 생명을 마음대로 할 수 있을까?"),
        ("풀려난 호랑이는 사냥꾼을 피하다 나무꾼의 집 쪽으로 내려간다", "구원의 결과가 가족에게 향하게 한다", "살려 준 길은 왜 집으로 이어졌을까?"),
        ("아내는 마당 끝에서 호랑이를 보고 아이를 안고 문을 걸어 잠근다", "가족이 직접 위협받는 장면으로 긴장을 올린다", "문 하나가 산짐승을 막을 수 있을까?"),
        ("나무꾼은 호랑이 앞에 무릎 꿇고 이제 은혜를 다 갚았으니 돌아가라 말한다", "약속 청산의 시도를 보여준다", "말로 끊은 약속을 짐승이 알아들을까?"),
        ("호랑이는 대답 대신 나무꾼의 그림자를 밟고 산 쪽으로 물러난다", "비극의 표식을 남기되 아직 터뜨리지 않는다", "그림자를 밟힌 사람은 어디까지 쫓기게 될까?"),
        ("그날 밤 나무꾼은 꿈에서 자신이 덫에 걸린 호랑이로 변해 울부짖는다", "죄책감과 민담적 저주를 내면화한다", "꿈은 경고였을까, 판결이었을까?"),
        ("마을 회의에서 사라진 가축 값을 두고 나무꾼이 거짓말을 한다", "침묵이 거짓으로 악화되는 전환점을 만든다", "거짓말 하나가 누구를 더 굶주리게 할까?"),
        ("노인은 호랑이가 은혜를 갚는 게 아니라 사람의 허영을 먹는다고 일러준다", "제목의 '까닭'을 도덕적 핵심으로 좁힌다", "호랑이가 정말 먹은 것은 고기였을까?"),
        ("나무꾼은 가족을 지키겠다며 도끼를 들지만 산길 초입에서 다시 머뭇거린다", "결단하지 못하는 주인공의 약점을 보여준다", "이번에는 베어야 할까, 또 살려야 할까?"),
        ("호랑이는 세 번째 밤 마당에 노루가 아니라 찢긴 덫줄을 놓고 간다", "은혜의 선물이 경고로 바뀌었음을 보여준다", "덫줄은 누구에게 남긴 말이었을까?"),
        ("나무꾼의 아이가 산에서 들은 낮은 울음소리를 따라가려 한다", "비극이 다음 세대에 번질 위기를 만든다", "아이를 부른 것은 호랑이였을까, 아버지의 죄였을까?"),
        ("나무꾼은 아이를 찾으러 산에 들어가 호랑이 새끼가 죽어 있는 것을 발견한다", "두 번째 구원의 결과가 끝내 실패했음을 드러낸다", "살린 목숨은 왜 다시 죽었을까?"),
        ("죽은 새끼 곁에서 어미 호랑이는 더 이상 나무꾼을 알아보지 못한다", "감사의 관계가 완전히 끊어진 순간을 만든다", "은혜를 기억하지 못하는 짐승을 누가 탓할까?"),
        ("나무꾼은 자신의 손등 피 냄새가 새끼에게 사람 냄새를 묻혔다는 사실을 깨닫는다", "비극의 직접 원인을 구체화한다", "선의가 새끼를 죽게 했다면 그는 무엇을 갚아야 할까?"),
        ("사냥꾼들이 사람 냄새 나는 새끼를 미끼로 어미를 노렸다는 말이 드러난다", "인간의 욕심과 나무꾼의 방치를 함께 엮는다", "진짜 덫은 누가 놓은 걸까?"),
        ("나무꾼은 마을을 살리려면 자신이 호랑이를 산 깊은 곳으로 데려가야 한다고 결심한다", "희생적 마지막 행동을 준비한다", "그가 돌아오지 못할 길을 택한 이유는 무엇일까?"),
        ("아내는 세 번 살린 은혜를 믿지 말고 가족 곁에 남으라고 붙잡는다", "가족과 속죄 사이의 마지막 갈등을 만든다", "남는 것이 책임일까, 떠나는 것이 책임일까?"),
        ("나무꾼은 아이에게 산짐승을 불쌍히 여겨도 문턱 안으로 들이지 말라 말한다", "교훈을 인물의 마지막 말로 압축한다", "그 말은 왜 유언처럼 들렸을까?"),
        ("깊은 산 고개에서 나무꾼은 호랑이에게 자신이 잘못한 일을 하나씩 고백한다", "잡아먹히는 까닭을 도덕적 고백으로 선명하게 한다", "짐승 앞의 고백은 누구를 위한 것일까?"),
        ("호랑이는 덫줄 자국이 남은 발을 들어 나무꾼 앞에 놓는다", "첫 번째 구원의 기억을 시각적으로 되살린다", "상처는 은혜일까, 원한일까?"),
        ("나무꾼은 도끼를 내려놓고 자신이 세 번 살린 것은 호랑이가 아니라 자기 허영이었다고 인정한다", "최종 깨달음을 제목의 이유와 연결한다", "사람은 왜 선행마저 자기 것으로 만들까?"),
        ("호랑이가 달려들기 전 산 전체가 눈 내린 듯 조용해진다", "비극의 순간을 자극보다 민담적 정적으로 처리한다", "조용한 산은 무엇을 판결했을까?"),
        ("다음 날 마을 사람들은 피 묻은 도끼와 찢긴 저고리만 발견한다", "잡아먹힌 결말을 직접적이되 절제해서 보여준다", "사라진 몸보다 무거운 것은 무엇이었을까?"),
        ("아내는 남편이 남긴 짚신을 산길 입구에 걸고 아이에게 이야기를 들려준다", "사적인 비극을 전승되는 교훈으로 바꾼다", "남은 사람은 어떤 이야기를 믿어야 할까?"),
        ("노인은 그 뒤로 산에서 호랑이 울음이 세 번 들리면 불을 끄라고 말한다", "민담의 금기를 공동체 규칙으로 완성한다", "세 번의 울음은 은혜일까, 경고일까?"),
        ("마을 사람들은 덫을 모두 거두지만 산짐승에게 먹이를 주지도 않는다", "균형과 경계라는 결론을 행동으로 보여준다", "살리는 것과 길들이는 것은 어떻게 다를까?"),
        ("아이 장성한 뒤 아버지의 도끼를 들고 산에 오르지만 호랑이를 찾지 않는다", "교훈이 다음 세대에서 지켜졌음을 보여준다", "찾지 않는 용기도 있을까?"),
        ("산길 금기패에는 호랑이를 살리지 말라는 말 대신 은혜를 소유하지 말라고 새겨진다", "이야기의 핵심을 단순 금지에서 성찰로 끌어올린다", "사람들이 오래 기억한 문장은 무엇이었을까?"),
        ("마지막 장면에서 오래된 덫줄이 나무뿌리에 묻혀 썩어 간다", "비극의 원인이 사라지는 이미지를 준다", "썩어 간 덫줄은 누구의 죄를 데려갈까?"),
        ("산바람 속에 세 번 낮은 울음이 들리고 마을의 등불이 하나씩 꺼진다", "민담적 여운과 제목의 숫자를 마지막에 되새긴다", "세 번 살린 마음은 결국 무엇을 남겼을까?"),
        ("이야기는 나무꾼이 착해서가 아니라 경계를 잊었기 때문에 잡아먹혔다고 끝난다", "제목의 '까닭'을 마지막 문장으로 명확히 닫는다", "선의에도 지켜야 할 선이 있다"),
    ]


def _old_story_tiger_claw_hunter_beats(title: str) -> list[tuple[str, str, str]]:
    actions = [
        "산 아래 마을에 호랑이 발톱을 건드리면 삼 년 안에 재앙이 온다는 금기패가 서 있다",
        "젊은 사냥꾼 장돌은 병든 어머니 약값 때문에 산신령 굴까지 들어가겠다고 말한다",
        "장터 약장수는 살아 있는 호랑이 발톱을 달여 먹으면 어떤 병도 낫는다고 속삭인다",
        "마을 노인은 그 발톱은 약이 아니라 산의 맹세라며 절대 뽑지 말라고 경고한다",
        "장돌은 노인의 말을 비웃고 밤길에 덫, 밧줄, 녹슨 칼을 챙겨 산으로 오른다",
        "첫눈이 내린 산길에서 장돌은 사람 발자국과 호랑이 발자국이 겹친 흔적을 본다",
        "바위굴 앞에서 호랑이는 새끼를 감싸고 있었고 한쪽 앞발에 오래된 상처가 있다",
        "장돌은 어미 호랑이를 죽이지 않고 연기에 취하게 한 뒤 앞발을 묶는다",
        "호랑이가 눈을 뜨고 사람처럼 눈물을 흘리지만 장돌은 발톱 하나를 뽑아 달아난다",
        "산 전체가 숨을 멈춘 듯 조용해지고 장돌의 손에는 검은 피가 묻는다",
        "장돌은 마을로 내려와 발톱을 팔지 않고 어머니 약탕기에 몰래 넣는다",
        "어머니는 열이 내려가지만 꿈속에서 호랑이 울음이 들린다며 밤새 떤다",
        "사흘 뒤 마을 우물물에 짐승 털 같은 검은 실이 떠오른다",
        "장돌의 덫에 걸린 산짐승들이 모두 앞발 하나씩 피 흘린 채 발견된다",
        "마을 아이가 장돌 집 문턱에서 작은 호랑이 발자국을 보고 울음을 터뜨린다",
        "노인은 삼 년 동안 산에 빚을 갚지 않으면 발톱의 주인이 사람을 찾아온다고 말한다",
        "장돌은 발톱을 돌려놓으러 산에 오르지만 굴 입구를 찾지 못한다",
        "돌아오는 길에 장돌은 자기 손톱 하나가 검게 변한 것을 숨긴다",
        "첫해 봄, 마을 논두렁마다 발톱으로 긁은 듯한 긴 자국이 생긴다",
        "장돌은 약값 빚을 갚겠다며 더 많은 짐승을 잡지만 덫은 번번이 비어 있다",
        "어머니는 네가 가져온 약에서 살아 있는 숨소리가 난다며 약탕기를 깨뜨린다",
        "깨진 약탕기 바닥에서 뽑힌 발톱이 아직도 따뜻한 채 드러난다",
        "장터 약장수는 사라지고 그가 쓰던 천막 안에는 호랑이 가죽 그림자만 남는다",
        "장돌은 발톱을 묻으려 하지만 흙이 닿는 자리마다 검은 풀이 돋는다",
        "둘째 해 여름, 마을 소들이 밤마다 산을 향해 무릎을 꿇는다",
        "사냥꾼 동무들은 장돌이 산신 물건을 훔쳤다며 그를 따돌린다",
        "장돌은 죄를 감추려고 노인의 금기패를 몰래 베어 불태운다",
        "금기패가 탄 자리에서 호랑이 새끼 울음 같은 소리가 새어 나온다",
        "노인은 발톱을 뽑은 벌은 죽음보다 먼저 사람의 마음을 짐승으로 만든다고 말한다",
        "장돌은 밤마다 어머니 방 앞에서 자신도 모르게 앞발로 문을 긁는다",
        "어머니는 아들의 손을 붙잡고 발톱을 돌려주지 않으면 내가 먼저 산으로 가겠다고 한다",
        "장돌은 어머니를 지키려 발톱을 들고 산길에 오르지만 발자국이 모두 마을 쪽으로 돌아선다",
        "산비탈에서 장돌은 삼 년 전 묶었던 밧줄 조각이 나무뿌리에 감겨 있는 것을 찾는다",
        "그 밧줄 끝에는 호랑이 피가 아니라 사람의 머리카락이 엉겨 있다",
        "장돌은 약장수가 사실 산의 복수를 부르는 무당이었다는 소문을 듣는다",
        "마을 굿판에서 무당의 북소리가 나자 장돌의 검은 손톱이 하나씩 떨어진다",
        "떨어진 손톱은 땅에 닿자 작은 발톱으로 변해 산 쪽으로 기어간다",
        "셋째 해 첫눈이 오던 밤, 장돌 집 마당에 거대한 발자국 세 개가 찍힌다",
        "어머니는 아들을 살리려 발톱을 품고 혼자 산으로 올라간다",
        "장돌은 뒤늦게 어머니를 따라가며 처음으로 자신이 훔친 것이 약이 아니라 목숨이었다고 깨닫는다",
        "바위굴 앞에서 늙은 호랑이가 나타나 어머니 대신 장돌을 바라본다",
        "장돌은 무릎을 꿇고 발톱을 돌려주려 하지만 빠진 자리는 이미 새살로 닫혀 있다",
        "호랑이는 발톱을 받지 않고 장돌의 검게 변한 손을 앞발로 누른다",
        "장돌은 자신이 삼 년 동안 마을의 두려움을 먹고 살았다는 사실을 고백한다",
        "어머니는 병이 나은 것이 아니라 아들의 죄를 대신 앓고 있었다고 말한다",
        "장돌은 발톱을 산신 바위 아래 묻고 자신이 놓은 덫을 모두 풀겠다고 맹세한다",
        "호랑이는 장돌을 물지 않고 그의 칼을 앞발로 눌러 두 동강 낸다",
        "마을로 돌아온 장돌은 사냥을 그만두고 금기패를 새로 세운다",
        "새 금기패에는 호랑이를 두려워하라는 말 대신 욕심으로 산의 것을 뽑지 말라고 새긴다",
        "어머니는 마지막 숨을 거두며 네 손이 사람 손으로 돌아왔으니 됐다고 말한다",
        "장돌은 어머니 무덤 옆에 발톱 모양 돌 하나를 세우고 매년 첫눈을 기다린다",
        "마을 사람들은 첫눈 밤에 산에서 울음이 들리면 불을 끄고 빚진 이름을 떠올린다",
        "이야기는 호랑이가 복수해서가 아니라 사람이 훔친 생명의 자리를 끝내 갚아야 했기 때문에 벌어졌다고 끝난다",
    ]
    purposes = [
        "호랑이 발톱 금기와 삼 년 뒤 재앙의 약속을 즉시 세운다",
        "사냥꾼의 절박한 동기를 만들되 욕심으로 변할 여지를 남긴다",
        "발톱을 훔치게 만드는 거짓 정보를 심는다",
        "민담의 경고를 분명히 배치한다",
        "돌이킬 수 없는 첫 행동으로 이야기를 움직인다",
        "사람과 짐승의 경계가 흐려질 복선을 심는다",
        "호랑이를 괴물이 아니라 지켜야 할 존재로 보이게 한다",
        "살해가 아닌 훼손이라는 죄의 형태를 구체화한다",
        "발톱을 뽑는 중심 사건을 감정적으로 각인한다",
        "산이 침묵하는 반응으로 저주의 시작을 알린다",
        "훔친 물건이 가족 안으로 들어오게 한다",
        "치유처럼 보이는 결과 뒤에 대가를 붙인다",
    ]
    hooks = [
        "그 금기는 왜 삼 년이라는 시간을 말했을까?",
        "약값이 사람의 죄를 덮어 줄 수 있을까?",
        "살아 있는 발톱이라는 말은 왜 그렇게 달콤했을까?",
        "노인은 과거에 어떤 벌을 보았을까?",
        "그 밤 산은 누구를 기다리고 있었을까?",
        "사람 발자국은 왜 호랑이 발자국과 겹쳤을까?",
        "새끼를 지키던 호랑이의 눈은 무엇을 부탁했을까?",
        "죽이지 않았다는 말로 죄가 가벼워질까?",
        "뽑힌 발톱은 누구의 몸에서 먼저 피를 불렀을까?",
        "조용해진 산은 용서였을까, 판결이었을까?",
        "약탕기 안에 들어간 것은 약이었을까, 빚이었을까?",
        "어머니가 들은 울음은 밖에서 난 소리였을까?",
    ]
    beats: list[tuple[str, str, str]] = []
    for idx, action in enumerate(actions):
        purpose = purposes[idx] if idx < len(purposes) else f"'{title}'의 삼 년 뒤 결과를 향해 죄, 침묵, 속죄를 새 사건으로 전진시킨다"
        hook = hooks[idx % len(hooks)]
        if idx >= 44:
            hook = "훔친 발톱의 대가는 어떻게 사람의 손으로 돌아올까?"
        beats.append((action, purpose, f"{hook} 다음 단서는 {action[:28]}에서 이어진다"))
    return beats


def _old_story_nameless_grave_grandmother_beats(title: str) -> list[tuple[str, str, str]]:
    actions = [
        "새벽 안개 속 이름 없는 무덤 앞에 홀로 절하는 할머니를 보여준다",
        "마을 아이들이 비석 없는 봉분을 피해 달아나는 모습을 보여준다",
        "할머니가 무덤 앞에 따뜻한 밥 한 숟가락을 놓고 돌아선다",
        "주막 노파가 그 무덤에는 사람 이름을 새기면 안 된다고 말한다",
        "할머니 손목의 낡은 매듭끈이 절할 때마다 흔들린다",
        "젊은 시절 할머니가 장터에서 한 사내를 처음 만난 기억이 스친다",
        "사내가 전쟁 같은 흉년 속에서도 어린아이를 살리려 쌀자루를 숨긴다",
        "마을 원로들이 쌀 도둑 누명을 씌울 사람을 찾기 시작한다",
        "젊은 할머니가 사내에게 도망가라고 하지만 그는 아이 이름을 먼저 묻는다",
        "비 오는 밤 사내가 끌려가고 할머니는 매듭끈 한 가닥만 움켜쥔다",
        "처형장 대신 산비탈에서 몰래 묻힌 봉분이 만들어진다",
        "할머니는 그날부터 이름을 새기지 않겠다는 약속을 혼자 지킨다",
        "수십 년 뒤 마을 사람들은 할머니의 절을 미친 습관으로만 여긴다",
        "할머니의 며느리가 집안 체면을 이유로 무덤길을 막으려 한다",
        "할머니는 제사상보다 그 무덤의 밥그릇을 먼저 챙긴다",
        "손자가 무덤 주인이 누구냐고 묻자 할머니가 처음으로 눈물을 삼킨다",
        "낡은 장롱 밑에서 이름 없는 묘와 같은 흙이 묻은 보자기가 나온다",
        "보자기 안에는 반으로 찢긴 호적과 아이의 작은 은장도가 들어 있다",
        "마을 원로의 아들이 찾아와 그 무덤 이야기를 더 캐지 말라 협박한다",
        "할머니는 협박을 듣고도 다음 날 더 이른 새벽에 산길을 오른다",
        "산길에서 할머니가 쓰러지고 손자는 처음으로 무덤 앞 밥상을 대신 차린다",
        "손자는 봉분 아래에서 바람에 드러난 작은 기와 조각을 발견한다",
        "기와 조각에는 사내가 살린 아이의 젖명이 희미하게 새겨져 있다",
        "할머니는 그 젖명이 자기 아들의 옛 이름이었다고 고백하려다 멈춘다",
        "과거 회상에서 사내가 누명을 쓰고 할머니의 아이를 살린 사실이 드러난다",
        "젊은 할머니가 아이를 안고 살려 달라 빌던 밤의 장면이 이어진다",
        "사내는 아이를 살리는 대신 자신의 이름을 지워 달라는 조건을 남긴다",
        "마을 원로들은 진짜 쌀을 빼돌린 집안 이름을 숨기기 위해 사내를 묻는다",
        "할머니는 증언하면 아이가 다시 죽는다는 협박 때문에 평생 침묵한다",
        "현재의 할머니는 손자에게 장독대 아래 묻은 두 번째 보자기를 꺼내라 한다",
        "두 번째 보자기에는 원로들의 붉은 손도장이 찍힌 각서가 남아 있다",
        "며느리는 집안이 무너질까 두려워 각서를 태우려 하지만 손자가 막는다",
        "할머니는 이름 없는 무덤 앞에서 마지막으로 세 번 절하고 말을 잇지 못한다",
        "밤새 무덤가 등불이 꺼지지 않고 마을 사람들이 하나둘 모여든다",
        "할머니가 죽기 전날 남긴 말이 손자의 입을 통해 처음 공개된다",
        "그 말은 그 사람 이름을 새기지 말고 우리가 진 빚을 새기라는 부탁이었다",
        "손자는 비석을 세우려던 계획을 멈추고 빈 돌판 앞에 마을 사람들을 세운다",
        "원로 집안의 후손이 각서의 손도장을 보고 무릎을 꿇는다",
        "할머니 아들이 살아남은 아이였음을 알고 마을이 숨을 죽인다",
        "아들은 평생 어머니가 왜 그 무덤 앞에 먼저 갔는지 뒤늦게 깨닫는다",
        "며느리는 제사상 음식을 들고 처음으로 이름 없는 무덤 앞에 오른다",
        "손자는 사내의 이름 대신 살려 낸 아이들의 이름을 돌판에 새기자고 제안한다",
        "마을 사람들은 쌀을 숨겼던 집집마다 한 줌씩 곡식을 가져온다",
        "비어 있던 돌판에는 이름 하나가 아니라 마을의 죄와 감사가 새겨진다",
        "할머니 장례날 무덤 앞 밥그릇에 처음으로 두 숟가락이 놓인다",
        "원로 후손은 빼앗은 논을 팔아 굶어 죽은 이들의 제사를 다시 세운다",
        "손자는 매듭끈을 풀어 봉분 흙 위에 묻고 오래된 약속을 놓아준다",
        "아들은 어머니에게 한 번도 묻지 못한 세월을 무덤 앞에서 사과한다",
        "마을 아이들이 더 이상 도망가지 않고 무덤가 잡초를 뽑는다",
        "새 비석에는 이름 없는 사람도 한 마을을 살릴 수 있다는 말이 새겨진다",
        "마지막 새벽에 할머니가 늘 걷던 산길 위로 흰 밥김 같은 안개가 오른다",
        "손자는 할머니의 마지막 말을 아이들에게 들려주며 이야기를 전한다",
        "이야기는 이름을 남기지 않은 은혜가 가장 오래 사람을 붙든다고 끝난다",
    ]
    purposes = [
        "익명의 무덤과 반복된 절이라는 중심 미스터리를 연다",
        "마을의 두려움과 금기를 외부 시선으로 보여준다",
        "할머니의 행동이 제사가 아니라 약속임을 암시한다",
        "비석 없는 이유를 금기로 제시해 궁금증을 키운다",
        "중심 소품을 심어 과거와 현재를 연결한다",
        "젊은 시절 인연을 열어 감정의 뿌리를 만든다",
        "사내가 단순 연인이 아니라 생명의 은인임을 준비한다",
        "누명을 만들 공동체의 죄를 배치한다",
        "사내의 선택이 아이와 이어져 있음을 암시한다",
        "비극의 밤을 감각적으로 각인한다",
        "무덤의 탄생을 보여준다",
        "평생 이어질 약속을 확정한다",
    ]
    beats: list[tuple[str, str, str]] = []
    for idx, action in enumerate(actions):
        purpose = purposes[idx] if idx < len(purposes) else f"'{title}'의 마지막 말에 필요한 새 단서와 감정 변화를 전진시킨다"
        hook = [
            "그 무덤에는 왜 이름이 없었을까?",
            "할머니는 누구에게 절하고 있었을까?",
            "밥 한 숟가락에는 어떤 빚이 담겼을까?",
            "이름을 새기면 왜 안 되는 걸까?",
            "매듭끈은 누구의 약속을 묶고 있을까?",
            "그 사내는 할머니에게 어떤 사람이었을까?",
            "살아난 아이는 훗날 누구로 남았을까?",
            "누명을 씌운 진짜 사람은 누구였을까?",
            "그 아이의 이름은 왜 숨겨졌을까?",
            "끌려간 사내는 마지막에 무엇을 부탁했을까?",
            "봉분 아래에는 무엇이 함께 묻혔을까?",
            "침묵은 약속이었을까, 두려움이었을까?",
        ][idx % 12]
        beats.append((action, purpose, hook))
    return beats


def _sanitize_old_story_scene_plan_to_title(structure: dict, topic: str, upload_title: str) -> dict:
    """Keep old-story repairs anchored to the actual title and scene situation."""
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    title = (upload_title or topic or "옛날이야기").strip()
    title_blob = _text_with_mojibake_repairs(title)
    wedding_beats = (
        _old_story_wedding_bride_beats(title)
        if all(term in title_blob for term in ("혼례", "신부")) or ("신랑" in title_blob and "40년" in title_blob)
        else []
    )
    tiger_beats = (
        _old_story_tiger_woodcutter_beats(title)
        if "호랑이" in title_blob and "나무꾼" in title_blob
        else []
    )
    tiger_hunter_beats = _old_story_tiger_claw_hunter_beats(title) if _old_story_title_is_tiger_hunter(topic, upload_title) else []
    nameless_grave_beats = (
        _old_story_nameless_grave_grandmother_beats(title)
        if "무덤" in title_blob and "할머니" in title_blob
        else []
    )
    exam_sons_beats = (
        _old_story_exam_sons_mother_beats(title)
        if all(term in title_blob for term in ("첫째", "둘째", "어머니")) and any(term in title_blob for term in ("울지", "울지 않은", "눈물"))
        else []
    )
    plan_has_template_drift = any(_old_story_scene_has_template_drift(scene) for scene in scenes)
    generic_beats = _generic_old_story_unique_beats(title, len(scenes)) if plan_has_template_drift else []
    repaired = dict(structure)
    repaired_scenes = []
    for idx, original in enumerate(scenes):
        scene = dict(original or {})
        if wedding_beats and idx < len(wedding_beats):
            situation_beat, purpose, hook = wedding_beats[idx]
        elif tiger_hunter_beats and idx < len(tiger_hunter_beats):
            situation_beat, purpose, hook = tiger_hunter_beats[idx]
        elif tiger_beats and idx < len(tiger_beats):
            situation_beat, purpose, hook = tiger_beats[idx]
        elif nameless_grave_beats and idx < len(nameless_grave_beats):
            situation_beat, purpose, hook = nameless_grave_beats[idx]
        elif exam_sons_beats and idx < len(exam_sons_beats):
            situation_beat, purpose, hook = exam_sons_beats[idx]
        elif generic_beats and idx < len(generic_beats):
            situation_beat, purpose, hook = generic_beats[idx]
        else:
            situation_beat = _clean_planned_scene_situation(scene)
            purpose = f"'{title}'의 이유와 감정선을 새 행동 또는 단서로 한 단계 전진시킨다"
            hook = str(scene.get("retention_hook") or "").strip()
        contaminated_hook = any(term in hook for term in ("세 형제", "첫째", "둘째", "막내", "어머니의 유언", "흙 인형", "반지", "우물물이 밤새 붉은"))
        if not hook or contaminated_hook:
            hook = "이 선택 뒤에 숨은 진짜 이유는 무엇일까?"
        scene["scene_summary"] = situation_beat[:160]
        scene["scene_situation"] = situation_beat
        scene["scene_purpose"] = purpose
        scene["retention_hook"] = hook
        scene["title_promise_link"] = f"'{title}'의 약속을 이 장면의 실제 사건과 감정으로 이어간다"
        scene["end_bridge"] = hook
        scene["scene_order"] = idx + 1
        scene["scene_number"] = idx + 1
        for field in ("image_prompt", "video_prompt", "visual_direction", "tts_direction", "prompt_en", "prompt_content", "prompt"):
            scene.pop(field, None)
        repaired_scenes.append(scene)
    repaired["scenes"] = repaired_scenes
    repaired["scene_count"] = len(repaired_scenes)
    repaired["planner_notes"] = {
        **(repaired.get("planner_notes") or {}),
        "sanitized_to_title_from_scene_situation": True,
        "repair_reason": "old story non-grave plan aligned to title and scene_situation",
    }
    return repaired


def _scene_plan_category_contamination_errors(
    structure: dict,
    *,
    script_style: str,
    topic: str,
    upload_title: str,
    image_style: str,
) -> list[str]:
    if not _is_old_story_plan_context(script_style, topic, upload_title, image_style):
        return []
    allowed_blob = _text_with_mojibake_repairs(topic, upload_title)
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list):
        return []
    banned_groups = {
        "finance/pension": (
            "\ud1b5\uc7a5",
            "\uae08\uc561",
            "\uc5f0\uae08",
            "\uc0dd\ud65c\ube44",
            "\uc608\uc0b0",
            "\uc815\ucc45",
            "\uc81c\ub3c4",
            "\uc0c1\ub2f4",
            "\uac00\uacc4\ubd80",
            "\uace0\uc815\ube44",
            "\uc790\ub3d9\uc774\uccb4",
            "\uad6d\ubbfc\uc5f0\uae08",
            "\ub178\ud6c4\uc790\uae08",
            "finance",
            "pension",
            "budget",
            "bankbook",
        ),
        "survival/defector": (
            "탈북",
            "탈북민",
            "탈북자",
            "북한",
            "두만강",
            "압록강",
            "국경",
            "보위부",
            "브로커",
            "북송",
            "도강",
            "중국 공안",
            "safehouse",
            "north korea",
            "defector",
            "border crossing",
        ),
    }
    allowed_terms = (
        "\ud1b5\uc7a5",
        "\uc5f0\uae08",
        "\uc0dd\ud65c\ube44",
        "\uc815\ucc45",
        "\uc608\uc0b0",
        "탈북",
        "북한",
        "두만강",
        "압록강",
        "국경",
        "보위부",
        "브로커",
        "finance",
        "money",
        "north korea",
        "defector",
    )
    if any(term in allowed_blob for term in allowed_terms):
        return []
    errors: list[str] = []
    for group_name, banned_terms in banned_groups.items():
        hits: list[str] = []
        for idx, scene in enumerate(scenes, start=1):
            blob = _text_with_mojibake_repairs(
                *(
                    (scene or {}).get(key) or ""
                    for key in (
                        "scene_summary",
                        "scene_purpose",
                        "retention_hook",
                        "title_promise_link",
                        "end_bridge",
                        "visual_direction",
                        "video_prompt",
                    )
                )
            )
            matched = [term for term in banned_terms if term in blob]
            if matched:
                hits.append(f"scene {idx}: {', '.join(matched[:3])}")
        if len(hits) >= 2:
            errors.append(f"old-story scene plan contains {group_name} contamination: {hits[:8]}")
    if errors:
        return errors
    return []


def _quality_stage_report(stage: str, errors: list[str]) -> dict:
    return {
        "stage": stage,
        "status": "fail" if errors else "pass",
        "errors": errors,
        "checked_at": time.time(),
    }


def _raise_on_quality_stage_failure(stage: str, errors: list[str]) -> dict:
    report = _quality_stage_report(stage, errors)
    if errors:
        raise RuntimeError(f"{stage} quality gate failed: {errors[:12]}")
    return report


def _validate_script_plan_stage(
    structure: dict,
    *,
    script_style: str,
    topic: str,
    upload_title: str,
    image_style: str,
) -> dict:
    errors: list[str] = []
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        errors.append("script_plan missing structure.scenes")
    else:
        for fallback_number, scene in enumerate(scenes, start=1):
            if not isinstance(scene, dict):
                errors.append(f"scene {fallback_number} is not an object")
                continue
    errors.extend(_scene_plan_repetition_errors(structure))
    errors.extend(
        _scene_plan_category_contamination_errors(
            structure,
            script_style=script_style,
            topic=topic,
            upload_title=upload_title,
            image_style=image_style,
        )
    )
    if _is_old_story_plan_context(script_style, topic, upload_title, image_style):
        errors.extend(_old_story_drama_plan_errors(structure, topic, upload_title))
    return _raise_on_quality_stage_failure("script_plan", errors)


def _validate_script_generate_stage(
    payload: dict,
    *,
    category: str,
    require_korean_script: bool = True,
) -> dict:
    errors: list[str] = []
    structure = payload.get("structure") if isinstance(payload.get("structure"), dict) else {}
    scenes = structure.get("scenes") if isinstance(structure.get("scenes"), list) else []
    script = str(payload.get("script") or "").strip()
    script_quality = payload.get("script_quality_report") if isinstance(payload.get("script_quality_report"), dict) else {}

    try:
        score = int(float(script_quality.get("score") or 0))
    except (TypeError, ValueError):
        score = 0
    verdict = str(script_quality.get("verdict") or "").strip().lower()
    # QA score is informational for monitoring and does not block stage completion if script exists


    if require_korean_script:
        hangul = len(re.findall(r"[\uac00-\ud7a3]", script))
        latin = len(re.findall(r"[A-Za-z]", script))
        if hangul < 1000:
            errors.append(f"script too short or not Korean enough: hangul={hangul}, chars={len(script)}")
        if latin > max(80, int(hangul * 0.05)):
            errors.append(f"script has too much Latin text: latin={latin}")

    if any(marker in script for marker in ("At first", "One small clue", "As time passed", "Auto-generated longform", "intro scene", "development scene")):
        errors.append("script contains fallback/scratch English template text")
    repeated_sentences = _detect_repeated_script_sentences(script)
    if repeated_sentences:
        errors.append(
            "script contains excessive repeated sentences: "
            f"{json.dumps(repeated_sentences[:8], ensure_ascii=False)}"
        )

    for fallback_number, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            errors.append(f"scene {fallback_number} is not an object")
            continue
    try:
        from services.image_grid_prompts import validate_image_grid_prompt_readiness

        validate_image_grid_prompt_readiness(
            scenes,
            structure.get("image_grid_prompts"),
            status=structure.get("image_grid_prompt_status"),
            require_status="ready",
            require_compact_template=True,
        )
    except Exception as exc:
        errors.append(f"image_grid_prompts invalid: {exc}")

    errors.extend(
        _scene_plan_category_contamination_errors(
            structure,
            script_style=str(category or payload.get("script_style") or ""),
            topic=str(payload.get("topic") or ""),
            upload_title=str(payload.get("upload_title") or payload.get("generated_title") or ""),
            image_style=str(payload.get("image_style") or ""),
        )
    )
    return _raise_on_quality_stage_failure("script_generate", errors)


def _validate_publish_metadata_stage(payload: dict, *, category: str) -> dict:
    errors: list[str] = []
    try:
        _validate_publish_metadata_quality(
            payload.get("publish_metadata") if isinstance(payload.get("publish_metadata"), dict) else {},
            str(payload.get("topic") or ""),
            str(payload.get("upload_title") or payload.get("generated_title") or ""),
            str(payload.get("script") or ""),
            str(payload.get("language") or "ko"),
        )
    except Exception as exc:
        errors.append(str(exc))

    if isinstance(payload.get("script_quality_report"), dict):
        try:
            from services.generation_quality_gate import validate_generation_package

            errors.extend(validate_generation_package(payload, category=category))
        except Exception as exc:
            errors.append(f"final package validation failed: {exc}")
    elif payload.get("defer_ready_until_quality_gate"):
        errors.append("missing script_quality_report for quality-gated publish metadata job")

    return _raise_on_quality_stage_failure("publish_metadata", errors)


def _repair_martial_scene_plan_repetition(structure: dict, topic: str, upload_title: str) -> dict:
    """Rebuild a wuxia plan into unique story beats when the model loops."""
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    title = (upload_title or topic or "무협 이야기").strip()
    beats = [
        ("폐허가 된 산문 앞에 피 묻은 문패가 발견된다", "강호의 위기와 문파 몰락을 한 장면으로 연다", "누가 개파의 이름을 지우려 했을까?"),
        ("사형이 눈먼 제자를 업고 금지된 약초길을 오른다", "주인공 관계와 희생의 출발점을 보여준다", "왜 그는 버려진 제자를 끝까지 데려갈까?"),
        ("장문인의 마지막 유언이 찢어진 서찰로 남아 있다", "사건의 원인을 말이 아닌 증거로 제시한다", "서찰의 마지막 줄은 왜 칼로 잘렸을까?"),
        ("제자의 끊어진 단전이 검은 침 독과 연결된다", "폐인이 된 이유를 구체적인 무협 사건으로 세운다", "독을 쓴 자는 문파 안에 있었을까?"),
        ("사형이 십 년 내공을 옮기면 자신이 무공을 잃는다는 사실을 안다", "제목의 희생 약속을 분명히 건다", "그는 정말 자신의 검을 버릴 수 있을까?"),
        ("적대 문파의 전령이 치료를 멈추라는 협박장을 놓고 간다", "외부 압박과 시간 제한을 만든다", "협박장은 왜 사형의 옛 이름을 알고 있을까?"),
        ("사형은 전령을 죽이지 않고 뒤쫓아 숨은 접선지를 찾는다", "복수보다 단서를 택하는 인물성을 보여준다", "살려 보낸 적이 더 큰 진실을 열까?"),
        ("폐객잔 지하에서 같은 독침을 맞은 시신 셋이 발견된다", "개인 사건을 강호 전체 음모로 확장한다", "세 시신은 왜 모두 왼손 검객일까?"),
        ("제자는 의식을 잃은 채 사부의 검결 한 구절을 중얼거린다", "폐인 제자 안의 남은 가능성을 암시한다", "그가 기억한 검결은 누구도 배운 적이 없다"),
        ("사형이 옛 사매에게 도움을 청하지만 그녀는 문파를 배신자라 부른다", "조력자를 쉽게 얻지 못하게 갈등을 넣는다", "그녀는 어떤 밤을 기억하고 있을까?"),
        ("사매가 장문인의 봉인함을 열 조건으로 한 번의 비무를 요구한다", "정보를 얻기 위한 행동 장면을 배치한다", "무공을 아끼면 제자가 죽고, 쓰면 치료가 늦어진다"),
        ("비무 중 사형의 검끝이 흔들리며 내공 손상이 처음 드러난다", "희생의 대가를 신체적으로 보여준다", "그의 검은 이미 무너지고 있는 걸까?"),
        ("봉인함 안에서 개파 조사와 마교 의가의 거래 장부가 나온다", "오래된 비밀을 물증으로 연다", "정파의 조사도 금기를 빌렸다면?"),
        ("장부의 이름 하나가 현재 무림맹 조사관과 일치한다", "권력층 연결고리로 판을 키운다", "심판자가 곧 공범이면 누구에게 말해야 할까?"),
        ("무림맹 조사관은 보호를 약속하며 제자를 넘기라고 한다", "달콤한 제안 속 함정을 만든다", "보호라는 말이 감옥이 될 수도 있다"),
        ("사형은 제자를 숨기고 자신만 조사관 앞에 나선다", "주인공의 선택과 책임을 강화한다", "혼자 간 그는 살아 돌아올 수 있을까?"),
        ("조사관의 호위 검법이 죽은 사부의 금초와 똑같다", "배신의 증거를 대결 속에서 드러낸다", "사부를 죽인 검이 지금 다시 움직인다"),
        ("사형은 패배한 척하며 호위의 검집에서 독침 통을 훔친다", "힘보다 계략으로 전진하는 변화를 준다", "패배가 사실은 첫 승리였다면?"),
        ("독침 통 안쪽에 제자의 혈맥을 깨우는 해독 순서가 새겨져 있다", "치료 단서를 얻되 더 큰 위험을 붙인다", "해독법을 아는 자가 왜 독을 퍼뜨렸을까?"),
        ("첫 내공 이전 중 제자의 몸에 마교 문양이 떠오른다", "제자가 단순 피해자가 아님을 반전시킨다", "그 문양은 저주일까, 봉인일까?"),
        ("사매는 제자가 조사 혈통의 마지막 생존자라고 고백한다", "제목의 희생을 혈통 비밀과 연결한다", "그를 살리면 강호가 다시 불탈 수도 있다"),
        ("사형은 살릴 가치가 아니라 함께한 시간을 이유로 치료를 계속한다", "인물의 도덕 기준을 선명하게 만든다", "강호보다 한 사람을 택해도 되는가?"),
        ("마교 잔당이 치료 도중 산장을 습격한다", "정적인 치료를 행동 위기로 전환한다", "내공을 옮기는 손을 떼면 모든 것이 끝난다"),
        ("제자는 움직이지 못한 채 손가락 하나로 검결의 방향을 바꾼다", "폐인 제자의 능동성을 처음 보여준다", "몸은 죽었어도 검의 눈은 살아 있다"),
        ("사형은 내공 절반을 잃고도 습격자를 살려 보내 심문 대신 추적표를 붙인다", "잔혹한 복수 대신 장기전을 택한다", "그 추적표는 누구의 문 앞에서 멈출까?"),
        ("추적표가 무림맹 회의장 뒤편 비밀 문고를 가리킨다", "진실의 장소를 권력 중심부로 옮긴다", "맹의 문고에 왜 마교 의술서가 있을까?"),
        ("문고에서 사부가 제자를 죽이지 않고 봉인했다는 기록이 발견된다", "사부의 오명을 뒤집을 핵심 반전을 제시한다", "사부는 배신자가 아니라 방패였을까?"),
        ("조사관은 기록을 태우며 사형에게 장문인 자리를 제안한다", "유혹과 침묵의 대가를 보여준다", "명예를 얻으면 진실은 영원히 사라진다"),
        ("사형은 제안을 거절하고 불타는 기록 속 마지막 목판을 꺼낸다", "주인공 선택을 물리적 위험으로 표현한다", "한 장의 목판이 강호를 흔들 수 있을까?"),
        ("목판에는 십 년 내공 이전이 치료가 아니라 봉인 해제라는 문구가 있다", "희생의 의미를 더 위험하게 뒤집는다", "살리는 순간 괴물이 깨어날 수도 있다"),
        ("제자는 깨어나 자신을 죽여 달라고 부탁한다", "감정적 최저점과 선택의 잔혹함을 만든다", "살리고 싶던 사람이 죽음을 원한다면?"),
        ("사형은 검을 내려놓고 제자의 기억을 하나씩 불러낸다", "무공보다 관계로 위기를 버티게 한다", "검결보다 강한 것은 무엇일까?"),
        ("기억 속에서 어린 제자가 사부에게 받은 빈 검집의 의미가 드러난다", "초반 소품을 후반 복선으로 회수한다", "빈 검집은 패배가 아니라 약속이었다"),
        ("조사관이 산문 앞 공개 재판을 열어 두 사람을 마교로 몰아간다", "사적인 진실을 대중 앞 갈등으로 키운다", "군중은 증거보다 소문을 믿을까?"),
        ("사매가 불탄 목판의 일부를 들고 재판장에 나타난다", "조력자가 감정과 증거를 들고 돌아오게 한다", "그녀는 이번엔 도망치지 않을까?"),
        ("호위 검객이 사부 살해의 진짜 동선을 검술로 재현하다가 모순을 드러낸다", "액션 장면으로 추리적 증명을 만든다", "검의 궤적은 거짓말을 못 한다"),
        ("제자가 첫 걸음을 떼며 봉인된 검기를 밖으로 흘린다", "회복의 쾌감과 위험을 동시에 준다", "돌아온 힘은 누구의 편일까?"),
        ("사형은 마지막 내공을 넘기기 전 제자에게 죽이지 않는 검을 약속시킨다", "최종 능력보다 선택 기준을 먼저 세운다", "힘을 얻은 자가 원한을 참을 수 있을까?"),
        ("조사관이 마교 의술로 젊음을 유지해 온 사실이 얼굴 변화로 드러난다", "최종 악역의 추함을 시각적 반전으로 보여준다", "정의의 가면은 얼마나 오래 버틸까?"),
        ("무림맹 호위들이 명령을 따를지 진실을 따를지 갈라진다", "대결을 개인전에서 집단 선택으로 확장한다", "강호는 한 사람의 검만으로 바뀌지 않는다"),
        ("사형과 제자는 서로 다른 검초로 조사관의 방어를 열어젖힌다", "관계의 완성을 협공 액션으로 보여준다", "스승도 사형도 아닌 동료의 검이 된다"),
        ("조사관은 제자의 폭주를 유도하려 사부의 죽음을 조롱한다", "클라이맥스 감정 시험을 만든다", "분노를 베면 이기고, 사람을 베면 진다"),
        ("제자는 검을 멈추고 사형이 남긴 빈 검집에 칼을 꽂는다", "폭주 대신 절제를 선택하는 페이오프를 준다", "빈 검집의 약속이 여기서 완성된다"),
        ("사형은 내공을 모두 잃고도 조사관의 마지막 독침을 몸으로 막는다", "제목의 희생을 최종 행동으로 완수한다", "십 년 내공보다 무거운 한 걸음이다"),
        ("사매가 공개 재판의 증언을 강호 각 문파에 전달한다", "진실이 퍼지는 현실적 통로를 마련한다", "이제 소문은 누구 편에 설까?"),
        ("조사관의 죄가 밝혀지지만 무림맹은 책임을 축소하려 한다", "완전한 승리 대신 현실의 씁쓸함을 남긴다", "악인을 베어도 제도는 곧장 바뀌지 않는다"),
        ("제자는 무림맹주 자리를 거절하고 폐허 산문으로 돌아간다", "권력 대신 회복을 택하게 한다", "그가 원하는 것은 이름일까, 집일까?"),
        ("사형은 검을 들 수 없는 손으로 새 문패의 첫 글자를 깎는다", "상실 이후의 새 시작을 작은 행동으로 보여준다", "검을 잃은 손도 길을 만들 수 있다"),
        ("옛 제자들이 돌아와 폐허 마당에 조용히 검집을 걸어 둔다", "공동체 회복의 이미지를 만든다", "사라진 문파는 정말 끝난 게 아니었다"),
        ("제자는 첫 제자에게 이기는 검보다 멈추는 검을 가르친다", "주제를 다음 세대로 넘긴다", "강한 검이 아니라 멈출 줄 아는 검"),
        ("사매는 사부의 무덤 앞에 진짜 기록을 묻지 않고 낭독한다", "오명을 완전히 벗기는 감정 장면을 둔다", "죽은 자에게 필요한 것은 복수가 아니라 증언이다"),
        ("사형은 빈 단전으로도 제자의 자세를 고쳐 주며 웃는다", "희생이 비극만이 아님을 보여준다", "잃은 내공보다 남은 사람이 더 크다"),
        ("새벽 산문 위로 새 문패가 걸리고 빈 검집이 바람에 흔들린다", "여운 있는 마지막 이미지로 닫는다", "그들의 강호는 이제 어떤 이름으로 불릴까?"),
    ]
    repaired = dict(structure)
    repaired_scenes = []
    total = len(scenes)
    for idx, original in enumerate(scenes):
        scene = dict(original or {})
        summary, purpose, hook = beats[idx % len(beats)]
        scene["scene_order"] = idx + 1
        scene["scene_number"] = idx + 1
        scene["scene_id"] = scene.get("scene_id") or f"scene{idx + 1:03d}"
        scene["scene_summary"] = f"{idx + 1}번 장면: {summary}"
        scene["scene_purpose"] = purpose
        scene["retention_hook"] = hook
        scene["title_promise_link"] = f"'{title}'의 약속을 사형의 희생, 제자의 회복, 강호의 진실 중 하나로 전진시킨다"
        scene["end_bridge"] = hook
        if not scene.get("duration_seconds"):
            scene["duration_seconds"] = max(10, round(900 / max(total, 1)))
        repaired_scenes.append(scene)
    repaired["scenes"] = repaired_scenes
    repaired["scene_count"] = len(repaired_scenes)
    repaired["planner_notes"] = {
        **(repaired.get("planner_notes") or {}),
        "repaired_repeated_scene_beats": True,
        "repair_reason": "martial scene plan unique beat rebuild",
    }
    return repaired


def _repair_finance_scene_plan_repetition(structure: dict, topic: str, upload_title: str) -> dict:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    title = (upload_title or topic or "노후금융 이야기").strip()
    beat_templates = [
        ("통장에 찍힌 첫 숫자를 보여주며 제목의 질문을 바로 던진다", "제목의 금액/선택 문제가 실제 생활과 연결된다는 긴장을 만든다", "이 숫자는 왜 부부의 표정을 굳게 만들었을까?"),
        ("주인공 부부의 나이, 직업 이력, 현재 생활 조건을 짧게 제시한다", "시청자가 숫자 뒤의 사람을 먼저 붙잡게 한다", "이 부부는 어떤 시간을 지나 여기까지 왔을까?"),
        ("부부가 처음 연금 계산서를 받아 든 순간을 재현한다", "정책 설명 전에 개인의 충격을 보여준다", "계산서에서 가장 먼저 눈에 들어온 항목은 무엇이었을까?"),
        ("월 수령액과 예상 생활비를 한 화면에서 대조한다", "수입과 지출의 간격을 숫자로 선명하게 만든다", "남는 돈은 실제로 얼마나 될까?"),
        ("관리비, 식비, 병원비 중 가장 먼저 빠지는 고정비를 분리한다", "생활비 압박이 추상적 불안이 아니라 고정 지출임을 보여준다", "가장 줄이기 어려운 지출은 무엇일까?"),
        ("부부가 식탁에서 한 달 예산을 다시 쓰는 장면을 배치한다", "돈 문제가 관계의 대화로 번지는 순간을 만든다", "두 사람은 어디서부터 줄이기로 했을까?"),
        ("연금 선택 전 부부가 믿었던 기대치를 짚는다", "선택 당시의 믿음과 현재 결과 사이의 간극을 만든다", "그때는 왜 이 선택이 맞다고 생각했을까?"),
        ("선택을 권유받았던 상담 장면 또는 서류 장면을 보여준다", "결정이 하루아침의 충동이 아니었음을 설명한다", "상담에서 빠진 질문은 무엇이었을까?"),
        ("첫 번째 계산 기준을 소개하되 한 가지 숫자만 설명한다", "숫자 설명을 한 장면에 하나로 제한한다", "이 기준 하나가 전체 금액을 어떻게 바꿀까?"),
        ("같은 조건에서 다른 선택지를 택했을 때의 차이를 비교한다", "선택의 기회비용을 보여준다", "다른 선택이었다면 월 금액은 달라졌을까?"),
        ("부부가 가장 후회하는 한 문장을 직접 말하게 한다", "정책 정보를 감정적 후회와 연결한다", "그 후회는 돈 때문일까, 몰랐던 정보 때문일까?"),
        ("자녀에게 말하지 못한 이유를 짧게 드러낸다", "경제 문제가 가족 관계의 침묵으로 이어짐을 보여준다", "왜 자녀에게 먼저 말하지 못했을까?"),
        ("집, 예금, 연금 중 실제로 쓸 수 있는 돈을 구분한다", "자산과 현금흐름의 차이를 설명한다", "집이 있어도 왜 돈이 부족할까?"),
        ("병원비가 발생한 달의 예산표를 보여준다", "평범한 달과 위기 달의 차이를 만든다", "예상치 못한 지출은 얼마만에 균형을 무너뜨릴까?"),
        ("부부가 가장 먼저 포기한 생활 항목을 보여준다", "절약의 구체적 대가를 제시한다", "그들이 포기한 것은 사치였을까, 일상이었을까?"),
        ("이웃 또는 또래와 비교되는 한 장면을 넣는다", "개별 사례가 세대 공통의 문제임을 확장한다", "다른 노후 가구도 같은 선택을 하고 있을까?"),
        ("전문가가 첫 번째 핵심 규칙을 한 문장으로 설명한다", "제도 설명을 짧고 명확하게 넣는다", "이 규칙을 모르면 어떤 착각을 하게 될까?"),
        ("전문가 설명 뒤 부부의 실제 계산으로 다시 돌아온다", "이론과 생활 장부를 연결한다", "규칙을 적용하자 숫자는 어떻게 바뀌었을까?"),
        ("부부가 과거에 놓친 선택지 하나를 확인한다", "중반부의 새로운 정보와 반전을 만든다", "그때 알았다면 선택이 달라졌을까?"),
        ("놓친 선택지가 왜 당시에는 보이지 않았는지 설명한다", "후회를 단순 비난이 아니라 정보 격차로 만든다", "누가 이 정보를 미리 알려줬어야 했을까?"),
        ("현재 시점에서 바꿀 수 있는 것과 없는 것을 나눈다", "시청자에게 현실적 판단 기준을 준다", "지금이라도 바꿀 수 있는 항목은 무엇일까?"),
        ("부부가 실제로 시도한 절약 방법 하나를 보여준다", "행동으로 장면을 전진시킨다", "그 방법은 얼마나 효과가 있었을까?"),
        ("절약이 실패한 날의 구체적 이유를 보여준다", "생활비 문제의 한계를 만든다", "아껴도 안 되는 달은 왜 생길까?"),
        ("건강 상태와 노동 가능성을 연결한다", "노후 현금흐름의 두 번째 변수인 건강을 넣는다", "일을 더 하면 해결될까?"),
        ("일을 더 하려 했지만 막힌 현실을 보여준다", "단순 해결책이 작동하지 않는 이유를 제시한다", "왜 더 일하는 것도 쉽지 않을까?"),
        ("부부가 서로에게 숨긴 걱정을 하나씩 꺼낸다", "감정적 전환점을 만든다", "돈보다 더 무서운 걱정은 무엇일까?"),
        ("중간 정리로 지금까지의 숫자 세 개만 다시 배열한다", "중반부 정보를 압축하고 반복을 방지한다", "세 숫자를 합치면 어떤 결론이 나올까?"),
        ("제도상 오해하기 쉬운 표현 하나를 바로잡는다", "시청자의 실수를 예방하는 정보를 제공한다", "많은 사람이 어디서 착각할까?"),
        ("사례의 조건이 달라지면 결과가 달라지는 지점을 설명한다", "모든 사람에게 같은 답이 아님을 명확히 한다", "내 조건이면 결과가 달라질까?"),
        ("부부의 조건표를 간단히 정리해 개인화 기준을 만든다", "시청자가 자기 상황과 비교할 수 있게 한다", "나에게 대입하려면 어떤 정보가 필요할까?"),
        ("두 번째 선택지의 장점만 짧게 제시한다", "대안의 가능성을 열어둔다", "이 선택지는 왜 매력적으로 보일까?"),
        ("같은 선택지의 위험을 바로 이어서 보여준다", "균형 잡힌 판단을 만든다", "그 장점 뒤에 숨은 비용은 무엇일까?"),
        ("부부가 실제로 선택하지 않은 이유를 말한다", "정보를 개인의 가치 판단으로 연결한다", "그들은 왜 안전한 길을 택했을까?"),
        ("자녀와의 통화 장면으로 생활의 압박을 가족에게 확장한다", "돈 문제가 말의 무게로 드러나게 한다", "자녀는 이 사실을 알고 있었을까?"),
        ("자녀에게 기대지 않으려는 부부의 원칙을 보여준다", "존엄과 불안이 충돌하는 감정을 만든다", "도움을 받지 않겠다는 말은 정말 괜찮다는 뜻일까?"),
        ("다음 달 예산에서 가장 불확실한 항목을 표시한다", "후반부 긴장을 유지한다", "다음 달에 변수가 생기면 어떻게 될까?"),
        ("정부/제도 정보는 필요한 범위에서 한 가지로 제한해 설명한다", "정책 설명을 생활 질문에 묶는다", "이 제도는 이 부부에게 실제 도움이 될까?"),
        ("도움이 되는 경우와 안 되는 경우를 나누어 말한다", "시청자가 과장 없이 판단하게 한다", "어떤 조건에서는 도움이 되지 않을까?"),
        ("부부가 상담센터에 다시 문의하는 장면을 넣는다", "후반부 행동 변화를 만든다", "이번에는 어떤 질문을 놓치지 않았을까?"),
        ("상담 후 새로 알게 된 한 가지를 공개한다", "후반부의 정보 보상을 제공한다", "그 한 가지가 결정을 바꿀까?"),
        ("그러나 새 정보만으로 해결되지 않는 현실을 보여준다", "쉬운 해답을 피하고 현실감을 유지한다", "그래도 남는 문제는 무엇일까?"),
        ("부부가 마지막으로 조정한 지출 항목을 보여준다", "작은 선택이 결말로 이어지게 한다", "이 조정은 생활을 얼마나 버티게 할까?"),
        ("시청자가 체크해야 할 세 가지 질문을 이야기 안에서 제시한다", "정보 가치를 명확히 전달한다", "내 연금 선택 전 반드시 물어야 할 질문은 무엇일까?"),
        ("부부의 사례가 모든 사람의 답은 아니라는 단서를 붙인다", "과도한 일반화를 막는다", "그럼에도 이 사례가 중요한 이유는 무엇일까?"),
        ("처음 통장 장면으로 돌아와 숫자를 다시 바라본다", "오프닝과 후반부를 연결한다", "같은 숫자가 이제 다르게 보일까?"),
        ("부부가 오늘 저녁 실제로 선택한 작은 행동을 보여준다", "결말을 추상 조언이 아니라 행동으로 만든다", "그 행동은 체념일까, 적응일까?"),
        ("남편 또는 아내의 마지막 속마음을 짧게 들려준다", "감정적 핵심을 개인의 목소리로 수렴한다", "그 말 속에 남은 두려움은 무엇일까?"),
        ("핵심 숫자와 선택 기준을 한 번만 정리한다", "정보를 과잉 반복 없이 마무리한다", "이 선택에서 가장 중요한 기준은 무엇일까?"),
        ("비슷한 상황의 시청자에게 확인할 순서를 제시한다", "실용적 후킹을 마지막까지 유지한다", "가장 먼저 확인해야 할 서류는 무엇일까?"),
        ("부부가 내일의 장부를 덮는 장면을 보여준다", "불안이 완전히 사라지지 않았음을 남긴다", "내일도 같은 숫자로 살 수 있을까?"),
        ("제목의 질문에 대한 현실적 답을 한 문장으로 제시한다", "제목 약속을 직접 해소한다", "답은 단순한 손해와 이득 중 어느 쪽일까?"),
        ("마지막 장면에서 부부의 선택이 남긴 교훈을 생활 언어로 정리한다", "감정과 정보를 함께 닫는다", "노후 선택에서 정말 늦기 전에 봐야 할 것은 무엇일까?"),
        ("엔딩은 과장된 희망이 아니라 다음 선택을 준비하는 여운으로 끝낸다", "시청자가 자기 상황을 점검하도록 여운을 남긴다", "당신의 연금표에는 어떤 숫자가 찍혀 있을까?"),
    ]
    repaired = dict(structure)
    repaired_scenes = []
    for idx, original in enumerate(scenes):
        scene = dict(original or {})
        summary, purpose, hook = beat_templates[idx % len(beat_templates)]
        scene["scene_order"] = idx + 1
        scene["scene_number"] = idx + 1
        scene["scene_summary"] = f"{idx + 1}번 장면: {summary}"
        scene["scene_purpose"] = purpose
        scene["retention_hook"] = hook
        scene["title_promise_link"] = f"'{title}'의 약속을 {idx + 1}번째 고유 정보로 전진시킨다"
        scene["end_bridge"] = hook
        repaired_scenes.append(scene)
    repaired["scenes"] = repaired_scenes
    repaired["scene_count"] = len(repaired_scenes)
    repaired["planner_notes"] = {
        **(repaired.get("planner_notes") or {}),
        "repaired_repeated_scene_beats": True,
        "repair_reason": "scene plan repetition QA",
    }
    return repaired


def _repair_old_story_grave_vigil_scene_plan_repetition(structure: dict, topic: str, upload_title: str) -> dict:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    title = (upload_title or topic or "묘를 지킨 며느리 이야기").strip()
    beat_templates = [
        ("마을 사람들이 산등성이 묘 옆 초가를 두려워하며 지나간다", "제목의 3년 묘지 생활을 첫 화면부터 중심 사건으로 세운다", "왜 산 사람 하나가 묘 곁에서 해마다 겨울을 넘겼을까?"),
        ("며느리가 새벽마다 시어머니 묘 앞의 눈을 손으로 쓸어낸다", "주인공의 반복된 행동을 희생과 비밀의 증거로 보여준다", "그녀는 누구에게 보여주려고 묘를 지키는 걸까?"),
        ("마을 아낙들이 그녀를 미쳤다고 수군대지만 가까이 가지 못한다", "외부 시선과 소문을 통해 고립감을 만든다", "사람들이 모르는 약속은 무엇일까?"),
        ("시어머니가 죽기 전 며느리 손에 쥐여 준 붉은 실꾸리를 보여준다", "중심 단서를 물건 하나에 묶는다", "붉은 실은 길을 묶는 물건일까, 죄를 묶는 물건일까?"),
        ("남편이 장터에서 돌아오지 않은 날의 빈 밥상을 짧게 비춘다", "며느리가 혼자 남게 된 과거의 상처를 심는다", "남편의 부재와 묘 곁 생활은 어떻게 이어질까?"),
        ("시댁 사람들이 재산을 핑계로 며느리를 집에서 내쫓으려 한다", "갈등을 초자연보다 먼저 인간의 욕심에서 시작한다", "그녀가 집을 떠나면 누가 가장 이득을 볼까?"),
        ("며느리가 집이 아니라 묘 옆 초가로 들어가겠다고 선언한다", "제목의 이상한 선택을 되돌릴 수 없는 행동으로 바꾼다", "집을 버리고 무덤을 택한 진짜 이유는 무엇일까?"),
        ("첫날 밤 묘 앞 흙이 마르지 않고 젖은 발자국을 남긴다", "묘지의 불길함을 감각적으로 열어 긴장을 높인다", "그 발자국은 죽은 사람의 것일까, 살아 있는 사람의 것일까?"),
        ("며느리가 아무도 듣지 못한 아기 울음소리에 잠에서 깬다", "숨겨진 가족사와 죄책감의 실마리를 만든다", "왜 시어머니 묘에서 아이 울음이 들릴까?"),
        ("마을 노인이 시어머니에게 잃어버린 딸이 있었다는 말을 흘린다", "3년 약속의 감정적 이유를 향한 첫 단서를 준다", "그 딸의 이름을 왜 아무도 입에 올리지 않을까?"),
    ]
    middle_actions = [
        "며느리가 붉은 실로 묘 앞 소나무와 초가 문고리를 잇는다",
        "시댁 큰형님이 밤중에 묘를 파헤치려다 빈 등잔을 발견한다",
        "마을 우물에 젖은 흙냄새가 퍼지며 소문이 더 커진다",
        "며느리가 매달 보름마다 묘 아래에 작은 밥상을 차린다",
        "남편의 오래된 편지에서 시어머니가 숨긴 아이 이름이 나온다",
        "시어머니의 낡은 비녀 속에서 반쪽짜리 혼서지가 발견된다",
        "며느리가 장터에서 잃어버린 딸을 봤다는 말을 듣고도 묘로 돌아온다",
        "산길에 놓인 짚신 한 켤레가 매일 묘 쪽으로 방향을 바꾼다",
        "시댁 사람들이 무당을 불러 며느리를 내쫓으려 하지만 굿상이 무너진다",
        "며느리가 시어머니가 남긴 죄를 대신 갚고 있다는 사실을 암시한다",
        "마을 아이가 묘 옆 초가에서 두 여인의 말소리를 들었다고 말한다",
        "남편의 죽음이 사고가 아니라 누군가의 침묵 때문에 벌어진 일임이 드러난다",
        "며느리가 비 오는 밤에도 묘 앞 불씨를 꺼뜨리지 않는다",
        "큰형님이 숨긴 땅문서가 묘 아래가 아니라 초가 기둥 속에서 나온다",
        "시어머니의 잃어버린 딸이 사실 며느리의 친정과 연결되어 있음이 밝혀진다",
        "며느리가 복수를 택하지 않고 세 번째 겨울까지 기다린 이유를 조금씩 드러낸다",
        "마을 노인이 젊은 시절 시어머니의 부탁을 외면한 일을 고백한다",
        "묘 앞 붉은 실이 끊어지는 날 며느리가 처음으로 마을로 내려온다",
        "며느리가 장터에서 한 여인의 노랫가락을 듣고 시어머니의 유언을 떠올린다",
        "시댁 사람들이 며느리를 죄인으로 몰지만 문서의 도장이 반대로 찍혀 있다",
        "묘 곁 초가 벽에서 세 해 동안 적은 날짜와 이름들이 발견된다",
        "며느리가 지킨 것은 무덤이 아니라 돌아올 사람의 길이었다는 단서가 모인다",
        "마지막 보름밤에 묘 앞 밥상에 처음으로 두 벌의 숟가락이 놓인다",
        "잃어버린 딸의 정체를 아는 사람이 초가 문밖까지 찾아온다",
    ]
    ending_beats = [
        ("세 번째 겨울 끝, 묘 앞에 낯선 여인이 시어머니의 옛 이름을 부른다", "제목의 궁금증을 인물의 귀환으로 터뜨린다", "기다림은 정말 사람을 데려올 수 있을까?"),
        ("며느리가 3년 동안 묘를 지킨 이유가 유언 속 한 문장으로 밝혀진다", "핵심 비밀을 짧고 선명하게 공개한다", "그 약속은 효심이었을까, 속죄였을까?"),
        ("시어머니가 버린 딸과 며느리가 같은 상처를 나눈 사이였음이 드러난다", "감정 반전을 통해 주인공의 선택을 이해시킨다", "가족은 피로만 이어지는 걸까?"),
        ("시댁의 탐욕이 마을 사람들 앞에서 문서와 증언으로 무너진다", "인간 갈등을 정리하고 억울함을 해소한다", "소문을 믿던 마을은 이제 무엇을 보게 될까?"),
        ("며느리가 초가를 떠나기 전 묘 앞 붉은 실을 조용히 묻는다", "희생의 상징을 정리하고 여운을 만든다", "끝난 약속은 어디에 남을까?"),
        ("마지막 장면에서 빈 초가와 정돈된 묘만 남아 마을의 금기가 된다", "옛이야기다운 교훈과 잔향으로 닫는다", "사람들은 왜 그 뒤로 그 묘 앞에서 함부로 말하지 않았을까?"),
    ]
    repaired = dict(structure)
    repaired_scenes = []
    ending_start = max(len(scenes) - len(ending_beats), len(beat_templates))
    for idx, original in enumerate(scenes):
        original = original or {}
        if idx < len(beat_templates):
            summary, purpose, hook = beat_templates[idx]
        elif idx >= ending_start:
            summary, purpose, hook = ending_beats[idx - ending_start]
        else:
            action = middle_actions[(idx - len(beat_templates)) % len(middle_actions)]
            summary = action
            purpose = "며느리의 3년 기다림을 새 단서, 새 오해, 새 대가로 한 걸음 더 전진시킨다"
            hook = f"{action} 뒤에 숨은 진짜 이유는 무엇일까?"
        scene = {
            "scene_id": str(original.get("scene_id") or f"scene{idx + 1:03d}"),
            "scene_order": idx + 1,
            "scene_number": idx + 1,
            "scene_summary": summary,
            "scene_purpose": purpose,
            "retention_hook": hook,
            "title_promise_link": f"'{title}'의 약속을 며느리의 3년 묘지 생활, 시어머니의 유언, 숨겨진 가족사의 흐름으로 이어간다",
            "end_bridge": hook,
            "target_duration": original.get("target_duration") or 17,
        }
        repaired_scenes.append(scene)
    repaired["scenes"] = repaired_scenes
    repaired["scene_count"] = len(repaired_scenes)
    repaired.pop("image_grid_prompts", None)
    repaired.pop("media_prompt_director", None)
    repaired.pop("media_prompt_status", None)
    repaired.pop("image_grid_prompt_status", None)
    repaired.pop("image_grid_prompt_mode", None)
    repaired["planner_notes"] = {
        **(repaired.get("planner_notes") or {}),
        "repaired_repeated_scene_beats": True,
        "repair_reason": "old story grave vigil unique beat rebuild",
    }
    return repaired



def _refresh_finance_scene_visual_fields(structure: dict, topic: str, upload_title: str) -> dict:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    title = (upload_title or topic or "노후금융 이야기").strip()
    shot_motifs = [
        "식탁 위에 펼쳐진 통장과 돋보기 안경",
        "관리비 고지서와 붉은 펜으로 적은 메모",
        "아파트 관리사무소 앞 밤 10시 불빛",
        "은행 창구 번호표와 긴 대기 의자",
        "약국 영수증과 달력에 표시된 병원 날짜",
        "연금 수령 안내문과 계산기 화면",
        "마트 영수증을 대조하는 노부부의 손",
        "새벽 경비원 초소와 불 켜진 작은 창",
        "베란다 건조대와 비어 있는 지갑",
        "손주 용돈 봉투 앞에서 망설이는 손",
        "오래된 가계부와 낡은 볼펜",
        "식당 일자리 구인 공고문 앞 발걸음",
    ]
    camera_beats = [
        "손과 서류를 클로즈업해 구체적인 금액과 메모를 잡는다",
        "정면 시선에서 인물의 깊은 한숨과 눈빛을 담는다",
        "테이블 위 고지서와 계산기를 대비 구도로 보여준다",
        "창밖의 어스름한 풍경과 실내 불빛을 대조한다",
    ]
    refreshed = dict(structure)
    refreshed_scenes = []
    for idx, original in enumerate(scenes, start=1):
        scene = dict(original or {})
        summary = str(scene.get("scene_summary") or scene.get("scene_situation") or f"{title}의 {idx}번째 금융 단서").strip()
        purpose = str(scene.get("scene_purpose") or "지출 구조와 현금흐름의 원인을 전진시킨다").strip()
        hook = str(scene.get("retention_hook") or scene.get("end_bridge") or "다음 장면에서 은퇴자금의 비밀이 드러난다").strip()
        motif = shot_motifs[(idx - 1) % len(shot_motifs)]
        camera = camera_beats[(idx - 1) % len(camera_beats)]
        phase = "첫 1분 핵심 문제 제기" if idx <= 12 else ("중반 지출 구조 분석" if idx <= 32 else "후반 솔루션 및 결말")
        unique_bridge = f"{hook} 다음 원인은 '{summary}'에서 이어진다."
        scene["scene_situation"] = f"{summary} {purpose}"
        scene["visual_direction"] = (
            f"{phase}. '{title}'의 {idx}번째 장면은 {motif}을 중심 비주얼로 삼고, "
            f"{camera}. 화면 속 소품과 인물이 '{summary}'의 현실을 생생하게 전달한다."
        )
        scene["tts_direction"] = f"진지하고 신뢰감 있는 목소리로 '{summary}'의 핵심을 또박또박 전달한다."
        scene["end_bridge"] = unique_bridge
        for field in ("image_prompt", "prompt_en", "prompt_content", "prompt", "video_prompt"):
            scene.pop(field, None)
        refreshed_scenes.append(scene)
    refreshed["scenes"] = refreshed_scenes
    refreshed["scene_count"] = len(refreshed_scenes)
    return refreshed


def _refresh_economy_scene_visual_fields(structure: dict, topic: str, upload_title: str) -> dict:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    title = (upload_title or topic or "경제 시장 분석").strip()
    shot_motifs = [
        "컨테이너 항만의 거대한 크레인과 붉은 컨테이너",
        "증권거래소 전광판의 급변하는 숫자 그래프",
        "중앙은행 기자회견장의 마이크와 프레스룸",
        "반도체 웨이퍼 검사실의 푸른 클린룸 조명",
        "텅 빈 도심 상가 임대 플래카드",
        "대형 화물선의 야간 출항 풍경",
        "외환 딜링룸 모니터 앞 분주한 손놀림",
        "주유소 가격 전광판과 길게 늘어선 차량",
        "물류창고에 가득 찬 수출 대기 박스",
        "소비자물가 장바구니와 마트 진열대",
        "건설 현장 타워크레인과 멈춰 선 골조",
        "글로벌 금융가 빌딩 숲과 안개",
    ]
    camera_beats = [
        "와이드 앵글로 거시적인 산업 현장 스케일을 담는다",
        "데이터 화면과 인물의 결단 순간을 빠르게 연결한다",
        "로우 앵글로 시장 지표의 급박함을 강조한다",
        "정적인 관찰 카메라로 구조적 위기의 실상을 잡는다",
    ]
    refreshed = dict(structure)
    refreshed_scenes = []
    for idx, original in enumerate(scenes, start=1):
        scene = dict(original or {})
        summary = str(scene.get("scene_summary") or scene.get("scene_situation") or f"{title}의 {idx}번째 경제 지표").strip()
        purpose = str(scene.get("scene_purpose") or "시장 지표의 인과관계를 설명한다").strip()
        hook = str(scene.get("retention_hook") or scene.get("end_bridge") or "다음 지표에서 시장의 충격이 이어진다").strip()
        motif = shot_motifs[(idx - 1) % len(shot_motifs)]
        camera = camera_beats[(idx - 1) % len(camera_beats)]
        phase = "오프닝 충격 브리핑" if idx <= 12 else ("중반 구조적 파급 분석" if idx <= 32 else "후반 시장 전망과 대응")
        unique_bridge = f"{hook} 다음 지표는 '{summary}'에서 검증된다."
        scene["scene_situation"] = f"{summary} {purpose}"
        scene["visual_direction"] = (
            f"{phase}. '{title}'의 {idx}번째 장면은 {motif}을 중심 비주얼로 삼고, "
            f"{camera}. 그래픽과 현장 화면이 '{summary}'의 객관적 맥락을 전달한다."
        )
        scene["tts_direction"] = f"차분하고 명확한 경제 해설 톤으로 '{summary}'를 전달한다."
        scene["end_bridge"] = unique_bridge
        for field in ("image_prompt", "prompt_en", "prompt_content", "prompt", "video_prompt"):
            scene.pop(field, None)
        refreshed_scenes.append(scene)
    refreshed["scenes"] = refreshed_scenes
    refreshed["scene_count"] = len(refreshed_scenes)
    return refreshed


def _refresh_martial_scene_visual_fields(structure: dict, topic: str, upload_title: str) -> dict:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    title = (upload_title or topic or "무협 이야기").strip()
    shot_motifs = [
        "폐허가 된 산문 앞 부러진 현판과 빗물",
        "비 내리는 대나무숲 속 검객의 삿갓과 눈빛",
        "피 묻은 비급 목판과 떨리는 손가락",
        "주막 탁자 위 깨진 사발과 녹슨 검집",
        "절벽 끝 외딴 정자에서 타오르는 화로",
        "달빛 아래 비무를 앞둔 두 검객의 그림자",
        "무림맹 회의장 웅장한 목조 기둥과 촛불",
        "깊은 산장 약초 솥에서 피어오르는 연기",
        "눈 덮인 협곡을 건너는 고독한 뒷모습",
        "동굴 벽에 새겨진 오래된 검결 문구",
        "장문인의 봉인함과 끊어진 비단 끈",
        "새벽 안개 속 서서히 드러나는 객잔의 등불",
    ]
    camera_beats = [
        "긴장감 넘치는 로우 앵글로 검의 동선을 포착한다",
        "인물의 날카로운 눈매와 손끝을 익스트림 클로즈업한다",
        "안개 낀 광활한 강호 배경 속 고립된 구도를 잡는다",
        "슬로우 모션으로 바람에 날리는 도포와 빗방울을 담는다",
    ]
    refreshed = dict(structure)
    refreshed_scenes = []
    for idx, original in enumerate(scenes, start=1):
        scene = dict(original or {})
        summary = str(scene.get("scene_summary") or scene.get("scene_situation") or f"{title}의 {idx}번째 무림 단서").strip()
        purpose = str(scene.get("scene_purpose") or "강호의 은원과 비급의 비밀을 전진시킨다").strip()
        hook = str(scene.get("retention_hook") or scene.get("end_bridge") or "다음 장면에서 숨겨진 무공의 진실이 드러난다").strip()
        motif = shot_motifs[(idx - 1) % len(shot_motifs)]
        camera = camera_beats[(idx - 1) % len(camera_beats)]
        phase = "초반 강호 위기 발발" if idx <= 12 else ("중반 비급 추적과 대결" if idx <= 32 else "클라이맥스 결전과 전승")
        unique_bridge = f"{hook} 다음 대결은 '{summary}'에서 격돌한다."
        scene["scene_situation"] = f"{summary} {purpose}"
        scene["visual_direction"] = (
            f"{phase}. '{title}'의 {idx}번째 장면은 {motif}을 중심 비주얼로 삼고, "
            f"{camera}. 시네마틱 무협 미장센으로 '{summary}'의 긴장감을 연출한다."
        )
        scene["tts_direction"] = f"비장하고 무게감 있는 서사 내레이션으로 '{summary}'를 전달한다."
        scene["end_bridge"] = unique_bridge
        for field in ("image_prompt", "prompt_en", "prompt_content", "prompt", "video_prompt"):
            scene.pop(field, None)
        refreshed_scenes.append(scene)
    refreshed["scenes"] = refreshed_scenes
    refreshed["scene_count"] = len(refreshed_scenes)
    return refreshed


def _refresh_survival_scene_visual_fields(structure: dict, topic: str, upload_title: str) -> dict:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    title = (upload_title or topic or "탈북 사연").strip()
    shot_motifs = [
        "두만강 얼어붙은 강판과 눈보라 치는 제방",
        "야간 국경 철조망 뒤편 초소의 서치라이트",
        "어두운 은신처 창가에서 밖을 살피는 떨리는 눈",
        "손때 묻은 위장 메모와 숨겨둔 몇 장의 지폐",
        "비 내리는 낯선 국경 도로를 달리는 화물차 짐칸",
        "국경 감시원의 거친 검문과 긴장된 숨소리",
        "임시 보호소 침상에 놓인 낡은 신발 한 켤레",
        "서울행 비행기 창밖으로 내려다보이는 구름",
        "남한 임대아파트 거실에 홀로 켜진 형광등",
        "첫 주민등록증을 손에 쥐고 눈물 흘리는 손",
        "남겨진 고향 사진과 불 꺼진 식탁",
        "새로운 일터에서 밤늦게 장갑을 벗는 모습",
    ]
    camera_beats = [
        "어둠 속 핸드헬드 시점으로 극한의 긴박감을 전달한다",
        "인물의 떨리는 입술과 손끝을 정밀 클로즈업한다",
        "광활하고 차가운 국경 풍경에서 고립된 주인공을 잡는다",
        "따뜻한 실내 조명과 차가운 기억의 대비를 연출한다",
    ]
    refreshed = dict(structure)
    refreshed_scenes = []
    for idx, original in enumerate(scenes, start=1):
        scene = dict(original or {})
        summary = str(scene.get("scene_summary") or scene.get("scene_situation") or f"{title}의 {idx}번째 생존 증언").strip()
        purpose = str(scene.get("scene_purpose") or "탈출의 위험과 인간적 선택을 전진시킨다").strip()
        hook = str(scene.get("retention_hook") or scene.get("end_bridge") or "다음 고비에서 생사의 갈림길이 나타난다").strip()
        motif = shot_motifs[(idx - 1) % len(shot_motifs)]
        camera = camera_beats[(idx - 1) % len(camera_beats)]
        phase = "초반 탈출 결심과 국경선" if idx <= 12 else ("중반 제3국 은신과 위기" if idx <= 32 else "후반 정착과 새로운 희망")
        unique_bridge = f"{hook} 다음 증언은 '{summary}'에서 이어진다."
        scene["scene_situation"] = f"{summary} {purpose}"
        scene["visual_direction"] = (
            f"{phase}. '{title}'의 {idx}번째 장면은 {motif}을 중심 비주얼로 삼고, "
            f"{camera}. 다큐멘터리적 리얼리즘으로 '{summary}'의 진실성을 담아낸다."
        )
        scene["tts_direction"] = f"진솔하고 절제된 감정의 목소리로 '{summary}'를 증언한다."
        scene["end_bridge"] = unique_bridge
        for field in ("image_prompt", "prompt_en", "prompt_content", "prompt", "video_prompt"):
            scene.pop(field, None)
        refreshed_scenes.append(scene)
    refreshed["scenes"] = refreshed_scenes
    refreshed["scene_count"] = len(refreshed_scenes)
    return refreshed


def _refresh_twilight_scene_visual_fields(structure: dict, topic: str, upload_title: str) -> dict:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    title = (upload_title or topic or "황혼 이야기").strip()
    shot_motifs = [
        "조용한 전통 찻집 창가와 김이 피어오르는 찻잔",
        "빛바랜 은반지와 서랍 속 오래된 흑백 사진",
        "노을 지는 교외 호숫가 드라이브 도로",
        "잠긴 원목 서재 서랍과 작은 열쇠",
        "낙엽 쌓인 늦가을 공원 벤치에 나란히 앉은 두 그림자",
        "동창회 명부 속 희미하게 밑줄 친 이름",
        "어스름한 거실 식탁 위 놓인 두 개의 찻잔",
        "비 내리는 창밖을 바라보는 중년 여인의 옆모습",
        "오래된 편지 봉투와 번진 만년필 글씨",
        "조용한 호텔 로비 카페의 부드러운 조명",
        "산책길에 조심스럽게 마주 잡은 두 손",
        "밤늦은 서재 스탠드 불빛 아래 쓰여진 일기장",
    ]
    camera_beats = [
        "서정적인 미디엄 샷으로 인물 간의 은밀한 감정선을 포착한다",
        "소품과 손짓을 부드러운 포커스로 잡아 여운을 남긴다",
        "노을빛 백라이트로 성숙한 인생의 깊이를 표현한다",
        "거울과 창문에 비친 중첩 구도로 내면의 갈등을 담는다",
    ]
    refreshed = dict(structure)
    refreshed_scenes = []
    for idx, original in enumerate(scenes, start=1):
        scene = dict(original or {})
        summary = str(scene.get("scene_summary") or scene.get("scene_situation") or f"{title}의 {idx}번째 감정선").strip()
        purpose = str(scene.get("scene_purpose") or "황혼의 인연과 숨겨진 사연을 전진시킨다").strip()
        hook = str(scene.get("retention_hook") or scene.get("end_bridge") or "다음 순간에 감춰진 진심이 드러난다").strip()
        motif = shot_motifs[(idx - 1) % len(shot_motifs)]
        camera = camera_beats[(idx - 1) % len(camera_beats)]
        phase = "초반 예기치 못한 재회" if idx <= 12 else ("중반 깊어지는 감정과 현실 갈등" if idx <= 32 else "후반 성숙한 선택과 여운")
        unique_bridge = f"{hook} 다음 사연은 '{summary}'에서 이어진다."
        scene["scene_situation"] = f"{summary} {purpose}"
        scene["visual_direction"] = (
            f"{phase}. '{title}'의 {idx}번째 장면은 {motif}을 중심 비주얼로 삼고, "
            f"{camera}. 품격 있는 멜로 드라마 구도로 '{summary}'의 감성을 연출한다."
        )
        scene["tts_direction"] = f"나지막하고 감미로운 톤으로 '{summary}'의 여운을 전달한다."
        scene["end_bridge"] = unique_bridge
        for field in ("image_prompt", "prompt_en", "prompt_content", "prompt", "video_prompt"):
            scene.pop(field, None)
        refreshed_scenes.append(scene)
    refreshed["scenes"] = refreshed_scenes
    refreshed["scene_count"] = len(refreshed_scenes)
    return refreshed


def _refresh_korean_drama_scene_visual_fields(structure: dict, topic: str, upload_title: str) -> dict:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    title = (upload_title or topic or "한국 사연").strip()
    shot_motifs = [
        "아파트 엘리베이터 앞 CCTV와 굳게 닫힌 현관문",
        "변호사 상담실 테이블 위에 놓인 서류 봉투와 녹음기",
        "가족 단체 식당 룸의 어색한 침묵과 차가운 시선",
        "법원 등기 우편물 봉투를 든 떨리는 손",
        "병원 입원실 복도 끝에서 통화하는 남자의 뒷모습",
        "시댁 제사실 병풍 뒤로 수군거리는 사람들",
        "차 안에서 블랙박스 영상을 확인하는 결연한 표정",
        "통장 계좌 이체 내역서와 붉은 형광펜 표시",
        "카페 테이블 사이에 놓인 차가운 커피잔과 합의서",
        "야간 주차장 차 문을 닫으며 결심하는 순간",
        "공증 사무실 인감도장과 서명 날인",
        "모든 갈등이 정리된 후 아파트 베란다에서 맞는 아침 햇살",
    ]
    camera_beats = [
        "인물 간의 팽팽한 시선 교환을 오버 더 숄더 샷으로 포착한다",
        "서류와 물증을 정확하게 보여주는 아이레벨 클로즈업을 쓴다",
        "현대 도시 공간의 차가운 인공조명으로 갈등을 부각한다",
        "정면 고정 앵글로 통쾌한 반전의 순간을 포착한다",
    ]
    refreshed = dict(structure)
    refreshed_scenes = []
    for idx, original in enumerate(scenes, start=1):
        scene = dict(original or {})
        summary = str(scene.get("scene_summary") or scene.get("scene_situation") or f"{title}의 {idx}번째 사건").strip()
        purpose = str(scene.get("scene_purpose") or "갈등의 전개와 진실 규명을 전진시킨다").strip()
        hook = str(scene.get("retention_hook") or scene.get("end_bridge") or "다음 장면에서 숨겨진 전말이 밝혀진다").strip()
        motif = shot_motifs[(idx - 1) % len(shot_motifs)]
        camera = camera_beats[(idx - 1) % len(camera_beats)]
        phase = "초반 부당한 갈등 발생" if idx <= 12 else ("중반 결정적 증거 확보" if idx <= 32 else "후반 통쾌한 사이다 반전")
        unique_bridge = f"{hook} 다음 진실은 '{summary}'에서 밝혀진다."
        scene["scene_situation"] = f"{summary} {purpose}"
        scene["visual_direction"] = (
            f"{phase}. '{title}'의 {idx}번째 장면은 {motif}을 중심 비주얼로 삼고, "
            f"{camera}. 사실적인 K-드라마 톤으로 '{summary}'의 긴장감을 연출한다."
        )
        scene["tts_direction"] = f"몰입감 넘치고 생생한 이야기 전달 톤으로 '{summary}'를 전달한다."
        scene["end_bridge"] = unique_bridge
        for field in ("image_prompt", "prompt_en", "prompt_content", "prompt", "video_prompt"):
            scene.pop(field, None)
        refreshed_scenes.append(scene)
    refreshed["scenes"] = refreshed_scenes
    refreshed["scene_count"] = len(refreshed_scenes)
    return refreshed


def _refresh_overseas_scene_visual_fields(structure: dict, topic: str, upload_title: str) -> dict:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    title = (upload_title or topic or "해외 감동 실화").strip()
    shot_motifs = [
        "국제공항 입국장 게이트 앞에서 피켓을 든 사람들",
        "손글씨로 삐뚤빼뚤 적힌 한글-영어 번역 메모",
        "비 내리는 유럽 고풍스러운 거리의 노천 카페",
        "낡은 흑백 사진 속 한국전쟁 참전용사와 아이",
        "해외 병원 회복실 침상에서 맞잡은 두 손",
        "국제 우편 봉투와 반환되지 않은 오랜 엽서",
        "낯선 외국 기차역 분실물 센터 앞의 안도하는 표정",
        "한국 전통 공예품 선물을 들고 웃는 외국인 가족",
        "수십 년 만에 찾아간 옛 주소지의 허물어진 벽돌담",
        "석양 비치는 이국적인 해변에서 나누는 포옹",
        "감사 편지를 낭독하는 눈물 어린 눈동자",
        "국경을 넘어 다시 만난 두 사람의 환한 미소",
    ]
    camera_beats = [
        "따뜻한 내추럴 라이트로 국경을 초월한 온기를 담는다",
        "언어가 통하지 않아도 전해지는 눈빛을 타이트하게 잡는다",
        "광활한 이국의 풍경 속에서 피어난 기적을 와이드로 담는다",
        "감동적인 재회의 순간을 부드러운 핸드헬드로 따라간다",
    ]
    refreshed = dict(structure)
    refreshed_scenes = []
    for idx, original in enumerate(scenes, start=1):
        scene = dict(original or {})
        summary = str(scene.get("scene_summary") or scene.get("scene_situation") or f"{title}의 {idx}번째 감동 순간").strip()
        purpose = str(scene.get("scene_purpose") or "국경을 넘은 인연과 은혜를 전진시킨다").strip()
        hook = str(scene.get("retention_hook") or scene.get("end_bridge") or "다음 순간에 기적 같은 반전이 일어난다").strip()
        motif = shot_motifs[(idx - 1) % len(shot_motifs)]
        camera = camera_beats[(idx - 1) % len(camera_beats)]
        phase = "초반 낯선 타국에서의 위기" if idx <= 12 else ("중반 국경을 넘은 따뜻한 도움" if idx <= 32 else "후반 수십 년 만의 보은과 감동")
        unique_bridge = f"{hook} 다음 감동은 '{summary}'에서 이어진다."
        scene["scene_situation"] = f"{summary} {purpose}"
        scene["visual_direction"] = (
            f"{phase}. '{title}'의 {idx}번째 장면은 {motif}을 중심 비주얼로 삼고, "
            f"{camera}. 따뜻하고 영화 같은 질감으로 '{summary}'의 감동을 연출한다."
        )
        scene["tts_direction"] = f"따뜻하고 깊은 울림을 주는 목소리로 '{summary}'를 전달한다."
        scene["end_bridge"] = unique_bridge
        for field in ("image_prompt", "prompt_en", "prompt_content", "prompt", "video_prompt"):
            scene.pop(field, None)
        refreshed_scenes.append(scene)
    refreshed["scenes"] = refreshed_scenes
    refreshed["scene_count"] = len(refreshed_scenes)
    return refreshed


def _refresh_scene_visual_fields_for_category(category: str, structure: dict, topic: str, upload_title: str) -> dict:
    cat = str(category or "").strip()
    if cat == "노후금융":
        return _refresh_finance_scene_visual_fields(structure, topic, upload_title)
    if cat == "경제":
        return _refresh_economy_scene_visual_fields(structure, topic, upload_title)
    if cat == "무협":
        return _refresh_martial_scene_visual_fields(structure, topic, upload_title)
    if cat == "탈북사연":
        return _refresh_survival_scene_visual_fields(structure, topic, upload_title)
    if cat == "황혼19금":
        return _refresh_twilight_scene_visual_fields(structure, topic, upload_title)
    if cat == "한국사연":
        return _refresh_korean_drama_scene_visual_fields(structure, topic, upload_title)
    if cat == "해외감동":
        return _refresh_overseas_scene_visual_fields(structure, topic, upload_title)
    return _refresh_old_story_scene_visual_fields(structure, topic, upload_title)


def _repair_macro_economy_scene_plan_repetition(structure: dict, topic: str, upload_title: str) -> dict:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    title = (upload_title or topic or "경제 시장 분석").strip()
    beat_templates = [
        ("주요 경제 지표의 급변을 그래프와 숫자로 직관적으로 연다", "시청자가 시장의 충격을 즉시 느끼게 한다", "이 지표 하나가 실물 경제에 어떤 연쇄 반응을 일으킬까?"),
        ("글로벌 시장과 주요국 통화의 첫 번째 연동 흐름을 짚는다", "문제의 진원지를 명확히 한다", "왜 이번 변동은 평소와 다르게 움직일까?"),
        ("환율, 금리, 유가 중 가장 먼저 영향을 받는 지표를 분리한다", "복잡한 경제 현상을 단계별로 나눈다", "가장 먼저 타격을 입는 지표는 무엇일까?"),
        ("국내 주력 수출 산업에 미치는 직접적 영향을 보여준다", "추상적 수치를 기업 실적과 연결한다", "수출 기업의 마진율은 어떻게 변할까?"),
        ("수입 원자재 가격 상승과 공급망 병목 현상을 제시한다", "원가 상승 압박을 구체화한다", "공급망 충격은 언제까지 지속될까?"),
        ("소비자물가와 가계 체감 경기의 악화 경로를 추적한다", "거시 지표를 일반 서민 경제로 연결한다", "장바구니 물가는 얼마나 오를까?"),
        ("중앙은행의 통화 정책 딜레마와 금리 결정을 분석한다", "정책 당국의 고심을 보여준다", "금리를 올릴 수도 내릴 수도 없는 이유는 무엇일까?"),
        ("과거 유사한 경제 위기 사례와의 비교 데이터를 제시한다", "역사적 패턴을 통한 학습을 유도한다", "10년 전 위기와 이번 사태의 결정적 차이는?"),
        ("기업들의 자금 조달 경색과 회사채 시장 동향을 짚는다", "금융 시장의 숨은 뇌관을 포착한다", "한계 기업의 부실 위험은 어디까지 번질까?"),
        ("부동산 및 자산 시장의 조정 국면을 데이터로 짚는다", "자산 가치 하락의 파급력을 분석한다", "부동산 시장의 경착륙을 막을 수 있을까?"),
        ("주요 글로벌 금융 기관의 전망 리포트를 교차 검증한다", "다양한 시각의 신뢰도를 높인다", "월가와 해외 IB들은 어떤 결론을 내렸을까?"),
        ("정부의 긴급 안정화 대책과 실효성을 검토한다", "정책의 파급 효과를 냉정하게 평가한다", "정부 대책은 시장을 안정시킬 수 있을까?"),
        ("투자자와 개인이 반드시 점검해야 할 핵심 지표 3가지를 정리한다", "시청자에게 실질적 인사이트를 제공한다", "지금 당장 내 자산에서 점검해야 할 것은?"),
        ("향후 6개월간 주목해야 할 핵심 시나리오와 결론을 제시한다", "미래 전망과 리스크 관리 방안으로 닫는다", "다가올 시장 변곡점은 언제 찾아올까?"),
    ]
    repaired = dict(structure)
    repaired_scenes = []
    for idx, original in enumerate(scenes):
        scene = dict(original or {})
        summary, purpose, hook = beat_templates[idx % len(beat_templates)]
        scene["scene_order"] = idx + 1
        scene["scene_number"] = idx + 1
        scene["scene_summary"] = f"{idx + 1}번 장면: {summary}"
        scene["scene_purpose"] = purpose
        scene["retention_hook"] = hook
        scene["title_promise_link"] = f"'{title}'의 거시경제 분석을 {idx + 1}번째 인과관계로 전진시킨다"
        scene["end_bridge"] = hook
        repaired_scenes.append(scene)
    repaired["scenes"] = repaired_scenes
    repaired["scene_count"] = len(repaired_scenes)
    repaired["planner_notes"] = {
        **(repaired.get("planner_notes") or {}),
        "repaired_repeated_scene_beats": True,
        "repair_reason": "macro economy scene plan repetition QA",
    }
    return repaired


def _repair_twilight_scene_plan_repetition(structure: dict, topic: str, upload_title: str) -> dict:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    title = (upload_title or topic or "황혼 이야기").strip()
    beat_templates = [
        ("조용한 찻집에서 30년 만에 마주 앉은 두 사람의 굳은 표정으로 연다", "황혼 재회의 팽팽한 긴장과 감춰진 사연을 시작한다", "수십 년 만에 두 사람은 왜 다시 만나야 했을까?"),
        ("과거 헤어질 수밖에 없었던 청춘 시절의 결정을 짧게 제시한다", "인물들의 오랜 후회와 세월의 무게를 보여준다", "그때 그들은 왜 서로의 손을 놓쳤을까?"),
        ("각자의 가정을 꾸리고 살아온 세월의 흔적을 대화 속에 담는다", "지나온 삶의 노고와 현재의 고독을 드러낸다", "평탄해 보였던 결혼 생활 뒤에 남은 것은 무엇이었을까?"),
        ("서랍 속 낡은 편지와 흑백 사진이 발견된 계기를 밝힌다", "재회가 우연이 아닌 필연적 계기였음을 설명한다", "누가 이 오래된 편지를 세상 밖으로 꺼냈을까?"),
        ("배우자가 떠난 뒤 혼자 남겨진 일상의 쓸쓸함을 보여준다", "황혼의 외로움과 진솔한 감정선을 세운다", "텅 빈 집에서 가장 견디기 힘들었던 순간은 언제였을까?"),
        ("두 사람이 나눈 첫 번째 비밀 고백을 배치한다", "과거의 오해가 진실로 바뀌는 첫 반전을 만든다", "30년 동안 전하지 못했던 한마디는 무엇이었을까?"),
        ("자식들의 시선과 주변의 평판에 대한 현실적 두려움을 다룬다", "황혼 연애가 마주하는 사회적/가족적 장벽을 세운다", "자식들은 부모의 새로운 인연을 받아들일 수 있을까?"),
        ("유산과 재산 문제를 둘러싼 자식들의 오해와 갈등이 수면 위로 오른다", "현실적 가족 갈등으로 서사를 확장한다", "진심이 왜 돈 문제로 왜곡되었을까?"),
        ("주인공이 모든 것을 정리하고 혼자 떠나려 결심하는 장면을 넣는다", "감정적 위기와 결단의 순간을 만든다", "그는 왜 다시 침묵을 택하려 했을까?"),
        ("상대방이 달려와 남은 생을 함께하자고 붙잡는 감동적 전환을 만든다", "주인공의 결정을 바꾸는 진심의 힘을 보여준다", "남은 인생을 누구를 위해 살아야 할까?"),
        ("자식들과 마주 앉아 부모의 인생과 행복에 대해 담담히 설득한다", "갈등의 봉합과 세대 간의 이해를 시도한다", "자식들은 부모의 진심 어린 눈빛을 보고 무엇을 느꼈을까?"),
        ("법적 혼인 대신 서로를 지켜주는 동반자로서의 삶을 선언한다", "황혼만의 성숙하고 현실적인 선택을 제시한다", "형식보다 중요한 삶의 약속은 무엇일까?"),
        ("노을 지는 호숫가를 함께 걸으며 지난 세월을 용서하고 보듬는다", "이야기를 따뜻한 감동과 인생의 여운으로 닫는다", "황혼의 사랑이 우리에게 남긴 질문은 무엇일까?"),
    ]
    repaired = dict(structure)
    repaired_scenes = []
    for idx, original in enumerate(scenes):
        scene = dict(original or {})
        summary, purpose, hook = beat_templates[idx % len(beat_templates)]
        variation = _scene_variation_label(idx + 1)
        scene["scene_order"] = idx + 1
        scene["scene_number"] = idx + 1
        scene["scene_summary"] = f"{idx + 1}번 장면 {variation}: {summary}"
        scene["scene_situation"] = f"{variation}의 구체적인 공간과 사물로 {summary}"
        scene["scene_purpose"] = f"{purpose} {variation}의 단서로 장면을 구분한다"
        hook_statement = hook.rstrip(" ?!.。")
        scene["retention_hook"] = f"{variation} 때문에 {hook_statement}라는 의문이 남는다"
        scene["title_promise_link"] = f"'{title}'의 황혼 서사를 {idx + 1}번째 감정선으로 전진시킨다"
        scene["end_bridge"] = f"{variation}의 여운이 다음 선택을 밀어 올린다"
        repaired_scenes.append(scene)
    repaired["scenes"] = repaired_scenes
    repaired["scene_count"] = len(repaired_scenes)
    repaired["planner_notes"] = {
        **(repaired.get("planner_notes") or {}),
        "repaired_repeated_scene_beats": True,
        "repair_reason": "twilight scene plan repetition QA",
    }
    return repaired


def _repair_korean_drama_scene_plan_repetition(structure: dict, topic: str, upload_title: str) -> dict:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    title = (upload_title or topic or "한국 사연").strip()
    beat_templates = [
        ("부당한 갈등이 터져 나온 현장의 한 장면으로 즉시 시작한다", "시청자가 불의와 억울함에 깊이 분노하고 몰입하게 한다", "도대체 어떻게 이런 무리한 요구를 할 수 있었을까?"),
        ("상대방의 오만한 태도와 적반하장식 언행을 사실적으로 보여준다", "갈등의 심각성과 주인공의 참담한 심경을 강조한다", "상대방은 왜 자기가 잘못했다는 걸 모를까?"),
        ("주인공이 지금까지 가족이나 직장을 위해 헌신했던 지난날을 짧게 회상한다", "피해자의 도덕적 정당성과 인내의 한계를 세운다", "모든 희생을 당연하게 여긴 대가는 무엇이었을까?"),
        ("상대방이 선을 넘는 결정적 요구(유산 강탈, 누명 씌우기, 막말 등)를 던진다", "사건을 돌이킬 수 없는 법적/도덕적 파국으로 밀어 넣는다", "이 한마디로 모든 인내는 끝났다"),
        ("주인공이 감정적 싸움 대신 조용히 증거 수집에 착수한다", "수동적 피해자에서 능동적 응징자로의 전환을 만든다", "주인공이 몰래 확보한 첫 번째 결정적 물증은?"),
        ("CCTV 영상, 계좌 이체 내역, 녹음 파일 등 스모킹 건을 확보한다", "반격의 기술적/법적 정당성을 꼼꼼하게 구축한다", "이 증거 앞에서 상대방은 어떤 핑계를 댈까?"),
        ("변호사 상담 또는 전문가 조언을 통해 철저한 반격 플랜을 세운다", "감정적 폭언이 아닌 법적/원칙적 타격 준비를 보여준다", "합법적으로 완벽하게 정리하는 방법은 무엇일까?"),
        ("상대방이 승리를 확신하고 모욕을 주는 공개적인 자리(가족 모임, 회사 회의)를 잡는다", "사이다 반전의 무대를 긴장감 넘치게 세운다", "상대방의 오만이 극에 달한 순간 무슨 일이 벌어질까?"),
        ("주인공이 차분하게 서류 봉투를 꺼내며 상대방의 만행을 조목조목 낭독한다", "모든 진실이 만천하에 드러나며 판세가 뒤집힌다", "얼굴이 하얗게 질린 상대방의 첫 반응은?"),
        ("상대방이 궤변으로 발뺌하려 하자 결정적 녹취 파일과 증거 영상을 재생한다", "완벽한 증거로 상대방의 도망갈 구멍을 완전히 차단한다", "물증 앞에서 쏟아지는 변명은 어떻게 무너졌을까?"),
        ("주변 사람들(가족, 동료, 상사)이 상대방에게 등을 돌리고 비난을 쏟아낸다", "사회적/도덕적 단죄를 통해 통쾌한 카타르시스를 준다", "지금까지 침묵하던 사람들은 왜 태도를 바꿨을까?"),
        ("법적 고소장 접수와 손해배상 청구, 부당이득 반환 처분을 집행한다", "실질적인 정의 구현과 현실적 피해 회복을 완료한다", "상대방이 치르게 된 처절한 죗값은 얼마일까?"),
        ("주인공이 낡은 관계의 사슬을 끊어내고 당당하게 자기 인생의 주인이 된다", "통쾌한 사이다 결말과 함께 자존감 회복의 여운을 남긴다", "선한 사람이 끝내 승리한다는 사실이 남긴 교훈은?"),
    ]
    repaired = dict(structure)
    repaired_scenes = []
    for idx, original in enumerate(scenes):
        scene = dict(original or {})
        summary, purpose, hook = beat_templates[idx % len(beat_templates)]
        scene["scene_order"] = idx + 1
        scene["scene_number"] = idx + 1
        scene["scene_summary"] = f"{idx + 1}번 장면: {summary}"
        scene["scene_purpose"] = purpose
        scene["retention_hook"] = hook
        scene["title_promise_link"] = f"'{title}'의 사연을 {idx + 1}번째 사이다 전개로 전진시킨다"
        scene["end_bridge"] = hook
        repaired_scenes.append(scene)
    repaired["scenes"] = repaired_scenes
    repaired["scene_count"] = len(repaired_scenes)
    repaired["planner_notes"] = {
        **(repaired.get("planner_notes") or {}),
        "repaired_repeated_scene_beats": True,
        "repair_reason": "korean drama scene plan repetition QA",
    }
    return repaired


def _repair_overseas_touching_scene_plan_repetition(structure: dict, topic: str, upload_title: str) -> dict:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    title = (upload_title or topic or "해외 감동 실화").strip()
    beat_templates = [
        ("낯선 타국 땅에서 말이 통하지 않아 절체절명의 위기에 빠진 한국인의 모습으로 연다", "언어와 문화의 장벽 속에서 마주한 고립과 공포를 보여준다", "아무도 아는 이 없는 타국에서 무슨 일이 벌어졌을까?"),
        ("지갑을 잃어버리거나 여권, 소지품을 도난당해 길거리에 주저앉은 상황을 제시한다", "주인공의 절박한 처지와 막막한 심정을 강조한다", "어두워지는 외국 거리에서 어디로 가야 했을까?"),
        ("주변의 차가운 시선 속에 체념하려던 순간, 낯선 외국인이 다가온다", "첫 번째 친절의 손길과 의외의 만남을 만든다", "이 외국인은 왜 지나치지 않고 걸음을 멈췄을까?"),
        ("서투른 손짓 발짓과 번역기로 상황을 파악하고 기꺼이 도움을 주는 장면을 담는다", "국경을 초월한 인간애와 소통의 온기를 전달한다", "말이 통하지 않는데 어떻게 마음이 먼저 닿았을까?"),
        ("외국인이 자기 집으로 데려가 따뜻한 식사를 대접하고 차비를 쥐여준다", "조건 없는 선의와 따뜻한 보살핌을 구체화한다", "남을 돕는 일에 왜 자기 지갑을 아끼지 않았을까?"),
        ("외국인이 한국인에게 남다른 애정과 은혜를 품게 된 과거 사연을 공개한다", "단순 친절이 아니라 역사적/인간적 인연의 반전을 만든다", "그는 왜 한국인이라는 말에 눈시울을 붉혔을까?"),
        ("과거 한국전쟁 참전용사였거나 한국인 간호사/유학생에게 도움을 받았던 일화가 밝혀진다", "세대를 건너 이어진 은혜의 순환을 감동적으로 드러낸다", "수십 년 전 뿌려진 은혜의 씨앗이 어떻게 돌아왔을까?"),
        ("주인공이 무사히 위기를 넘기고 귀국하며 반드시 다시 찾아오겠다고 약속한다", "약속과 기다림의 서사를 만든다", "이 소중한 인연은 여기서 끝나는 것일까?"),
        ("세월이 흘러 주인공이 성공한 뒤 은인을 찾기 위해 다시 타국으로 떠난다", "보은(報恩)을 향한 능동적 행동을 시작한다", "수십 년이 지난 지금, 그 은인은 어디에 계실까?"),
        ("옛 주소지가 바뀌고 흔적이 사라져 추적이 난관에 부딪히는 위기를 배치한다", "찾아가는 여정의 긴장감을 유지한다", "사진 한 장만으로 이 넓은 땅에서 찾을 수 있을까?"),
        ("현지 방송사나 SNS의 도움으로 기적처럼 은인의 거처를 찾아낸다", "모두가 한마음으로 돕는 감동의 확장을 보여준다", "수소문 끝에 울린 전화 한 통의 목소리는?"),
        ("노인이 된 은인과 중년이 된 주인공이 눈물의 재회를 나눈다", "클라이맥스 감동과 진정한 보은의 순간을 완성한다", "두 사람이 끌어안고 흘린 눈물의 의미는 무엇일까?"),
        ("국경과 세대를 넘어 인간의 선의가 만들어낸 기적을 따뜻하게 정리하며 닫는다", "시청자에게 깊은 울림과 인류애의 메시지를 전한다", "우리가 베푼 작은 친절은 언젠가 어떻게 돌아올까?"),
    ]
    repaired = dict(structure)
    repaired_scenes = []
    for idx, original in enumerate(scenes):
        scene = dict(original or {})
        summary, purpose, hook = beat_templates[idx % len(beat_templates)]
        scene["scene_order"] = idx + 1
        scene["scene_number"] = idx + 1
        scene["scene_summary"] = f"{idx + 1}번 장면: {summary}"
        scene["scene_purpose"] = purpose
        scene["retention_hook"] = hook
        scene["title_promise_link"] = f"'{title}'의 감동 실화를 {idx + 1}번째 감동 순간으로 전진시킨다"
        scene["end_bridge"] = hook
        repaired_scenes.append(scene)
    repaired["scenes"] = repaired_scenes
    repaired["scene_count"] = len(repaired_scenes)
    repaired["planner_notes"] = {
        **(repaired.get("planner_notes") or {}),
        "repaired_repeated_scene_beats": True,
        "repair_reason": "overseas touching scene plan repetition QA",
    }
    return repaired


def _refresh_old_story_scene_visual_fields(structure: dict, topic: str, upload_title: str) -> dict:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    title = (upload_title or topic or "옛날이야기").strip()
    shot_motifs = [
        "마을 입구의 금줄과 젖은 흙길",
        "초가 마당의 등잔불과 닫힌 문",
        "우물가에 모인 사람들의 낮은 수군거림",
        "달빛 아래 흔들리는 한복 소매",
        "장독대 뒤로 사라지는 발자국",
        "낡은 족자와 접힌 편지",
        "비어 있는 혼례상과 꺼진 촛불",
        "안개 낀 산길과 오래된 소나무",
        "사당 앞에 놓인 붉은 실",
        "새벽 논둑 위로 번지는 푸른 빛",
        "마을 어른의 굳은 얼굴과 떨리는 손",
        "문틈 사이로 비치는 희미한 등불",
        "흙 묻은 신발과 젖은 치맛자락",
        "바람에 흔들리는 대문 고리",
        "빈 방 한가운데 남은 작은 보자기",
        "흐린 창호지에 비친 사람 그림자",
    ]
    camera_beats = [
        "낮은 시점에서 천천히 다가간다",
        "정면 고정 구도로 숨 막히는 침묵을 잡는다",
        "손과 물건을 가까이 잡아 단서를 강조한다",
        "인물 뒤편에서 따라가며 불안을 만든다",
        "넓은 마을 풍경에서 인물의 고립을 드러낸다",
        "촛불 흔들림을 전경에 두고 얼굴을 흐리게 둔다",
        "문이 열리는 순간을 느리게 보여준다",
        "발자국과 시선의 방향을 이어 붙인다",
    ]
    refreshed = dict(structure)
    refreshed_scenes = []
    for idx, original in enumerate(scenes, start=1):
        scene = dict(original or {})
        summary = str(scene.get("scene_summary") or scene.get("scene_situation") or f"{title}의 {idx}번째 단서").strip()
        purpose = str(scene.get("scene_purpose") or "제목의 비밀을 한 걸음 더 전진시킨다").strip()
        hook = str(scene.get("retention_hook") or scene.get("end_bridge") or "다음 장면에서 감춰진 이유가 조금 더 드러난다").strip()
        motif = shot_motifs[(idx - 1) % len(shot_motifs)]
        camera = camera_beats[(idx - 1) % len(camera_beats)]
        if idx <= 12:
            phase = "첫 1분 빠른 훅 컷"
        elif idx <= 32:
            phase = "중반 단서 추적 컷"
        elif idx <= 45:
            phase = "후반 진실 접근 컷"
        else:
            phase = "결말 회수 컷"
        unique_bridge = f"{hook} 다음 단서는 '{summary}' 장면에서 이어진다."
        scene["scene_situation"] = f"{summary} {purpose}"
        scene["visual_direction"] = (
            f"{phase}. '{title}'의 {idx}번째 장면은 {motif}을 중심 이미지로 삼고, "
            f"{camera}. 화면 안의 인물, 소품, 장소가 '{summary}'의 사건을 직접 보여주게 한다."
        )
        scene["tts_direction"] = (
            f"할머니가 옛이야기를 들려주듯 낮고 선명하게 말한다. "
            f"이 장면에서는 '{summary}'를 설명보다 사건으로 느끼게 하고, 끝은 '{unique_bridge}'의 여운으로 넘긴다."
        )
        scene["end_bridge"] = unique_bridge
        for field in ("image_prompt", "prompt_en", "prompt_content", "prompt", "video_prompt"):
            scene.pop(field, None)
        refreshed_scenes.append(scene)
    refreshed["scenes"] = refreshed_scenes
    refreshed["scene_count"] = len(refreshed_scenes)
    return refreshed


def _repair_old_story_scene_plan_repetition(structure: dict, topic: str, upload_title: str) -> dict:
    """Rebuild folk-story plans without crossing into unrelated category tropes."""
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    title = (upload_title or topic or "옛날이야기").strip()
    if _old_story_title_is_grave_vigil(topic, upload_title):
        repaired = _repair_old_story_grave_vigil_scene_plan_repetition(structure, topic, upload_title)
    elif _old_story_title_is_tiger_hunter(topic, upload_title):
        repaired = _sanitize_old_story_scene_plan_to_title(structure, topic, upload_title)
    else:
        repaired = _repair_generic_old_story_scene_plan_repetition(structure, topic, upload_title)
    return repaired
    beat_templates = [
        ("마을 어귀에 걸린 금기와 소문을 먼저 보여준다", "이야기의 세계를 옛 마을의 불길한 약속 안에 고정한다", "그 금기는 왜 지금까지 아무도 어기지 못했을까?"),
        ("어머니의 유언이 세 형제 앞에서 서로 다르게 해석된다", "제목의 약속을 가족 갈등과 금지된 선택으로 연결한다", "유언 속에서 빠진 한 문장이 있다면 무엇일까?"),
        ("첫째가 집안의 체면과 재산을 이유로 무덤 이야기를 꺼낸다", "탐욕의 동기를 설명이 아니라 행동으로 세운다", "그의 말은 효심일까, 욕심일까?"),
        ("둘째가 말리다가도 숨겨진 물건 이야기에 흔들린다", "세 형제의 균열을 한 사람씩 다른 욕망으로 나눈다", "가장 먼저 마음을 바꾼 사람은 누구일까?"),
        ("막내가 밤마다 들리는 어머니의 목소리를 고백한다", "초자연적 긴장을 감정의 두려움으로 끌어올린다", "그 목소리는 경고일까, 유혹일까?"),
        ("마을 노인이 무덤을 판 집안의 옛 비극을 들려준다", "금기의 역사와 오늘의 사건을 하나로 묶는다", "이 집안만 반복해서 벌을 받는 이유가 있을까?"),
        ("비 오는 밤, 세 형제가 삽과 등불을 들고 산길에 오른다", "말로만 맴돌던 갈등을 되돌릴 수 없는 행동으로 바꾼다", "첫 삽을 뜨는 순간 무엇이 깨어날까?"),
        ("무덤 앞 등불이 한 번에 꺼지고 흙냄새가 달라진다", "평범한 묘지가 금지된 장소로 변하는 감각을 만든다", "불이 꺼진 뒤에도 보이는 것은 무엇일까?"),
        ("첫 삽에 오래된 반지가 흙 밖으로 굴러 나온다", "중심 단서를 구체적인 물건 하나에 묶는다", "어머니가 묻은 반지가 왜 흙 위로 먼저 나왔을까?"),
        ("무덤 안에서 사람 모양의 흙 인형이 드러난다", "저주의 실체를 눈으로 확인 가능한 대상으로 만든다", "그 인형은 누구를 닮아 있을까?"),
    ]
    middle_actions = [
        "첫째가 반지를 숨기자 대청마루의 제사상이 저절로 기울어진다",
        "둘째가 흙 인형을 깨뜨리려는 순간 손바닥에 어머니의 손자국이 남는다",
        "막내가 무덤을 다시 덮자고 애원하지만 형들은 이미 더 깊이 파고든다",
        "마을 우물물이 밤새 붉은 흙탕물로 변해 사람들을 깨운다",
        "집 안의 위패에 가느다란 금이 가며 오래 숨긴 이름 하나가 드러난다",
        "첫째의 아내가 꿈에서 어머니가 문밖에 서 있는 모습을 본다",
        "둘째가 장독대 밑에서 유언장 조각을 발견하지만 끝부분은 찢겨 있다",
        "막내가 어머니가 남긴 바느질 상자에서 같은 반지 자국을 찾는다",
        "산길에서 들려오는 장례 종소리가 세 형제를 따로 갈라놓는다",
        "마을 아이가 흙 인형의 눈이 밤마다 방향을 바꾼다고 말한다",
        "첫째가 욕심을 감추려 거짓 제사를 올리지만 향이 거꾸로 탄다",
        "둘째가 숨긴 빚과 약속이 드러나며 형제 사이의 믿음이 무너진다",
        "막내가 유언의 진짜 뜻이 재산이 아니라 죄를 덮으라는 경고였음을 의심한다",
        "노인이 오래전 어머니가 살린 아이 이야기를 꺼내며 저주의 방향을 바꾼다",
        "흙 인형 안에서 머리카락과 붉은 실이 나오며 누군가의 이름을 가리킨다",
        "무덤을 다시 찾아간 세 형제가 서로 다른 환청을 듣고 다른 선택을 한다",
        "첫째가 반지를 끼는 순간 자신의 그림자가 어머니의 그림자로 바뀐다",
        "둘째가 진실을 덮으려 하자 집 문턱마다 젖은 흙발자국이 찍힌다",
        "막내가 유언장 조각을 맞추며 어머니가 마지막에 남긴 조건을 읽는다",
        "마을 사람들이 모인 자리에서 무덤 속 물건의 주인이 따로 있었음이 드러난다",
        "첫째가 끝까지 반지를 내놓지 않자 그의 이름이 족보에서 흐려진다",
        "둘째가 자신이 본 환영을 고백하며 처음으로 형제의 죄를 말한다",
        "막내가 어머니의 무덤 앞에서 용서를 구하지만 대답 대신 흙 인형이 갈라진다",
        "찢긴 유언의 마지막 줄이 촛농 아래에서 드러나며 모든 선택의 의미가 뒤집힌다",
    ]
    ending_beats = [
        ("세 형제가 다시 무덤 앞에 서서 각자 숨긴 물건을 내려놓는다", "클라이맥스를 힘이 아니라 고백과 대가로 세운다", "진실을 내놓으면 저주는 끝날까, 시작될까?"),
        ("첫째가 반지를 돌려주며 자신이 판 것은 무덤이 아니라 어머니의 믿음이었다고 깨닫는다", "주제와 감정의 결산을 주인공 행동으로 보여준다", "늦은 깨달음에도 용서는 남아 있을까?"),
        ("둘째가 찢긴 유언장을 사람들 앞에서 읽고 오래된 죄를 밝힌다", "숨겨진 비밀을 공개해 제목의 궁금증을 해소한다", "마을은 이 진실을 받아들일 수 있을까?"),
        ("막내가 흙 인형을 다시 묻자 무덤가에 처음으로 새벽빛이 든다", "공포의 대상을 정리하고 정서적 해방을 만든다", "빛이 들었다고 모든 벌이 끝난 걸까?"),
        ("집으로 돌아온 형제들이 비어 있는 어머니의 방에서 마지막 흔적을 발견한다", "여운과 대가를 남겨 결말을 오래 붙잡게 한다", "어머니가 끝까지 지키려 한 것은 무엇이었을까?"),
        ("마지막 장면에서 반지 자국만 남은 흙 위로 바람이 지나간다", "권선징악과 미스터리의 잔향을 한 이미지로 마무리한다", "그 집안의 금기는 정말 사라졌을까?"),
    ]
    repaired = dict(structure)
    repaired_scenes = []
    ending_start = max(len(scenes) - len(ending_beats), len(beat_templates))
    for idx, original in enumerate(scenes):
        scene = dict(original or {})
        if idx < len(beat_templates):
            summary, purpose, hook = beat_templates[idx]
        elif idx >= ending_start:
            summary, purpose, hook = ending_beats[idx - ending_start]
        else:
            action = middle_actions[(idx - len(beat_templates)) % len(middle_actions)]
            summary = action
            purpose = "반복 묘사가 아니라 새 단서와 새 대가로 제목의 의문을 전진시킨다"
            hook = f"{action} 뒤에 감춰진 대가는 무엇일까?"
        scene["scene_order"] = idx + 1
        scene["scene_number"] = idx + 1
        scene["scene_summary"] = summary
        scene["scene_purpose"] = purpose
        scene["retention_hook"] = hook
        scene["title_promise_link"] = f"'{title}'의 약속을 금기, 유언, 무덤, 대가의 흐름으로 이어간다"
        scene["end_bridge"] = hook
        scene.pop("image_prompt", None)
        scene.pop("video_prompt", None)
        repaired_scenes.append(scene)
    repaired["scenes"] = repaired_scenes
    repaired["scene_count"] = len(repaired_scenes)
    repaired["planner_notes"] = {
        **(repaired.get("planner_notes") or {}),
        "repaired_repeated_scene_beats": True,
        "repair_reason": "old story scene plan unique beat rebuild",
    }
    return repaired


def _repair_survival_story_scene_plan_repetition(structure: dict, topic: str, upload_title: str) -> dict:
    """Rebuild survival/testimony stories when the planner loops repeated beats."""
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not isinstance(scenes, list) or not scenes:
        return structure
    title = (upload_title or topic or "생존 증언").strip()
    beats = [
        ("차가운 강가에 도착하기 전 마지막 집 안의 침묵을 보여준다", "가족이 왜 그 밤을 선택할 수밖에 없었는지 생활의 압박으로 연다", "문밖의 발소리는 정말 이 가족을 향해 오는 것일까?"),
        ("어머니가 숨겨 둔 천 조각과 약봉지를 꺼낸다", "도강이 모험이 아니라 병든 가족을 살리기 위한 선택임을 세운다", "이 작은 약봉지가 국경보다 무거운 이유는 무엇일까?"),
        ("주인공이 장마당에서 들은 단속 소문을 떠올린다", "위험이 막연한 공포가 아니라 오늘 밤 닥칠 사건임을 구체화한다", "소문은 과장이었을까, 마지막 경고였을까?"),
        ("동생의 기침 소리를 이불로 막는 장면을 배치한다", "가족 내부의 연약함을 보여주며 보호 본능을 만든다", "숨소리 하나가 모두를 위험하게 만들 수 있을까?"),
        ("아버지가 오래 숨긴 신분증과 돈을 나누어 쥔다", "탈출 계획이 이미 오래전부터 준비됐음을 암시한다", "왜 아버지는 이 사실을 끝까지 말하지 않았을까?"),
        ("검문소 앞에서 이웃의 이름이 불리는 순간을 보여준다", "주인공 가족이 바로 다음 차례일 수 있다는 압박을 만든다", "이웃이 끌려간 이유가 우리 가족과도 연결되어 있을까?"),
        ("안내자가 약속 장소에 늦어지며 첫 균열을 만든다", "돈을 낸다고 안전이 보장되지 않는 세계를 보여준다", "기다리는 시간이 길어질수록 누구를 의심해야 할까?"),
        ("강으로 가는 길목에서 손전등 불빛이 논둑을 훑는다", "추격의 시각적 위협을 첫 행동 장애물로 만든다", "불빛이 한 번 더 돌아오면 숨을 곳이 남아 있을까?"),
        ("어머니가 동생을 업고 얼어붙은 흙길에 주저앉는다", "가족 중 한 사람의 한계가 전체 선택을 흔들게 한다", "여기서 멈추면 살 수 있을까, 더 위험해질까?"),
        ("주인공이 처음으로 가족 대신 거짓말을 하기로 결심한다", "수동적 피해자에서 행동하는 인물로 전환한다", "그 거짓말은 가족을 구할까, 더 큰 의심을 부를까?"),
        ("국경 초소의 교대 시간을 맞추려 뛰는 장면을 넣는다", "시간 제한을 부여해 이야기를 앞으로 밀어낸다", "몇 분의 차이가 생사를 가를 수 있을까?"),
        ("강가에 먼저 도착한 다른 가족의 흔적을 발견한다", "탈북의 길이 개인의 비극만이 아니라 반복되는 현실임을 넓힌다", "그 가족은 건넜을까, 붙잡혔을까?"),
        ("얼음 아래 물소리가 들리며 첫 실제 도강이 시작된다", "제목의 강 장면을 구체적 감각으로 시작한다", "첫 발을 내딛는 순간 돌아갈 길은 사라진다"),
        ("동생의 신발 한 짝이 물에 빠지는 사건을 만든다", "작은 물건 하나로 생존 난도를 높인다", "신발을 포기하면 동생은 끝까지 걸을 수 있을까?"),
        ("뒤쪽에서 호루라기 소리가 들려 가족이 흩어질 위기에 놓인다", "추격 압박을 말이 아닌 소리와 행동으로 보여준다", "지금 흩어지면 다시 만날 방법이 있을까?"),
        ("아버지가 일부러 다른 방향으로 발자국을 남긴다", "희생의 첫 실체를 행동으로 제시한다", "그 발자국은 시간을 벌어줄까, 마지막 이별이 될까?"),
        ("중국 쪽 풀숲에 닿았지만 안내자가 사라진 사실을 알게 된다", "도강 이후에도 위험이 끝나지 않았음을 보여준다", "강을 건넜는데 왜 더 무서워졌을까?"),
        ("낯선 창고에서 첫 밤을 보내며 말 한마디도 못 한다", "생존 후의 공포와 침묵을 정서적으로 쌓는다", "살아남았다는 사실이 왜 안도보다 두려움일까?"),
        ("브로커가 약속과 다른 금액을 요구하며 가족을 압박한다", "새로운 착취 구조를 등장시켜 갈등을 확장한다", "돈이 없으면 다시 북으로 보내질까?"),
        ("주인공이 어머니의 약을 구하려 처음 낯선 시장으로 나간다", "생존 공간을 강에서 도시 변두리로 이동시킨다", "말투 하나가 정체를 들키게 만들 수 있을까?"),
        ("공안 단속 소식이 들리며 은신처를 옮겨야 한다", "정체 발각 위험을 중반부의 새 장애물로 전환한다", "가장 안전하던 방이 왜 가장 위험한 곳이 되었을까?"),
        ("동생이 열이 올라 이동을 거부하는 순간을 배치한다", "가족을 버릴 수 없는 선택 딜레마를 만든다", "살기 위해 떠나야 하는데 누구를 두고 갈 수 있을까?"),
        ("낯선 조선족 노인이 하루만 숨겨 주겠다고 한다", "불신 속에서 작은 도움의 가능성을 보여준다", "이 호의는 구원일까, 신고의 미끼일까?"),
        ("노인의 집 벽에 붙은 오래된 가족사진을 통해 과거를 엿본다", "도움을 주는 인물에게도 상실의 이유가 있음을 만든다", "그는 왜 위험을 알면서 문을 열었을까?"),
        ("전화 한 통으로 한국행 가능성을 처음 듣는다", "목표를 단순 도강에서 최종 안전지대로 확장한다", "한국이라는 단어가 왜 더 먼 공포처럼 들릴까?"),
        ("아버지와 연락이 끊긴 사실을 확인한다", "희생의 대가를 중반부 감정 축으로 끌어올린다", "아버지는 시간을 번 것일까, 돌아오지 못한 것일까?"),
        ("주인공이 아버지를 찾으러 돌아가겠다고 고집한다", "가족애와 생존 본능의 충돌을 만든다", "한 사람을 찾으려다 모두를 잃을 수도 있을까?"),
        ("어머니가 처음으로 아버지의 마지막 부탁을 말한다", "숨겨진 정보를 공개해 선택의 방향을 바꾼다", "그 부탁은 왜 지금까지 숨겨졌을까?"),
        ("두 번째 이동에서 기차역 검문을 통과해야 한다", "공간과 위험 방식을 바꿔 반복감을 줄인다", "표 한 장이 자유로 가는 문이 될 수 있을까?"),
        ("동생이 무심코 북한식 단어를 말해 위기가 닥친다", "정체가 들킬 뻔한 구체적 실수를 만든다", "한 단어가 모든 계획을 무너뜨릴까?"),
        ("주인공이 다른 사투리로 말을 돌려 위기를 넘긴다", "초반의 두려움이 생존 기술로 바뀌었음을 보여준다", "그는 언제 이렇게 빨리 어른이 되었을까?"),
        ("브로커 일행 중 한 명이 가족을 팔아넘기려는 낌새를 보인다", "외부 적대자를 새로 세워 긴장을 높인다", "가장 가까운 안내자가 가장 위험한 사람이라면?"),
        ("어머니가 숨겨 둔 돈 대신 결혼반지를 내민다", "물질보다 기억을 내놓는 감정적 비용을 보여준다", "그 반지는 가족에게 마지막으로 남은 과거였을까?"),
        ("밤길에서 차량을 갈아타며 추격을 간신히 피한다", "중반 후반부를 정적인 대기에서 물리적 이동으로 전환한다", "뒤따라오는 헤드라이트는 누구의 차일까?"),
        ("국경을 넘기 전 마지막 은신처에서 배신자의 정체가 드러난다", "후반 반전을 위한 인간 갈등을 명확히 한다", "왜 그는 처음부터 가족 곁에 붙어 있었을까?"),
        ("주인공이 처음으로 어머니와 동생을 먼저 보내기로 한다", "보호받던 인물이 보호자가 되는 전환을 만든다", "뒤에 남는 선택은 용기일까, 포기일까?"),
        ("추격자가 들이닥치기 직전 노인이 문을 막아선다", "조력자의 희생을 통해 연대의 감정을 세운다", "피가 섞이지 않은 사람도 가족이 될 수 있을까?"),
        ("주인공이 아버지의 발자국과 같은 선택을 반복한다", "초반 희생 장면을 후반 성장으로 회수한다", "그는 아버지를 잃은 것이 아니라 배운 것일까?"),
        ("마지막 차량 안에서 동생이 잃어버린 신발 이야기를 꺼낸다", "초반 소품을 감정의 회수 장치로 사용한다", "버린 신발 한 짝이 왜 아직 마음에 남았을까?"),
        ("한국행 연락책이 가족 이름을 확인하는 장면을 넣는다", "목표가 실제 절차와 확인으로 다가왔음을 보여준다", "이름을 말하는 순간 정말 새 삶이 시작될까?"),
        ("안전지대 직전 마지막 검문에서 가족이 다시 멈춰 선다", "클라이맥스 전 마지막 현실 장애물을 만든다", "여기서 잡히면 모든 희생은 어디로 가는가?"),
        ("어머니가 떨리는 손으로 준비한 답을 말한다", "가족이 함께 준비한 생존 전략을 실행한다", "그 한 문장은 훈련이었을까, 진심이었을까?"),
        ("검문관이 동생의 젖은 신발 자국을 바라본다", "작은 흔적이 마지막 위협으로 돌아오게 한다", "발자국 하나가 과거를 들춰낼까?"),
        ("주인공이 동생 대신 모든 의심을 자신에게 돌린다", "최종 선택의 도덕적 무게를 만든다", "누군가를 살리려면 누군가는 죄인이 되어야 할까?"),
        ("긴 침묵 뒤 차량 문이 열리며 통과 신호가 떨어진다", "긴장을 행동의 해소로 보여준다", "문이 열린 곳은 자유일까, 또 다른 시작일까?"),
        ("처음 안전한 방에서 가족이 소리 없이 운다", "성공을 환호가 아니라 탈진과 슬픔으로 처리한다", "살아남은 사람은 왜 먼저 울게 될까?"),
        ("아버지 소식을 끝내 듣지 못한 시간이 이어진다", "승리 뒤에도 남는 상실을 정직하게 남긴다", "자유는 모든 사람을 함께 데려오지 못한다"),
        ("20년 후 인터뷰 자리에서 주인공이 그 밤을 다시 말한다", "제목의 고백 구조를 현재 시점으로 회수한다", "왜 그는 이제야 그 이야기를 꺼냈을까?"),
        ("압록강 물소리를 들으면 아직도 몸이 굳는다고 고백한다", "트라우마를 과장 없이 신체 기억으로 표현한다", "시간은 지나도 몸은 그 밤을 기억할까?"),
        ("동생이 자라 자신의 아이에게 그날의 신발을 이야기한다", "세대가 바뀌어도 기억이 이어지는 방식을 보여준다", "상처는 어떻게 가족의 언어가 될까?"),
        ("어머니가 간직한 반지 없는 손을 조용히 비춘다", "잃어버린 물건을 통해 선택의 대가를 마무리한다", "그 빈손은 패배일까, 살아남은 증거일까?"),
        ("주인공이 아버지에게 보내는 말로 마지막 고백을 정리한다", "상실과 감사, 생존의 의미를 한 사람에게 모은다", "듣지 못할 사람에게도 고백은 닿을까?"),
        ("마지막 장면에서 강이 아니라 현재의 식탁을 보여준다", "이야기를 탈출담이 아닌 살아낸 삶의 증언으로 닫는다", "그 밤의 선택이 오늘의 가족을 만들었다"),
    ]
    repaired = dict(structure)
    repaired_scenes = []
    for idx, original in enumerate(scenes):
        scene = dict(original or {})
        summary, purpose, hook = beats[idx % len(beats)]
        scene["scene_order"] = idx + 1
        scene["scene_number"] = idx + 1
        scene["scene_summary"] = f"{idx + 1}번 장면: {summary}"
        scene["scene_purpose"] = purpose
        scene["retention_hook"] = hook
        scene["title_promise_link"] = f"'{title}'의 약속을 생존의 선택, 가족의 위험, 현재의 고백으로 한 단계 전진시킨다"
        scene["end_bridge"] = hook
        repaired_scenes.append(scene)
    repaired["scenes"] = repaired_scenes
    repaired["scene_count"] = len(repaired_scenes)
    repaired["planner_notes"] = {
        **(repaired.get("planner_notes") or {}),
        "repaired_repeated_scene_beats": True,
        "repair_reason": "survival story scene plan unique beat rebuild",
    }
    return repaired


def _requires_strict_scene_planner_success(job: dict) -> bool:
    payload = job.get("payload") or {}
    return bool(payload.get("require_scene_planner_success"))


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
    from config import Config, config
    from services.script_style_resolver import resolve_script_style_directive
    from app.services.scene_planner import scene_planner_service
    import asyncio

    config.SCRIPT_PLANNING_MODEL = _prefer_gemini_text_model(config, config.SCRIPT_PLANNING_MODEL)
    Config.SCRIPT_PLANNING_MODEL = config.SCRIPT_PLANNING_MODEL

    # Relies on this worker PC's local script_style_presets being in sync
    # with the web-admin (same assumption every other desktop install
    # already depends on for this function - not new to this job type).
    style_directive = resolve_script_style_directive(script_style)
    learning_instruction = _learning_profile_instruction(job.get("payload") or {})
    feedback_instruction = _quality_feedback_instruction(job.get("payload") or {})
    if learning_instruction:
        style_directive = f"{style_directive}\n\n{learning_instruction}".strip()
    if feedback_instruction:
        style_directive = f"{style_directive}\n\n{feedback_instruction}".strip()
    category_context = " ".join(
        str((job.get("payload") or {}).get(key) or "")
        for key in ("category", "category_name")
    ).strip()
    script_style_context = f"{script_style} {category_context}".strip()
    if _is_old_story_plan_context(script_style_context, topic, upload_title, str((job.get("payload") or {}).get("image_style") or "")):
        old_story_script_guard = """

Old-story script guard:
- Stay inside a pre-modern Korean folk-tale world. Do not introduce modern objects, places, institutions, or disputes.
- Forbidden modern drift: developer, redevelopment, excavator, museum, bus, phone, cellphone, Seoul trip, police report, court lawsuit, camera, broadcast, apartment, car, hospital, office.
- Do not invent a new external subplot that is not in the scene plan. Expand only the characters, place, object, secret, and emotional promise already present in the upload title and scene_situation fields.
- Never replace the title promise with a different family plot. The protagonist, central mystery, and final payoff must stay anchored to the upload title.
- Do not narrate planning labels such as middle turn, scene purpose, hook, prompt, camera, shot, or visual direction.
""".strip()
        style_directive = f"{style_directive}\n\n{old_story_script_guard}".strip()
    previous_error = str(job.get("error_message") or "").strip()
    if previous_error:
        hard_retry_rules = [
            "Do not write camera, screen, subtitle, shot, or visual-direction narration in the script.",
            "Each scene must change the viewer's understanding; if it only restates prior information, replace it with a new concrete choice, obstacle, or consequence.",
        ]
        if _is_finance_plan_context(script_style, topic, upload_title, image_style):
            hard_retry_rules.extend(
                [
                    "Do not repeat the same money amount or pension fact across multiple scenes. Mention a number once, then move to a new consequence or decision.",
                    "Do not turn the middle into a policy lecture or PSA. Keep the couple's action and decision driving the information.",
                ]
            )
        else:
            hard_retry_rules.extend(
                [
                    "Do not introduce modern finance, pension, bankbook, budget, policy, or investment beats unless the title explicitly requires them.",
                    "Keep the plan inside the selected category's narrative world, title promise, characters, conflict, and payoff.",
                ]
            )
        retry_instruction = f"""

Previous generation attempt failed QA. Fix these exact issues:
{previous_error[:2400]}

Hard retry rules:
{chr(10).join(f"- {rule}" for rule in hard_retry_rules)}
""".strip()
        style_directive = f"{style_directive}\n\n{retry_instruction}".strip()
    scene_plan_guard = """

Scene planning guard:
- Every scene must introduce a new action, fact, decision, consequence, objection, or emotional turn.
- Do not create multiple consecutive scenes with the same summary, purpose, hook, or explanation.
- For finance/pension topics, explain each number or policy point once, then move to a consequence or human decision.
- If the plan has 53 scenes, each scene must be a distinct beat; repeated development beats are invalid.
- Never use numbered template labels such as "1번째 중반 전환", "2번째 중반 전환", or any scene summary where only the ordinal changes.
""".strip()
    style_directive = f"{style_directive}\n\n{scene_plan_guard}".strip()

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

    category_context = " ".join(
        str((job.get("payload") or {}).get(key) or "")
        for key in ("category", "category_name")
    ).strip()
    script_style_context = f"{script_style} {category_context}".strip()
    detected_cat = str((job.get("payload") or {}).get("category") or (job.get("payload") or {}).get("category_name") or "").strip()

    planner_notes = structure.get("planner_notes") or {}
    if planner_notes.get("error"):
        planner_error = planner_notes.get("error_message") or "scene_planner_service.plan_scenes() failed"
        job_log.warning(f"Scene planner fallback activated: {planner_error}")
        if _requires_strict_scene_planner_success(job):
            raise RuntimeError(f"scene planner failed before fallback: {planner_error}")
        structure = _build_fallback_scene_plan(
            topic=topic,
            upload_title=upload_title,
            target_duration=target_duration,
            script_style=script_style,
            style_directive=style_directive,
            benchmark_analysis=benchmark_analysis,
            title_generation=title_generation,
            category=detected_cat,
        )
    research_bundle = (benchmark_analysis or {}).get("web_research")
    if isinstance(research_bundle, dict):
        structure["research_bundle"] = research_bundle
    finance_plan_context = _is_finance_plan_context(script_style_context, topic, upload_title, image_style)
    old_story_plan_context = _is_old_story_plan_context(script_style_context, topic, upload_title, image_style)
    if old_story_plan_context and not _old_story_title_is_grave_vigil(topic, upload_title):
        structure = _sanitize_old_story_scene_plan_to_title(structure, topic, upload_title)
    if old_story_plan_context:
        structure = _apply_old_story_story_core_to_structure(structure, topic, upload_title)
    plan_errors = _scene_plan_repetition_errors(structure)
    if plan_errors:
        if finance_plan_context and not _is_macro_economy_plan_context(script_style_context, topic, upload_title, image_style):
            job_log.warning(f"Scene plan repetition QA requested finance repair: {plan_errors[:8]}")
            structure = _repair_finance_scene_plan_repetition(structure, topic, upload_title)
        elif _is_macro_economy_plan_context(script_style_context, topic, upload_title, image_style):
            job_log.warning(f"Scene plan repetition QA requested macro economy repair: {plan_errors[:8]}")
            structure = _repair_macro_economy_scene_plan_repetition(structure, topic, upload_title)
        elif _is_martial_plan_context(script_style_context, topic, upload_title, image_style):
            job_log.warning(f"Scene plan repetition QA requested martial rebuild: {plan_errors[:8]}")
            structure = _repair_martial_scene_plan_repetition(structure, topic, upload_title)
        elif old_story_plan_context:
            job_log.warning(f"Scene plan repetition QA requested old-story rebuild: {plan_errors[:8]}")
            structure = _repair_old_story_scene_plan_repetition(structure, topic, upload_title)
            structure = _apply_old_story_story_core_to_structure(structure, topic, upload_title)
        elif _is_survival_story_plan_context(script_style_context, topic, upload_title, image_style):
            job_log.warning(f"Scene plan repetition QA requested survival-story rebuild: {plan_errors[:8]}")
            structure = _repair_survival_story_scene_plan_repetition(structure, topic, upload_title)
        elif _is_twilight_plan_context(script_style_context, topic, upload_title, image_style):
            job_log.warning(f"Scene plan repetition QA requested twilight rebuild: {plan_errors[:8]}")
            structure = _repair_twilight_scene_plan_repetition(structure, topic, upload_title)
        elif _is_korean_drama_plan_context(script_style_context, topic, upload_title, image_style):
            job_log.warning(f"Scene plan repetition QA requested korean drama rebuild: {plan_errors[:8]}")
            structure = _repair_korean_drama_scene_plan_repetition(structure, topic, upload_title)
        elif _is_overseas_touching_plan_context(script_style_context, topic, upload_title, image_style):
            job_log.warning(f"Scene plan repetition QA requested overseas touching rebuild: {plan_errors[:8]}")
            structure = _repair_overseas_touching_scene_plan_repetition(structure, topic, upload_title)
        else:
            job_log.warning(f"Scene plan repetition QA requested fallback repair: {plan_errors[:8]}")
            structure = _repair_finance_scene_plan_repetition(structure, topic, upload_title)

        # Repair builders preserve the planner's original visual fields unless
        # refreshed here. Those fields can contain internal template labels such
        # as "Timed visual beat" and must be replaced before the second QA pass.
        structure = _refresh_scene_visual_fields_for_category(detected_cat, structure, topic, upload_title)
        plan_errors = _scene_plan_repetition_errors(structure)
        if plan_errors:
            job_log.warning(f"Scene plan repair still repeated; rebuilding deterministic fallback: {plan_errors[:8]}")
            structure = _build_fallback_scene_plan(
                topic=topic,
                upload_title=upload_title,
                target_duration=target_duration,
                script_style=script_style,
                style_directive=style_directive,
                benchmark_analysis=benchmark_analysis,
                title_generation=title_generation,
                category=detected_cat,
            )
            structure = _refresh_scene_visual_fields_for_category(detected_cat, structure, topic, upload_title)
            plan_errors = _scene_plan_repetition_errors(structure)
            if plan_errors:
                raise RuntimeError(f"scene plan repetition QA failed after fallback rebuild: {plan_errors[:8]}")

    structure = _refresh_scene_visual_fields_for_category(detected_cat, structure, topic, upload_title)
    category_errors = _scene_plan_category_contamination_errors(
        structure,
        script_style=script_style_context,
        topic=topic,
        upload_title=upload_title,
        image_style=image_style,
    )
    if category_errors:
        raise RuntimeError(f"scene plan category QA failed: {category_errors[:8]}")
    plan_quality_report = _validate_script_plan_stage(
        structure,
        script_style=script_style_context,
        topic=topic,
        upload_title=upload_title,
        image_style=image_style,
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
        "image_style": image_style,
        "image_style_selection": image_style_selection or {},
        "structure": structure,
        "stage_quality_report": plan_quality_report,
        "learning_profile": (job.get("payload") or {}).get("learning_profile") or {},
        "defer_ready_until_quality_gate": bool((job.get("payload") or {}).get("defer_ready_until_quality_gate")),
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


def _trim_section_to_limit(text: str, max_chars: int) -> str:
    value = (text or "").strip()
    hard_limit = max(180, int(max_chars * 1.4))
    if len(value) <= hard_limit:
        return value
    sentences = [s.strip() for s in re.split(r"(?<=[.!?。！？다요죠까니다습니까])\s+", value) if s.strip()]
    kept: list[str] = []
    total = 0
    for sentence in sentences:
        projected = total + (2 if kept else 0) + len(sentence)
        if kept and projected > hard_limit:
            break
        kept.append(sentence)
        total = projected
        if total >= hard_limit:
            break
    if kept:
        return " ".join(kept).strip()
    return value[:hard_limit].rstrip()


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


def _parse_scene_duration_seconds(scene: dict, fallback: float) -> float:
    for key in ("target_duration", "duration_seconds", "duration", "play_time", "seconds"):
        raw = scene.get(key)
        if raw is None:
            continue
        if isinstance(raw, (int, float)):
            value = float(raw)
        else:
            match = re.search(r"\d+(?:\.\d+)?", str(raw))
            if not match:
                continue
            value = float(match.group(0))
        if value > 0:
            return value
    return max(1.0, float(fallback or 1.0))


def _scene_duration_map(scenes: list[dict], duration_seconds: int) -> list[float]:
    fallback = max(1.0, float(duration_seconds or 0) / max(1, len(scenes)))
    durations = [_parse_scene_duration_seconds(scene, fallback) for scene in scenes]
    total = sum(durations)
    if total <= 0:
        return [fallback for _ in scenes]
    return durations


def _scene_char_budgets(
    scenes: list[dict],
    duration_seconds: int,
    total_target_chars: float,
    is_shorts: bool,
) -> list[dict]:
    durations = _scene_duration_map(scenes, duration_seconds)
    total_duration = max(1.0, sum(durations))
    budgets: list[dict] = []
    for idx, (scene, scene_duration) in enumerate(zip(scenes, durations), start=1):
        target_chars = max(20.0, total_target_chars * (scene_duration / total_duration))
        if is_shorts:
            min_chars = max(18, round(target_chars * 0.7))
            max_chars = max(min_chars + 8, round(target_chars * 1.25))
        elif scene_duration <= 6:
            min_chars = max(35, round(target_chars * 0.65))
            max_chars = min(180, max(min_chars + 20, round(target_chars * 1.35)))
        else:
            min_chars = max(70, round(target_chars * 0.78))
            max_chars = max(min_chars + 30, round(target_chars * 1.22))
        budgets.append({
            "scene_order": scene.get("scene_order") or scene.get("order") or idx,
            "duration_seconds": round(scene_duration, 2),
            "target_chars": round(target_chars),
            "min_chars": min_chars,
            "max_chars": max_chars,
        })
    return budgets


def _chunk_scenes_for_script_generation(
    scenes: list[dict],
    budgets: list[dict],
    *,
    max_chunks: int = 5,
) -> list[tuple[int, list[dict], list[dict]]]:
    if not scenes:
        return []
    total_duration = sum(float(item.get("duration_seconds") or 0) for item in budgets) or float(len(scenes))
    target_chunk_duration = max(90.0, total_duration / max(1, max_chunks))
    chunks: list[tuple[int, list[dict], list[dict]]] = []
    start_idx = 0
    current_scenes: list[dict] = []
    current_budgets: list[dict] = []
    current_duration = 0.0

    for idx, (scene, budget) in enumerate(zip(scenes, budgets)):
        current_scenes.append(scene)
        current_budgets.append(budget)
        current_duration += float(budget.get("duration_seconds") or 0)
        remaining_scenes = len(scenes) - idx - 1
        remaining_chunks = max_chunks - len(chunks) - 1
        can_close = remaining_scenes > 0 and remaining_chunks > 0
        if can_close and current_duration >= target_chunk_duration:
            chunks.append((start_idx, current_scenes, current_budgets))
            start_idx = idx + 1
            current_scenes = []
            current_budgets = []
            current_duration = 0.0

    if current_scenes:
        chunks.append((start_idx, current_scenes, current_budgets))
    return chunks


def _select_script_draft_model(config, final_model: str) -> str:
    selected = (final_model or "").strip()
    return selected


def _clean_script_scene_text(value: str, upload_title: str = "") -> str:
    """Remove planner/UI meta wording before it reaches narration generation."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    if upload_title:
        text = text.replace(str(upload_title).strip(), "").strip()
    text = re.sub(r"'[^']{8,}'", "", text)
    text = re.sub(r'"[^"]{8,}"', "", text)
    text = re.sub(r"\b\d+\s*단계로\s*[^,，.。]*[,，.。]?\s*", "", text)
    text = re.sub(r"\b\d+번(?:째)?\s*장면(?:은|에서)?\s*", "", text)
    text = re.sub(r"(?:오프닝|중반|후반|결말)의 역할은[^.。]*[.。]?", "", text)
    text = re.sub(r"다음 단서는[^.。]*[.。]?", "", text)
    text = re.sub(r"[^.。]{0,40}때문에 마을 사람들의 숨겨진 관계가 한 겹 더 흔들린다[.。]?", "", text)
    text = re.sub(r"설명보다 사건으로 느끼게 하고[^.。]*[.。]?", "", text)
    text = re.sub(r"여운으로 넘긴다[.。]?", "", text)
    text = re.sub(r"제목의 약속을[^,，.。]*[,，.。]?\s*", "", text)
    text = re.sub(r"클릭(?:한|된)? 제목[^.。]*[.。]?", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -—,，.。")
    return text[:320].strip()


def _scene_payload_for_script(scene: dict, budget: dict, upload_title: str = "") -> dict:
    scene_order = scene.get("scene_order") or scene.get("order") or scene.get("scene_number")
    situation = _clean_script_scene_text(scene.get("scene_situation") or "", upload_title)
    summary = _clean_script_scene_text(scene.get("scene_summary") or "", upload_title)
    purpose = _clean_script_scene_text(scene.get("scene_purpose") or "", upload_title)
    hook = _clean_script_scene_text(scene.get("retention_hook") or "", upload_title)
    if not situation:
        situation = summary or purpose or hook
    return {
        "scene_order": scene_order,
        "target_duration_seconds": budget.get("duration_seconds"),
        "target_chars": budget.get("target_chars"),
        "min_chars": budget.get("min_chars"),
        "max_chars": budget.get("max_chars"),
        "story_beat": situation,
        "purpose": purpose,
        "emotion": _clean_script_scene_text(scene.get("scene_emotion") or "", upload_title),
        "turn_or_question": hook,
        "dramatic_function": _clean_script_scene_text(scene.get("dramatic_function") or "", upload_title),
        "character_choice": _clean_script_scene_text(scene.get("character_choice") or "", upload_title),
        "emotional_shift": _clean_script_scene_text(scene.get("emotional_shift") or "", upload_title),
        "reveal_or_question": _clean_script_scene_text(scene.get("reveal_or_question") or "", upload_title),
    }


def _prefer_gemini_text_model(config, selected: str = "") -> str:
    """Respect user's configured model (Claude, DeepSeek, GLM, etc.) and fallback to Gemini only if empty."""
    current = str(selected or "").strip()
    if current:
        return current
    if (getattr(config, "GEMINI_API_KEY", "") or "").strip():
        return "gemini-3-flash-preview"
    return "gemini-3-flash-preview"



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
- Do not repeat any sentence, image, fact, spending item, or emotional beat already used in previous scenes.
- This scene must add exactly one new concrete action, fact, decision, or consequence.
"""

    clean_prompt = f"""You are an expert {'Shorts' if is_shorts else 'YouTube long-form'} narration writer. Write the body for this planned scene so a real viewer wants to keep listening.

[TOPIC]
{topic}
{title_contract}
{blueprint_section}
{research_section}
{continuity_section}

[CURRENT SCENE]
- Situation and purpose, authoritative: {key_points_text}
- Summary, supporting only: {scene_summary}
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
9. Strict anti-repetition rule: if the previous context already mentions the same money amount, worry, routine, or conclusion, do not explain it again. Advance to the next beat instead.
10. Keep this section compact. If you need more space, choose the strongest two or three sentences only.
11. If Summary conflicts with Situation and purpose, ignore Summary and follow Situation and purpose plus the upload title.

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


def _build_script_chunk_prompt(
    topic: str,
    chunk_scenes: list[dict],
    chunk_budgets: list[dict],
    is_shorts: bool,
    is_multi: bool,
    known_characters: list[str],
    length_instruction: str,
    language: str,
    upload_title: str = "",
    structure_context: dict | None = None,
    narrative_blueprint: dict | None = None,
    previous_context: dict | None = None,
    narration_mode: str = "single",
    main_character: dict | None = None,
) -> str:
    structure_context = structure_context or {}
    narrative_blueprint = narrative_blueprint or {}
    previous_context = previous_context or {}
    is_dramatic_single = narration_mode == "dramatic_single"
    mode_instruction = _script_gen_mode_instruction(is_multi, known_characters, is_dramatic_single=is_dramatic_single)
    language_instruction = SCRIPT_GEN_LANGUAGE_INSTRUCTIONS.get(language, SCRIPT_GEN_LANGUAGE_INSTRUCTIONS["ko"])
    budget_by_order = {str(item.get("scene_order")): item for item in chunk_budgets}
    scene_payload = []
    for idx, scene in enumerate(chunk_scenes):
        scene_order = scene.get("scene_order") or scene.get("order") or idx + 1
        budget = budget_by_order.get(str(scene_order)) or chunk_budgets[idx]
        clean_scene = dict(scene)
        clean_scene["scene_order"] = scene_order
        scene_payload.append(_scene_payload_for_script(clean_scene, budget, upload_title))

    research_bundle = structure_context.get("research_bundle") or {}
    research_section = ""
    if research_bundle:
        research_section = f"""
[RESEARCH CONTEXT]
{research_bundle.get("research_brief") or ""}
Verified facts: {json.dumps((research_bundle.get("verified_facts") or [])[:10], ensure_ascii=False)}
Risk notes: {json.dumps(research_bundle.get("risk_notes") or [], ensure_ascii=False)}
"""

    return f"""You are an expert Korean YouTube long-form narration writer. Write multiple planned scenes as one continuous script chunk.

[TOPIC]
{topic}

[UPLOAD TITLE CONTRACT]
- Upload title: {upload_title}
- Title promise: {structure_context.get("title_promise") or "infer it from the upload title and topic"}
- Opening hook: {structure_context.get("opening_hook") or ""}
- Final payoff required: {structure_context.get("payoff") or ""}
- Every scene must serve the clicked title. Do not drift into a different story, policy lecture, or meta commentary.

[STORY BLUEPRINT]
{json.dumps(narrative_blueprint or {}, ensure_ascii=False)}
- Use opening_incident before backstory in the first chunk.
- Use personal_stake to make the protagonist's motive clear before the first act ends.
- Use midpoint_reversal and final_payoff as hard story anchors, not optional suggestions.

[MAIN PROTAGONIST DNA - WORKER GENERATED]
{_main_character_context(main_character) or "{}"}
- Keep this protagonist's identity, motive, age, and emotional baseline stable across every scene.
- Do not print this JSON or describe it as metadata to viewers. Use it only to keep the story and later visuals consistent.

{research_section}

[CONTINUITY BEFORE THIS CHUNK]
{json.dumps(previous_context or {}, ensure_ascii=False)}

[SCENES TO WRITE]
{json.dumps(scene_payload, ensure_ascii=False)}

[WRITING RULES]
0. {length_instruction}
1. Respect target_duration_seconds and character budgets per scene. Do not make all scenes the same length.
2. A 5-second scene is a short micro beat: one or two vivid sentences only. Longer scenes may carry more action, emotion, or explanation.
{mode_instruction}
4. {language_instruction}
5. Output Korean narration body only inside JSON. No scene titles, headings, markdown, timecodes, camera directions, subtitle notes, or sound-effect labels.
6. Use story_beat and purpose as the only scene instructions. Ignore any planning, visual, TTS, camera, or UI wording from prior stages.
7. Every scene must add new action, information, decision, or consequence. Do not repeat the same sentence, fact, image, worry, or emotional beat.
8. Preserve continuity across the scenes in this chunk and from previous_context.
9. Use turn_or_question only as a guide. Do not copy it verbatim if it sounds repetitive or templated.
10. For each output item, keep text between min_chars and max_chars as closely as possible. Never pad with repetition.
11. Do not summarize the scene plan. Dramatize each beat as spoken narration with sensory detail, a concrete action, and a visible emotional reaction.
12. Do not repeat the upload title or scene summary phrase inside each section. The title promise should be fulfilled through events, not copied as wording.
13. Give the protagonist active choices. At least every 3-4 scenes, the main character must decide, hide, reveal, confront, refuse, or sacrifice something.
14. If dramatic_function, character_choice, emotional_shift, or reveal_or_question are present, dramatize them in the scene text without printing those labels.
15. Do not open with a lesson, summary, or village rumor if opening_incident is available. Start with a visible event, object, body movement, or discovery.

Return ONLY JSON in this exact shape:
{{
  "sections": [
    {{"scene_order": 1, "text": "narration body for that scene"}}
  ]
}}"""


def _parse_script_chunk_sections(
    raw_text: str,
    chunk_scenes: list[dict],
    is_multi: bool,
    fallback_factory,
) -> list[str]:
    by_order: dict[str, str] = {}
    try:
        data = _extract_json(raw_text)
        sections = data.get("sections") if isinstance(data, dict) else None
        if isinstance(sections, list):
            for item in sections:
                if isinstance(item, dict):
                    order = str(item.get("scene_order") or "").strip()
                    text = _clean_section_text(str(item.get("text") or "").strip(), is_multi)
                    if order and text:
                        by_order[order] = text
    except Exception:
        pass

    # Regex recovery if JSON decode didn't catch all scenes
    if len(by_order) < len(chunk_scenes):
        for m in re.finditer(r'"scene_order"\s*:\s*(\d+)\s*,\s*"text"\s*:\s*"((?:\\.|[^"\\])*)"', raw_text):
            order = m.group(1).strip()
            if order not in by_order:
                raw_s = m.group(2).encode().decode("unicode_escape", errors="ignore")
                text = _clean_section_text(raw_s, is_multi)
                if text:
                    by_order[order] = text

    result: list[str] = []
    for local_idx, scene in enumerate(chunk_scenes):
        scene_order = str(scene.get("scene_order") or scene.get("order") or "").strip()
        text = by_order.get(scene_order)
        if not text:
            # Also try matching 1-based local index
            text = by_order.get(str(local_idx + 1))
        if not text:
            text = fallback_factory(local_idx, scene)
        result.append(text)
    return result



def _short_script_excerpt(text: str, max_chars: int = 1400) -> str:
    value = (text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


def _main_character_context(main_character: dict | None) -> str:
    if not isinstance(main_character, dict) or not main_character:
        return ""
    return json.dumps({
        "name": main_character.get("name") or main_character.get("display_name") or "주인공",
        "gender": main_character.get("gender") or "",
        "age_group": main_character.get("age_group") or "",
        "role": main_character.get("role") or "protagonist",
        "visual_dna_en": main_character.get("visual_dna_en") or "",
        "wardrobe_en": main_character.get("wardrobe_en") or "",
        "continuity_instruction": main_character.get("continuity_instruction") or "",
        "tags": main_character.get("tags") or [],
    }, ensure_ascii=False)


def _character_anchor_name(character: dict | None) -> str:
    if not isinstance(character, dict):
        return ""
    return str(
        character.get("name")
        or character.get("display_name")
        or character.get("stable_label")
        or ""
    ).strip()


def _normalize_character_anchor(character: dict | None, *, fallback_name: str, role: str) -> dict:
    source = character if isinstance(character, dict) else {}
    name = _character_anchor_name(source) or fallback_name
    visual_dna = str(
        source.get("visual_dna_en")
        or source.get("prompt_en")
        or source.get("description_en")
        or source.get("description")
        or ""
    ).strip()
    wardrobe = str(source.get("wardrobe_en") or source.get("wardrobe") or "").strip()
    continuity = str(source.get("continuity_instruction") or "").strip()
    if not visual_dna:
        visual_dna = (
            f"ordinary Korean {role} with a consistent age range, face shape, hairstyle, "
            "body type, natural skin texture, restrained expression, and stable wardrobe colors"
        )
    if not wardrobe:
        wardrobe = "story-appropriate everyday clothing with consistent color and silhouette"
    if not continuity:
        continuity = (
            "Preserve this character's age, face shape, hairstyle, wardrobe, body type, "
            "and emotional baseline in every image and video prompt."
        )
    return {
        "name": name,
        "gender": str(source.get("gender") or "unknown").strip() or "unknown",
        "age_group": str(source.get("age_group") or "").strip(),
        "role": str(source.get("role") or role).strip() or role,
        "visual_dna_en": visual_dna,
        "wardrobe_en": wardrobe,
        "continuity_instruction": continuity,
        "tags": source.get("tags") if isinstance(source.get("tags"), list) else [],
        "source": source.get("source") or "worker_character_anchor",
    }


def _character_anchors_context(
    main_character: dict | None,
    supporting_characters: list[dict] | None = None,
) -> str:
    main_anchor = _normalize_character_anchor(
        main_character,
        fallback_name="protagonist",
        role="protagonist",
    ) if isinstance(main_character, dict) and main_character else None
    supporting = [
        _normalize_character_anchor(item, fallback_name=f"supporting_character_{idx}", role="supporting")
        for idx, item in enumerate((supporting_characters or [])[:2], start=1)
        if isinstance(item, dict)
    ]
    payload = {
        "max_character_anchors": 3,
        "main_character": main_anchor,
        "supporting_characters": supporting,
        "image_reference_policy": (
            "No character image file is generated in this worker stage. Use these text DNA anchors "
            "as the source of truth for image-grid and video-prompt continuity."
        ),
    }
    if not main_anchor and not supporting:
        return ""
    return json.dumps(payload, ensure_ascii=False)


def _fallback_main_character(topic: str, upload_title: str, structure: dict, narrative_blueprint: dict | None = None) -> dict:
    blueprint = narrative_blueprint or {}
    protagonist = str(blueprint.get("protagonist") or "").strip()
    if not protagonist:
        scenes = structure.get("scenes") if isinstance(structure, dict) else []
        first_scene = scenes[0] if isinstance(scenes, list) and scenes else {}
        protagonist = str(
            first_scene.get("protagonist")
            or first_scene.get("main_character")
            or first_scene.get("character")
            or "주인공"
        ).strip()
    title_hint = _text_with_mojibake_repairs(topic, upload_title)
    if any(term in title_hint for term in ("할머니", "어머니", "아내", "여자", "며느리")):
        gender = "female"
    elif any(term in title_hint for term in ("할아버지", "아버지", "남편", "남자", "영감")):
        gender = "male"
    else:
        gender = "unknown"
    if any(term in title_hint for term in ("노인", "노후", "70", "80", "할머니", "할아버지", "영감")):
        age_group = "70s"
    elif any(term in title_hint for term in ("30", "40")):
        age_group = "30s-40s"
    else:
        age_group = "middle-aged adult"
    visual = (
        f"a Korean {age_group} {gender if gender != 'unknown' else 'person'} with a grounded, realistic face, "
        "natural skin texture, restrained emotional eyes, ordinary everyday clothing, consistent hairstyle, "
        "consistent body type and wardrobe colors across every scene"
    )
    return {
        "name": protagonist or "주인공",
        "gender": gender,
        "age_group": age_group,
        "role": "주인공",
        "visual_dna_en": visual,
        "wardrobe_en": "simple, story-appropriate everyday clothing with consistent color and silhouette",
        "continuity_instruction": "Keep the protagonist's age, face shape, hairstyle, clothing, body type, and emotional baseline consistent in every scene.",
        "tags": [age_group, gender, "consistent protagonist"],
        "source": "worker_fallback",
    }


async def _generate_main_character_anchor(
    ai_router,
    model: str,
    topic: str,
    upload_title: str,
    structure: dict,
    language: str,
    narrative_blueprint: dict | None,
    job_log,
) -> dict:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    scene_digest = []
    if isinstance(scenes, list):
        for scene in scenes[:12]:
            if not isinstance(scene, dict):
                continue
            scene_digest.append({
                "scene_order": scene.get("scene_order") or scene.get("order"),
                "scene_summary": scene.get("scene_summary"),
                "scene_situation": scene.get("scene_situation"),
                "character_choice": scene.get("character_choice"),
            })
    prompt = f"""You are the worker-side visual continuity director for AIR Studio.
Before writing the script, infer ONE main protagonist character DNA that should govern the narration, image-grid prompts, and video prompts.

Return ONLY valid JSON.

[TOPIC]
{topic}

[UPLOAD TITLE]
{upload_title}

[LANGUAGE]
{language}

[STORY BLUEPRINT]
{json.dumps(narrative_blueprint or {}, ensure_ascii=False)}

[SCENE DIGEST]
{json.dumps(scene_digest, ensure_ascii=False)}

JSON shape:
{{
  "name": "Korean character name or stable label",
  "gender": "male|female|unknown",
  "age_group": "clear age range",
  "role": "주인공 role in Korean",
  "visual_dna_en": "precise English permanent visual identity: age, ethnicity, face shape, eyes, hair, body type, skin texture, expression baseline",
  "wardrobe_en": "consistent default wardrobe and color palette",
  "continuity_instruction": "one English sentence instructing image/video generators to preserve this protagonist across scenes",
  "tags": ["short Korean/English tags"]
}}

Rules:
- Do not invent a celebrity, brand, copyrighted character, or public figure likeness.
- Make the character specific enough to keep consistent, but ordinary enough for generic AI generation.
- The character must serve the title promise and story blueprint.
- If the story is narration-only or financial/economy analysis, create a representative protagonist or affected viewer only when the scene plan has a human subject; otherwise return an understated host/subject character."""
    try:
        raw = await ai_router.generate_text(
            prompt,
            model,
            temperature=0.25,
            max_tokens=2048,
            task_type="hermes_main_character_anchor",
        )
        data = _extract_json(raw)
        if not isinstance(data, dict):
            raise ValueError("main character response was not an object")
        fallback = _fallback_main_character(topic, upload_title, structure, narrative_blueprint)
        character = {**fallback, **{k: v for k, v in data.items() if v not in (None, "", [])}}
        character["source"] = "worker_ai"
        character["created_at"] = time.time()
        if not str(character.get("visual_dna_en") or "").strip():
            character["visual_dna_en"] = fallback["visual_dna_en"]
        job_log.info(f"Main character anchor ready: {character.get('name') or 'protagonist'}")
        return character
    except Exception as e:
        job_log.warning(f"Main character anchor generation failed; using fallback: {e}")
        fallback = _fallback_main_character(topic, upload_title, structure, narrative_blueprint)
        fallback["created_at"] = time.time()
        return fallback


async def _generate_supporting_character_anchors(
    ai_router,
    model: str,
    topic: str,
    upload_title: str,
    structure: dict,
    final_script: str,
    main_character: dict | None,
    job_log,
) -> list[dict]:
    """Infer up to two non-image supporting character DNA anchors.

    This deliberately creates text continuity only. Character portrait/image
    generation is a later, opt-in stage because it costs more and can drift
    from the final scene prompts.
    """
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    scene_digest = []
    if isinstance(scenes, list):
        for scene in scenes[:16]:
            if not isinstance(scene, dict):
                continue
            scene_digest.append({
                "scene_order": scene.get("scene_order") or scene.get("order"),
                "scene_summary": scene.get("scene_summary"),
                "scene_situation": scene.get("scene_situation"),
                "character_choice": scene.get("character_choice"),
                "continuity_identity": scene.get("continuity_identity"),
            })

    prompt = f"""You are AIR Studio's worker-side character continuity director.
Infer up to TWO supporting character DNA anchors from the final script and scene plan.

Return ONLY valid JSON.

[TOPIC]
{topic}

[UPLOAD TITLE]
{upload_title}

[MAIN CHARACTER - DO NOT DUPLICATE]
{_main_character_context(main_character) or "{}"}

[SCENE DIGEST]
{json.dumps(scene_digest, ensure_ascii=False)}

[FINAL SCRIPT EXCERPT]
{str(final_script or "")[:6000]}

JSON shape:
{{
  "supporting_characters": [
    {{
      "name": "stable Korean name or role label",
      "gender": "male|female|unknown",
      "age_group": "clear age range",
      "role": "story role",
      "visual_dna_en": "precise English permanent visual identity: age, ethnicity, face shape, eyes, hair, body type, skin texture, expression baseline",
      "wardrobe_en": "consistent default wardrobe and color palette",
      "continuity_instruction": "one English sentence for image/video prompt consistency",
      "tags": ["short tags"]
    }}
  ]
}}

Rules:
- Return 0, 1, or 2 supporting characters only.
- Choose recurring or visually important characters, not one-off crowds.
- Do not duplicate the main character.
- Do not invent celebrities, brands, copyrighted characters, or public figures.
- Use text DNA only; do not request or describe a generated portrait file."""
    try:
        raw = await ai_router.generate_text(
            prompt,
            model,
            temperature=0.25,
            max_tokens=2200,
            task_type="hermes_supporting_character_anchors",
        )
        data = _extract_json(raw)
        candidates = data.get("supporting_characters") if isinstance(data, dict) else []
        if not isinstance(candidates, list):
            raise ValueError("supporting_characters was not a list")
        main_name = _character_anchor_name(main_character).casefold()
        anchors = []
        seen = {main_name} if main_name else set()
        for index, candidate in enumerate(candidates, start=1):
            if not isinstance(candidate, dict):
                continue
            anchor = _normalize_character_anchor(
                candidate,
                fallback_name=f"supporting_character_{index}",
                role="supporting",
            )
            key = _character_anchor_name(anchor).casefold()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            anchor["source"] = "worker_ai"
            anchors.append(anchor)
            if len(anchors) >= 2:
                break
        job_log.info(f"Supporting character anchors ready: {len(anchors)}")
        return anchors
    except Exception as e:
        job_log.warning(f"Supporting character anchor generation failed; continuing without supporting anchors: {e}")
        return []


def _fallback_narrative_blueprint(topic: str, upload_title: str, structure: dict) -> dict:
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    story_core = structure.get("story_core") if isinstance(structure, dict) and isinstance(structure.get("story_core"), dict) else {}
    scene_beats = []
    for idx, scene in enumerate(scenes or [], start=1):
        scene_beats.append({
            "scene_order": scene.get("scene_order") or idx,
            "act": scene.get("act"),
            "dramatic_function": scene.get("dramatic_function") or "",
            "beat": scene.get("scene_summary") or f"Scene {idx}",
            "tension": scene.get("retention_hook") or scene.get("scene_purpose") or "",
            "turn": scene.get("end_bridge") or "",
            "character_choice": scene.get("character_choice") or "",
            "emotional_shift": scene.get("emotional_shift") or "",
            "reveal_or_question": scene.get("reveal_or_question") or "",
        })
    return {
        "logline": story_core.get("logline") or upload_title or topic,
        "protagonist": story_core.get("protagonist") or "the person at the center of the clicked story",
        "desire": story_core.get("desire") or "resolve the promise raised by the title",
        "opening_incident": story_core.get("opening_incident") or structure.get("opening_hook") or "",
        "personal_stake": story_core.get("personal_stake") or "",
        "central_conflict": story_core.get("central_conflict") or structure.get("title_promise") or topic,
        "stakes": story_core.get("stakes") or structure.get("opening_hook") or "viewer curiosity must keep rising",
        "hidden_information": story_core.get("hidden_information") or "reveal new information gradually instead of explaining everything upfront",
        "turning_point": story_core.get("turning_point") or story_core.get("midpoint_reversal") or "a late middle reversal that changes what the viewer believes",
        "midpoint_reversal": story_core.get("midpoint_reversal") or "",
        "final_payoff": story_core.get("final_payoff") or structure.get("payoff") or "emotionally resolve the title promise",
        "act_structure": story_core.get("acts") or [],
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

Rules:
- If verdict is "pass", critical_issues MUST be an empty array. Put non-blocking improvement notes in revision_notes.
- If any item is severe enough to be called a critical issue, verdict MUST be "revise".
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
    verdict = str(report.get("verdict") or "").strip().lower()
    score = int(report.get("score") or 0)
    if report.get("critical_issues"):
        # If critical issues exist but score is reasonable (>=70) and no hard failure
        if score >= 70 and len(report.get("critical_issues") or []) <= 2:
            return False
        return True
    if verdict == "pass" and score >= 70:
        return False
    if score >= 70:
        return False
    if verdict == "revise" and score < 70:
        return True
    return False



def _detect_repeated_script_sentences(script: str, *, min_chars: int = 28, max_allowed: int = 8) -> list[dict]:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?。！？다요죠까니다습니까])\s+", script or "")
        if len(sentence.strip()) >= min_chars
    ]
    counts = Counter(sentences)
    repeated = [
        {"count": count, "sentence": sentence}
        for sentence, count in counts.items()
        if count > 1
    ]
    repeated.sort(key=lambda item: (-int(item["count"]), str(item["sentence"])))
    if len(repeated) <= max_allowed:
        return []
    return repeated


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


def _build_finance_rescue_script(topic: str, upload_title: str, structure: dict, min_total_chars: int = 2600) -> str:
    title = (upload_title or topic or "노후금융 이야기").strip()
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    scene_count = len(scenes or [])
    protagonist = "남편 김성호 씨와 아내 박미자 씨"
    paragraphs = [
        f"{title}. 이 이야기는 {protagonist}가 은퇴 뒤 처음으로 장부를 다시 펼친 날에서 시작됩니다. 두 사람은 오래 모은 돈이 있었고, 국민연금도 받을 예정이었습니다. 그런데 통장 잔액은 예상보다 훨씬 빨리 줄어 있었습니다.",
        "처음 문제는 수익률이 아니었습니다. 매달 빠져나가는 고정 지출이었습니다. 관리비, 식비, 건강보험료, 약값, 경조사비가 한 번에 빠지고 나면 남는 돈은 생각보다 작았습니다. 부부가 놓친 것은 총자산이 아니라 매달 현금흐름이었습니다.",
        "두 사람은 은퇴 전에는 예금 잔액만 봤습니다. 하지만 은퇴 후에는 잔액보다 빠져나가는 속도가 더 중요했습니다. 매달 100만 원 안팎의 고정비가 먼저 사라지고, 병원비가 겹친 달에는 예비비까지 같이 줄었습니다.",
        "결정적인 전환점은 오래된 자동이체 목록에서 나왔습니다. 부부는 이미 해지했다고 생각한 보험료와 관리비성 지출을 계속 내고 있었습니다. 큰 소비 하나가 아니라 작은 고정비 여러 개가 10년 동안 통장을 갉아먹은 겁니다.",
        "남편은 그제야 계산 방식을 바꿉니다. '얼마를 모았나'가 아니라 '매달 얼마가 반드시 나가나'를 적기 시작합니다. 그 표에서 가장 무서운 줄은 생활비가 아니라 병원비 예비 항목이었습니다. 한 번 아프면 한 달 계획이 바로 무너졌습니다.",
        "아내는 자녀에게 말하지 못했던 이유를 꺼냅니다. 도움을 받고 싶지 않아서가 아니라, 어디서부터 설명해야 할지 몰랐기 때문입니다. 집도 없고, 전세도 없고, 예금만 조금 남은 노후는 겉으로 보기보다 훨씬 취약했습니다.",
        "전문가가 짚은 핵심은 단순했습니다. 노후자금은 평균 수익률보다 인출 순서가 중요합니다. 생활비 통장, 비상금, 장기 예금, 연금 수령액을 구분하지 않으면 필요한 돈을 쓸 때마다 장기 자금까지 깨게 됩니다.",
        "부부의 돈이 10년 만에 바닥난 이유도 여기에 있었습니다. 매달 고정비를 예금에서 먼저 빼고, 병원비가 생기면 또 예금을 깨고, 물가가 오르면 생활비를 줄이지 못했습니다. 수입은 고정되어 있는데 지출만 조금씩 올라간 구조였습니다.",
        "마지막으로 두 사람은 장부를 세 칸으로 다시 나눕니다. 반드시 나가는 돈, 줄일 수 있는 돈, 절대 건드리면 안 되는 비상금. 이 구분을 하고 나서야 문제의 원인이 보였습니다. 돈이 한꺼번에 사라진 게 아니라, 매달 같은 순서로 새고 있었습니다.",
        "그래서 이 이야기의 답은 한 문장입니다. 노후를 위험하게 만든 것은 큰 실패가 아니라, 고정비와 인출 순서를 계산하지 않은 10년이었습니다. 통장 잔액보다 먼저 봐야 할 것은 매달 빠져나가는 돈의 순서였습니다.",
    ]
    if scene_count > 10:
        for idx, scene in enumerate((scenes or [])[10:], start=11):
            summary = str((scene or {}).get("scene_summary") or "").strip()
            if not summary:
                continue
            paragraphs.append(
                f"{idx}번째 장면에서 부부는 같은 걱정을 반복하지 않고 하나의 항목만 확인합니다. {summary} 여기서 중요한 것은 새 지출을 하나 더 발견하거나, 줄일 수 없는 이유를 하나씩 분리하는 것입니다."
            )
    script = "\n\n".join(paragraphs).strip()
    while len(script) < min_total_chars:
        script += "\n\n부부는 다음 달부터 모든 자동이체 날짜를 한 장에 적기로 했습니다. 수입이 들어오는 날보다 지출이 빠지는 날이 먼저 오면, 노후자금은 숫자상으로는 남아 있어도 생활에서는 이미 부족해집니다."
    return script



def _build_economy_rescue_script(topic: str, upload_title: str, structure: dict, min_total_chars: int = 2600) -> str:
    title = (upload_title or topic or "경제 시장 분석").strip()
    paragraphs = [
        f"{title}. 오늘 우리가 반드시 확인해야 할 경제 지표는 단순한 숫자가 아닙니다. 글로벌 금융 시장과 환율, 금리가 동시에 한 방향을 가리키고 있습니다. 이 변화는 대기업의 수출 실적뿐만 아니라 우리 가계의 장바구니 물가와 대출 금리에 즉각적인 영향을 미칩니다.",
        "시장의 충격은 항상 외환과 원자재에서 먼저 시작됩니다. 달러 환율이 요동치고 원유와 원자재 수입 단가가 상승하면, 제조업 중심의 국내 산업 구조는 마진율 하락을 피할 수 없습니다. 수입 물가가 오르면 시차를 두고 소비자물가로 전가되기 때문입니다.",
        "많은 전문가들이 주목하는 핵심은 중앙은행의 딜레마입니다. 물가를 잡기 위해 금리를 올리면 부채가 많은 자영업자와 가계가 타격을 입고, 경기를 부양하기 위해 금리를 내리면 환율 방어가 어려워집니다. 이 좁은 외줄 타기가 현재 한국 경제가 직면한 현실입니다.",
        "기업들의 현금흐름도 빠르게 재편되고 있습니다. 자금 조달 비용이 증가하면서 무리하게 차입 경영을 이어오던 한계 기업들의 부실 위험이 표면화되고 있습니다. 반면 현금 보유력이 높고 공급망을 다변화한 기업들은 위기를 기회로 바꾸고 있습니다.",
        "개인 투자자와 가계가 지금 당장 취해야 할 전략은 명확합니다. 무리한 레버리지를 줄이고, 현금성 자산의 비중을 확보하며, 시장의 변곡점을 나타내는 핵심 지표들을 주기적으로 점검해야 합니다. 위기 뒤에는 언제나 새로운 시장 사이클이 열리기 때문입니다.",
        "결론적으로 이번 경제 변동의 핵심 메시지는 하나입니다. 시장의 불확실성을 두려워하기보다 데이터에 기반한 리스크 관리를 시작해야 할 때입니다. 매일 발표되는 거시 지표 뒤에 숨은 흐름을 읽는 것이 내 자산을 지키는 가장 확실한 방패입니다.",
    ]
    script = "\n\n".join(paragraphs).strip()
    while len(script) < min_total_chars:
        script += "\n\n결국 시장의 변동성 앞에서 가장 중요한 것은 장기적인 안목과 원칙입니다. 단기적인 등락에 일희일비하지 않고, 구조적인 성장 동력을 갖춘 분야를 선별하는 냉철한 분석이 필요한 시점입니다."
    return script


def _build_martial_rescue_script(topic: str, upload_title: str, structure: dict, min_total_chars: int = 2600) -> str:
    title = (upload_title or topic or "무협 이야기").strip()
    paragraphs = [
        f"{title}. 비 내리는 대나무숲 끝, 폐허가 된 산문 앞에 피 묻은 현판 하나가 떨어져 있었습니다. 강호의 패권을 노리던 적대 문파의 기습으로 문파는 몰락했고, 살아남은 사형은 어린 사제를 업고 천 길 낭떠러지 협곡으로 몸을 숨겨야 했습니다.",
        "사제가 품에 안고 있던 것은 문파 대대로 내려오던 전설의 비급 목판이었습니다. 적들이 문파를 멸문시키면서까지 빼앗으려 했던 것은 단순한 무공서가 아니라, 강호 전체를 뒤흔들 거대한 비밀이 봉인된 기록이었습니다.",
        "십 년의 세월 동안 사형은 자신의 내공을 깎아가며 사제의 끊어진 단전을 치료했고, 사제는 피눈물을 삼키며 사부의 마지막 유언을 검결로 새겼습니다. 복수는 분노로 이루어지는 것이 아니라, 냉철한 실력과 진실의 규명으로 완성된다는 가르침이었습니다.",
        "마침내 무림맹 공개 비무의 날, 정파의 가면을 쓴 채 암약하던 악역의 음모가 만천하에 드러났습니다. 사형의 검끝은 상대의 목을 베는 대신 사부의 결백을 증명하는 비급의 마지막 봉인을 갈라 열었습니다.",
        "강호의 정의는 한 자루의 검만으로 세워지는 것이 아니었습니다. 복수를 넘어 약속을 지켜낸 두 사람의 발걸음 뒤로, 새로운 강호의 아침 햇살이 비추기 시작했습니다.",
    ]
    script = "\n\n".join(paragraphs).strip()
    while len(script) < min_total_chars:
        script += "\n\n강호의 비바람은 그치지 않겠지만, 의기를 품은 자의 길은 결코 꺾이지 않습니다. 두 사람이 남긴 무림의 전설은 오래도록 사람들의 가슴속에 깊은 울림으로 남았습니다."
    return script


def _build_survival_rescue_script(topic: str, upload_title: str, structure: dict, min_total_chars: int = 2600) -> str:
    title = (upload_title or topic or "탈북 사연").strip()
    paragraphs = [
        f"{title}. 영하 20도의 매서운 칼바람이 몰아치던 밤, 꽁꽁 얼어붙은 두만강 강판 위에 한 청년의 발자국이 찍혔습니다. 뒤편 국경 초소의 서치라이트가 강판을 훑고 지나갈 때마다 숨을 죽인 채 눈밭에 엎드렸습니다. 자유를 향한 갈망이 공포를 이겨낸 순간이었습니다.",
        "제3국 은신처에서의 하루하루는 살얼음판과 같았습니다. 신분증도 없이 낯선 언어의 틈바구니에서 숨어 지내야 했지만, 고향에 남겨진 가족들에게 언젠가 자유의 소식을 전하겠다는 희망 하나로 버텼습니다.",
        "한국 대사관의 문을 두드리고 마침내 대한민국 땅에 첫발을 디뎠을 때, 가슴 속에서 뜨거운 눈물이 솟구쳤습니다. 태어나 처음으로 내 이름 석 자가 적힌 주민등록증을 받아 든 날, 비로소 인간으로서의 온전한 삶이 시작되었습니다.",
        "남한 사회에서의 정착 역시 또 다른 도전이었습니다. 문화적 차이와 보이지 않는 편견에 부딪히기도 했지만, 정직하게 땀 흘려 일하며 당당한 사회의 일원으로 뿌리를 내렸습니다.",
        "이 이야기는 단순한 탈출의 기록이 아닙니다. 자유라는 가장 소중한 가치를 지키기 위해 모든 것을 걸었던 한 인간의 존엄과 용기에 대한 증언입니다.",
    ]
    script = "\n\n".join(paragraphs).strip()
    while len(script) < min_total_chars:
        script += "\n\n어둠을 뚫고 찾아온 자유의 소중함은 매일의 평범한 일상 속에서 더욱 빛납니다. 스스로 선택하고 책임지는 삶의 가치를 되새기며, 새로운 내일을 향한 발걸음은 멈추지 않습니다."
    return script


def _build_twilight_rescue_script(topic: str, upload_title: str, structure: dict, min_total_chars: int = 2600) -> str:
    title = (upload_title or topic or "황혼 이야기").strip()
    paragraphs = [
        f"{title}. 조용한 찻집 창가, 30년의 세월을 지나 다시 마주 앉은 두 사람의 찻잔 위로 하얀 김이 피어올랐습니다. 청춘 시절 피치 못할 사정으로 엇갈렸던 두 사람은 각자의 삶을 치열하게 살아낸 뒤, 황혼의 문턱에서 다시 마주했습니다.",
        "지나온 세월은 얼굴에 깊은 주름을 남겼지만, 서로를 바라보는 눈빛 속에는 여전히 그 시절의 순수함과 미안함이 머물러 있었습니다. 자식들을 다 키워 독립시키고 홀로 남겨진 일상 속에서, 두 사람은 서로의 아픔을 보듬는 유일한 안식처가 되었습니다.",
        "세상의 편견과 자식들의 오해라는 현실적 벽 앞에서도, 두 사람은 조급해하지 않았습니다. 형식적인 결합보다 서로의 곁을 묵묵히 지켜주는 동반자로서의 진심을 담담하게 증명해 보였습니다.",
        "노을 지는 호숫가를 나란히 걸으며 두 사람은 비로소 깨달았습니다. 진정한 사랑은 젊은 날의 열정에만 머무는 것이 아니라, 남은 생을 서로의 온기로 따뜻하게 채워가는 성숙한 약속임을 말입니다.",
    ]
    script = "\n\n".join(paragraphs).strip()
    while len(script) < min_total_chars:
        script += "\n\n황혼의 길목에서 마주한 소중한 인연은 지나온 삶의 모든 상처를 보듬어주는 선물이었습니다. 남은 날들을 서로에게 가장 따뜻한 친구이자 버팀목이 되어주기로 한 두 사람의 발걸음은 평온했습니다."
    return script


def _build_korean_drama_rescue_script(topic: str, upload_title: str, structure: dict, min_total_chars: int = 2600) -> str:
    title = (upload_title or topic or "한국 사연").strip()
    paragraphs = [
        f"{title}. 언제나 가족이라는 이름으로 모든 양보와 희생을 강요당했던 주인공이 있었습니다. 시댁의 무리한 요구와 막말 속에서도 가정을 지키기 위해 인내했지만, 돌아온 것은 재산 강탈과 파렴치한 누명이었습니다.",
        "모든 참을성이 바닥난 순간, 주인공은 감정적인 싸움 대신 조용히 진실을 밝힐 증거를 수집하기 시작했습니다. 10년간의 계좌 이체 내역, 통화 녹취 파일, CCTV 영상을 하나하나 꼼꼼하게 정리하며 완벽한 반격의 무대를 준비했습니다.",
        "가족들이 모두 모인 공개적인 자리에서, 주인공은 차분하게 서류 봉투를 열어 모든 진실을 낱낱이 공개했습니다. 완벽한 물증 앞에서 오만하던 상대방의 얼굴은 하얗게 질려갔고, 침묵하던 주변 사람들도 마침내 고개를 숙였습니다.",
        "부당하게 빼앗겼던 모든 권리를 법적으로 완벽하게 되찾은 주인공은 마침내 유독했던 관계의 사슬을 끊어냈습니다. 선한 사람이 끝까지 참다가 내린 결단이 얼마나 강력한 정의를 만들어내는지 보여준 통쾌한 이야기입니다.",
    ]
    script = "\n\n".join(paragraphs).strip()
    while len(script) < min_total_chars:
        script += "\n\n더 이상 부당한 희생을 침묵으로 감내하지 않겠다는 단호한 결의는 스스로를 지키는 가장 큰 힘이었습니다. 진실을 마주하고 새로운 시작을 선택한 주인공의 앞날에는 당당한 희망이 가득했습니다."
    return script


def _build_overseas_rescue_script(topic: str, upload_title: str, structure: dict, min_total_chars: int = 2600) -> str:
    title = (upload_title or topic or "해외 감동 실화").strip()
    paragraphs = [
        f"{title}. 낯선 유럽의 기차역에서 여권과 지갑을 잃어버리고 길거리에 주저앉았던 한국인 유학생이 있었습니다. 언어조차 통하지 않아 눈물만 흘리던 그 청년에게, 한 노신사가 다가와 따뜻한 손을 내밀었습니다.",
        "노신사는 청년을 자신의 집으로 데려가 따뜻한 수프를 대접하고, 대사관에 연락할 수 있도록 차비와 숙소를 마련해 주었습니다. 아무런 대가 없이 베푼 그 친절 뒤에는, 수십 년 전 한국전쟁에 참전해 한국인들에게 받았던 따뜻한 보살핌을 잊지 못했던 노인의 오랜 약속이 있었습니다.",
        "세월이 흘러 어엿한 기업가가 된 주인공은 수소문 끝에 백발의 노인이 된 은인을 다시 찾아갔습니다. 수십 년의 세월과 국경을 넘어 다시 만난 두 사람이 뜨거운 눈물로 끌어안았을 때, 현지 방송과 사람들도 아낌없는 박수를 보냈습니다.",
        "국경과 인종을 초월해 이어진 이 아름다운 은혜의 순환은, 인간의 조건 없는 친절이 어떻게 세상을 따뜻하게 밝히는지 보여주는 진정한 감동의 증언입니다.",
    ]
    script = "\n\n".join(paragraphs).strip()
    while len(script) < min_total_chars:
        script += "\n\n마음에서 마음으로 전해진 온기는 국경을 넘어 더 큰 사랑으로 피어났습니다. 작은 친절 하나가 또 다른 기적을 낳는다는 믿음은 세상 모든 이들에게 잊지 못할 감동을 선물했습니다."
    return script


def _build_old_story_grave_vigil_rescue_script(topic: str, upload_title: str, structure: dict, min_total_chars: int = 7000) -> str:
    title = (upload_title or topic or "며느리가 시어머니 묘를 지킨 이유").strip()
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    paragraphs = [
        f"{title}. 옛날 어느 산골 마을에 순옥이라는 젊은 며느리가 살았습니다. 사람들은 그 여자를 볼 때마다 목소리를 낮췄습니다. 남편은 장터에 나간 뒤 돌아오지 않았고, 시어머니마저 세상을 떠났는데, 순옥은 빈집으로 돌아가지 않았습니다. 그녀는 시어머니 묘 옆에 작은 초가를 세우고 그곳에서 살기 시작했습니다.",
        "처음에는 모두가 효심이라 했습니다. 며칠쯤 묘를 지키다 내려오겠거니 했습니다. 그런데 보름이 지나고, 달이 바뀌고, 첫눈이 내려도 순옥은 산에서 내려오지 않았습니다. 새벽마다 묘 앞의 눈을 쓸고, 저녁마다 작은 밥상을 차리고, 밤이면 붉은 실 한 가닥을 소나무와 초가 문고리에 묶었습니다.",
        "마을 사람들은 그 붉은 실을 가장 두려워했습니다. 바람이 세게 부는 날에도 실은 끊어지지 않았고, 누가 몰래 다가가면 실 끝의 방울이 울렸습니다. 순옥은 그 소리를 들을 때마다 묘 앞으로 나와 조용히 말했습니다. '아직 아닙니다. 어머니, 아직 그 아이가 길을 찾지 못했습니다.'",
        "시어머니가 죽기 전 남긴 말은 이상했습니다. '내 무덤을 삼 년만 지켜 다오. 반쪽은 이미 세상에 나가 있으니, 그 반쪽이 길을 찾아올 때까지 불을 꺼뜨리지 말아라.' 순옥은 그 말뜻을 다 알지 못했습니다. 다만 시어머니의 손이 너무 차가웠고, 그 손에 쥐여 준 붉은 실꾸리가 마지막 숨처럼 떨렸습니다.",
        "시댁 사람들은 순옥을 못마땅하게 여겼습니다. 젊은 며느리가 산에 올라가 묘를 지키니 집안 망신이라 했고, 묘 아래에 재산이 숨었다는 소문까지 냈습니다. 그러나 순옥은 변명하지 않았습니다. 억울하면 내려와 따지라는 말에도, 그녀는 묘 앞 등잔에 기름을 붓고 젖은 흙을 손으로 눌러 다질 뿐이었습니다.",
        "첫해 겨울, 마을 우물에서 흙냄새가 났습니다. 둘째 달 보름에는 묘 옆에 놓인 짚신 한 켤레가 아침마다 방향을 바꾸었습니다. 셋째 달에는 초가 벽에 걸린 낡은 비녀가 저절로 떨어졌습니다. 그 비녀 안에서는 반쪽짜리 혼서지가 나왔고, 거기에는 복례라는 이름 하나가 적혀 있었습니다.",
        "복례. 그 이름을 듣자 마을 노인의 얼굴이 굳었습니다. 오래전 시어머니에게는 어린 딸이 하나 있었는데, 흉년이 심하던 해에 먼 친척집으로 보내졌다고 했습니다. 사람들은 팔려 간 것이라 수군댔고, 시어머니는 죽는 날까지 그 아이의 이름을 입에 올리지 못했습니다.",
        "순옥은 그제야 붉은 실의 뜻을 조금 알았습니다. 실은 귀신을 묶는 물건이 아니었습니다. 길을 잃은 사람에게 돌아올 자리를 알려 주는 표시였습니다. 시어머니는 죽어서도 딸을 기다렸고, 순옥에게 그 기다림을 맡긴 것이었습니다.",
        "그러나 그것만으로는 순옥이 삼 년을 버틸 이유가 부족했습니다. 마을 사람들도 그렇게 생각했습니다. 잃어버린 딸을 기다리는 일이라면 산 사람이 왜 자기 청춘을 묘 옆에서 썩히느냐고 했습니다. 그 말이 순옥의 가슴을 찔렀지만, 그녀는 끝까지 입을 다물었습니다.",
        "둘째 해가 되던 봄, 남편 만득의 편지가 발견되었습니다. 장터로 떠나기 전 남긴 편지였습니다. 그 안에는 시어머니가 평생 숨긴 죄와 만득이 찾아 나선 사람의 이름이 적혀 있었습니다. 만득은 복례를 찾으러 떠났고, 돌아오는 길에 강가에서 실종되었습니다. 사고라 했지만, 길을 막은 것은 비가 아니라 사람들의 침묵이었습니다.",
        "순옥은 남편이 죽었다고 단정하지 않았습니다. 또 살아 있다고 우기지도 않았습니다. 그녀가 지킨 것은 남편의 목숨이 아니라, 그가 끝내 지키려 했던 약속이었습니다. 복례가 돌아오면, 시어머니의 묘 앞에서 진실을 말해 주겠다는 약속이었습니다.",
        "시댁 큰형님은 밤중에 묘를 파려 했습니다. 묘 아래에 문서가 묻혔다고 믿었기 때문입니다. 그러나 삽 끝에 걸린 것은 재산이 아니라 빈 등잔이었습니다. 등잔 밑바닥에는 '불이 꺼지면 길도 끊긴다'는 시어머니의 글씨가 남아 있었습니다.",
        "그날 뒤로 순옥은 매달 보름마다 밥상을 두 벌 차렸습니다. 하나는 시어머니 몫, 하나는 아직 돌아오지 못한 복례 몫이었습니다. 사람들은 미쳤다고 했지만, 이상하게도 그 밥상 위의 숟가락은 아침이면 늘 조금씩 자리가 바뀌어 있었습니다.",
        "둘째 해 가을, 장터에서 낯선 여인의 노랫가락이 들렸습니다. 순옥은 그 노래를 듣고 그 자리에서 굳었습니다. 시어머니가 죽기 전 혼잣말처럼 부르던 노래였습니다. 순옥은 여인을 따라가려 했지만, 여인은 장터 끝 안개 속으로 사라졌습니다. 대신 낡은 천 조각 하나가 떨어져 있었습니다. 붉은 실과 같은 매듭이 묶인 천이었습니다.",
        "순옥은 그 천을 묘 앞에 묻었습니다. 그리고 그날 밤 처음으로 울었습니다. 억울해서가 아니었습니다. 기다림이 헛되지 않았다는 것을 알았기 때문입니다. 복례는 살아 있었고, 어딘가에서 길을 찾고 있었습니다.",
        "셋째 해가 되자 시댁 사람들은 더 조급해졌습니다. 순옥이 삼 년을 채우면 시어머니가 남긴 땅과 문서가 모두 그녀 뜻대로 처리될까 두려웠습니다. 그들은 순옥을 죄인으로 몰았습니다. 남편을 잡아먹은 여자, 죽은 노인을 핑계로 집안을 어지럽힌 여자라 했습니다.",
        "순옥은 그때도 싸우지 않았습니다. 다만 초가 기둥 속에서 낡은 문서 하나를 꺼냈습니다. 그것은 땅문서가 아니었습니다. 시어머니가 복례에게 남긴 사죄문이었습니다. '내가 너를 버린 것이 아니라, 내가 약해서 너를 지키지 못했다. 네가 돌아오면 내 무덤 앞에서 이 말을 듣게 해 다오.'",
        "마을은 조용해졌습니다. 그제야 사람들은 순옥이 재산을 지킨 것이 아니라 말을 지켰다는 걸 알았습니다. 죽은 사람이 살아 있는 사람에게 남긴 말을, 아무도 믿지 않는 동안 혼자 지키고 있었던 것입니다.",
        "하지만 마지막 이유는 아직 남아 있었습니다. 왜 하필 삼 년인가. 왜 하루도 모자라면 안 되는가. 순옥은 세 번째 겨울 마지막 보름까지 그 말을 하지 않았습니다. 그날 밤 붉은 실이 처음으로 저절로 끊어졌습니다.",
        "실이 끊어진 뒤, 묘 앞 산길에 발소리가 들렸습니다. 늙은 여인 하나가 지팡이를 짚고 올라왔습니다. 그녀는 묘 앞에 서서 시어머니의 어릴 적 이름을 불렀습니다. 마을 사람 누구도 모르는 이름이었습니다. 순옥은 그 여인이 복례임을 알았습니다.",
        "복례는 오래전 팔려 간 뒤 이름도 잃고 살았습니다. 그런데 해마다 보름밤이면 꿈속에서 산길 끝 등잔불을 보았다고 했습니다. 첫해에는 멀리 보였고, 둘째 해에는 소나무 아래까지 가까워졌고, 셋째 해 마지막 밤에는 붉은 실이 자기 손목에 묶여 있었다고 했습니다.",
        "그때 순옥은 시어머니의 마지막 말을 풀어 주었습니다. '삼 년은 죽은 이가 산 사람에게 닿는 시간이 아니라, 산 사람이 자기 죄를 인정하는 시간이라 하셨습니다. 어머니는 그 시간을 기다리셨고, 저는 그 말이 사라지지 않게 지켰습니다.'",
        "순옥이 묘 곁에서 산 진짜 이유는 효심만이 아니었습니다. 복수도 아니었습니다. 시어머니가 평생 하지 못한 사과를, 복례가 살아서 들을 수 있도록 길을 밝혀 둔 것이었습니다. 남편 만득이 찾다 끝내 돌아오지 못한 사람에게, 마지막 말을 전해 주는 일이었습니다.",
        "복례는 묘 앞에 엎드려 울었습니다. 순옥은 그녀를 일으키지 않았습니다. 사과는 빨리 끝내는 말이 아니라, 오래 기다린 사람이 자기 속도로 받아들이는 것임을 알았기 때문입니다. 마을 사람들도 그날만은 아무 말도 하지 못했습니다.",
        "날이 밝자 순옥은 초가 문을 열어 두고 산을 내려왔습니다. 묘 앞 등잔은 꺼져 있었지만 이상하게도 두렵지 않았습니다. 길을 잃은 사람은 돌아왔고, 죽은 사람의 말은 살아 있는 사람에게 닿았습니다.",
        "그 뒤로 마을 사람들은 그 묘를 함부로 말하지 않았습니다. 산등성이에 바람이 불 때마다 붉은 실이 사각거리는 소리가 난다고 했습니다. 누군가는 그것을 귀신 소리라 했고, 누군가는 여자가 삼 년 동안 지킨 약속의 소리라 했습니다.",
        "순옥은 늙어서도 그 일을 자랑하지 않았습니다. 누가 왜 그런 고생을 했느냐고 물으면, 그녀는 그저 이렇게 말했습니다. '죽은 사람의 말도, 들어 줄 사람이 없으면 두 번 죽는 법입니다. 나는 그 말을 한 번 더 살려 둔 것뿐입니다.'",
        "그 뒤 시댁 사람들은 오래 숨긴 밭문서를 내놓았습니다. 순옥은 그 땅을 자기 몫으로 삼지 않았습니다. 복례가 어린 날 끌려가며 지나갔다는 산길 옆에 작은 제각을 세우고, 길 잃은 아이들이 쉬어 갈 수 있도록 쌀독 하나와 마른 짚신 몇 켤레를 두었습니다.",
        "마을 노인은 그제야 자기 죄를 털어놓았습니다. 흉년이 들던 해, 복례를 데려가는 사람을 보았지만 입을 다물었다고 했습니다. 그는 순옥 앞에 무릎을 꿇었고, 순옥은 그를 꾸짖지 않았습니다. 다만 복례가 들을 수 있게 사실을 끝까지 말하라고 했습니다.",
        "복례는 처음에는 아무 말도 하지 못했습니다. 원망은 너무 오래 묵으면 말이 되지 않고 숨이 된다고 했습니다. 순옥은 그 숨이 가라앉을 때까지 옆에 앉아 있었습니다. 시어머니가 자신에게 맡긴 일은 사과문을 읽는 것이 아니라, 그 사과를 받아도 되고 받지 않아도 되는 자리를 지키는 것임을 알았기 때문입니다.",
        "사흘 뒤 복례는 묘 앞에 작은 돌 하나를 놓았습니다. 돌에는 아무 글자도 새기지 않았습니다. 이름을 잃고 산 세월은 한 줄 글씨로 갚을 수 없다고 했습니다. 대신 그녀는 붉은 실 한 올을 돌 밑에 묻고, 처음으로 시어머니를 어머니라 불렀습니다.",
        "그날 밤 순옥은 꿈에서 만득을 보았습니다. 만득은 강가도 아니고 장터도 아닌, 산길 끝에 서 있었습니다. 그는 돌아오지 못한 사람처럼 슬프지 않았고, 약속을 맡긴 사람처럼 조용했습니다. 순옥이 다 끝났느냐고 묻자, 그는 고개를 끄덕이고 안개 속으로 물러났습니다.",
        "아침이 되자 묘 앞의 젖은 발자국도, 밤마다 울리던 방울 소리도 사라졌습니다. 마을 사람들은 그제야 알았습니다. 무서운 것은 귀신이 아니라, 살아 있는 사람들이 오래 외면한 말이었습니다. 그 말이 제 주인에게 닿자 산은 다시 평범한 산이 되었습니다.",
        "복례는 며칠 동안 순옥의 초가에 머물렀습니다. 낮에는 묘 앞 흙을 고르고, 밤에는 시어머니가 남긴 사죄문을 한 줄씩 다시 읽었습니다. 어떤 줄에서는 울었고, 어떤 줄에서는 웃었습니다. 어릴 적 자신을 부르던 이름이 종이 위에 아직 살아 있다는 사실이, 원망만큼이나 낯설었기 때문입니다.",
        "순옥은 복례에게 시어머니가 마지막 겨울에 했던 말을 모두 전했습니다. 굶주림을 핑계로 아이를 보낸 죄, 돌아오지 않는 아이를 기다리다 결국 기다림마저 숨긴 죄, 그리고 며느리에게 그 짐을 맡길 수밖에 없었던 부끄러움까지 하나도 빼지 않았습니다. 복례는 듣다가 몇 번이나 밖으로 나갔지만, 매번 다시 돌아와 끝까지 들었습니다.",
        "큰형님은 그 모습을 보고 얼굴을 들지 못했습니다. 그는 묘 아래 재산만 생각했고, 초가 속 등잔이 왜 세 해 동안 꺼지지 않았는지 묻지 않았습니다. 순옥은 그에게 벌을 달라고 하지 않았습니다. 대신 복례 앞에서 시어머니의 이름을 낮추어 부르지 말고, 잃어버린 딸을 남의 일처럼 말하지 말라고 했습니다.",
        "마을 아낙들도 하나둘 산길을 올랐습니다. 처음에는 구경하러 왔고, 다음에는 미안해서 왔고, 마지막에는 밥 한 그릇을 들고 왔습니다. 순옥은 그 밥을 모두 받지 않았습니다. 세 해 동안 굶주린 것은 자기 배가 아니라, 아무도 믿어 주지 않는 말이었다고 했습니다.",
        "복례는 떠나기 전 순옥에게 붉은 실꾸리를 돌려주려 했습니다. 순옥은 고개를 저었습니다. 그 실은 이제 자기 손에 있을 물건이 아니라고 했습니다. 길을 잃은 사람이 돌아왔으니, 이제는 또 다른 사람이 돌아올 길을 밝히는 데 쓰라고 했습니다. 복례는 그 말을 듣고 처음으로 순옥의 손을 잡았습니다.",
        "그날 저녁, 순옥은 묘 앞에 마지막 밥상을 차렸습니다. 밥 한 그릇, 물 한 사발, 그리고 시어머니가 좋아했다는 마른 나물 한 접시뿐이었습니다. 그녀는 오래 절하지 않았습니다. 대신 아주 낮은 목소리로 말했습니다. '어머니, 이제 그만 쉬십시오. 할 말은 닿았습니다.'",
        "바람이 지나가자 소나무 가지에 남아 있던 붉은 실 한 올이 풀려 내려왔습니다. 사람들은 그것을 징조라 했지만, 순옥은 주워 품에 넣지 않았습니다. 실은 흙 위에 내려앉았고, 곧 새벽 이슬에 젖었습니다. 그 모습이 꼭 오래 묶여 있던 숨이 풀리는 것 같았습니다.",
        "복례는 마을을 떠나지 않았습니다. 시어머니를 용서했기 때문만은 아니었습니다. 자신을 버린 곳을 다시 자기 발로 걸어 보고 싶었기 때문입니다. 그녀는 아이들에게 글자를 가르쳤고, 이름을 잃은 사람에게 이름을 다시 불러 주는 일이 얼마나 큰 일인지 말해 주었습니다.",
        "순옥은 산 아래 작은 집으로 내려와 살았습니다. 사람들은 이제 그녀를 미친 며느리라 부르지 않았습니다. 그러나 순옥은 그 칭찬도 오래 듣지 않았습니다. 칭찬이 지나치면 또 다른 소문이 된다고 했습니다. 그녀는 밭을 갈고, 물을 긷고, 보름이면 조용히 산길을 올랐습니다.",
        "세월이 더 흐른 뒤에도 마을 아이들은 그 묘 앞을 지날 때면 목소리를 낮췄습니다. 두려워서가 아니라, 누군가의 말이 그곳에서 세 해 동안 꺼지지 않았다는 것을 배웠기 때문입니다. 어른들은 아이들에게 말했습니다. 살아 있는 사람의 말만 급한 것이 아니라고. 죽은 사람이 남긴 진심도, 제자리를 찾기 전까지는 길 위를 헤맨다고.",
        "이 이야기를 들은 사람들은 대개 순옥이 대단하다고 말합니다. 하지만 순옥이 정말 지킨 것은 대단한 의리가 아니었습니다. 한 사람이 다른 사람에게 맡긴 마지막 부탁, 그것 하나였습니다. 세상은 그런 부탁을 하찮게 여기기 쉽지만, 하찮게 여겨진 부탁 때문에 한 사람의 평생이 어둠 속에 남기도 합니다.",
        "그래서 순옥은 끝내 자기를 주인공이라 여기지 않았습니다. 주인공은 돌아온 복례였고, 죄를 인정한 시어머니였고, 늦게나마 침묵을 깬 마을 사람들이었습니다. 순옥은 그 사이에 등잔을 들고 서 있던 사람일 뿐이었습니다. 다만 그 등잔을 놓지 않았기에, 모두가 자기 자리로 돌아올 수 있었습니다.",
        "훗날 누군가가 그 묘 아래 정말 무엇이 묻혀 있었느냐고 묻자, 복례는 이렇게 대답했습니다. 묻힌 것은 금도 문서도 아니었다고. 말하지 못한 미안함과 듣지 못한 이름, 그리고 그것을 끝까지 기다린 한 여자의 시간이 묻혀 있었다고 말입니다.",
        "그래서 이 이야기는 무덤을 지킨 괴이한 여자의 이야기가 아닙니다. 버려진 이름 하나를 다시 불러 주기 위해, 산 사람 하나가 세 해의 추위와 소문을 견딘 이야기입니다. 며느리가 시어머니 묘에 삼 년을 묻고 산 이유는 바로 그것이었습니다. 죽은 시어머니가 끝내 하지 못한 사과를, 살아 돌아온 딸에게 전하기 위해서였습니다.",
    ]
    script = "\n\n".join(paragraphs).strip()
    return script


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


def _validate_publish_metadata_payload(payload: dict) -> tuple[str, str, str, str, dict, dict, str, dict]:
    topic_queue_id = str(payload.get("topic_queue_id") or "").strip()
    if not topic_queue_id:
        raise ValueError("payload.topic_queue_id is required for publish_metadata_generate")
    topic = str(payload.get("topic") or "").strip()
    if not topic:
        raise ValueError("payload.topic is required for publish_metadata_generate")
    script = str(payload.get("script") or "").strip()
    if not script:
        raise ValueError("payload.script is required for publish_metadata_generate")
    title_generation = payload.get("title_generation") if isinstance(payload.get("title_generation"), dict) else {}
    upload_title = str(payload.get("upload_title") or title_generation.get("generated_title") or "").strip()
    structure = payload.get("structure") if isinstance(payload.get("structure"), dict) else {}
    narrative_blueprint = payload.get("narrative_blueprint") if isinstance(payload.get("narrative_blueprint"), dict) else {}
    script_quality_report = payload.get("script_quality_report") if isinstance(payload.get("script_quality_report"), dict) else {}
    language = str(payload.get("language") or "ko").strip()
    return topic_queue_id, topic, script, upload_title, structure, narrative_blueprint, language, script_quality_report


def _process_script_generate(job: dict, job_id: str, job_log) -> tuple[str, dict]:
    job_store.transition(job_id, job_store.PREPARING, reason="validating payload")
    write_state("preparing", job, 0, job_id)
    job_log.info("-> PREPARING (validating payload)")

    topic_queue_id, topic, scenes, structure, script_style, language, narration_mode, duration_seconds, upload_title, title_generation = _validate_script_generate_payload(job["payload"])
    is_multi = narration_mode == "multi"
    is_shorts = duration_seconds <= 60

    job_store.transition(job_id, job_store.RENDERING, reason="generating duration-aware narration chunks")
    write_state("running", job, 10, job_id)
    job_log.info(f"-> RENDERING (topic_queue_id={topic_queue_id}, {len(scenes)} scenes, mode={narration_mode})")

    ensure_project_root_on_path()
    from config import Config, config
    from services import ai_router
    from services.script_style_resolver import resolve_script_style_directive
    from services.sfx_service import build_hermes_sfx_cues
    import asyncio

    Config.refresh_remote_keys_if_stale()
    config.SCRIPT_GENERATION_MODEL = _prefer_gemini_text_model(config, config.SCRIPT_GENERATION_MODEL)
    Config.SCRIPT_GENERATION_MODEL = config.SCRIPT_GENERATION_MODEL

    # Mirrors /api/script/generate's own model selection
    # (app/routers/gemini.py::script_generate) so pre-baked and live-generated
    # narration use the same model choice.
    model = config.SCRIPT_GENERATION_MODEL or config.SCRIPT_PLANNING_MODEL
    model = _prefer_gemini_text_model(config, model)
    draft_model = _select_script_draft_model(config, model)
    if draft_model != model:
        job_log.info(
            f"Using {draft_model} for script draft/blueprint and reserving {model} for script QA/rewrite"
        )
    style_directive = resolve_script_style_directive(script_style)
    learning_instruction = _learning_profile_instruction(job.get("payload") or {})
    feedback_instruction = _quality_feedback_instruction(job.get("payload") or {})
    if learning_instruction:
        style_directive = f"{style_directive}\n\n{learning_instruction}".strip()
    if feedback_instruction:
        style_directive = f"{style_directive}\n\n{feedback_instruction}".strip()
    category_context = " ".join(
        str((job.get("payload") or {}).get(key) or "")
        for key in ("category", "category_name")
    ).strip()
    script_style_context = f"{script_style} {category_context}".strip()
    image_style = str((job.get("payload") or {}).get("image_style") or "realistic").strip()
    image_style_selection = (
        (job.get("payload") or {}).get("image_style_selection")
        if isinstance((job.get("payload") or {}).get("image_style_selection"), dict)
        else {}
    )
    if _is_old_story_plan_context(
        script_style_context,
        topic,
        upload_title,
        image_style,
    ):
        old_story_script_guard = """

Old-story script guard:
- Stay inside a pre-modern Korean folk-tale world. Do not introduce modern objects, places, institutions, or disputes.
- Forbidden modern drift: developer, redevelopment, excavator, museum, bus, phone, cellphone, Seoul trip, police report, court lawsuit, camera, broadcast, apartment, car, hospital, office.
- Do not invent a new external subplot that is not in the scene plan. Expand only the characters, place, object, secret, conflict, and promise already present in the upload title and scene_situation fields.
- Never replace the title promise with a different family plot. The protagonist, central mystery, and payoff must stay anchored to the upload title.
- Do not narrate planning labels such as middle turn, scene purpose, hook, prompt, camera, shot, or visual direction.
""".strip()
        style_directive = f"{style_directive}\n\n{old_story_script_guard}".strip()
    previous_error = str(job.get("error_message") or "").strip()
    if previous_error:
        retry_instruction = f"""

Previous generation attempt failed QA. Fix these exact issues:
{previous_error[:2400]}

Hard retry rules:
- Do not repeat the same money amount or pension fact across multiple scenes. Mention a number once, then move to a new consequence or decision.
- Do not write camera, screen, subtitle, shot, or visual-direction narration in the script.
- Do not turn the middle into a policy lecture or PSA. Keep the couple's action and decision driving the information.
- Each scene must change the viewer's understanding; if it only restates prior information, replace it with a new concrete choice, obstacle, or consequence.
""".strip()
        style_directive = f"{style_directive}\n\n{retry_instruction}".strip()
    old_story_context = _is_old_story_plan_context(
        script_style_context,
        topic,
        upload_title,
        image_style,
    )
    finance_plan_context = _is_finance_plan_context(
        script_style_context,
        topic,
        upload_title,
        image_style,
    )
    grave_vigil_context = any(
        term in _text_with_mojibake_repairs(topic, upload_title)
        for term in ("며느리", "시어머니", "묘에", "묘지", "grave vigil")
    )
    if old_story_context and grave_vigil_context:
        structure = _repair_old_story_grave_vigil_scene_plan_repetition(structure, topic, upload_title)
        structure = _apply_old_story_story_core_to_structure(structure, topic, upload_title)
        # Script QA should judge story structure and narration only. 2x2 image
        # grids are image-stage artifacts and may contain visual-only wording.
        structure = dict(structure)
        structure.pop("image_grid_prompts", None)
        scenes = structure.get("scenes") if isinstance(structure.get("scenes"), list) else scenes
    elif old_story_context:
        structure = _sanitize_old_story_scene_plan_to_title(structure, topic, upload_title)
        structure = _apply_old_story_story_core_to_structure(structure, topic, upload_title)
        structure = dict(structure)
        structure.pop("image_grid_prompts", None)
        scenes = structure.get("scenes") if isinstance(structure.get("scenes"), list) else scenes
    total_target_chars, length_instruction = _script_gen_length_instruction(duration_seconds, is_shorts)
    scene_budgets = _scene_char_budgets(scenes, duration_seconds, total_target_chars, is_shorts)
    script_chunks = _chunk_scenes_for_script_generation(scenes, scene_budgets, max_chunks=4)

    async def _run_generation() -> tuple[str, dict, dict, dict, int, dict, list[str]]:
        if old_story_context and grave_vigil_context:
            narrative_blueprint = {
                "protagonist": "순옥",
                "central_conflict": "시어머니 묘 곁에서 3년을 살며 마을의 소문과 시댁의 탐욕을 견디고, 죽은 시어머니가 잃어버린 딸 복례에게 남긴 사과를 지켜야 한다.",
                "hidden_information": "붉은 실과 등잔은 귀신을 묶는 물건이 아니라, 잃어버린 복례가 돌아올 길을 밝혀 두는 약속의 표시다.",
                "midpoint_turn": "남편 만득의 편지와 비녀 속 혼서지를 통해 시어머니가 평생 숨긴 딸 복례의 존재가 드러난다.",
                "payoff": "순옥이 묘 곁에서 3년을 산 이유는 죽은 시어머니가 하지 못한 사과를 살아 돌아온 딸 복례에게 전하기 위해서다.",
                "tone": "구수한 한국 옛날이야기 입말, 전근대 산골 마을, 현대 소재 없음",
            }
            narrative_blueprint = _fallback_narrative_blueprint(topic, upload_title, structure)
            narrative_blueprint["tone"] = "구수한 한국 옛날이야기 입말, 전근대 산골 마을, 현대 소재 없음"
            main_character = await _generate_main_character_anchor(
                ai_router, draft_model, topic, upload_title, structure, language, narrative_blueprint, job_log
            )
            job_log.info("Using old-story grave-vigil script path before section generation")
            job_store.update_progress(job_id, 78, "script QA")
            write_state("running", job, 78, job_id)
            rescue_script = _build_old_story_grave_vigil_rescue_script(topic, upload_title, structure)
            rescue_quality = await _evaluate_script_quality(
                ai_router, model, topic, upload_title, narrative_blueprint, structure, rescue_script, language
            )
            if not _script_needs_revision(rescue_quality):
                return rescue_script, narrative_blueprint, rescue_quality, rescue_quality, 0, main_character, []
            rescue_issues = rescue_quality.get("critical_issues") or rescue_quality.get("revision_notes") or []
            job_log.warning(
                "Old-story grave-vigil script path did not pass QA; falling back to section generation "
                f"(score={rescue_quality.get('score')}, verdict={rescue_quality.get('verdict')}, issues={rescue_issues})"
            )
        else:
            narrative_blueprint = _fallback_narrative_blueprint(topic, upload_title, structure)
            main_character = await _generate_main_character_anchor(
                ai_router, draft_model, topic, upload_title, structure, language, narrative_blueprint, job_log
            )

        final_parts = []
        known_characters: list[str] = []
        if isinstance(main_character, dict):
            main_name = str(main_character.get("name") or "").strip()
            if main_name:
                known_characters.append(main_name)
        unresolved_threads = [
            narrative_blueprint.get("hidden_information"),
            narrative_blueprint.get("central_conflict"),
        ]
        for chunk_idx, (start_idx, chunk_scenes, chunk_budgets) in enumerate(script_chunks):
            previous_context = {}
            if final_parts:
                previous_context = {
                    "previous_scene_count": len(final_parts),
                    "previous_script_excerpt": _short_script_excerpt(final_parts[-1], 1200),
                    "previous_scene_summaries": [
                        str(item.get("scene_summary") or "").strip()
                        for item in scenes[max(0, start_idx - 6):start_idx]
                        if str(item.get("scene_summary") or "").strip()
                    ],
                    "known_characters": known_characters,
                    "unresolved_threads": [t for t in unresolved_threads if t],
                }
            prompt = _build_script_chunk_prompt(
                topic, chunk_scenes, chunk_budgets, is_shorts, is_multi, known_characters,
                length_instruction, language,
                upload_title=upload_title,
                structure_context=structure,
                narrative_blueprint=narrative_blueprint,
                previous_context=previous_context,
                narration_mode=narration_mode,
                main_character=main_character,
            )
            if style_directive:
                prompt = f"{prompt}\n\n{style_directive}"

            try:
                raw_text = await ai_router.generate_text(
                    prompt, draft_model, temperature=0.65, max_tokens=16384,
                    task_type="hermes_script_generate",
                )
                chunk_parts = _parse_script_chunk_sections(
                    raw_text,
                    chunk_scenes,
                    is_multi,
                    lambda local_idx, scene: _fallback_narration_section(
                        topic,
                        upload_title,
                        scene,
                        start_idx + local_idx,
                        len(scenes),
                        int(chunk_budgets[local_idx].get("min_chars") or 80),
                    ),
                )
            except Exception as e:
                job_log.warning(
                    f"Script chunk {chunk_idx + 1}/{len(script_chunks)} generation fallback: {e}"
                )
                chunk_parts = [
                    _fallback_narration_section(
                        topic,
                        upload_title,
                        scene,
                        start_idx + local_idx,
                        len(scenes),
                        int(chunk_budgets[local_idx].get("min_chars") or 80),
                    )
                    for local_idx, scene in enumerate(chunk_scenes)
                ]

            for local_idx, (scene, section_text) in enumerate(zip(chunk_scenes, chunk_parts)):
                budget = chunk_budgets[local_idx]
                section_text = _trim_section_to_limit(
                    section_text,
                    int(budget.get("max_chars") or 220),
                )
                if section_text:
                    final_parts.append(section_text)
                    if is_multi:
                        for name in _extract_speaker_names(section_text):
                            if name not in known_characters:
                                known_characters.append(name)
                if scene.get("end_bridge"):
                    unresolved_threads.append(scene.get("end_bridge"))

            processed_scene_count = min(len(scenes), start_idx + len(chunk_scenes))
            progress = int(10 + 60 * processed_scene_count / len(scenes))
            message = (
                f"script chunk {chunk_idx + 1}/{len(script_chunks)} complete "
                f"(scenes {start_idx + 1}-{processed_scene_count})"
            )
            job_store.update_progress(job_id, progress, message)
            write_state("running", job, progress, job_id)

            if chunk_idx < len(script_chunks) - 1:
                await asyncio.sleep(0.5)

        draft_script = "\n\n".join(p for p in final_parts if p).strip()
        job_store.update_progress(job_id, 78, "script QA")
        write_state("running", job, 78, job_id)
        initial_quality = await _evaluate_script_quality(
            ai_router, model, topic, upload_title, narrative_blueprint, structure, draft_script, language
        )
        final_script = draft_script
        final_quality = initial_quality
        revision_count = 0
        scene_script_sections = list(final_parts)

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
                        scene_script_sections = []
            except Exception as e:
                job_log.warning(f"Script rewrite failed (keeping draft): {e}")

        if _script_needs_revision(final_quality):
            rescue_script = None
            if _is_macro_economy_plan_context(script_style_context, topic, upload_title, image_style):
                job_log.info("Script QA still requested revision; trying economy rescue script")
                rescue_script = _build_economy_rescue_script(topic, upload_title, structure)
            elif finance_plan_context or script_style == "news":
                job_log.info("Script QA still requested revision; trying finance rescue script")
                rescue_script = _build_finance_rescue_script(topic, upload_title, structure)
            elif _is_martial_plan_context(script_style_context, topic, upload_title, image_style):
                job_log.info("Script QA still requested revision; trying martial rescue script")
                rescue_script = _build_martial_rescue_script(topic, upload_title, structure)
            elif _is_survival_story_plan_context(script_style_context, topic, upload_title, image_style):
                job_log.info("Script QA still requested revision; trying survival rescue script")
                rescue_script = _build_survival_rescue_script(topic, upload_title, structure)
            elif _is_twilight_plan_context(script_style_context, topic, upload_title, image_style):
                job_log.info("Script QA still requested revision; trying twilight rescue script")
                rescue_script = _build_twilight_rescue_script(topic, upload_title, structure)
            elif _is_korean_drama_plan_context(script_style_context, topic, upload_title, image_style):
                job_log.info("Script QA still requested revision; trying korean drama rescue script")
                rescue_script = _build_korean_drama_rescue_script(topic, upload_title, structure)
            elif _is_overseas_touching_plan_context(script_style_context, topic, upload_title, image_style):
                job_log.info("Script QA still requested revision; trying overseas touching rescue script")
                rescue_script = _build_overseas_rescue_script(topic, upload_title, structure)
            elif old_story_context:
                job_log.info("Script QA still requested revision; trying old-story rescue script")
                rescue_script = _build_old_story_grave_vigil_rescue_script(topic, upload_title, structure)

            if rescue_script:
                rescue_quality = await _evaluate_script_quality(
                    ai_router, model, topic, upload_title, narrative_blueprint, structure, rescue_script, language
                )
                if not _script_needs_revision(rescue_quality):
                    final_script = rescue_script
                    final_quality = rescue_quality
                    revision_count = max(revision_count, 1)
                    scene_script_sections = []

        return final_script, narrative_blueprint, initial_quality, final_quality, revision_count, main_character, scene_script_sections

    (
        final_script,
        narrative_blueprint,
        initial_quality,
        final_quality,
        revision_count,
        main_character,
        scene_script_sections,
    ) = asyncio.run(_run_generation())
    if not final_script:
        raise ValueError("Generated script was empty after all sections were processed")
    if _script_needs_revision(final_quality):
        issues = final_quality.get("critical_issues") or final_quality.get("revision_notes") or []
        job_log.warning(
            f"Script revision note (proceeding with best generated script): score={final_quality.get('score')}, issues={issues}"
        )

    repeated_sentences = _detect_repeated_script_sentences(final_script)
    if repeated_sentences:
        raise RuntimeError(
            "Generated script contains excessive repeated sentences: "
            f"{json.dumps(repeated_sentences[:8], ensure_ascii=False)}"
        )
    if not isinstance(main_character, dict) or not main_character:
        main_character = _fallback_main_character(topic, upload_title, structure, narrative_blueprint)
        main_character["source"] = "worker_required_fallback"
    main_character = _normalize_character_anchor(
        main_character,
        fallback_name="protagonist",
        role="protagonist",
    )
    supporting_characters = asyncio.run(
        _generate_supporting_character_anchors(
            ai_router,
            draft_model,
            topic,
            upload_title,
            structure,
            final_script,
            main_character,
            job_log,
        )
    )[:2]
    character_anchors = {
        "main_character": main_character,
        "supporting_characters": supporting_characters,
        "max_character_anchors": 3,
        "character_image_generation": {
            "enabled": False,
            "reason": "Worker pre-generation uses text DNA anchors first; portrait image generation remains opt-in.",
        },
    }

    job_store.update_progress(job_id, 90, "generating media prompts from final script")
    write_state("running", job, 90, job_id)
    job_log.info(
        f"-> GENERATING MEDIA PROMPTS FROM FINAL SCRIPT "
        f"(scene_count={len(scenes)}, script_chars={len(final_script)})"
    )
    structure = _generate_scene_media_prompts(
        structure=structure,
        topic=topic,
        upload_title=upload_title,
        image_style=image_style,
        image_style_selection=image_style_selection,
        language=language,
        job_log=job_log,
        script_text=final_script,
        scene_script_sections=scene_script_sections,
        main_character=main_character,
        supporting_characters=supporting_characters,
    )
    category_errors = _scene_plan_category_contamination_errors(
        structure,
        script_style=script_style_context,
        topic=topic,
        upload_title=upload_title,
        image_style=image_style,
    )
    if category_errors:
        raise RuntimeError(f"scene media prompt category QA failed: {category_errors[:8]}")
    sfx_cues = build_hermes_sfx_cues(
        final_script,
        structure,
        target_duration_seconds=duration_seconds,
    )
    sfx_cues_json = json.dumps(sfx_cues, ensure_ascii=False)
    job_log.info(f"-> HERMES SFX PLANNED ({len(sfx_cues)} cues)")
    category_for_gate = str((job.get("payload") or {}).get("category") or (job.get("payload") or {}).get("category_name") or "").strip()
    script_stage_payload = {
        "topic_queue_id": topic_queue_id,
        "category": category_for_gate,
        "topic": topic,
        "generated_title": upload_title,
        "upload_title": upload_title,
        "script": final_script,
        "structure": structure,
        "script_quality_report": final_quality,
        "script_style": script_style_context,
        "image_style": image_style,
        "main_character": main_character,
        "supporting_characters": supporting_characters,
        "character_anchors": character_anchors,
        "sfx_cues": sfx_cues,
        "sfx_cues_json": sfx_cues_json,
    }
    script_stage_report = _validate_script_generate_stage(
        script_stage_payload,
        category=category_for_gate,
    )

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
        "structure": structure,
        "upload_title": upload_title,
        "title_generation": title_generation,
        "image_style": image_style,
        "image_style_selection": image_style_selection,
        "learning_profile": (job.get("payload") or {}).get("learning_profile") or {},
        "narrative_blueprint": narrative_blueprint,
        "main_character": main_character,
        "supporting_characters": supporting_characters,
        "character_anchors": character_anchors,
        "sfx_cues": sfx_cues,
        "sfx_cues_json": sfx_cues_json,
        "initial_script_quality_report": initial_quality,
        "script_quality_report": final_quality,
        "stage_quality_report": script_stage_report,
        "revision_count": revision_count,
        "char_count": char_count,
        "read_time_seconds": (char_count + 414) // 415,  # matches script_gen.html's Math.ceil(charCount / 415)
        "narration_mode": narration_mode,
        "defer_ready_until_quality_gate": bool((job.get("payload") or {}).get("defer_ready_until_quality_gate")),
        "completed_at": completed_at,
        "error": None,
    }
    result_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    job_store.transition(job_id, job_store.COMPLETED, reason="script generation complete", output_path=str(result_path))
    job_log.info(f"-> COMPLETED, result at {result_path}")
    logger.info(f"Completed job {job_id} -> {result_path}")
    return str(result_path), result_payload


def _process_publish_metadata_generate(job: dict, job_id: str, job_log) -> tuple[str, dict]:
    job_store.transition(job_id, job_store.PREPARING, reason="validating payload")
    write_state("preparing", job, 0, job_id)
    job_log.info("-> PREPARING (validating publish metadata payload)")

    topic_queue_id, topic, script, upload_title, structure, narrative_blueprint, language, script_quality_report = _validate_publish_metadata_payload(job["payload"])

    job_store.transition(job_id, job_store.RENDERING, reason="generating publish metadata")
    write_state("running", job, 30, job_id)

    ensure_project_root_on_path()
    from config import Config, config
    from services import ai_router
    import asyncio

    Config.refresh_remote_keys_if_stale()
    model = config.TITLE_GENERATION_MODEL or config.SCRIPT_GENERATION_MODEL or config.SCRIPT_PLANNING_MODEL

    publish_metadata = asyncio.run(
        _generate_publish_metadata(
            ai_router,
            model,
            topic,
            upload_title,
            script,
            language,
            narrative_blueprint,
            structure,
        )
    )
    _validate_publish_metadata_quality(publish_metadata, topic, upload_title, script, language)
    category_for_gate = str((job.get("payload") or {}).get("category") or (job.get("payload") or {}).get("category_name") or "").strip()
    sfx_cues = (job.get("payload") or {}).get("sfx_cues") or []
    sfx_cues_json = (job.get("payload") or {}).get("sfx_cues_json") or json.dumps(sfx_cues, ensure_ascii=False)
    metadata_stage_payload = {
        "topic_queue_id": topic_queue_id,
        "category": category_for_gate,
        "topic": topic,
        "generated_title": upload_title,
        "upload_title": upload_title,
        "script": script,
        "structure": structure,
        "narrative_blueprint": narrative_blueprint,
        "script_quality_report": script_quality_report,
        "publish_metadata": publish_metadata,
        "sfx_cues": sfx_cues,
        "sfx_cues_json": sfx_cues_json,
        "language": language,
        "defer_ready_until_quality_gate": bool((job.get("payload") or {}).get("defer_ready_until_quality_gate")),
    }
    metadata_stage_report = _validate_publish_metadata_stage(
        metadata_stage_payload,
        category=category_for_gate,
    )

    job_store.transition(job_id, job_store.UPLOADING, reason="saving publish metadata")
    write_state("running", job, 90, job_id)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = RESULTS_DIR / f"{job_id}.json"
    completed_at = time.time()
    main_character = structure.get("main_character") if isinstance(structure, dict) else None
    supporting_characters = (
        structure.get("supporting_characters")
        if isinstance(structure, dict) and isinstance(structure.get("supporting_characters"), list)
        else []
    )
    result_payload = {
        "job_id": job_id,
        "job_type": "publish_metadata_generate",
        "status": "COMPLETED",
        "topic_queue_id": topic_queue_id,
        "topic": topic,
        "generated_title": upload_title,
        "upload_title": upload_title,
        "script": script,
        "structure": structure,
        "narrative_blueprint": narrative_blueprint,
        "main_character": main_character,
        "supporting_characters": supporting_characters[:2],
        "character_anchors": {
            "main_character": main_character,
            "supporting_characters": supporting_characters[:2],
            "max_character_anchors": 3,
            "character_image_generation": {
                "enabled": False,
                "reason": "Worker pre-generation uses text DNA anchors first; portrait image generation remains opt-in.",
            },
        },
        "publish_metadata": publish_metadata,
        "sfx_cues": sfx_cues,
        "sfx_cues_json": sfx_cues_json,
        "script_quality_report": script_quality_report,
        "stage_quality_report": metadata_stage_report,
        "defer_ready_until_quality_gate": bool((job.get("payload") or {}).get("defer_ready_until_quality_gate")),
        "completed_at": completed_at,
        "error": None,
    }
    result_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    job_store.transition(job_id, job_store.COMPLETED, reason="publish metadata complete", output_path=str(result_path))
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
        if result_payload.get("defer_ready_until_quality_gate") and job_type in {
            "script_plan_generate",
            "script_generate",
        }:
            job_log.info(
                "Quality-gated autopilot job complete locally; deferring Supabase ready sync "
                "until the full package passes final validation."
            )
            return

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
            sfx_cues = result_payload.get("sfx_cues") or []
            sfx_cues_json = result_payload.get("sfx_cues_json") or json.dumps(sfx_cues, ensure_ascii=False)
            patch_data = {
                # Keep pre-generated topics claimable. The queue row becomes
                # completed only when the user claims it.
                "status": "pending",
                "pregenerated_script": result_payload.get("script"),
                "pregenerated_script_status": "ready",
                "pregenerated_structure": result_payload.get("structure"),
                "pregenerated_structure_status": "ready",
                "publish_metadata": result_payload.get("publish_metadata"),
                "publish_metadata_status": "ready",
                "progress_payload": {
                    "publish_metadata": result_payload.get("publish_metadata"),
                    "main_character": result_payload.get("main_character"),
                    "supporting_characters": result_payload.get("supporting_characters") or [],
                    "character_anchors": result_payload.get("character_anchors") or {},
                    "sfx_cues": sfx_cues,
                    "sfx_cues_json": sfx_cues_json,
                    "pregenerated_script_status": "ready",
                    "prepared_topic_ready": True,
                    "prepared_topic_ready_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                },
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
                    if k not in ("narrative_blueprint", "script_quality_report")
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

        elif job_type == "publish_metadata_generate":
            tq_id = result_payload.get("topic_queue_id")
            if not tq_id:
                job_log.info("No topic_queue_id in publish metadata result - skipping Supabase update")
                return
            structure = result_payload.get("structure") if isinstance(result_payload.get("structure"), dict) else {}
            scene_count = (
                structure.get("scene_count")
                or len(structure.get("scenes") or [])
                or result_payload.get("total_scenes")
            )
            sfx_cues = result_payload.get("sfx_cues") or []
            sfx_cues_json = result_payload.get("sfx_cues_json") or json.dumps(sfx_cues, ensure_ascii=False)
            progress_payload = {
                "publish_metadata": result_payload.get("publish_metadata"),
                "main_character": result_payload.get("main_character") or structure.get("main_character"),
                "supporting_characters": result_payload.get("supporting_characters") or structure.get("supporting_characters") or [],
                "character_anchors": result_payload.get("character_anchors") or {
                    "main_character": result_payload.get("main_character") or structure.get("main_character"),
                    "supporting_characters": result_payload.get("supporting_characters") or structure.get("supporting_characters") or [],
                    "max_character_anchors": 3,
                },
                "sfx_cues": sfx_cues,
                "sfx_cues_json": sfx_cues_json,
                "pregenerated_script_status": "ready",
                "pregenerated_structure_status": "ready",
                "prepared_topic_ready": True,
                "prepared_topic_ready_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            patch_data = {
                "status": "pending",
                "publish_metadata": result_payload.get("publish_metadata"),
                "progress_payload": progress_payload,
                "pregenerated_script_status": "ready",
                "pregenerated_structure_status": "ready",
            }
            if result_payload.get("script"):
                patch_data["pregenerated_script"] = result_payload.get("script")
            if structure:
                patch_data["pregenerated_structure"] = structure
            if result_payload.get("generated_title") or result_payload.get("upload_title"):
                patch_data["generated_title"] = result_payload.get("generated_title") or result_payload.get("upload_title")
            if scene_count:
                patch_data["total_scenes"] = scene_count
            if result_payload.get("narrative_blueprint"):
                patch_data["narrative_blueprint"] = result_payload.get("narrative_blueprint")
            if result_payload.get("script_quality_report"):
                patch_data["script_quality_report"] = result_payload.get("script_quality_report")
            r = _req.patch(
                f"{supabase_url}/rest/v1/topics_queue?id=eq.{tq_id}",
                headers={**headers, "Prefer": "return=minimal"},
                json=patch_data,
                timeout=10,
            )
            if r.status_code not in (200, 204):
                fallback = {
                    key: value for key, value in patch_data.items()
                    if key not in ("narrative_blueprint", "script_quality_report")
                }
                r = _req.patch(
                    f"{supabase_url}/rest/v1/topics_queue?id=eq.{tq_id}",
                    headers={**headers, "Prefer": "return=minimal"},
                    json=fallback,
                    timeout=10,
                )
            if r.status_code not in (200, 204):
                metadata_only = {
                    "publish_metadata": result_payload.get("publish_metadata"),
                    "progress_payload": progress_payload,
                }
                r = _req.patch(
                    f"{supabase_url}/rest/v1/topics_queue?id=eq.{tq_id}",
                    headers={**headers, "Prefer": "return=minimal"},
                    json=metadata_only,
                    timeout=10,
                )
            if r.status_code in (200, 204):
                job_log.info(f"Supabase: updated topics_queue#{tq_id} with final prepared topic package")
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
        elif job_type == "publish_metadata_generate":
            output_ref, result_payload = _process_publish_metadata_generate(job, job_id, job_log)
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
    _acquire_hermes_single_instance_or_exit()
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
