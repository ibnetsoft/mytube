import os
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


_SCENE_PATTERNS = (
    re.compile(r"(?:^|[^a-z0-9])(?:scene|sc|s)[\s_-]*0*(\d+)(?:[^0-9]|$)", re.IGNORECASE),
    re.compile(r"^0*(\d+)(?:[\s_.-]|$)"),
)


def extract_scene_number(filename: str) -> Optional[int]:
    stem = os.path.splitext(os.path.basename(filename or ""))[0]
    for pattern in _SCENE_PATTERNS:
        match = pattern.search(stem)
        if match:
            value = int(match.group(1))
            return value if value > 0 else None
    return None


def build_assignment_plan(
    assets: Iterable[Dict[str, Any]],
    valid_scene_numbers: Iterable[int],
    existing_slots: Dict[Tuple[int, str], bool],
    ai_mapping: Optional[Dict[str, int]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    valid_scenes: Set[int] = {int(value) for value in valid_scene_numbers}
    ai_mapping = ai_mapping or {}
    claimed_slots: Set[Tuple[int, str]] = set()
    result: Dict[str, List[Dict[str, Any]]] = {
        "matched": [],
        "unmatched": [],
        "duplicates": [],
        "invalid": [],
    }

    for asset in assets:
        filename = str(asset.get("original_name") or "")
        media_type = "video" if asset.get("is_video") else "image"
        mapped_scene = extract_scene_number(filename)
        match_source = "filename"

        if mapped_scene is None:
            mapped_scene = ai_mapping.get(filename)
            match_source = "ai"

        if mapped_scene is None:
            result["unmatched"].append({**asset, "reason": "no_scene_match"})
            continue

        try:
            scene_number = int(mapped_scene)
        except (TypeError, ValueError):
            result["invalid"].append({
                **asset,
                "reason": "invalid_scene_number",
                "scene_number": mapped_scene,
                "match_source": match_source,
            })
            continue

        if scene_number not in valid_scenes:
            result["invalid"].append({
                **asset,
                "reason": "scene_out_of_range",
                "scene_number": scene_number,
                "match_source": match_source,
            })
            continue

        slot = (scene_number, media_type)
        if existing_slots.get(slot):
            result["duplicates"].append({
                **asset,
                "reason": "scene_slot_occupied",
                "scene_number": scene_number,
                "media_type": media_type,
                "match_source": match_source,
            })
            continue

        if slot in claimed_slots:
            result["duplicates"].append({
                **asset,
                "reason": "duplicate_in_upload",
                "scene_number": scene_number,
                "media_type": media_type,
                "match_source": match_source,
            })
            continue

        claimed_slots.add(slot)
        result["matched"].append({
            **asset,
            "scene_number": scene_number,
            "media_type": media_type,
            "match_source": match_source,
        })

    return result


def find_missing_scenes(scenes: Iterable[Dict[str, Any]]) -> Dict[str, List[int]]:
    missing_images: List[int] = []
    missing_videos: List[int] = []

    for scene in scenes:
        number = int(scene["scene_number"])
        if not scene.get("image_url"):
            missing_images.append(number)
        if not scene.get("video_url"):
            missing_videos.append(number)

    return {"images": missing_images, "videos": missing_videos}
