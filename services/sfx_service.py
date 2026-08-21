import json
import math
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Iterable


KEYWORD_RULES = [
    ("doors", ["문", "방문", "현관", "열렸", "닫혔", "door", "creak", "open", "close"]),
    ("ambience", ["비", "빗", "폭우", "천둥", "rain", "storm", "thunder"]),
    ("footsteps", ["발자국", "걸음", "걸었다", "달렸다", "뛰", "footstep", "walk", "run"]),
    ("glass", ["유리", "깨졌", "깨진", "산산조각", "glass", "break", "shatter"]),
    ("impact", ["쾅", "충격", "부딪", "폭발", "추락", "impact", "hit", "boom", "explosion"]),
    ("technology", ["키보드", "타이핑", "컴퓨터", "keyboard", "typing", "laptop"]),
    ("transition", ["전환", "순간", "갑자기", "휙", "whoosh", "swoosh", "transition"]),
    ("ui", ["팝", "클릭", "알림", "버튼", "pop", "click", "notification"]),
]

KOREAN_KEYWORD_RULES = {
    "doors": [
        "\ubb38",
        "\ubb38\uc774 \uc5f4",
        "\ubb38\uc774 \ub2eb",
        "\ud604\uad00",
        "\ubc29\ubb38",
        "\ub178\ud06c",
    ],
    "ambience": [
        "\ube44",
        "\ube57\uc18c\ub9ac",
        "\ucc9c\ub465",
        "\ud3ed\ud48d",
        "\ubc14\ub78c",
        "\ube57\ubb3c",
    ],
    "footsteps": [
        "\ubc1c\uc790\uad6d",
        "\uac78\uc74c",
        "\uac78\uc5b4",
        "\ub6f0\uc5b4",
        "\ub2ec\ub824",
    ],
    "glass": [
        "\uc720\ub9ac",
        "\uae68\uc9d0",
        "\uae68\uc9c4",
        "\uc0b0\uc0b0\uc870\uac01",
    ],
    "impact": [
        "\ucfe0",
        "\ucda9\uaca9",
        "\ud3ed\ubc1c",
        "\ucd94\ub77d",
        "\ubd80\ub52a",
        "\uc0ac\uace0",
    ],
    "technology": [
        "\ud0a4\ubcf4\ub4dc",
        "\ud0c0\uc774\ud551",
        "\ucef4\ud4e8\ud130",
        "\ud734\ub300\ud3f0",
        "\uc2a4\ub9c8\ud2b8\ud3f0",
    ],
    "transition": [
        "\uc804\ud658",
        "\uac11\uc790\uae30",
        "\uc21c\uac04",
        "\uc7a5\uba74\uc774 \ubc14\ub00c",
    ],
    "ui": [
        "\ud074\ub9ad",
        "\uc54c\ub9bc",
        "\ubc84\ud2bc",
        "\ud31d\uc5c5",
    ],
}

PREFERRED_TITLE_TOKENS = {
    "doors": ["creak", "door", "open"],
    "ambience": ["rain", "storm"],
    "footsteps": ["footstep"],
    "glass": ["glass", "break", "shatter"],
    "impact": ["impact", "trailer", "deep"],
    "technology": ["keyboard", "typing"],
    "transition": ["whoosh", "woosh"],
    "ui": ["pop", "click"],
}

HERMES_SCENE_TEXT_FIELDS = (
    "scene_text",
    "script_excerpt",
    "narration",
    "voiceover",
    "scene_summary",
    "scene_situation",
    "scene_purpose",
    "visual_direction",
    "video_prompt",
    "prompt_en",
    "retention_hook",
    "end_bridge",
    "sound_effect",
    "sound_effects",
    "sfx",
)


def _default_sfx_library_dir() -> Path:
    explicit = os.environ.get("AIRWORKER_SFX_LIBRARY_DIR")
    if explicit:
        return Path(explicit)
    local_appdata = os.environ.get("LOCALAPPDATA")
    base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
    return base / "AIRStudio" / "AIRWorker" / "assets" / "sfx"


