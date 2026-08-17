"""Build and validate strict 2x2 storyboard image prompts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


GRID_PROMPT_TEMPLATE = "strict_2x2_v1"
COMPACT_GRID_PROMPT_TEMPLATE = "strict_2x2_compact_v1"
GRID_PANEL_POSITIONS = ("Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right")


def _scene_number(scene: Mapping[str, Any], fallback: int) -> int | str:
    value = scene.get("scene_order") or scene.get("scene_number") or fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(value)


def _scene_panel_brief(scene: Mapping[str, Any]) -> str:
    """Return a visual brief from story/planning fields, not image prompts."""
    for key in (
        "panel_prompt",
        "scene_situation",
        "scene_summary",
        "visual_direction",
        "scene_text",
        "narration",
        "description",
        "scene_title",
        "title",
    ):
        text = str(scene.get(key) or "").strip()
        if text:
            return text
    return ""


def _grid_windows(scene_count: int) -> list[tuple[int, int]]:
    """Return 4-scene windows, adding an overlapping final window for tails."""
    if scene_count < 4:
        return []

    windows = [(start, start + 4) for start in range(0, scene_count - 3, 4)]
    if scene_count % 4:
        final_window = (scene_count - 4, scene_count)
        if windows[-1] != final_window:
            windows.append(final_window)
    return windows


def grid_windows(scene_count: int) -> list[tuple[int, int]]:
    return _grid_windows(scene_count)


def make_compact_image_grid_prompt(
    panels: Iterable[Mapping[str, Any]],
    *,
    shared_style: str = "",
    negative_prompt: str = "",
) -> str:
    """Compose one compact 2x2 prompt from four panel-level briefs.

    Unlike ``build_image_grid_prompts``, this does not concatenate four full
    scene prompts. The caller should provide one short visual beat per panel
    plus a shared style block, which keeps the final prompt manageable for
    external image generators.
    """
    panel_records = list(panels)
    panel_lines: list[str] = []
    for index, panel in enumerate(panel_records[:4]):
        brief = str(
            panel.get("panel_prompt")
            or panel.get("brief")
            or panel.get("prompt")
            or ""
        ).strip()
        if not brief:
            brief = f"Scene {index + 1}: distinct story beat with consistent characters and setting."
        panel_lines.append(
            f"- Panel {index + 1} (Position: {GRID_PANEL_POSITIONS[index]}): {brief}"
        )

    shared = str(shared_style or "").strip()
    negative = str(negative_prompt or "").strip()
    if not negative:
        negative = (
            "no text, no words, no letters, no labels, no captions, no watermarks, "
            "no borders, no grid lines, no dividers, correct anatomy, no extra limbs"
        )

    return (
        "Create a strict 2x2 image grid: exactly 2 columns, 2 rows, 4 equal panels. "
        "No borders, NO grid lines, NO white lines, NO dividers, NO crosshairs; panels touch seamlessly. "
        "Use one consistent visual world across all panels.\n"
        f"Shared style and continuity: {shared or 'consistent characters, wardrobe, props, lighting direction, palette, era, and location logic.'}\n"
        "Panel briefs:\n"
        + "\n".join(panel_lines)
        + "\nNegative guardrails: "
        + negative
        + "\nEach panel must visibly match its assigned position and story beat while staying distinct in action, composition, and emotion."
    )


def build_compact_image_grid_prompts(
    grid_specs: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize AI-authored 2x2 grid specs into persisted prompt records."""
    normalized: list[dict[str, Any]] = []
    for index, spec in enumerate(grid_specs, start=1):
        if not isinstance(spec, Mapping):
            continue
        panels = spec.get("panels")
        if not isinstance(panels, list) or len(panels) != 4:
            continue
        prompt = str(spec.get("prompt") or "").strip()
        if not prompt:
            prompt = make_compact_image_grid_prompt(
                panels,
                shared_style=str(spec.get("shared_style") or ""),
                negative_prompt=str(spec.get("negative_prompt") or ""),
            )
        scene_numbers = spec.get("scene_numbers")
        if not isinstance(scene_numbers, list) or len(scene_numbers) != 4:
            scene_numbers = [
                panel.get("scene_number")
                for panel in panels
                if isinstance(panel, Mapping) and panel.get("scene_number") is not None
            ]
        scene_ids = spec.get("scene_ids")
        if not isinstance(scene_ids, list):
            scene_ids = [
                str(panel.get("scene_id") or "").strip()
                for panel in panels
                if isinstance(panel, Mapping) and str(panel.get("scene_id") or "").strip()
            ]
        if len(scene_numbers) != 4:
            continue
        normalized.append(
            {
                "grid_number": spec.get("grid_number") or index,
                "template": spec.get("template") or COMPACT_GRID_PROMPT_TEMPLATE,
                "scene_numbers": scene_numbers,
                "scene_ids": scene_ids,
                "panel_count": 4,
                "shared_style": str(spec.get("shared_style") or "").strip(),
                "panels": panels,
                "prompt": prompt,
            }
        )
    return normalized


