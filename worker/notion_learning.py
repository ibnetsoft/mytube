"""Optional Notion-backed text learning memory for Hermes workers."""

from __future__ import annotations

import os
from typing import Any

import httpx


NOTION_VERSION = "2022-06-28"


def _token() -> str:
    return (os.environ.get("NOTION_API_KEY") or os.environ.get("NOTION_TOKEN") or "").strip()


def _database_id() -> str:
    return (os.environ.get("NOTION_LEARNING_DATABASE_ID") or "").strip()


def _plain_text(prop: dict[str, Any] | None) -> str:
    if not isinstance(prop, dict):
        return ""
    values = prop.get("title") or prop.get("rich_text") or []
    return "".join(str(item.get("plain_text") or "") for item in values if isinstance(item, dict)).strip()


def _select_name(prop: dict[str, Any] | None) -> str:
    if not isinstance(prop, dict):
        return ""
    select = prop.get("select") or {}
    return str(select.get("name") or "").strip()


def _number(prop: dict[str, Any] | None) -> float | None:
    if not isinstance(prop, dict):
        return None
    value = prop.get("number")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _date_start(prop: dict[str, Any] | None) -> str:
    if not isinstance(prop, dict):
        return ""
    date = prop.get("date") or {}
    return str(date.get("start") or "").strip()


def _row_from_page(page: dict[str, Any]) -> dict[str, Any]:
    props = page.get("properties") if isinstance(page, dict) else {}
    props = props if isinstance(props, dict) else {}
    return {
        "generated_title": _plain_text(props.get("Name")),
        "production_topic": _plain_text(props.get("Learning Text")),
        "category_id": _plain_text(props.get("Category ID")),
        "category_name": _plain_text(props.get("Category")),
        "title_score": _number(props.get("Title Score")),
        "script_score": _number(props.get("Script Score")),
        "outcome_quality": _select_name(props.get("Quality")) or "unknown",
        "feedback_source": _select_name(props.get("Source")) or "notion",
        "metrics": {},
        "evaluation": {
            "type": "notion_text_memory",
            "learning_text": _plain_text(props.get("Learning Text")),
        },
        "created_at": _date_start(props.get("Created At")) or page.get("created_time"),
    }


def _rich_text(text: Any) -> dict[str, Any]:
    return {"rich_text": [{"type": "text", "text": {"content": str(text or "")[:1900]}}]}


def _title_text(text: Any) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": str(text or "AIR learning row")[:1900]}}]}


def _select_value(text: Any, fallback: str = "unknown") -> dict[str, Any]:
    return {"select": {"name": str(text or fallback)[:100]}}


def _date_value(text: Any) -> dict[str, Any]:
    value = str(text or "").strip()
    if not value:
        from datetime import datetime, timezone
        value = datetime.now(timezone.utc).isoformat()
    return {"date": {"start": value}}


async def _database_properties(token: str, database_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"https://api.notion.com/v1/databases/{database_id}",
            headers={"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION},
        )
    if response.status_code != 200:
        return {}
    data = response.json()
    props = data.get("properties") if isinstance(data, dict) else {}
    return props if isinstance(props, dict) else {}


def _title_property_name(properties: dict[str, Any]) -> str:
    for name, meta in properties.items():
        if isinstance(meta, dict) and meta.get("type") == "title":
            return name
    return "Name"


def _property_value(prop_type: str | None, value: Any) -> dict[str, Any] | None:
    if prop_type == "title":
        return _title_text(value)
    if prop_type == "rich_text":
        return _rich_text(value)
    if prop_type == "select":
        return _select_value(value)
    if prop_type == "date":
        return _date_value(value)
    if prop_type == "number":
        try:
            return {"number": float(value)}
        except (TypeError, ValueError):
            return {"number": None}
    return None


def _put_property(target: dict[str, Any], properties: dict[str, Any], name: str, value: Any) -> None:
    meta = properties.get(name)
    if not isinstance(meta, dict):
        return
    converted = _property_value(meta.get("type"), value)
    if converted is not None:
        target[name] = converted


async def fetch_learning_rows(category_id: str | None, category_name: str, limit: int = 30) -> list[dict[str, Any]]:
    token = _token()
    database_id = _database_id()
    if not token or not database_id:
        return []

    filters: list[dict[str, Any]] = []
    if category_id:
        filters.append({"property": "Category ID", "rich_text": {"equals": str(category_id)}})
    if category_name:
        filters.append({"property": "Category", "rich_text": {"equals": str(category_name)}})

    payload: dict[str, Any] = {
        "page_size": max(1, min(100, int(limit or 30))),
        "sorts": [{"property": "Created At", "direction": "descending"}],
    }
    if len(filters) == 1:
        payload["filter"] = filters[0]
    elif filters:
        payload["filter"] = {"or": filters}

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"https://api.notion.com/v1/databases/{database_id}/query",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Notion-Version": NOTION_VERSION,
            },
            json=payload,
        )
    if response.status_code != 200:
        return []
    data = response.json()
    return [_row_from_page(page) for page in data.get("results") or [] if isinstance(page, dict)]