def _catalog_path() -> Path:
    return Path(os.environ.get("AIRWORKER_SFX_CATALOG_PATH", _default_sfx_library_dir() / "catalog.json"))


def load_catalog() -> dict[str, Any]:
    path = _catalog_path()
    if not path.exists():
        return {"version": 1, "items": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "items": []}


def _items_by_category(catalog: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in catalog.get("items") or []:
        category = str(item.get("category") or "").strip()
        rel_path = item.get("relative_path")
        if not category or not rel_path:
            continue
        path = _default_sfx_library_dir() / rel_path
        if path.exists():
            grouped.setdefault(category, []).append(item)
    for category, items in grouped.items():
        preferred = PREFERRED_TITLE_TOKENS.get(category, [])

        def _score(item: dict[str, Any]) -> int:
            haystack = " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("key") or ""),
                    " ".join(str(tag) for tag in (item.get("tags") or [])),
                ]
            ).lower()
            return sum(1 for token in preferred if token in haystack)

        items.sort(key=_score, reverse=True)
    return grouped


def resolve_catalog_item_path(item: dict[str, Any]) -> Path | None:
    rel_path = item.get("relative_path")
    if not rel_path:
        return None
    path = _default_sfx_library_dir() / rel_path
    return path if path.exists() else None


def resolve_sfx_path(value: str | None, packaged_root: Path | None = None) -> Path | None:
    if not value:
        return None
    raw = str(value)
    candidate = Path(raw)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    if not candidate.is_absolute() and candidate.exists():
        return candidate
    if packaged_root:
        for rel in (Path("sfx") / raw, Path(raw)):
            path = packaged_root / rel
            if path.exists():
                return path
    catalog = load_catalog()
    for item in catalog.get("items") or []:
        if raw in {item.get("key"), item.get("relative_path"), item.get("source_id")}:
            return resolve_catalog_item_path(item)
    path = _default_sfx_library_dir() / raw
    return path if path.exists() else None


def load_saved_sfx_cues(settings: dict[str, Any] | None) -> list[dict[str, Any]]:
    settings = settings or {}
    raw_json = settings.get("sfx_cues_json")
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
    raw_path = settings.get("sfx_cues_path")
    if raw_path and os.path.exists(raw_path):
        try:
            parsed = json.loads(Path(raw_path).read_text(encoding="utf-8"))
            if isinstance(parsed, list):
                return parsed
        except (OSError, json.JSONDecodeError):
            pass
    return []


def infer_sfx_cues_from_subtitles(subtitles: Iterable[dict[str, Any]], *, min_gap_seconds: float = 3.0) -> list[dict[str, Any]]:
    catalog = load_catalog()
    grouped = _items_by_category(catalog)
    if not grouped:
        return []

    cues: list[dict[str, Any]] = []
    last_by_category: dict[str, float] = {}
    for sub in subtitles or []:
        text = str(sub.get("text") or "").lower()
        if not text:
            continue
        try:
            start = float(sub.get("start") or 0.0)
        except (TypeError, ValueError):
            continue

        for category, keywords in KEYWORD_RULES:
            if category not in grouped:
                continue
            korean_keywords = KOREAN_KEYWORD_RULES.get(category, [])
            if not any(keyword.lower() in text for keyword in keywords) and not any(keyword in text for keyword in korean_keywords):
                continue
            if start - last_by_category.get(category, -math.inf) < min_gap_seconds:
                continue
            used = len([c for c in cues if c.get("category") == category])
            item = grouped[category][used % len(grouped[category])]
            cues.append(
                {
                    "start": round(start, 3),
                    "key": item.get("key"),
                    "category": category,
                    "volume_db": item.get("default_volume_db", -18.0),
                    "duration": None,
                    "fade_in": 0.02,
                    "fade_out": 0.12,
                    "source": "subtitle_auto",
                    "subtitle_text": sub.get("text") or "",
                }
            )
            last_by_category[category] = start
            break
    return cues


