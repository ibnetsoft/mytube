"""Build strict 2x2 storyboard prompts from four scene image prompts."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any


GRID_PROMPT_TEMPLATE = "strict_2x2_v1"
GRID_PANEL_POSITIONS = ("Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right")
_DYNAMIC_PROMPT_MARKERS = (
    "Dynamic elements:",
    "동적인 요소:",
    "[대본 기반 동적 변경 - 가장 중요]",
    "[Dynamic Scene Detail]",
)


def extract_pure_image_prompt(value: Any) -> str:
    """Match the legacy image-page cleanup before composing a grid prompt."""
    if isinstance(value, Mapping):
        value = value.get("prompt_en") or value.get("image_prompt") or ""

    text = str(value or "").strip()
    if not text:
        return ""

    if text.startswith("{"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, Mapping):
                text = str(parsed.get("prompt_en") or parsed.get("image_prompt") or text).strip()
        except (TypeError, ValueError):
            pass

    for marker in _DYNAMIC_PROMPT_MARKERS:
        marker_index = text.find(marker)
        if marker_index >= 0:
            return text[:marker_index].strip()
    return text


def _scene_number(scene: Mapping[str, Any], fallback: int) -> int | str:
    value = scene.get("scene_order") or scene.get("scene_number") or fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(value)


def _scene_image_prompt(scene: Mapping[str, Any]) -> str:
    return extract_pure_image_prompt(
        scene.get("image_prompt")
        or scene.get("prompt_en")
        or scene.get("prompt_content")
        or scene.get("prompt")
        or scene.get("prompt_ko")
    )


def build_image_grid_prompts(scenes: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Create one persisted 2x2 prompt per complete chronological four-scene block.

    A 2x2 image must have exactly four described panels. Trailing one-to-three
    scenes intentionally remain individual prompts instead of asking a model to
    invent unspecified panels.
    """
    ordered_scenes: list[dict[str, Any]] = []
    for fallback_number, scene in enumerate(scenes, start=1):
        if not isinstance(scene, Mapping):
            continue
        prompt = _scene_image_prompt(scene)
        if not prompt:
            continue
        ordered_scenes.append(
            {
                "scene_number": _scene_number(scene, fallback_number),
                "scene_id": str(scene.get("scene_id") or "").strip(),
                "prompt": prompt,
            }
        )

    grid_prompts: list[dict[str, Any]] = []
    for start_index in range(0, len(ordered_scenes) - 3, 4):
        panels = ordered_scenes[start_index : start_index + 4]
        panel_lines = [
            f"- Panel {index + 1} (Position: {GRID_PANEL_POSITIONS[index]}): {panel['prompt']}"
            for index, panel in enumerate(panels)
        ]
        prompt = (
            "Create a strict 2x2 grid layout (exactly 2 columns and 2 rows, 4 equal-sized panels total). "
            "There must be NO borders, NO grid lines, NO white lines, and NO dividers/crosshairs between the panels. "
            "The panels must touch seamlessly. Each panel must represent one scene:\n"
            + "\n".join(panel_lines)
            + "\n\nCRITICAL: You must generate EXACTLY 4 panels in a perfect 2x2 grid with absolutely NO black borders, "
            "NO outlines, NO white borders, and NO dividing lines/crosses. Every panel must seamlessly connect to the edge. "
            "No more, no less. Maintain consistent characters across all panels."
        )
        grid_prompts.append(
            {
                "grid_number": len(grid_prompts) + 1,
                "template": GRID_PROMPT_TEMPLATE,
                "scene_numbers": [panel["scene_number"] for panel in panels],
                "scene_ids": [panel["scene_id"] for panel in panels if panel["scene_id"]],
                "panel_count": 4,
                "prompt": prompt,
            }
        )
    return grid_prompts


def normalize_image_grid_prompts(value: Any) -> list[dict[str, Any]]:
    """Return only complete, display-safe persisted grid prompt records."""
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, Mapping):
            continue
        prompt = str(item.get("prompt") or item.get("grid_prompt") or "").strip()
        scene_numbers = item.get("scene_numbers")
        if not prompt or not isinstance(scene_numbers, list) or len(scene_numbers) != 4:
            continue
        normalized.append(
            {
                "grid_number": item.get("grid_number") or index,
                "template": item.get("template") or GRID_PROMPT_TEMPLATE,
                "scene_numbers": scene_numbers,
                "scene_ids": item.get("scene_ids") if isinstance(item.get("scene_ids"), list) else [],
                "panel_count": 4,
                "prompt": prompt,
            }
        )
    return normalized
