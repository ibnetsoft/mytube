import json
from pathlib import Path
from typing import Any

from worker_config import SFX_CATALOG_PATH, SFX_LIBRARY_DIR


def load_sfx_catalog() -> dict[str, Any]:
    if not SFX_CATALOG_PATH.exists():
        return {"version": 1, "items": []}
    try:
        return json.loads(SFX_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "items": []}


def list_sfx_items() -> list[dict[str, Any]]:
    catalog = load_sfx_catalog()
    items = catalog.get("items")
    return items if isinstance(items, list) else []


def resolve_sfx_path(key: str) -> Path | None:
    for item in list_sfx_items():
        if item.get("key") != key:
            continue
        rel_path = item.get("relative_path")
        if not rel_path:
            return None
        path = SFX_LIBRARY_DIR / rel_path
        return path if path.exists() else None
    return None


def sfx_status() -> dict[str, Any]:
    items = list_sfx_items()
    existing = 0
    for item in items:
        rel_path = item.get("relative_path")
        if rel_path and (SFX_LIBRARY_DIR / rel_path).exists():
            existing += 1
    return {
        "library_dir": str(SFX_LIBRARY_DIR),
        "catalog_path": str(SFX_CATALOG_PATH),
        "catalog_exists": SFX_CATALOG_PATH.exists(),
        "item_count": len(items),
        "existing_file_count": existing,
    }
