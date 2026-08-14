"""YouTube Data API helpers with API-key failover."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple

import httpx
import requests

from config import config


RETRYABLE_STATUSES = {403, 429, 500, 502, 503, 504}
MAX_YOUTUBE_KEYS = 5


def normalized_youtube_keys() -> list[str]:
    """Return up to five unique YouTube API keys in primary-then-backup order."""
    return config.youtube_api_keys()[:MAX_YOUTUBE_KEYS]


def _error_message(data: Any, fallback: str = "YouTube API Error") -> str:
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if message:
                return str(message)
            errors = error.get("errors")
            if isinstance(errors, list) and errors:
                first = errors[0]
                reason = first.get("reason") if isinstance(first, dict) else None
                if reason:
                    return str(reason)
    return fallback


def _is_retryable(status_code: int, message: str) -> bool:
    lower = str(message or "").lower()
    return (
        status_code in RETRYABLE_STATUSES
        or "api key" in lower
        or "apikey" in lower
        or "quota" in lower
        or "rate limit" in lower
    )


def _with_key(params: Dict[str, Any] | None, key: str) -> Dict[str, Any]:
    merged = dict(params or {})
    merged["key"] = key
    return merged


def _failure_summary(failures: Iterable[Tuple[int, int, str]]) -> str:
    return " | ".join(f"key {index}: HTTP {status} - {message}" for index, status, message in failures)


async def async_youtube_get(
    path_or_url: str,
    params: Dict[str, Any] | None = None,
    *,
    timeout: float = 15.0,
) -> Dict[str, Any]:
    keys = normalized_youtube_keys()
    if not keys:
        return {"error": "YOUTUBE_API_KEY_NOT_CONFIGURED", "message": "YouTube API key is not configured."}

    url = path_or_url if path_or_url.startswith("http") else f"{config.YOUTUBE_BASE_URL}/{path_or_url.lstrip('/')}"
    failures: list[Tuple[int, int, str]] = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        for index, key in enumerate(keys, start=1):
            response = await client.get(url, params=_with_key(params, key))
            try:
                data = response.json()
            except ValueError:
                data = {}
            if response.status_code == 200:
                if isinstance(data, dict):
                    data.setdefault("_youtube_key_index", index)
                    return data
                return {"data": data, "_youtube_key_index": index}

            message = _error_message(data)
            failures.append((index, response.status_code, message))
            if not _is_retryable(response.status_code, message):
                break

    return {
        "error": "YOUTUBE_API_ERROR",
        "message": _failure_summary(failures) or "YouTube API Error",
        "failover_attempts": len(failures),
    }


def sync_youtube_get(
    path_or_url: str,
    params: Dict[str, Any] | None = None,
    *,
    timeout: float = 20.0,
) -> Dict[str, Any]:
    keys = normalized_youtube_keys()
    if not keys:
        raise RuntimeError("YouTube API key is not configured")

    url = path_or_url if path_or_url.startswith("http") else f"{config.YOUTUBE_BASE_URL}/{path_or_url.lstrip('/')}"
    failures: list[Tuple[int, int, str]] = []
    for index, key in enumerate(keys, start=1):
        response = requests.get(url, params=_with_key(params, key), timeout=timeout)
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code == 200:
            if isinstance(data, dict):
                data.setdefault("_youtube_key_index", index)
                return data
            return {"data": data, "_youtube_key_index": index}

        message = _error_message(data, response.text[:200] if response.text else "YouTube API Error")
        failures.append((index, response.status_code, message))
        if not _is_retryable(response.status_code, message):
            break

    raise RuntimeError(f"YouTube Data API error after {len(failures)} key(s): {_failure_summary(failures)}")