def _parse_scene_duration_seconds(scene: dict[str, Any], fallback: float) -> float:
    for key in ("target_duration_seconds", "target_duration", "duration_seconds", "duration", "play_time", "seconds"):
        value = scene.get(key)
        if value is None:
            continue
        try:
            duration = float(value)
        except (TypeError, ValueError):
            continue
        if duration > 0:
            return duration
    return fallback


def _scene_timeline(starts_count: int, structure: dict[str, Any], target_duration_seconds: float | None) -> list[float]:
    scenes = structure.get("scenes") if isinstance(structure, dict) else None
    if not isinstance(scenes, list) or not scenes:
        return [0.0 for _ in range(starts_count)]
    total = float(target_duration_seconds or structure.get("target_duration_seconds") or 0.0)
    fallback = max(1.0, total / max(1, len(scenes))) if total > 0 else 8.0
    starts: list[float] = []
    cursor = 0.0
    for scene in scenes:
        starts.append(cursor)
        if isinstance(scene, dict):
            cursor += _parse_scene_duration_seconds(scene, fallback)
        else:
            cursor += fallback
    return starts


def _scene_context_text(scene: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in HERMES_SCENE_TEXT_FIELDS:
        value = scene.get(field)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(item) for item in value if item)
        elif isinstance(value, dict):
            parts.extend(str(item) for item in value.values() if item)
    return " ".join(part.strip() for part in parts if str(part).strip())


