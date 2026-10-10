"""Deterministic preflight and render review for AE manga scene templates.

The checks in this module validate the *instructions* and the exported media.
They cannot prove that a depicted character is the intended character, that a
particle follows the body in every frame, or that rendered Hangul is readable.
Those items remain explicit visual-review points in every template report.
"""
from __future__ import annotations

import io
import math
import re
import subprocess
from pathlib import Path
from typing import Any

try:
    from .manga_lip_sync import MOUTH_ROLES, validate_lip_sync
    from .manga_caption_animation import validate_caption_animation, validate_sfx_text_animation
except ImportError:
    from manga_lip_sync import MOUTH_ROLES, validate_lip_sync
    from manga_caption_animation import validate_caption_animation, validate_sfx_text_animation


TEMPLATES = {
    "parallax_layered_scene": ("background", "foreground"),
    "directed_performance": ("background",),
    "dialogue_closeup": ("background", "character"),
    "angled_triple_reaction": ("background", "character_left", "character_center", "character_right"),
    "body_following_qi": ("background", "character", "talisman"),
    "ink_splat_impact": ("background", "character", "talisman"),
    "wall_impact_debris": ("background", "character", "wall_intact", "wall_broken"),
    "glasses_reflection": ("background", "character", "reflection_scene"),
    "kinetic_title_reveal": ("background", "character"),
    "backlit_hand_reveal": ("background", "hand_foreground"),
}
REVIEW_POINTS = {
    "parallax_layered_scene": ["Check that only approved layers move and that foreground/background separation has no seams or exposed holes.",
                                "Check that faces, hands, captions, and the main story subject remain stable and readable through the full move."],
    "directed_performance": ["Check each pose or prop reveal against the corresponding narration beat and supplied layer role.",
                             "Check that attention cues point to the intended story subject and remain subtle.",
                             "Check that alternate poses align without seams, identity drift, or unintended repeated movement."],
    "dialogue_closeup": ["Listen to the final dialogue while checking mouth changes frame by frame at the first word, pauses, and last word.",
                         "Check that all three mouth patches cover the original lips without seams, face drift, identity changes, or a visible mouth during silence."],
    "angled_triple_reaction": ["Check that all three faces remain visible and the panel seams do not cut through eyes or captions.",
                               "Check character identity, panel order, and text readability at playback speed."],
    "body_following_qi": ["Check that the qi follows the body rather than floating over the background.",
                          "Check that the character and talisman remain recognizable through the glow."],
    "ink_splat_impact": ["Check that the ink burst and onomatopoeia appear at the actual story impact.",
                         "Check Korean glyphs, safe margins, contrast, and text readability at playback speed."],
    "wall_impact_debris": ["Check that the broken wall replaces the intact wall at contact and the fracture matches the character's body.",
                           "Check that the debris bursts outward from the contact point and settles without covering the subject."],
    "glasses_reflection": ["Check that the remembered scene stays inside both glasses lenses as the camera pushes in.",
                            "Check the reflected characters, lens boundaries, glint, and face identity at playback speed."],
    "kinetic_title_reveal": ["Check the Korean headline and accent text for legibility, spelling, contrast, and safe margins.",
                             "Check that the text appears on the scripted beat and remains readable through the hold."],
    "backlit_hand_reveal": ["Check that the raised hand has the intended character identity and a readable silhouette.",
                            "Check that light ignites at the palm and rays bloom behind the hand without obscuring it."],
}


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _point(value: Any) -> tuple[float, float] | None:
    if isinstance(value, dict):
        x, y = _number(value.get("x")), _number(value.get("y"))
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        x, y = _number(value[0]), _number(value[1])
    else:
        return None
    if x is None or y is None or not (0 <= x <= 1 and 0 <= y <= 1):
        return None
    return x, y


def _duration(scene: dict[str, Any], supplied: Any = None) -> float | None:
    plan = _mapping(scene.get("ae_effect_plan"))
    value = supplied if supplied is not None else (plan.get("duration_seconds") or scene.get("duration_seconds"))
    result = _number(value)
    return result if result is not None and result > 0 else None


def _result(stage: str, template: str | None, errors: list[str], warnings: list[str],
            checks: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    applicable = template is not None
    return {
        "stage": stage,
        "template": template,
        "applicable": applicable,
        "passed": not errors,
        "status": "fail" if errors else ("needs_review" if applicable else "not_applicable"),
        "review_required": applicable,
        "review_points": REVIEW_POINTS.get(template, []) if applicable else [],
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        **extra,
    }


def _check(checks: list[dict[str, Any]], errors: list[str], code: str,
           condition: bool, message: str) -> None:
    checks.append({"code": code, "passed": bool(condition), "message": message})
    if not condition:
        errors.append(message)


def _asset(asset_metadata: Any) -> dict[str, Any]:
    metadata = _mapping(asset_metadata)
    nested = metadata.get("psd_layer_asset")
    return _mapping(nested) if isinstance(nested, dict) else metadata


def _raw_layer_names(asset_metadata: Any) -> list[str]:
    asset = _asset(asset_metadata)
    value = asset.get("layers") or asset.get("layer_names") or asset.get("psd_layers") or []
    names: list[str] = []
    if isinstance(value, dict):
        value = list(value.keys())
    if isinstance(value, list):
        for entry in value:
            name = entry.get("name") if isinstance(entry, dict) else entry
            if isinstance(name, str) and name.strip():
                names.append(name.strip().casefold())
    return names


def _required_layers(plan: dict[str, Any], template: str) -> set[str]:
    requirements = plan.get("asset_requirements")
    if isinstance(requirements, dict):
        requirements = (requirements.get("required_layers") or requirements.get("layers")
                        or requirements.get("named_layers") or [])
    if not isinstance(requirements, list):
        requirements = []
    required = {name.casefold() for name in TEMPLATES[template]} | {
        item.strip().casefold() for item in requirements if isinstance(item, str) and item.strip()
    }
    if template == "kinetic_title_reveal" and _mapping(plan.get("title")).get("style") == "training_emphasis":
        required.add("training_prop")
    if _mapping(plan.get("lip_sync")).get("enabled") is True:
        required.update(MOUTH_ROLES)
    return required


def _polygon_area(points: list[tuple[float, float]]) -> float:
    return abs(sum(points[index][0] * points[(index + 1) % len(points)][1]
                   - points[(index + 1) % len(points)][0] * points[index][1]
                   for index in range(len(points)))) / 2


def _is_slanted(points: list[tuple[float, float]]) -> bool:
    # Polygon of a side panel must have a diagonal boundary, not only an
    # axis-aligned crop. Ignore tiny pixel-rounding differences.
    return any(abs(a[0] - b[0]) > .025 and abs(a[1] - b[1]) > .025
               for a, b in zip(points, points[1:] + points[:1]))


def _validate_text(text: Any, label: str, errors: list[str], warnings: list[str]) -> None:
    if not isinstance(text, str) or not text.strip():
        errors.append(f"{label} text is missing")
        return
    stripped = text.strip()
    if any(ord(character) < 32 and character not in "\n\t" for character in stripped):
        errors.append(f"{label} text contains a control character")
    if len(stripped) > 28:
        warnings.append(f"{label} text is {len(stripped)} characters; review legibility at playback speed")
    if "�" in stripped:
        errors.append(f"{label} text contains a replacement glyph")


def _template_beat_times(timed_beats: list[tuple[float, str, str]],
                         targets: dict[str, str], checks: list[dict[str, Any]],
                         errors: list[str]) -> dict[str, float]:
    """Require one unambiguous event for each renderer-facing action and role."""
    found: dict[str, float] = {}
    for action, target in targets.items():
        matching = [(at, role) for at, beat_action, role in timed_beats if beat_action == action]
        _check(checks, errors, f"{action}_beat", len(matching) == 1,
               f"{action} requires exactly one timed beat")
        if len(matching) == 1:
            at, role = matching[0]
            found[action] = at
            _check(checks, errors, f"{action}_target", role == target,
                   f"{action} must target {target}")
    return found


def _lens(value: Any) -> tuple[tuple[float, float], tuple[float, float]] | None:
    entry = _mapping(value)
    center, radius = _point(entry.get("center")), _point(entry.get("radius"))
    if center is None or radius is None or not (.035 <= radius[0] <= .32 and .035 <= radius[1] <= .32):
        return None
    if not (radius[0] <= center[0] <= 1 - radius[0]
            and radius[1] <= center[1] <= 1 - radius[1]):
        return None
    return center, radius


def validate_scene_plan(scene: dict[str, Any], asset_metadata: dict[str, Any] | None,
                        duration: float | None = None) -> dict[str, Any]:
    """Fail unsafe/missing template inputs before AE render.

    ``asset_metadata`` may be the complete scene metadata object or its
    ``psd_layer_asset`` value. Layer names must describe real PSD layers; the
    caller should also verify the downloaded PSD layer table before render.
    """
    plan = _mapping(scene.get("ae_effect_plan"))
    template = str(plan.get("template") or "").strip() or None
    if template is None:
        return _result("plan", None, [], [], [])
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []
    if template not in TEMPLATES:
        return _result("plan", template, [f"unsupported manga template: {template}"], [], checks)

    seconds = _duration(scene, duration)
    _check(checks, errors, "duration", seconds is not None, "scene duration must be positive and finite")
    if seconds is None:
        seconds = 0

    asset = _asset(asset_metadata)
    source = str(asset.get("local_path") or asset.get("gcs_path") or asset.get("object_path")
                 or asset.get("path") or "").strip()
    _check(checks, errors, "layered_source", source.lower().endswith(".psd"),
           "manga template requires a layered PSD source asset")
    local_path = asset.get("local_path")
    if isinstance(local_path, str) and local_path.strip():
        path = Path(local_path)
        try:
            signature = path.open("rb").read(4)
        except OSError:
            signature = b""
        _check(checks, errors, "psd_signature", signature == b"8BPS",
               "local PSD asset must exist and have an 8BPS header")
    raw_names = _raw_layer_names(asset_metadata)
    names = set(raw_names)
    required = _required_layers(plan, template)
    _check(checks, errors, "layer_manifest", bool(names),
           "PSD layer manifest is required to verify named character/background layers")
    _check(checks, errors, "unique_layer_names", len(raw_names) == len(names),
           "PSD layer names must be unique")
    missing = sorted(required - names)
    _check(checks, errors, "required_layers", not missing,
           "PSD layer manifest is missing: " + ", ".join(missing) if missing else "required PSD layers are declared")
    if plan.get("lip_sync") is not None:
        lip_errors = validate_lip_sync(
            plan.get("lip_sync"), template=template,
            character_key=str(_mapping(plan.get("character_role_keys")).get("character") or ""),
            duration=seconds,
        )
        _check(checks, errors, "lip_sync", not lip_errors,
               "; ".join(lip_errors) if lip_errors else "lip sync uses the approved final voice timing")
    if plan.get("caption_animation") is not None:
        caption_errors = validate_caption_animation(plan.get("caption_animation"), duration=seconds)
        _check(checks, errors, "caption_animation", not caption_errors,
               "; ".join(caption_errors) if caption_errors else "animated captions match the approved voice words")
        warnings.append("Review animated Korean glyphs, emphasis colors, subject overlap, and caption timing at playback speed")
    if plan.get("sfx_text_animation") is not None:
        sfx_text_errors = validate_sfx_text_animation(plan.get("sfx_text_animation"), duration=seconds)
        _check(checks, errors, "sfx_text_animation", not sfx_text_errors,
               "; ".join(sfx_text_errors) if sfx_text_errors else "onomatopoeia is bound to approved scene SFX event times")
        warnings.append("Review onomatopoeia spelling, placement, and sync against the final sound-effect mix")

    beats = plan.get("beats")
    _check(checks, errors, "beats", isinstance(beats, list) and bool(beats),
           "template requires timed beats")
    timed_beats: list[tuple[float, str, str]] = []
    if isinstance(beats, list):
        for index, beat in enumerate(beats, 1):
            entry = _mapping(beat)
            at = _number(entry.get("at_seconds"))
            action = str(entry.get("action") or "").strip()
            _check(checks, errors, f"beat_{index}_time", at is not None and 0 <= at < seconds,
                   f"beat {index} time must be inside the scene")
            _check(checks, errors, f"beat_{index}_action", bool(action), f"beat {index} action is missing")
            if at is not None and action:
                timed_beats.append((at, action.casefold(), str(entry.get("target") or "").casefold()))
            target = entry.get("target")
            if isinstance(target, (list, tuple, dict)):
                _check(checks, errors, f"beat_{index}_target", _point(target) is not None,
                       f"beat {index} target coordinates must be normalized to 0..1")
            if entry.get("text") is not None:
                _validate_text(entry.get("text"), f"beat {index}", errors, warnings)
    if timed_beats and [at for at, _, _ in timed_beats] != sorted(at for at, _, _ in timed_beats):
        errors.append("beats must be ordered by at_seconds")

    if template == "dialogue_closeup":
        closeup = _template_beat_times(timed_beats, {
            "face_hold": "character", "camera_push": "character",
        }, checks, errors)
        if len(closeup) == 2:
            _check(checks, errors, "closeup_beat_order",
                   closeup["face_hold"] <= closeup["camera_push"] < seconds,
                   "close-up must hold the speaker before its camera push")
        if not _mapping(plan.get("character_role_keys")).get("character"):
            errors.append("close-up needs an approved visible character key")
    elif template == "angled_triple_reaction":
        panels = plan.get("panels")
        _check(checks, errors, "panel_count", isinstance(panels, list) and len(panels) == 3,
               "angled triple reaction requires exactly three panels")
        if isinstance(panels, list):
            roles: list[str] = []
            slanted_count = 0
            for index, panel in enumerate(panels, 1):
                entry = _mapping(panel)
                role = str(entry.get("role") or "").strip().casefold()
                roles.append(role)
                raw_polygon = entry.get("polygon")
                points = [_point(point) for point in raw_polygon] if isinstance(raw_polygon, list) else []
                valid_polygon = len(points) >= 3 and all(point is not None for point in points)
                if valid_polygon:
                    solid_points = [point for point in points if point is not None]
                    valid_polygon = _polygon_area(solid_points) >= .002
                    slanted_count += int(_is_slanted(solid_points))
                _check(checks, errors, f"panel_{index}_polygon", valid_polygon,
                       f"panel {index} needs a nondegenerate normalized polygon")
                enter_at = _number(entry.get("enter_at"))
                _check(checks, errors, f"panel_{index}_enter", enter_at is not None and 0 <= enter_at < seconds,
                       f"panel {index} enter_at must be inside the scene")
            _check(checks, errors, "panel_roles", set(roles) ==
                   {"character_left", "character_center", "character_right"},
                   "panels must have distinct character_left, character_center, and character_right roles")
            _check(checks, errors, "angled_seams", slanted_count >= 2,
                   "at least two panel polygons need diagonal seams")
            for panel in panels:
                entry = _mapping(panel)
                role = str(entry.get("role") or "").casefold()
                enter_at = _number(entry.get("enter_at"))
                matching = [(at, action) for at, action, target in timed_beats
                            if action == "panel_reveal" and target == role]
                _check(checks, errors, f"panel_reveal_{role}", enter_at is not None and
                       any(abs(at - enter_at) <= 1 / 24 for at, _ in matching),
                       f"panel {role} reveal beat must match enter_at within one 24 fps frame")

    elif template == "body_following_qi":
        _check(checks, errors, "talisman_target", _point(plan.get("talisman_target")) is not None,
               "talisman_target must be normalized to 0..1 on the character")
        path = plan.get("qi_path")
        points = [_point(point) for point in path] if isinstance(path, list) else []
        valid = len(points) >= 2 and all(point is not None for point in points)
        _check(checks, errors, "qi_path", valid,
               "qi_path needs at least two normalized points along the body")
        if valid:
            solid_points = [point for point in points if point is not None]
            travel = sum(math.dist(a, b) for a, b in zip(solid_points, solid_points[1:]))
            _check(checks, errors, "qi_path_travel", travel >= .05,
                   "qi_path must travel across the body, not collapse to one point")
        attach = [at for at, action, _ in timed_beats if action == "talisman_attach"]
        trace = [at for at, action, _ in timed_beats if action == "qi_trace_start"]
        _check(checks, errors, "qi_timing", bool(attach and trace and min(attach) <= min(trace)),
               "qi trace must start after the timed talisman attachment")
        warnings.append("Body alignment of qi_path requires visual review against the rendered character layer")

    elif template == "ink_splat_impact":
        impact = _mapping(plan.get("impact"))
        at = _number(impact.get("at_seconds"))
        point = _point(impact)
        _check(checks, errors, "impact_time", at is not None and 0 <= at < seconds,
               "impact.at_seconds must be inside the scene")
        _check(checks, errors, "impact_target", point is not None,
               "impact x/y must be normalized to 0..1")
        _validate_text(impact.get("text"), "impact onomatopoeia", errors, warnings)
        if at is not None:
            matching = [beat_time for beat_time, action, _ in timed_beats
                        if any(token in action for token in ("impact", "ink", "splat", "onomatopoeia"))]
            _check(checks, errors, "impact_beat_alignment", any(abs(beat_time - at) <= 1 / 24 for beat_time in matching),
                   "ink/impact beat must align with impact.at_seconds within one 24 fps frame")
            burst = [beat_time for beat_time, action, _ in timed_beats if action == "ink_splat"]
            lettering = [beat_time for beat_time, action, _ in timed_beats if action == "onomatopoeia"]
            _check(checks, errors, "impact_burst_lettering", bool(burst and lettering and
                   at <= min(burst) <= at + .15 and at <= min(lettering) <= at + .2),
                   "ink burst and onomatopoeia must begin within 0.2 seconds after impact")
            if lettering:
                _check(checks, errors, "lettering_hold", seconds - min(lettering) >= .35,
                       "onomatopoeia must remain in the clip for at least 0.35 seconds")
        if point is not None and (point[0] < .04 or point[0] > .96 or point[1] < .04 or point[1] > .96):
            warnings.append("Impact is near an edge; review splat and text safe margins")

    elif template == "wall_impact_debris":
        impact = _mapping(plan.get("impact"))
        at, point = _number(impact.get("at_seconds")), _point(impact)
        _check(checks, errors, "wall_impact_time", at is not None and 0 <= at < seconds,
               "wall impact.at_seconds must be inside the scene")
        _check(checks, errors, "wall_impact_target", point is not None,
               "wall impact x/y must be normalized to 0..1")
        wall_beats = _template_beat_times(timed_beats, {
            "wall_contact": "impact", "wall_reveal": "wall_broken",
            "debris_burst": "impact", "debris_settle": "impact",
        }, checks, errors)
        if at is not None and "wall_contact" in wall_beats:
            _check(checks, errors, "wall_contact_alignment", abs(wall_beats["wall_contact"] - at) <= 1 / 24,
                   "wall_contact must match impact.at_seconds within one 24 fps frame")
        if len(wall_beats) == 4:
            contact, reveal = wall_beats["wall_contact"], wall_beats["wall_reveal"]
            burst, settle = wall_beats["debris_burst"], wall_beats["debris_settle"]
            _check(checks, errors, "wall_beat_order", contact <= reveal <= burst < settle,
                   "wall reveal and debris burst must follow contact before debris settles")
            _check(checks, errors, "wall_reveal_timing", reveal <= contact + .15,
                   "broken wall must appear within 0.15 seconds after contact")
            _check(checks, errors, "debris_burst_timing", burst <= contact + .2,
                   "debris must burst within 0.2 seconds after contact")
            _check(checks, errors, "wall_settle_hold", seconds - settle >= .15 - 1e-6,
                   "debris settle must leave at least 0.15 seconds in the clip")
        if point is not None and (point[0] < .05 or point[0] > .95 or point[1] < .05 or point[1] > .95):
            warnings.append("Wall impact is near an edge; review fracture and debris safe margins")

    elif template == "glasses_reflection":
        reflection = _mapping(plan.get("reflection"))
        at = _number(reflection.get("at_seconds"))
        _check(checks, errors, "reflection_time", at is not None and 0 <= at < seconds,
               "reflection.at_seconds must be inside the scene")
        left, right = _lens(reflection.get("left_lens")), _lens(reflection.get("right_lens"))
        _check(checks, errors, "left_lens", left is not None,
               "left_lens needs normalized center and bounded, nonzero radius inside the frame")
        _check(checks, errors, "right_lens", right is not None,
               "right_lens needs normalized center and bounded, nonzero radius inside the frame")
        if left is not None and right is not None:
            _check(checks, errors, "lens_order", left[0][0] + left[1][0] < right[0][0] - right[1][0],
                   "left and right lens masks must be distinct and nonoverlapping")
        reflection_beats = _template_beat_times(timed_beats, {
            "reflection_reveal": "reflection_scene", "lens_glint": "reflection_scene",
            "camera_push": "character",
        }, checks, errors)
        if at is not None and "reflection_reveal" in reflection_beats:
            _check(checks, errors, "reflection_alignment", abs(reflection_beats["reflection_reveal"] - at) <= 1 / 24,
                   "reflection_reveal must match reflection.at_seconds within one 24 fps frame")
        if len(reflection_beats) == 3:
            reveal, glint = reflection_beats["reflection_reveal"], reflection_beats["lens_glint"]
            push = reflection_beats["camera_push"]
            _check(checks, errors, "reflection_beat_order", reveal < glint <= push,
                   "lens glint and camera push must follow reflection reveal")
            _check(checks, errors, "reflection_glint_timing", glint <= reveal + .5,
                   "lens glint must occur within 0.5 seconds of reflection reveal")
            _check(checks, errors, "reflection_hold", seconds - push >= .1 - 1e-6,
                   "camera push must leave at least 0.1 seconds to see the reflection")

    elif template == "kinetic_title_reveal":
        title = _mapping(plan.get("title"))
        at, position = _number(title.get("at_seconds")), _point(title.get("position"))
        _check(checks, errors, "title_time", at is not None and 0 <= at < seconds,
               "title.at_seconds must be inside the scene")
        _check(checks, errors, "title_position", position is not None,
               "title.position must be normalized to 0..1")
        _check(checks, errors, "title_style", title.get("style") in {"threat_red", "training_emphasis"},
               "title.style must be threat_red or training_emphasis")
        _validate_text(title.get("text"), "title", errors, warnings)
        _validate_text(title.get("accent_text"), "title accent", errors, warnings)
        if isinstance(title.get("text"), str) and isinstance(title.get("accent_text"), str):
            _check(checks, errors, "title_accent", bool(title["accent_text"].strip())
                   and title["accent_text"].strip() in title["text"],
                   "title accent_text must be a visible substring of title.text")
        title_beats = _template_beat_times(timed_beats, {
            "text_reveal": "title", "text_punch": "title", "text_hold": "title",
        }, checks, errors)
        if at is not None and "text_reveal" in title_beats:
            _check(checks, errors, "title_alignment", abs(title_beats["text_reveal"] - at) <= 1 / 24,
                   "text_reveal must match title.at_seconds within one 24 fps frame")
        if len(title_beats) == 3:
            reveal, punch, hold = (title_beats[action] for action in ("text_reveal", "text_punch", "text_hold"))
            _check(checks, errors, "title_beat_order", reveal < punch <= hold,
                   "text punch and hold must follow text reveal")
            _check(checks, errors, "title_punch_timing", punch <= reveal + .35,
                   "text punch must occur within 0.35 seconds of text reveal")
            _check(checks, errors, "title_readable_hold", seconds - hold >= .35 - 1e-6,
                   "title must remain in the clip for at least 0.35 seconds after text_hold")
        if isinstance(beats, list):
            for action, field in (("text_reveal", "text"), ("text_punch", "accent_text")):
                matching = [_mapping(beat) for beat in beats if _mapping(beat).get("action") == action]
                if len(matching) == 1:
                    _check(checks, errors, f"{action}_copy", matching[0].get("text") == title.get(field),
                           f"{action} text must match title.{field}")
        if position is not None and (position[0] < .08 or position[0] > .92 or
                                     position[1] < .10 or position[1] > .90):
            warnings.append("Title is near an edge; review full glyph bounds and safe margins")

    elif template == "backlit_hand_reveal":
        _check(checks, errors, "light_origin", _point(plan.get("light_origin")) is not None,
               "light_origin must be normalized to 0..1")
        light_beats = _template_beat_times(timed_beats, {
            "hand_raise": "hand_foreground", "light_ignite": "light_origin",
            "ray_burst": "light_origin", "afterglow": "light_origin",
        }, checks, errors)
        if len(light_beats) == 4:
            raise_at, ignite, burst, glow = (light_beats[action] for action in
                                            ("hand_raise", "light_ignite", "ray_burst", "afterglow"))
            _check(checks, errors, "backlight_beat_order", raise_at <= ignite < burst <= glow,
                   "hand raise and light ignition must precede ray burst and afterglow")
            _check(checks, errors, "backlight_ray_timing", burst <= ignite + min(1.5, seconds * .15),
                   "rays must burst soon after light ignition")
            _check(checks, errors, "backlight_hold", seconds - glow >= .15 - 1e-6,
                   "afterglow must leave at least 0.15 seconds in the clip")
        warnings.append("Palm alignment of light_origin requires visual review against the hand layer")

    return _result("plan", template, errors, warnings, checks,
                   duration_seconds=seconds, required_layers=sorted(required), declared_layers=sorted(names))


def _ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def _probe_video(path: Path) -> dict[str, Any]:
    command = [_ffmpeg(), "-hide_banner", "-i", str(path), "-map", "0:v:0",
               "-frames:v", "1", "-f", "null", "-"]
    completed = subprocess.run(command, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=90)
    stderr = completed.stderr
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    video_line = next((line for line in stderr.splitlines() if "Video:" in line), "")
    dimensions = re.search(r"(?<!\d)(\d{2,5})x(\d{2,5})(?!\d)", video_line)
    rate = re.search(r"([\d.]+)\s+fps", video_line)
    if completed.returncode or not duration_match or not dimensions:
        raise ValueError("MP4 has no decodable video stream or readable duration/resolution")
    hours, minutes, seconds = duration_match.groups()
    return {"duration_seconds": int(hours) * 3600 + int(minutes) * 60 + float(seconds),
            "width": int(dimensions.group(1)), "height": int(dimensions.group(2)),
            "fps": float(rate.group(1)) if rate else None}


def _sample_frame(path: Path, at_seconds: float) -> dict[str, Any]:
    from PIL import Image, ImageChops, ImageStat

    completed = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error",
                                "-ss", f"{at_seconds:.3f}", "-i", str(path),
                                "-map", "0:v:0", "-frames:v", "1", "-f", "image2pipe",
                                "-vcodec", "png", "-"],
                               capture_output=True, timeout=90)
    if completed.returncode or not completed.stdout:
        raise ValueError(f"cannot decode video frame at {at_seconds:.3f}s")
    with Image.open(io.BytesIO(completed.stdout)) as image:
        small = image.convert("RGB")
        small.thumbnail((256, 144))
        grayscale = small.convert("L")
        stats = ImageStat.Stat(grayscale)
        return {"at_seconds": round(at_seconds, 3), "mean_luma": round(stats.mean[0], 2),
                "luma_stddev": round(stats.stddev[0], 2), "image": small.copy()}