async def fetch_music_learning_rows(target_market: str, genre: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    token = _token()
    database_id = _database_id()
    if not token or not database_id:
        return []

    category_terms = [f"music:{str(target_market or '').strip().lower()}"]
    if genre:
        category_terms.append(str(genre).strip().lower())
    filters: list[dict[str, Any]] = [
        {"property": "Source", "select": {"equals": "music_submission"}},
        {"property": "Source", "select": {"equals": "music_prompt_pack"}},
    ]
    category_filters = [
        {"property": "Category", "rich_text": {"contains": term}}
        for term in category_terms
        if term
    ]
    payload: dict[str, Any] = {
        "page_size": max(1, min(100, int(limit or 20))),
        "sorts": [{"property": "Created At", "direction": "descending"}],
        "filter": {"and": [{"or": filters}, {"or": category_filters}]} if category_filters else {"or": filters},
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"https://api.notion.com/v1/databases/{database_id}/query",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Notion-Version": NOTION_VERSION,
            },
            json=payload,
        )
    if response.status_code != 200:
        return []
    data = response.json()
    return [_row_from_page(page) for page in data.get("results") or [] if isinstance(page, dict)]


async def create_music_learning_row(row: dict[str, Any]) -> bool:
    token = _token()
    database_id = _database_id()
    if not token or not database_id or not row:
        return False

    properties_meta = await _database_properties(token, database_id)
    title_prop = _title_property_name(properties_meta)
    category = row.get("category") or ":".join(
        part for part in ["music", str(row.get("target_market") or "global").lower(), str(row.get("genre") or "").lower()] if part
    )
    learning_text = "\n".join(
        part for part in [
            f"Source ID: {row.get('source_id') or row.get('job_id') or '-'}",
            f"Market: {row.get('target_market') or '-'}",
            f"Genre: {row.get('genre') or '-'}",
            f"Mood: {row.get('mood') or '-'}",
            f"Prompt: {row.get('prompt') or row.get('prompt_used') or '-'}",
            f"Negative rules: {', '.join(row.get('negative_rules') or [])}" if isinstance(row.get("negative_rules"), list) else "",
            str(row.get("quality_note") or ""),
        ]
        if part
    )
    properties: dict[str, Any] = {title_prop: _title_text(row.get("title") or row.get("source_id") or "AIR music learning row")}
    _put_property(properties, properties_meta, "Category", category)
    _put_property(properties, properties_meta, "Category ID", category)
    _put_property(properties, properties_meta, "Quality", row.get("outcome_quality") or "music_memory")
    _put_property(properties, properties_meta, "Source", row.get("source") or "music_prompt_pack")
    _put_property(properties, properties_meta, "Source Job ID", row.get("source_id") or row.get("job_id") or "")
    _put_property(properties, properties_meta, "Title Score", row.get("title_score") or "")
    _put_property(properties, properties_meta, "Script Score", row.get("script_score") or "")
    _put_property(properties, properties_meta, "Created At", row.get("created_at") or "")
    _put_property(properties, properties_meta, "Learning Text", learning_text)

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://api.notion.com/v1/pages",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Notion-Version": NOTION_VERSION,
            },
            json={
                "parent": {"database_id": database_id},
                "properties": properties,
                "children": [
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"type": "text", "text": {"content": learning_text[:1900]}}]},
                    }
                ],
            },
        )
    return response.status_code in (200, 201)