def _script_chunks(script_text: str, target_duration_seconds: float | None, chunk_count: int = 12) -> list[dict[str, Any]]:
    clean = re.sub(r"\s+", " ", str(script_text or "")).strip()
    if not clean:
        return []
    pieces = re.split(r"(?<=[.!?\n。！？])\s+", clean)
    pieces = [piece.strip() for piece in pieces if piece.strip()]
    if not pieces:
        pieces = [clean]

    total_chars = sum(len(piece) for piece in pieces) or 1
    total_duration = float(target_duration_seconds or max(30.0, total_chars / 7.0))
    cues = []
    cursor = 0.0
    bucket_text: list[str] = []
    bucket_chars = 0
    target_chars = max(80, total_chars // max(1, min(chunk_count, len(pieces))))
    for piece in pieces:
        if bucket_text and bucket_chars >= target_chars:
            cues.append({"start": round(cursor, 3), "text": " ".join(bucket_text)})
            cursor += total_duration * (bucket_chars / total_chars)
            bucket_text = []
            bucket_chars = 0
        bucket_text.append(piece)
        bucket_chars += len(piece)
    if bucket_text:
        cues.append({"start": round(cursor, 3), "text": " ".join(bucket_text)})
    return cues


def build_hermes_sfx_cues(
    script_text: str,
    structure: dict[str, Any] | None = None,
    *,
    target_duration_seconds: float | None = None,
    max_cues: int = 24,
) -> list[dict[str, Any]]:
    """Plan timeline SFX cues from Hermes' script/scene context.

    Hermes owns the creative decision here; render workers only resolve files
    and mix the cues on the requested timeline.
    """
    structure = structure if isinstance(structure, dict) else {}
    scenes = structure.get("scenes") if isinstance(structure.get("scenes"), list) else []
    pseudo_subtitles: list[dict[str, Any]] = []
    if scenes:
        starts = _scene_timeline(len(scenes), structure, target_duration_seconds)
        for index, scene in enumerate(scenes):
            if not isinstance(scene, dict):
                continue
            text = _scene_context_text(scene)
            if not text:
                continue
            pseudo_subtitles.append(
                {
                    "start": starts[index] if index < len(starts) else 0.0,
                    "text": text,
                    "scene_number": index + 1,
                }
            )
    else:
        pseudo_subtitles = _script_chunks(script_text, target_duration_seconds)

    cues = infer_sfx_cues_from_subtitles(pseudo_subtitles, min_gap_seconds=5.0)
    planned: list[dict[str, Any]] = []
    for cue in cues[:max_cues]:
        enriched = dict(cue)
        enriched["source"] = "hermes_script"
        if isinstance(enriched.get("subtitle_text"), str):
            enriched["subtitle_text"] = enriched["subtitle_text"][:220]
        enriched.setdefault("volume_db", -18.0)
        enriched.setdefault("fade_in", 0.02)
        enriched.setdefault("fade_out", 0.12)
        planned.append(enriched)
    return planned


def scene_mapping_to_cues(settings: dict[str, Any] | None, project_id: int | None, image_timing_starts: list[float] | None) -> list[dict[str, Any]]:
    if not settings or not project_id:
        return []
    raw = settings.get("sfx_mapping_json")
    if not raw:
        return []
    try:
        mapping = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(mapping, dict):
        return []

    try:
        from config import config
        base_dir = Path(config.OUTPUT_DIR) / str(project_id) / "assets" / "sound"
    except Exception:
        base_dir = Path("output") / str(project_id) / "assets" / "sound"

    cues = []
    starts = image_timing_starts or []
    for scene_key, filename in mapping.items():
        try:
            scene_number = int(scene_key)
        except (TypeError, ValueError):
            continue
        start = starts[scene_number - 1] if scene_number - 1 < len(starts) else 0.0
        path = base_dir / str(filename)
        if path.exists():
            cues.append({"start": round(float(start), 3), "path": str(path), "category": "scene", "volume_db": -16.0, "source": "scene_mapping"})
    return cues


def build_render_sfx_cues(settings: dict[str, Any] | None, subtitles: list[dict[str, Any]] | None, project_id: int | None = None, image_timing_starts: list[float] | None = None) -> list[dict[str, Any]]:
    explicit = load_saved_sfx_cues(settings)
    if explicit:
        return explicit
    scene_cues = scene_mapping_to_cues(settings, project_id, image_timing_starts)
    if scene_cues:
        return scene_cues
    return infer_sfx_cues_from_subtitles(subtitles or [])


def package_sfx_cues(cues: list[dict[str, Any]], temp_dir: str | Path) -> list[dict[str, Any]]:
    packaged: list[dict[str, Any]] = []
    sfx_dir = Path(temp_dir) / "sfx"
    sfx_dir.mkdir(parents=True, exist_ok=True)
    for index, cue in enumerate(cues or []):
        if cue.get("enabled") is False:
            continue
        path = resolve_sfx_path(cue.get("path") or cue.get("file") or cue.get("filename") or cue.get("key"))
        if not path or not path.exists():
            continue
        ext = path.suffix.lower() or ".mp3"
        safe_stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", path.stem)[:48]
        dest_name = f"sfx_{index:03d}_{safe_stem}{ext}"
        dest = sfx_dir / dest_name
        if not dest.exists():
            shutil.copy2(path, dest)
        packaged_cue = dict(cue)
        packaged_cue.pop("path", None)
        packaged_cue["filename"] = dest_name
        packaged_cue["relative_path"] = f"sfx/{dest_name}"
        packaged.append(packaged_cue)
    return packaged


def save_project_sfx_cues(project_id: int, cues: list[dict[str, Any]]) -> str:
    try:
        from config import config
        import database as db
        output_dir = Path(config.OUTPUT_DIR)
    except Exception:
        output_dir = Path.cwd() / "output"
        db = None
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"sfx_cues_{project_id}_{int(time.time())}.json"
    path.write_text(json.dumps(cues, ensure_ascii=False, indent=2), encoding="utf-8")
    if db:
        db.update_project_setting(project_id, "sfx_cues_path", str(path))
    return str(path)


def db_to_volume_factor(volume_db: Any, fallback: float = -18.0) -> float:
    try:
        db_value = float(volume_db)
    except (TypeError, ValueError):
        db_value = fallback
    return max(0.0, min(2.0, 10 ** (db_value / 20.0)))
