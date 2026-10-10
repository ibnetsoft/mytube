"""Named directing profiles for the scene visual director stage."""
from __future__ import annotations

from typing import Any


DEFAULT_PROFILE = "standard"

DIRECTING_PROFILES: dict[str, dict[str, str]] = {
    "standard": {
        "label": "기본 영상 연출",
        "description": "장면의 극적 목적에 맞춘 절제된 범용 AIR Studio 연출",
        "directive": """Use restrained story-led screen direction. Prefer a deliberate hold when movement adds no meaning. Keep camera, light, atmosphere, and approved-layer motion subordinate to dialogue, faces, continuity, and readable subtitles.""",
    },
    "japanese_folktale": {
        "label": "일본옛날이야기",
        "description": "일본 시대극·설화의 정서와 대사 호흡을 보존하는 절제된 연출",
        "directive": """Direct this as a Japanese folktale or period human drama. Preserve ma: let silence, held reactions, entrances, exits, weather, lantern light, shoji, and seasonal atmosphere carry meaning. Favor stable compositions, restrained push-ins or pans, motivated cutaways, and clear speaker geography. Do not turn every line into a zoom, do not use modern trailer rhythms, flashy particles, handheld shake, or exaggerated comic impacts. Use stronger motion only for an actual reveal, threat, pursuit, or emotional turn. Keep architecture, costume, gesture, social distance, and period objects culturally coherent. Dialogue and narration must remain easy to follow; effects must not cover faces or subtitle-safe areas.""",
    },
    "vertical_webtoon_speed": {
        "label": "세로형 웹툰 속도연출",
        "description": "원본 세로 PSD의 컷 순서와 레이어를 이용한 속도감 있는 영상 연출",
        "directive": """Direct from the original vertical-webtoon PSD as an ordered sequence of panels and approved layers. First establish the intended top-to-bottom reading order, panel boundaries, dialogue bubbles, sound lettering, character focus, and safe crop for the delivery frame. Build pace with acceleration, brief readable holds, impact pauses, and re-acceleration. Use camera_move or shot_sequence for fast panel traversal and transition for a motivated whip-like handoff; never skip a story panel merely to increase speed. Hold long enough for dialogue and essential text to be read. On action or reveal beats, use one short approach, a two-to-six-frame-feeling impact hold, then a controlled release; describe this with real scene seconds rather than invented FPS assets. Use depth_parallax only with verified foreground, character, and background layers. Use prop_motion, pose_change, mask_reveal, hair_cloth, light, or atmosphere only when those approved layers exist. Preserve PSD layer order and do not expose transparent seams or invent hidden body/background content. Avoid constant zooming, continuous scrolling at one speed, arbitrary shake, repeated flashes, and motion that reverses the authored reading order. Every plan must identify the source panel or PSD layer in its targets and include QA for reading order, text readability, crop safety, layer seams, and motion comfort.""",
    },
}


def _text(value: Any) -> str:
    return str(value or "").strip().lower()


def resolve_directing_profile(payload: dict[str, Any] | None) -> dict[str, str]:
    """Resolve an explicit profile, or the safe legacy-compatible automatic profile."""
    data = payload if isinstance(payload, dict) else {}
    requested = _text(data.get("direction_profile") or data.get("directing_profile"))
    if requested and requested != "auto":
        if requested not in DIRECTING_PROFILES:
            raise ValueError(f"unsupported direction_profile: {requested}")
        return {"id": requested, **DIRECTING_PROFILES[requested], "selection": "explicit"}

    language = _text(data.get("language") or (data.get("content_setting") or {}).get("language"))
    category = " ".join(_text(data.get(key)) for key in ("category", "category_name", "script_style"))
    country = _text(data.get("setting_country") or (data.get("content_setting") or {}).get("setting_country"))
    production_mode = _text(data.get("production_mode"))
    image_style = _text(data.get("image_style") or (data.get("content_setting") or {}).get("image_style"))
    if language == "ja" and ("옛날" in category or "昔" in category or "folktale" in category or country in {"일본", "japan", "日本"}):
        selected = "japanese_folktale"
    elif production_mode == "moving_comic" and ("웹툰" in image_style or "webtoon" in image_style):
        selected = "vertical_webtoon_speed"
    else:
        selected = DEFAULT_PROFILE
    return {"id": selected, **DIRECTING_PROFILES[selected], "selection": "automatic"}


def directing_profile_options() -> tuple[tuple[str, str], ...]:
    return tuple((key, profile["label"]) for key, profile in DIRECTING_PROFILES.items())
