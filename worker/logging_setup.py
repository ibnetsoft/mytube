"""
[AIR-0227A/B Stage 4 / Stage 11] Per-process + per-job logging helper.

docs/AIR_WORKER_PROCESS_MODEL.md §4: each process writes only to its own
log file - no shared-file write contention between processes.

[AIR-0227B Stage 11] adds:
  - a per-job log file (worker/state/logs/jobs/<job_id>.log) so a single
    render's full lifecycle can be inspected without grepping the whole
    render_worker.log
  - a redaction filter applied to every handler - secrets (Worker Token,
    Drive OAuth token contents, any Supabase key shape) must never reach a
    log file even if a caller accidentally includes one in a message
    (docs/AIR_WORKER_SECURITY.md §4 "실 Worker Token 커밋 금지" extended to
    "실 시크릿 로그 금지").
"""
import logging
import re
import sys

from worker_config import JOB_LOG_DIR, LOG_FILES

# Patterns for values that must never appear in a log line. Conservative on
# purpose - false positives (over-redacting) are acceptable, a leaked
# secret is not.
_SECRET_PATTERNS = [
    re.compile(r"(eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"),  # JWT-shaped (Supabase keys, session tokens)
    re.compile(r"(sk-[A-Za-z0-9]{16,})"),                                            # OpenAI/Anthropic-style API keys
    re.compile(r"(AIza[A-Za-z0-9_-]{20,})"),                                         # Google API keys
    re.compile(r"(worker_token[\"']?\s*[:=]\s*[\"']?)([^\s\"',]{6,})", re.IGNORECASE),
    re.compile(r"(access_token[\"']?\s*[:=]\s*[\"']?)([^\s\"',]{6,})", re.IGNORECASE),
    re.compile(r"(service_role[\"']?\s*[:=]\s*[\"']?)([^\s\"',]{6,})", re.IGNORECASE),
]


def redact_secrets(message: str) -> str:
    if not message:
        return message
    redacted = message
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(lambda m: (m.group(1) + "***REDACTED***") if m.lastindex and m.lastindex >= 2 else "***REDACTED***", redacted)
    return redacted


class _RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact_secrets(str(record.msg))
        except Exception:
            pass
        return True


def get_logger(process_name: str) -> logging.Logger:
    if process_name not in LOG_FILES:
        raise ValueError(f"Unknown process_name '{process_name}' - not in worker_config.LOG_FILES")

    logger = logging.getLogger(process_name)
    if logger.handlers:
        return logger  # already configured (e.g. re-imported)

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    redact_filter = _RedactingFilter()

    file_handler = logging.FileHandler(LOG_FILES[process_name], encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.addFilter(redact_filter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    stream_handler.addFilter(redact_filter)
    logger.addHandler(stream_handler)

    logger.propagate = False
    return logger


def get_job_logger(job_id: str) -> logging.Logger:
    """[AIR-0227B Stage 11] One log file per job_id, required content:
    claim time, prepare/render/upload transition timestamps, progress
    checkpoints, final status, and (on failure) the error. Callers append
    to this logger at each state_machine transition."""
    name = f"job.{job_id}"
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    path = JOB_LOG_DIR / f"{job_id}.log"

    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.addFilter(_RedactingFilter())
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger
