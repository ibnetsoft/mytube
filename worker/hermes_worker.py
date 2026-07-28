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
Same scope limit as topic_research above: no central Supabase upload yet,
result is written to the same local RESULTS_DIR only (see
docs/AIR_0230_HERMES_BENCHMARK_WORKER_ARCHITECTURE.md §2a/§4 for the
follow-up that adds central upload + the web-admin trigger).
"""
import json
import os
import re
import signal
import sys
import time
from pathlib import Path

import job_store
from logging_setup import get_job_logger, get_logger
from shutdown_flag import clear_shutdown_flag, is_shutdown_requested
from worker_config import OUTPUT_DIR, STATE_DIR, ensure_project_root_on_path

STATE_FILE = STATE_DIR / "hermes_worker.json"
PAUSE_FLAG_FILE = STATE_DIR / "hermes_worker.pause"
RESULTS_DIR = OUTPUT_DIR / "hermes_results"
logger = get_logger("hermes_worker")

_shutdown_requested = False
SUPPORTED_JOB_TYPES = ["topic_research", "topic_benchmark_analyze"]
DEFAULT_COUNT = 10
MAX_COUNT = 30

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
                "last_error": last_error if last_error is not None else prev.get("last_error"),
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
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, re.DOTALL)
    if fence:
        stripped = fence.group(1)
    else:
        brace = re.search(r"\{.*\}", stripped, re.DOTALL)
        if brace:
            stripped = brace.group(0)
    return json.loads(stripped)


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

    return keyword, language, video_type, max_candidates, search_pool_size


async def _youtube_get(path: str, params: dict) -> dict:
    """Same request shape as app/routers/youtube.py's endpoints, called
    directly here rather than through FastAPI (this process has no HTTP
    server of its own for the desktop app's routes, and importing FastAPI
    route handlers as plain functions isn't a supported pattern in that
    router - see its Request-bound signatures)."""
    import httpx
    from config import config

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{config.YOUTUBE_BASE_URL}/{path}",
            params={**params, "key": config.YOUTUBE_API_KEY},
        )
        data = response.json()
        if response.status_code != 200:
            error_message = (data.get("error") or {}).get("message", "YouTube API Error")
            raise RuntimeError(f"YouTube API error ({path}): {error_message}")
        return data


async def _search_candidate_videos(keyword: str, language: str, video_type: str, max_results: int) -> list[dict]:
    params = {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "maxResults": max_results,
        "order": "viewCount",
        "relevanceLanguage": language,
    }
    if video_type == "shorts":
        params["videoDuration"] = "short"
    else:
        params["videoDuration"] = "medium"

    data = await _youtube_get("search", params)
    candidates = []
    for item in data.get("items", []):
        video_id = (item.get("id") or {}).get("videoId")
        channel_id = (item.get("snippet") or {}).get("channelId")
        if not video_id or not channel_id:
            continue
        candidates.append({
            "video_id": video_id,
            "channel_id": channel_id,
            "title": item["snippet"].get("title", ""),
            "channel_title": item["snippet"].get("channelTitle", ""),
        })
    return candidates


async def _fetch_video_and_channel_stats(candidates: list[dict]) -> list[dict]:
    """Adds view_count/subscriber_count/performance_ratio to each candidate.
    performance_ratio mirrors the "성과도(구독자 대비 조회수)" the desktop
    app's topic.html computes client-side only (never sent to a server) -
    here it's the actual ranking signal, not just a display column."""
    if not candidates:
        return []

    video_ids = ",".join(c["video_id"] for c in candidates)
    channel_ids = ",".join(sorted({c["channel_id"] for c in candidates}))

    videos_data = await _youtube_get("videos", {"part": "statistics", "id": video_ids})
    channels_data = await _youtube_get("channels", {"part": "statistics", "id": channel_ids})

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
    return enriched


async def _fetch_comments(video_id: str, max_results: int = DEFAULT_COMMENT_SAMPLE_SIZE) -> list[str]:
    """Best-effort: comments can be disabled on a video - that should not
    fail the whole job (analyze_comments() already handles an empty list;
    it just leans more on the transcript)."""
    try:
        data = await _youtube_get(
            "commentThreads",
            {"part": "snippet", "videoId": video_id, "maxResults": max_results, "order": "relevance"},
        )
    except Exception:
        return []

    comments = []
    for item in data.get("items", []):
        text = ((item.get("snippet") or {}).get("topLevelComment") or {}).get("snippet", {}).get("textDisplay", "")
        if text:
            comments.append(text)
    return comments


