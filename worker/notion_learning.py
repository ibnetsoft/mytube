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