def build_image_grid_prompts(scenes: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Create persisted strict 2x2 prompts from chronological scene briefs.

    Every grid prompt describes exactly four panels. When the total scene count
    leaves a trailing one-to-three scenes, the final 2x2 prompt overlaps the
    previous block and uses the last four scenes so the tail is still visible in
    the user app without inventing blank or fake panels.

    This function deliberately ignores per-scene image prompt fields. The 2x2
    prompt is derived from planning/story context only.
    """
    ordered_scenes: list[dict[str, Any]] = []
    for fallback_number, scene in enumerate(scenes, start=1):
        if not isinstance(scene, Mapping):
            continue
        brief = _scene_panel_brief(scene)
        if not brief:
            continue
        ordered_scenes.append(
            {
                "scene_number": _scene_number(scene, fallback_number),
                "scene_id": str(scene.get("scene_id") or "").strip(),
                "prompt": brief,
            }
        )

    grid_prompts: list[dict[str, Any]] = []
    for start_index, end_index in _grid_windows(len(ordered_scenes)):
        panels = ordered_scenes[start_index:end_index]
        panel_lines = [
            f"- Panel {index + 1} (Position: {GRID_PANEL_POSITIONS[index]}): {panel['prompt']}"
            for index, panel in enumerate(panels)
        ]
        prompt = (
            "Create a strict 2x2 grid layout (exactly 2 columns and 2 rows, 4 equal-sized panels total). "
            "There must be NO borders, NO grid lines, NO white lines, and NO dividers/crosshairs between the panels. "
            "The panels must touch seamlessly. No text, no words, no letters, no labels, no captions, no watermarks anywhere. "
            "Keep recurring characters, wardrobe, props, location logic, lighting direction, and color palette consistent across all four panels, "
            "while making each panel clearly different in action, composition, and emotional beat. Each panel must represent one scene:\n"
            + "\n".join(panel_lines)
            + "\n\nCRITICAL: You must generate EXACTLY 4 panels in a perfect 2x2 grid with absolutely NO black borders, "
            "NO outlines, NO white borders, and NO dividing lines/crosses. Every panel must seamlessly connect to the edge. "
            "No more, no less. Maintain consistent characters across all panels. The Top-Left, Top-Right, Bottom-Left, and Bottom-Right panels "
            "must each visibly correspond to their assigned scene prompt."
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


def validate_image_grid_prompt_readiness(
    scenes: Iterable[Mapping[str, Any]],
    image_grid_prompts: Any,
    *,
    require_status: str | None = None,
    status: Any = None,
    require_compact_template: bool = False,
) -> None:
    """Raise ValueError unless persisted 2x2 prompts cover every promptable scene."""
    if require_status is not None and str(status or "").strip() != require_status:
        raise ValueError(f"image_grid_prompt_status must be {require_status}")

    scene_numbers: list[int | str] = []
    for fallback_number, scene in enumerate(scenes, start=1):
        if not isinstance(scene, Mapping):
            continue
        scene_numbers.append(_scene_number(scene, fallback_number))

    if len(scene_numbers) >= 4 and not image_grid_prompts:
        raise ValueError("image_grid_prompts missing")

    grids = normalize_image_grid_prompts(image_grid_prompts)
    if len(scene_numbers) >= 4 and not grids:
        raise ValueError("no valid image_grid_prompts")

    seen_prompts: set[str] = set()
    covered_scene_numbers: set[int | str] = set()
    expected_prompt_count = len(_grid_windows(len(scene_numbers)))
    if len(grids) != expected_prompt_count:
        raise ValueError(f"image_grid_prompts count mismatch: expected {expected_prompt_count}, got {len(grids)}")

    for grid in grids:
        prompt = str(grid.get("prompt") or "").strip()
        if require_compact_template and grid.get("template") != COMPACT_GRID_PROMPT_TEMPLATE:
            raise ValueError(
                f"image_grid_prompt must use {COMPACT_GRID_PROMPT_TEMPLATE} for grid {grid.get('grid_number')}"
            )
        if len(prompt) < 420:
            raise ValueError(f"image_grid_prompt too short for grid {grid.get('grid_number')}")
        for position in GRID_PANEL_POSITIONS:
            if f"Position: {position}" not in prompt:
                raise ValueError(f"image_grid_prompt missing panel position {position} for grid {grid.get('grid_number')}")
        for required in ("NO borders", "NO grid lines", "no text", "no words", "no letters", "no captions", "no watermarks"):
            if required.lower() not in prompt.lower():
                raise ValueError(f"image_grid_prompt missing guardrail '{required}' for grid {grid.get('grid_number')}")
        if prompt in seen_prompts:
            raise ValueError(f"duplicate image_grid_prompt for grid {grid.get('grid_number')}")
        seen_prompts.add(prompt)
        numbers = grid.get("scene_numbers")
        if not isinstance(numbers, list) or len(numbers) != 4:
            raise ValueError(f"image_grid_prompt must contain exactly 4 scene numbers for grid {grid.get('grid_number')}")
        covered_scene_numbers.update(numbers)

    missing = [number for number in scene_numbers if number not in covered_scene_numbers]
    if missing:
        raise ValueError(f"image_grid_prompts do not cover scene(s): {missing}")