def validate_render(scene: dict[str, Any], mp4_path: Path | str, fps: float | None = None,
                    *, duration_seconds: float | None = None) -> dict[str, Any]:
    """Check exported media integrity and event-frame evidence before publish.

    A frame difference is only evidence of motion, not proof that a specific
    layer, burst or glyph is correct. The report always requests visual review.
    """
    plan = _mapping(scene.get("ae_effect_plan"))
    template = str(plan.get("template") or "").strip() or None
    if template is None:
        return _result("render", None, [], [], [])
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []
    if template not in TEMPLATES:
        return _result("render", template, [f"unsupported manga template: {template}"], [], checks)
    path = Path(mp4_path)
    _check(checks, errors, "mp4_file", path.is_file() and path.suffix.lower() == ".mp4"
           and path.stat().st_size >= 1024, "render must be a nonempty MP4 file")
    if errors:
        return _result("render", template, errors, warnings, checks)
    try:
        probe = _probe_video(path)
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired, ImportError) as exc:
        return _result("render", template, [f"MP4 probe failed: {exc}"], warnings, checks)
    expected = _duration(scene, duration_seconds)
    _check(checks, errors, "video_duration", expected is not None and
           .8 * expected <= probe["duration_seconds"] <= 1.25 * expected + .1,
           "render duration must be within 80–125% of the planned AE clip duration")
    _check(checks, errors, "video_dimensions", probe["width"] >= 640 and probe["height"] >= 360,
           "render resolution must be at least 640x360")
    actual_fps = probe.get("fps")
    if fps is not None:
        _check(checks, errors, "video_fps", actual_fps is not None and abs(actual_fps - fps) <= 1,
               "render frame rate differs from AE plan by more than 1 fps")
    if errors:
        return _result("render", template, errors, warnings, checks, video=probe)

    duration = probe["duration_seconds"]
    times = [min(.3, duration / 4), duration / 2, max(.0, duration - .25)]
    lip_sync = _mapping(plan.get("lip_sync"))
    mouth_times: tuple[float, float] | None = None
    if lip_sync.get("enabled") is True:
        cues = lip_sync.get("cues") if isinstance(lip_sync.get("cues"), list) else []
        first_open = next((item for item in cues if isinstance(item, dict) and item.get("pose") == "open"), None)
        first_closed = next((item for item in cues if isinstance(item, dict) and item.get("pose") == "closed"), None)
        if not first_open or not first_closed:
            return _result("render", template, ["lip sync needs closed and open mouth frames"], warnings, checks, video=probe)
        mouth_times = (round(min(duration - .03, float(first_closed["at_seconds"]) + .5 / (actual_fps or 24)), 3),
                       round(min(duration - .03, float(first_open["at_seconds"]) + .5 / (actual_fps or 24)), 3))
        times.extend(mouth_times)
    beats = plan.get("beats")
    ignite_at = next((beat.get("at_seconds") for beat in beats
                      if isinstance(beat, dict) and beat.get("action") == "light_ignite"), None) if isinstance(beats, list) else None
    event_specs = {
        "ink_splat_impact": ("impact", _mapping(plan.get("impact")).get("at_seconds"), "planned impact"),
        "wall_impact_debris": ("wall_contact", _mapping(plan.get("impact")).get("at_seconds"), "planned wall contact"),
        "glasses_reflection": ("reflection", _mapping(plan.get("reflection")).get("at_seconds"), "planned reflection reveal"),
        "kinetic_title_reveal": ("title", _mapping(plan.get("title")).get("at_seconds"), "planned title reveal"),
        "backlit_hand_reveal": ("light_ignite", ignite_at, "planned light ignition"),
    }
    event_name = None
    event_times: tuple[float, float] | None = None
    event_description = None
    directed_events: list[tuple[int, float, float, str]] = []
    if template == "directed_performance" and isinstance(beats, list):
        for index, beat in enumerate(beats, 1):
            entry = _mapping(beat)
            action = str(entry.get("action") or "")
            if action not in {"pose_reveal", "prop_reveal", "mask_reveal"}:
                continue
            moment = _number(entry.get("at_seconds"))
            _check(checks, errors, f"directorial_beat_{index}_in_video",
                   moment is not None and 0 <= moment <= duration - .07,
                   f"directorial action {action} must occur within the rendered clip")
            if moment is not None:
                pair = (max(0.0, moment - 0.12), min(duration - .03, moment + 0.18))
                directed_events.append((index, pair[0], pair[1], str(entry.get("target") or "")))
                times.extend(pair)
    if template in event_specs:
        event_name, raw_time, event_description = event_specs[template]
        event_at = _number(raw_time)
        _check(checks, errors, "planned_event_in_video", event_at is not None and 0 <= event_at <= duration - .07,
               f"{event_description} must occur in the rendered video")
        if errors:
            return _result("render", template, errors, warnings, checks, video=probe)
        event_times = (max(0, event_at - .12), min(duration - .03, event_at + .12))
        times.extend(event_times)
    caption_pairs = []
    for cue in _mapping(plan.get("caption_animation")).get("captions", []):
        start = _number(_mapping(cue).get("start_seconds"))
        position = _point(_mapping(cue).get("position"))
        if start is not None and position is not None and start >= .08:
            pair = (round(max(0, start - .06), 3), round(min(duration - .03, start + .18), 3), position)
            caption_pairs.append(pair)
            times.extend(pair[:2])
    sfx_text_pairs = []
    for cue in _mapping(plan.get("sfx_text_animation")).get("cues", []):
        start = _number(_mapping(cue).get("start_seconds"))
        position = _point(_mapping(cue).get("position"))
        if start is not None and position is not None and start >= .08:
            pair = (round(max(0, start - .06), 3), round(min(duration - .03, start + .18), 3), position)
            sfx_text_pairs.append(pair)
            times.extend(pair[:2])
    samples: list[dict[str, Any]] = []
    try:
        for time_value in sorted(set(round(max(0, t), 3) for t in times)):
            samples.append(_sample_frame(path, time_value))
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired, ImportError) as exc:
        return _result("render", template, [f"MP4 sample-frame decode failed: {exc}"], warnings,
                       checks, video=probe)
    blank = all((sample["mean_luma"] < 2 or sample["mean_luma"] > 253)
                and sample["luma_stddev"] < 1 for sample in samples)
    _check(checks, errors, "nonblank_frames", not blank,
           "sampled frames must not all be flat black or white")
    from PIL import ImageChops, ImageStat

    def difference(before: dict[str, Any], after: dict[str, Any]) -> float:
        diff = ImageChops.difference(before["image"], after["image"])
        return round(sum(ImageStat.Stat(diff).mean) / 3, 2)

    if len(samples) >= 2:
        differences = []
        for before, after in zip(samples, samples[1:]):
            differences.append(difference(before, after))
        if max(differences, default=0) < 0.7:
            warnings.append("Sampled frames show almost no change; verify the planned animation")
    else:
        differences = []
    event_difference = None
    mouth_difference = None
    if mouth_times is not None:
        by_time = {item["at_seconds"]: item for item in samples}
        closed = by_time.get(mouth_times[0])
        opened = by_time.get(mouth_times[1])
        box = lip_sync.get("mouth_box")
        if closed and opened and isinstance(box, list) and len(box) == 4:
            from PIL import ImageChops, ImageStat
            w, h = closed["image"].size
            crop = tuple(round(float(box[index]) * (w if index % 2 == 0 else h)) for index in range(4))
            before = closed["image"].crop(crop)
            after = opened["image"].crop(crop)
            mouth_difference = round(sum(ImageStat.Stat(ImageChops.difference(before, after)).mean) / 3, 2)
        _check(checks, errors, "mouth_frame_change", mouth_difference is not None and mouth_difference >= .5,
               "the approved mouth area must visibly change between closed and spoken frames")
        warnings.append("Mouth-area frame change does not prove lip sync; listen to the final audio and inspect seam-free poses")
    if event_times is not None:
        by_time = {item["at_seconds"]: item for item in samples}
        before = by_time.get(round(event_times[0], 3))
        after = by_time.get(round(event_times[1], 3))
        if before is not None and after is not None:
            event_difference = difference(before, after)
            _check(checks, errors, f"{event_name}_frame_change", event_difference >= .7,
                   f"frames around the {event_description} must show a visible change")
        warnings.append(f"Frame change cannot prove the {event_description} is visually correct; inspect the event frame")
    if directed_events:
        by_time = {item["at_seconds"]: item for item in samples}
        for index, before_at, after_at, target in directed_events:
            before, after = by_time.get(round(before_at, 3)), by_time.get(round(after_at, 3))
            change = difference(before, after) if before is not None and after is not None else 0.0
            _check(checks, errors, f"directorial_beat_{index}_frame_change", change >= .35,
                   f"render must visibly change around directed beat {index} ({target})")
        warnings.append("Frame-change checks do not prove pose identity or clean compositing; inspect each directed beat at playback speed")
    if caption_pairs:
        by_time = {item["at_seconds"]: item for item in samples}
        for index, (before_at, after_at, position) in enumerate(caption_pairs, 1):
            before, after = by_time.get(before_at), by_time.get(after_at)
            if before and after:
                width, height = before["image"].size
                x, y = position
                bounds = (max(0, round((x - .24) * width)), max(0, round((y - .13) * height)),
                          min(width, round((x + .24) * width)), min(height, round((y + .13) * height)))
                region_before = {"image": before["image"].crop(bounds)}
                region_after = {"image": after["image"].crop(bounds)}
                _check(checks, errors, f"animated_caption_{index}_frame_change",
                       difference(region_before, region_after) >= .7,
                       f"caption {index} area must visibly change at its approved spoken word")
        warnings.append("Caption-area frame change does not prove legibility or exact lip/voice sync; inspect the rendered text while listening")
    if sfx_text_pairs:
        by_time = {item["at_seconds"]: item for item in samples}
        for index, (before_at, after_at, position) in enumerate(sfx_text_pairs, 1):
            before, after = by_time.get(before_at), by_time.get(after_at)
            if before and after:
                width, height = before["image"].size
                bounds = (max(0, round((position[0] - .24) * width)), max(0, round((position[1] - .13) * height)),
                          min(width, round((position[0] + .24) * width)), min(height, round((position[1] + .13) * height)))
                region_before = {"image": before["image"].crop(bounds)}
                region_after = {"image": after["image"].crop(bounds)}
                _check(checks, errors, f"sfx_text_{index}_frame_change",
                       difference(region_before, region_after) >= .7,
                       f"SFX text cue {index} area must visibly change at its sound-effect event")
        warnings.append("SFX text frame change does not prove exact sync with the final mixed effect audio; inspect playback")
    sample_summary = [{key: value for key, value in item.items() if key != "image"} for item in samples]
    return _result("render", template, errors, warnings, checks, video=probe,
                   samples=sample_summary, adjacent_frame_differences=differences,
                   mouth_frame_difference=mouth_difference,
                   event_frame_difference=event_difference,
                   impact_frame_difference=event_difference if template == "ink_splat_impact" else None)
