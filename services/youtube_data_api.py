"""YouTube Data API helpers with API-key failover."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterable, Tuple

import httpx
import requests

from config import config


RETRYABLE_STATUSES = {403, 429, 500, 502, 503, 504}
MAX_YOUTUBE_KEYS = 5
YOUTUBE_RSS_URL = "https://www.youtube.com/feeds/videos.xml"
YOUTUBE_RSS_NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


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


def parse_channel_rss_videos(xml_text: str) -> list[dict]:
    """Parse YouTube channel RSS XML into lightweight video records.

    This consumes zero YouTube Data API quota and is the preferred seed for
    benchmark candidate collection. API calls should be reserved for enriching
    these real video IDs with statistics via videos.list/channels.list.
    """
    root = ET.fromstring(xml_text)
    videos: list[dict] = []
    for entry in root.findall("atom:entry", YOUTUBE_RSS_NAMESPACES):
        video_id = (entry.findtext("yt:videoId", default="", namespaces=YOUTUBE_RSS_NAMESPACES) or "").strip()
        channel_id = (entry.findtext("yt:channelId", default="", namespaces=YOUTUBE_RSS_NAMESPACES) or "").strip()
        title = (entry.findtext("atom:title", default="", namespaces=YOUTUBE_RSS_NAMESPACES) or "").strip()
        published_at = (entry.findtext("atom:published", default="", namespaces=YOUTUBE_RSS_NAMESPACES) or "").strip()
        updated_at = (entry.findtext("atom:updated", default="", namespaces=YOUTUBE_RSS_NAMESPACES) or "").strip()
        author = entry.find("atom:author", YOUTUBE_RSS_NAMESPACES)
        channel_title = ""
        if author is not None:
            channel_title = (author.findtext("atom:name", default="", namespaces=YOUTUBE_RSS_NAMESPACES) or "").strip()
        media_group = entry.find("media:group", YOUTUBE_RSS_NAMESPACES)
        description = ""
        thumbnail_url = None
        if media_group is not None:
            description = (
                media_group.findtext("media:description", default="", namespaces=YOUTUBE_RSS_NAMESPACES) or ""
            ).strip()
            thumbnail = media_group.find("media:thumbnail", YOUTUBE_RSS_NAMESPACES)
            if thumbnail is not None:
                thumbnail_url = thumbnail.attrib.get("url")
        if not video_id or not channel_id:
            continue
        videos.append({
            "video_id": video_id,
            "channel_id": channel_id,
            "title": title,
            "channel_title": channel_title,
            "published_at": published_at or None,
            "updated_at": updated_at or None,
            "description": description,
            "thumbnail_url": thumbnail_url,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "performance_data_source": "youtube_rss_seed",
        })
    return videos


async def async_fetch_channel_rss_videos(
    channel_id: str,
    *,
    limit: int = 15,
    timeout: float = 10.0,
) -> list[dict]:
    channel_id = str(channel_id or "").strip()
    if not channel_id:
        return []
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(YOUTUBE_RSS_URL, params={"channel_id": channel_id})
        response.raise_for_status()
    return parse_channel_rss_videos(response.text)[: max(0, int(limit))]


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(items), size):
        yield items[index:index + size]


def unique_nonempty(values: Iterable[Any]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


async def async_youtube_list_by_ids(
    endpoint: str,
    ids: Iterable[Any],
    *,
    part: str,
    timeout: float = 15.0,
    max_ids_per_call: int = 50,
) -> dict:
    """Call a YouTube list endpoint in quota-cheap 50-ID batches."""
    cleaned_ids = unique_nonempty(ids)
    if not cleaned_ids:
        return {"items": [], "batch_count": 0, "responses": []}
    items: list[dict] = []
    responses: list[dict] = []
    for batch in _chunks(cleaned_ids, max_ids_per_call):
        data = await async_youtube_get(endpoint, {"part": part, "id": ",".join(batch)}, timeout=timeout)
        if data.get("error"):
            return data
        responses.append(data)
        batch_items = data.get("items") if isinstance(data, dict) else []
        if isinstance(batch_items, list):
            items.extend(batch_items)
    return {
        "items": items,
        "batch_count": len(responses),
        "responses": responses,
        "_youtube_key_index": next(
            (response.get("_youtube_key_index") for response in responses if response.get("_youtube_key_index")),
            None,
        ),
    }


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
