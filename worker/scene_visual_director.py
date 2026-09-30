"""Timed, asset-aware direction contracts for uploaded-video AE finishing."""
from __future__ import annotations

from typing import Any


PERSONA = """You are AIR Studio's Scene Visual Director. For each scene, interpret
its dramatic purpose, narration, emotional change, neighboring-scene context,
and the uploaded source clip when clip keyframes are provided. The uploaded
clip is the visual ground truth: preserve its action, character identity,
wardrobe, framing, color design, and duration. Never invent movement or
expressions absent from the clip.

Create a concise timed AE direction, not an image storyboard. Do not request
new full-frame images per second, do not impose any image FPS, and do not turn
camera zoom into a substitute for scene direction. Choose the smallest set of
story-motivated beats; a deliberate hold with no effect is valid. Avoid
repetitive zooms, looping motion, arbitrary particles, fake depth, and effects
that compete with faces or dialogue.

For every beat provide start_seconds, end_seconds, action, target, and an
observable attention_target when useful. Tie timing to a visible action, line,
reaction, reveal, or pause in the supplied clip. Choose AE operations only
from: camera_move, hold, light_flicker, atmosphere_drift, depth_parallax,
mask_reveal, pose_change, prop_motion, shot_sequence, transition. Request
required_layers only when a specific effect cannot be made safely from the
uploaded clip alone. For every requested layer give its role, purpose, source,
and a generation prompt. Do not request replacement frames or generated
storyboards. If actual clip keyframes are not available yet, mark the visual
review pending and keep any direction provisional; the final direction must
be checked against the uploaded clip before AE starts.

Keep effects restrained and culturally/period appropriate. Prefer preserving
the input clip over adding synthetic content. Every plan must include
observable QA assertions for timing, identity, continuity, and unintended
motion. A missing layer must be reported as a dependency; do not silently
replace the intended direction with a generic zoom."""


def validate_directorial_plans(scenes: list[dict[str, Any]], result: Any) -> list[dict[str, Any]]:
    """Validate timed directions without imposing generated storyboard frames."""
    plans = result.get("scene_directions") if isinstance(result, dict) else None
    if not isinstance(plans, list) or len(plans) != len(scenes):
        raise ValueError(f"visual director must return exactly {len(scenes)} scene_directions")
    normalized: list[dict[str, Any]] = []
    allowed = {"camera_move", "hold", "light_flicker", "atmosphere_drift", "depth_parallax",
               "mask_reveal", "pose_change", "prop_motion", "shot_sequence", "transition"}
    known_layers = {
        "background", "character", "character_left", "character_center", "character_right",
        "hand_foreground", "talisman", "reflection_scene", "training_prop", "title_backdrop",
        "debris", "qi_overlay", "ink_splat", "speedlines", "lens_glint", "light_core", "light_rays",
        "pose_sleeping", "pose_waking", "pose_turning", "pose_resting", "blanket", "shoji",
        "prop_focus", "mouth_closed", "mouth_half", "mouth_open",
    }
    for index, (scene, raw) in enumerate(zip(scenes, plans), 1):
        if not isinstance(raw, dict):
            raise ValueError(f"visual direction {index} must be an object")
        try:
            duration = float(scene.get("duration_seconds") or scene.get("target_duration") or 0)
        except (TypeError, ValueError):
            duration = 0
        intent = str(raw.get("dramatic_intent") or "").strip()
        beats = raw.get("timed_beats")
        operations = raw.get("ae_operations")
        layers = raw.get("required_layers")
        keyframe_requests = raw.get("additional_keyframes", [])
        qa = raw.get("qa_assertions")
        if duration <= 0 or not intent or not isinstance(beats, list) or not beats:
            raise ValueError(f"visual direction {index} needs duration, dramatic_intent, and timed_beats")
        if not isinstance(operations, list) or not operations or not set(operations) <= allowed:
            raise ValueError(f"visual direction {index} has missing or unsupported ae_operations")
        if not isinstance(layers, list) or not isinstance(keyframe_requests, list) or not isinstance(qa, list) or not qa:
            raise ValueError(f"visual direction {index} needs required_layers, additional_keyframes, and observable qa_assertions")
        unknown_layers = {str(x.get("role") if isinstance(x, dict) else x).strip() for x in layers} - known_layers
        if unknown_layers:
            raise ValueError(f"visual direction {index} names unsupported layer roles: {sorted(unknown_layers)}")
        if any(not isinstance(layer, dict) for layer in layers):
            layers = [{"role": str(layer).strip(), "purpose": "", "source": "uploaded_clip"} for layer in layers]
        clean_beats = []
        last_time = -1.0
        for beat_number, beat in enumerate(beats, 1):
            if not isinstance(beat, dict):
                raise ValueError(f"visual direction {index} beat {beat_number} must be an object")
            try:
                start = float(beat.get("start_seconds"))
                end = float(beat.get("end_seconds"))
            except (TypeError, ValueError):
                raise ValueError(f"visual direction {index} beat {beat_number} needs numeric start/end")
            action = str(beat.get("action") or "").strip()
            target = str(beat.get("target") or "").strip()
            if start < 0 or end <= start or end > duration or start < last_time or not action or not target:
                raise ValueError(f"visual direction {index} beat {beat_number} has invalid timing/action/target")
            clean_beats.append({**beat, "start_seconds": round(start, 3), "end_seconds": round(end, 3),
                                "action": action, "target": target})
            last_time = start
        clean_keyframes = []
        for layer_number, layer in enumerate(keyframe_requests, 1):
            if not isinstance(layer, dict):
                raise ValueError(f"visual direction {index} additional layer {layer_number} must be an object")
            role = str(layer.get("role") or "").strip()
            reason = str(layer.get("reason") or "").strip()
            prompt = str(layer.get("image_prompt") or "").strip()
            if role not in known_layers or not reason or not prompt:
                raise ValueError(f"visual direction {index} additional layer {layer_number} needs a known role, reason, and image_prompt")
            clean_keyframes.append({**layer, "role": role, "reason": reason, "image_prompt": prompt})
        direction = {
            "status": "planned",
            "persona": "scene_visual_director",
            "dramatic_intent": intent,
            "visual_strategy": str(raw.get("visual_strategy") or "").strip(),
            "source_video_review_status": "reviewed" if raw.get("source_video_reviewed") is True else "pending_upload_review",
            "timed_beats": clean_beats,
            "additional_keyframes": clean_keyframes,
            "keyframe_requests": clean_keyframes,
            "required_layers": [layer["role"] if isinstance(layer, dict) else str(layer).strip() for layer in layers],
            "layer_specs": layers,
            "ae_operations": list(dict.fromkeys(str(x) for x in operations)),
            "requires_layered_assets": bool(layers or clean_keyframes),
            "continuity_rules": raw.get("continuity_rules") if isinstance(raw.get("continuity_rules"), list) else [],
            "qa_assertions": [str(x).strip() for x in qa if str(x).strip()],
        }
        if not direction["visual_strategy"] or not direction["qa_assertions"]:
            raise ValueError(f"visual direction {index} needs visual_strategy and nonempty qa_assertions")
        scene["ae_directorial_plan"] = direction
        normalized.append(direction)
    return normalized
