"""Shared image shot-design contract for scene prompt generation."""

SCENE_SHOT_SIZES = ("extreme_wide", "wide", "medium", "close_up", "detail")
SCENE_CAMERA_ANGLES = ("eye_level", "high_angle", "low_angle", "overhead", "oblique")
SCENE_SUBJECT_PRESENCE = ("character_required", "character_optional", "environment_only", "object_insert")
SCENE_SUBJECT_SCALES = ("none", "small", "medium", "large", "detail")


def normalize_scene_shot_design(value, scene_number, panel_prompt="") -> dict:
    """Normalize a scene's explicit image composition contract."""
    raw = value if isinstance(value, dict) else {}
    try:
        index = max(0, int(scene_number or 1) - 1)
    except (TypeError, ValueError):
        index = 0
    text = str(panel_prompt or "").lower()
    empty_scene = any(phrase in text for phrase in (
        "no people", "without people", "empty background", "empty room", "unoccupied", "no characters",
    ))
    defaults = {
        "shot_size": SCENE_SHOT_SIZES[index % len(SCENE_SHOT_SIZES)],
        "camera_angle": SCENE_CAMERA_ANGLES[(index * 2) % len(SCENE_CAMERA_ANGLES)],
        "subject_presence": "environment_only" if empty_scene else "character_optional",
        "subject_scale": "none" if empty_scene else "medium",
    }
    clean = {}
    for key, allowed in (
        ("shot_size", SCENE_SHOT_SIZES),
        ("camera_angle", SCENE_CAMERA_ANGLES),
        ("subject_presence", SCENE_SUBJECT_PRESENCE),
        ("subject_scale", SCENE_SUBJECT_SCALES),
    ):
        item = str(raw.get(key) or defaults[key]).strip().lower()
        clean[key] = item if item in allowed else defaults[key]
    clean["composition"] = str(raw.get("composition") or "Use clear foreground, midground, and background placement with a deliberate focal point.").strip()
    clean["repetition_reason"] = str(raw.get("repetition_reason") or "").strip()
    if clean["subject_presence"] == "environment_only":
        clean["subject_scale"] = "none"
    elif clean["subject_presence"] == "object_insert":
        clean["subject_scale"] = "detail"
    return clean


def apply_scene_shot_design(panel_prompt: str, shot_design: dict) -> str:
    """Make the shot contract explicit in the final image-generation prompt."""
    prompt = str(panel_prompt or "").strip()
    if prompt.startswith("Shot contract:"):
        return prompt
    presence_rules = {
        "character_required": "Show the story-required character(s), and no additional people.",
        "character_optional": "Include a character only if the narrated beat needs one; do not add people as decoration.",
        "environment_only": "Show the environment only: absolutely no people, human silhouettes, faces, or human reflections.",
        "object_insert": "Show only the story-relevant object detail; no people, hands, or faces.",
    }
    contract = (
        f"Shot contract: {shot_design['shot_size']} framing, {shot_design['camera_angle']} camera angle, "
        f"{shot_design['subject_presence']} ({presence_rules[shot_design['subject_presence']]}), "
        f"subject scale {shot_design['subject_scale']}; composition: {shot_design['composition']}"
    )
    return f"{contract}. {prompt}" if prompt else contract
