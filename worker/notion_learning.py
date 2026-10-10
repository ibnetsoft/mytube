"""Optional Notion-backed text learning memory for Hermes workers."""

from __future__ import annotations

import os
import json
from typing import Any

import httpx
import worker_config  # noqa: F401  # ensure worker env is loaded before reading Notion settings


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
    if value is None:
        text_value = _plain_text(prop)
        if text_value:
            value = text_value
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _date_start(prop: dict[str, Any] | None) -> str:
    if not isinstance(prop, dict):
        return ""
    date = prop.get("date") or {}
    return str(date.get("start") or "").strip()


def _first_prop_by_type(props: dict[str, Any], prop_type: str) -> dict[str, Any] | None:
    for value in props.values():
        if isinstance(value, dict) and str(value.get("type") or "").strip() == prop_type:
            return value
    return None


def _row_from_page(page: dict[str, Any]) -> dict[str, Any]:
    props = page.get("properties") if isinstance(page, dict) else {}
    props = props if isinstance(props, dict) else {}
    title_prop = props.get("Name") or props.get("이름") or _first_prop_by_type(props, "title")
    notion_blocks = page.get("_notion_blocks") if isinstance(page.get("_notion_blocks"), dict) else {}
    title_generation = notion_blocks.get("title_generation") if isinstance(notion_blocks.get("title_generation"), dict) else {}
    compact_title_generation = notion_blocks.get("title_candidates_compact") if isinstance(notion_blocks.get("title_candidates_compact"), dict) else {}
    if not title_generation and compact_title_generation:
        title_generation = compact_title_generation
    elif title_generation and compact_title_generation:
        existing = title_generation.get("title_candidates")
        if (not isinstance(existing, list) or not existing) and isinstance(compact_title_generation.get("title_candidates"), list):
            title_generation = {
                **title_generation,
                "generated_title": title_generation.get("generated_title") or compact_title_generation.get("generated_title"),
                "selected_score": title_generation.get("selected_score", compact_title_generation.get("selected_score")),
                "title_candidates": compact_title_generation.get("title_candidates") or [],
            }
    metrics = notion_blocks.get("metrics") if isinstance(notion_blocks.get("metrics"), dict) else {}
    evaluation = notion_blocks.get("evaluation") if isinstance(notion_blocks.get("evaluation"), dict) else {}
    identifiers = notion_blocks.get("identifiers") if isinstance(notion_blocks.get("identifiers"), dict) else {}
    return {
        "generated_title": _plain_text(title_prop) or str(title_generation.get("generated_title") or title_generation.get("final_title") or "").strip(),
        "production_topic": _plain_text(props.get("Learning Text")),
        "topic_queue_id": _plain_text(props.get("Topic Queue ID")) or str(identifiers.get("topic_queue_id") or "").strip(),
        "source_job_id": _plain_text(props.get("Source Job Key")) or _plain_text(props.get("Source Job Text")) or str(identifiers.get("source_job_id") or "").strip(),
        "category_id": _plain_text(props.get("Category ID")) or str(identifiers.get("category_id") or "").strip(),
        "category_name": _plain_text(props.get("Category")),
        "title_score": _number(props.get("Title Score")),
        "script_score": _number(props.get("Script Score")),
        "outcome_quality": _select_name(props.get("Quality")) or "unknown",
        "feedback_source": _select_name(props.get("Source")) or "notion",
        "metrics": metrics,
        "title_generation": title_generation,
        "benchmark_summary": notion_blocks.get("benchmark_summary") if isinstance(notion_blocks.get("benchmark_summary"), dict) else {},
        "evaluation": {
            "type": "notion_text_memory",
            "learning_text": _plain_text(props.get("Learning Text")),
            **evaluation,
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
    try:
        numeric = float(value)
        if numeric > 1_000_000_000:
            from datetime import datetime, timezone
            value = datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        pass
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


def _put_first_property(target: dict[str, Any], properties: dict[str, Any], names: tuple[str, ...], value: Any) -> None:
    for name in names:
        before = len(target)
        _put_property(target, properties, name, value)
        if len(target) > before:
            return


def _first_text_value(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _parse_code_block_payload(block: dict[str, Any]) -> tuple[str, Any] | None:
    if not isinstance(block, dict) or str(block.get("type") or "") != "code":
        return None
    code = block.get("code")
    if not isinstance(code, dict):
        return None
    text = "".join(
        str(((item.get("text") or {}).get("content")) or "")
        for item in (code.get("rich_text") or [])
        if isinstance(item, dict)
    ).strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or len(payload) != 1:
        return None
    key = next(iter(payload))
    return str(key), payload.get(key)


async def _fetch_page_blocks(
    client: httpx.AsyncClient,
    token: str,
    page_id: str,
) -> dict[str, Any]:
    response = await client.get(
        f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION,
        },
    )
    if response.status_code != 200:
        return {}
    data = response.json()
    blocks: dict[str, Any] = {}
    for item in data.get("results") or []:
        parsed = _parse_code_block_payload(item)
        if not parsed:
            continue
        key, value = parsed
        blocks[key] = value
    return blocks


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
        rows = []
        for page in data.get("results") or []:
            if not isinstance(page, dict):
                continue
            page_id = str(page.get("id") or "").strip()
            if page_id:
                page["_notion_blocks"] = await _fetch_page_blocks(client, token, page_id)
            rows.append(_row_from_page(page))
        return rows


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


async def create_content_learning_row(row: dict[str, Any]) -> bool:
    """Persist a completed Codex content package as reusable learning memory."""
    token = _token()
    database_id = _database_id()
    if not token or not database_id or not row:
        return False

    properties_meta = await _database_properties(token, database_id)
    title_prop = _title_property_name(properties_meta)
    title_generation = row.get("title_generation") if isinstance(row.get("title_generation"), dict) else {}
    quality = row.get("script_quality_report") if isinstance(row.get("script_quality_report"), dict) else {}
    blueprint = row.get("narrative_blueprint") if isinstance(row.get("narrative_blueprint"), dict) else {}
    title = str(row.get("generated_title") or row.get("upload_title") or "AIR content learning row").strip()
    topic_queue_id = _first_text_value(row.get("topic_queue_id"), row.get("topic_id"))
    source_job_id = _first_text_value(row.get("source_job_id"), row.get("job_id"))
    category_id = _first_text_value(row.get("category_id"))
    learning_text = "\n".join(part for part in [
        f"Title: {title}",
        f"Category: {row.get('category') or '-'}",
        f"Category ID: {category_id or '-'}",
        f"Topic Queue ID: {topic_queue_id or '-'}",
        f"Source Job ID: {source_job_id or '-'}",
        f"Quality score: {quality.get('score') or '-'}",
        f"Theme: {blueprint.get('core_theme') or blueprint.get('theme') or '-'}",
        f"Logline: {blueprint.get('logline') or '-'}",
        "Use the stored structured blocks for title candidates, benchmark summary, and evaluation.",
    ] if part)
    properties: dict[str, Any] = {title_prop: _title_text(title)}
    _put_property(properties, properties_meta, "Category", row.get("category") or "")
    _put_property(properties, properties_meta, "Category ID", category_id)
    _put_first_property(properties, properties_meta, ("Topic Queue ID", "Topic ID", "Queue ID"), topic_queue_id)
    # This Notion database has controlled select options.  Use its existing
    # worker values instead of attempting to create new options at write time.
    _put_property(properties, properties_meta, "Quality", "pass")
    _put_property(properties, properties_meta, "Source", "worker_history")
    _put_first_property(properties, properties_meta, ("Source Job Key", "Source Job Text", "Source Job ID"), source_job_id)
    _put_property(properties, properties_meta, "Title Score", title_generation.get("selected_score") or quality.get("score") or "")
    _put_property(properties, properties_meta, "Script Score", quality.get("score") or "")
    _put_property(properties, properties_meta, "Created At", row.get("completed_at") or "")
    _put_property(properties, properties_meta, "Learning Text", learning_text)
    benchmark = row.get("benchmark_analysis") if isinstance(row.get("benchmark_analysis"), dict) else {}
    web_research = benchmark.get("web_research") if isinstance(benchmark.get("web_research"), dict) else {}
    benchmark_summary = {
        "selected_title": benchmark.get("selected_title") or benchmark.get("representative_title"),
        "audit_summary": benchmark.get("audit_summary") or {},
        "sources": [
            {"title": item.get("title"), "url": item.get("url")}
            for item in (web_research.get("sources") or [])[:8]
            if isinstance(item, dict)
        ],
    }
    blocks = {
        "identifiers": {
            "topic_queue_id": topic_queue_id,
            "source_job_id": source_job_id,
            "category_id": category_id,
            "category": row.get("category") or "",
            "job_type": row.get("job_type") or "",
        },
        "title_generation": title_generation,
        "title_candidates_compact": {"generated_title": title, "title_candidates": title_generation.get("title_candidates") or []},
        "benchmark_summary": benchmark_summary,
        "evaluation": {"source": "codex_content_generate", "script_quality_report": quality},
    }
    children = [
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": learning_text[:1900]}}]}},
        *[
            {"object": "block", "type": "code", "code": {"language": "json", "rich_text": [{"type": "text", "text": {"content": json.dumps({key: value}, ensure_ascii=False)[:1900]}}]}}
            for key, value in blocks.items()
        ],
    ]
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://api.notion.com/v1/pages",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Notion-Version": NOTION_VERSION},
            json={"parent": {"database_id": database_id}, "properties": properties, "children": children},
        )
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Notion page creation failed: {response.status_code} {response.text[:300]}")
    return True
