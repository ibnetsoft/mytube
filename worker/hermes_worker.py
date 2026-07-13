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
SUPPORTED_JOB_TYPES = ["topic_research"]
DEFAULT_COUNT = 10
MAX_COUNT = 30


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


def process_one_job(job: dict) -> None:
    job_id = job["job_id"]
    job_log = get_job_logger(job_id)
    job_log.info(f"Claimed topic_research job, payload={job['payload']}")
    logger.info(f"Claimed job {job_id}")

    try:
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
