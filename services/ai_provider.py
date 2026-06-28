from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import database as db
from config import config


VALID_PROVIDERS = {"gemini", "claude"}


@dataclass
class AISelection:
    provider: str
    model: str


def normalize_provider(value: Optional[str]) -> str:
    if not value:
        return "gemini"
    value = str(value).strip().lower()
    if value not in VALID_PROVIDERS:
        return "gemini"
    return value


def _project_settings(project_id: Optional[int]) -> dict[str, Any]:
    if not project_id:
        return {}
    try:
        return db.get_project_settings(project_id) or {}
    except Exception:
        return {}


def _global_setting(*keys: str) -> Optional[str]:
    for key in keys:
        try:
            value = db.get_global_setting(key)
        except Exception:
            value = None
        if value not in (None, ""):
            return str(value)
    return None


def resolve_ai_selection(
    task_key: str,
    project_id: Optional[int] = None,
    requested_provider: Optional[str] = None,
    requested_model: Optional[str] = None,
) -> AISelection:
    settings = _project_settings(project_id)
    provider_key = f"{task_key}_provider"
    model_key = f"{task_key}_model"
    fallback_provider_key = "script_generation_provider" if task_key == "image_prompt" else None
    fallback_model_key = "script_generation_model" if task_key == "image_prompt" else None

    provider = normalize_provider(
        requested_provider
        or settings.get(provider_key)
        or (settings.get(fallback_provider_key) if fallback_provider_key else None)
        or _global_setting(f"sys_api_{provider_key}", provider_key, "ai_provider")
        or (_global_setting(f"sys_api_{fallback_provider_key}", fallback_provider_key) if fallback_provider_key else None)
        or getattr(config, provider_key.upper(), None)
        or getattr(config, "AI_PROVIDER", None)
    )

    model = (
        requested_model
        or settings.get(model_key)
        or (settings.get(fallback_model_key) if fallback_model_key else None)
        or _global_setting(f"sys_api_{model_key}", model_key, "ai_model")
        or (_global_setting(f"sys_api_{fallback_model_key}", fallback_model_key) if fallback_model_key else None)
        or getattr(config, model_key.upper(), None)
        or getattr(config, f"{task_key.upper()}_MODEL", None)
    )

    if not model:
        if provider == "claude":
            model = getattr(config, "CLAUDE_SCRIPT_MODEL", None) or "claude-sonnet-4-6"
        else:
            model = getattr(config, "SCRIPT_GENERATION_MODEL", None) or "gemini-2.5-flash"

    if provider == "claude" and not str(model).startswith("claude-"):
        model = "claude-sonnet-4-6"
    elif provider == "gemini" and not str(model).startswith("gemini-"):
        model = "gemini-2.5-flash"

    return AISelection(provider=provider, model=str(model))