def _process_topic_research(job: dict, job_id: str, job_log) -> None:
    job_store.transition(job_id, job_store.PREPARING, reason="preparing prompt")
    write_state("preparing", job, 0, job_id)
    job_log.info("-> PREPARING (building prompt)")

    keyword, language, country, count = _validate_payload(job["payload"])
    prompt = _build_prompt(keyword, language, country, count)

    job_store.transition(job_id, job_store.RENDERING, reason="calling AI provider")
    write_state("running", job, 30, job_id)
    job_log.info("-> RENDERING (calling AI provider for topic research)")

    ensure_project_root_on_path()
    from config import config
    from services import ai_router
    import asyncio

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
    result_path.write_text(
        json.dumps(
            {
                "job_id": job_id,
                "job_type": "topic_research",
                "status": "COMPLETED",
                "topics": topics,
                "model": model,
                "completed_at": completed_at,
                "error": None,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    job_store.transition(job_id, job_store.COMPLETED, reason="topic research complete", output_path=str(result_path))
    job_log.info(f"-> COMPLETED, result at {result_path}")
    logger.info(f"Completed job {job_id} -> {result_path}")
    write_state("idle", None, 0, last_success_at=completed_at)


def _process_topic_benchmark_analyze(job: dict, job_id: str, job_log) -> None:
    job_store.transition(job_id, job_store.PREPARING, reason="validating payload")
    write_state("preparing", job, 0, job_id)
    job_log.info("-> PREPARING (validating payload)")

    keyword, language, video_type, max_candidates, search_pool_size = _validate_benchmark_payload(job["payload"])

    job_store.transition(job_id, job_store.RENDERING, reason="searching YouTube for high-performing videos")
    write_state("running", job, 10, job_id)
    job_log.info(f"-> RENDERING (keyword={keyword!r}, video_type={video_type}, pool={search_pool_size}, pick={max_candidates})")

    ensure_project_root_on_path()
    from services.gemini_service import gemini_service
    from services.source_service import source_service
    import asyncio

    async def _run_analysis() -> list[dict]:
        candidates = await _search_candidate_videos(keyword, language, video_type, search_pool_size)
        if not candidates:
            raise ValueError(f"YouTube search returned no candidates for keyword={keyword!r}")

        enriched = await _fetch_video_and_channel_stats(candidates)
        enriched.sort(key=lambda c: c["performance_ratio"], reverse=True)
        top_candidates = enriched[:max_candidates]

        results = []
        for candidate in top_candidates:
            video_id = candidate["video_id"]

            transcript = None
            try:
                extracted = await source_service.extract_text_from_youtube(
                    f"https://www.youtube.com/watch?v={video_id}"
                )
                transcript = extracted.get("content")
            except Exception as e:
                # Best-effort: plenty of high-performing videos have no
                # captions. analyze_comments() degrades gracefully to
                # comments-only analysis when transcript is None.
                job_log.warning(f"Transcript extraction failed for {video_id} (continuing without it): {e}")

            comments = await _fetch_comments(video_id)
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
        return results

    results = asyncio.run(_run_analysis())

    job_store.transition(job_id, job_store.UPLOADING, reason="saving result")
    write_state("running", job, 90, job_id)
    job_log.info(f"-> UPLOADING (saving benchmark analysis for {len(results)} video(s))")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = RESULTS_DIR / f"{job_id}.json"
    completed_at = time.time()
    result_path.write_text(
        json.dumps(
            {
                "job_id": job_id,
                "job_type": "topic_benchmark_analyze",
                "status": "COMPLETED",
                "keyword": keyword,
                "language": language,
                "video_type": video_type,
                # [TODO][AIR-0230] Local-only for now, same scope limit as
                # topic_research (see module docstring). Uploading this to a
                # central Supabase table (topic_benchmark_analysis /
                # success_knowledge_central per
                # docs/AIR_0230_HERMES_BENCHMARK_WORKER_ARCHITECTURE.md §2a)
                # is a follow-up tied to the P4 central-job-sync work.
                "candidates": results,
                "completed_at": completed_at,
                "error": None,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    job_store.transition(job_id, job_store.COMPLETED, reason="benchmark analysis complete", output_path=str(result_path))
    job_log.info(f"-> COMPLETED, result at {result_path}")
    logger.info(f"Completed job {job_id} -> {result_path}")
    write_state("idle", None, 0, last_success_at=completed_at)


def process_one_job(job: dict) -> None:
    job_id = job["job_id"]
    job_type = job.get("job_type") or "topic_research"
    job_log = get_job_logger(job_id)
    job_log.info(f"Claimed {job_type} job, payload={job['payload']}")
    logger.info(f"Claimed job {job_id} ({job_type})")

    try:
        if job_type == "topic_benchmark_analyze":
            _process_topic_benchmark_analyze(job, job_id, job_log)
        else:
            _process_topic_research(job, job_id, job_log)

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
        write_state("idle", None, 0, last_error=error_message)


def run_forever():
    clear_shutdown_flag("hermes_worker")
    logger.info(f"Hermes Worker (real) starting, pid={os.getpid()}")
    write_state("idle", None, 0)

    try:
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
