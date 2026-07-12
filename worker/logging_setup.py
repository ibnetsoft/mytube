"""
[AIR-0227A Stage 12] Per-process logging helper.

docs/AIR_WORKER_PROCESS_MODEL.md §4: each process writes only to its own
log file - no shared-file write contention between processes.
"""
import logging
import sys

from config import LOG_FILES


def get_logger(process_name: str) -> logging.Logger:
    if process_name not in LOG_FILES:
        raise ValueError(f"Unknown process_name '{process_name}' - not in config.LOG_FILES")

    logger = logging.getLogger(process_name)
    if logger.handlers:
        return logger  # already configured (e.g. re-imported)

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = logging.FileHandler(LOG_FILES[process_name], encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    logger.propagate = False
    return logger
