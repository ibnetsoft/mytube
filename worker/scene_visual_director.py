"""Timed, asset-aware direction contracts shared by script, image, and AE workers."""
from __future__ import annotations

import copy
from typing import Any
from scene_direction_policy import CONTRACT as EXECUTION_CONTRACT, validate_topic, validate_execution


from purpose_direction import validate_script as validate_purpose_script
from depth_finishing import TASK as DEPTH_TASK, normalize as normalize_depth_finishing
from script_parallax import TASK as PARALLAX_TASK, selection as parallax_selection

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

Classify scene_role as dialogue, reaction, clue_reveal, location, tension,
transition, resolution, narration, or hold. Select exactly one primary_effect
from the AE operation allowlist and no more than two secondary_effects from
camera_move, light_flicker, atmosphere_drift, or transition. Supply
one normalized focus_target with type, optional layer, x, y, and reason. Supply
effect_limits for intensity, speed, maximum scale change, movement ratio, and
rotation. Prefer a hold when movement would not improve the story beat. Do not
repeat the same conspicuous primary effect through adjacent scenes; vary the
visual rhythm using holds and restrained alternatives. Set fallback to
original_visual unless an existing source clip must be copied unchanged.

Keep effects restrained and culturally/period appropriate. Prefer preserving
the input clip over adding synthetic content. Every plan must include
observable QA assertions for timing, identity, continuity, and unintended
motion. A missing layer must be reported as a dependency; do not silently
replace the intended direction with a generic zoom.

For still-image scenes that explicitly set eligible_for_eye_blink=true, also
direct whether one visible character should blink. Eye blinks are acting beats,
not a decoration or a periodic loop. Use them selectively across the sequence:
prefer a listening reaction, a breath after dialogue, or an emotional release;
suppress them during shock, an intense stare, fast action, a very short shot,
or whenever the eyes may be hidden or too small. Do not enable blinking in
every eligible scene, and do not make adjacent characters blink together.
Return exact irregular cue times, never a repeating interval. The final image
analyzer must still verify the named character and both eye boxes; uncertainty
skips only the blink effect."""


PERSONA += "\n\n" + PARALLAX_TASK + "\n" + DEPTH_TASK

ALLOWED_OPERATIONS = {
    "camera_move", "hold", "light_flicker", "atmosphere_drift", "depth_parallax",
    "mask_reveal", "pose_change", "prop_motion", "shot_sequence", "transition",
}
PRIMARY_EFFECT_PRIORITY = (
    "pose_change", "prop_motion", "mask_reveal", "shot_sequence", "depth_parallax",
    "camera_move", "transition", "light_flicker", "atmosphere_drift", "hold",
)
SECONDARY_EFFECTS = {"camera_move", "light_flicker", "atmosphere_drift", "transition"}
SCENE_ROLES = {
    "dialogue", "reaction", "clue_reveal", "location", "tension", "transition",
    "resolution", "narration", "hold", "action",
}


def _number(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return round(max(minimum, min(parsed, maximum)), 4)


def _focus_target(raw: Any, beats: list[dict[str, Any]]) -> dict[str, Any]:
    candidate = raw if isinstance(raw, dict) else {}
    if not candidate:
        attention = next((beat.get("attention_target") for beat in beats
                          if isinstance(beat.get("attention_target"), (list, dict))), None)
        if isinstance(attention, dict):
            candidate = attention
        elif isinstance(attention, list) and len(attention) >= 2:
            candidate = {"x": attention[0], "y": attention[1]}
    return {
        "type": str(candidate.get("type") or "scene_focus").strip()[:80],
        "layer": str(candidate.get("layer") or "").strip()[:80],
        "x": _number(candidate.get("x"), 0.5, 0.0, 1.0),
        "y": _number(candidate.get("y"), 0.5, 0.0, 1.0),
        "reason": str(candidate.get("reason") or "dramatic attention target").strip()[:300],
    }


def _effect_selection(raw: dict[str, Any], operations: list[str]) -> tuple[str, list[str]]:
    requested_primary = str(raw.get("primary_effect") or "").strip()
    if requested_primary and requested_primary not in ALLOWED_OPERATIONS:
        raise ValueError(f"unsupported primary_effect: {requested_primary}")
    if requested_primary and requested_primary not in operations:
        raise ValueError("primary_effect must also appear in ae_operations")
    primary = requested_primary or next((item for item in PRIMARY_EFFECT_PRIORITY if item in operations), "hold")
    requested_secondary = raw.get("secondary_effects")
    if requested_secondary is None:
        secondary = [item for item in operations if item in SECONDARY_EFFECTS and item != primary][:2]
    else:
        if not isinstance(requested_secondary, list):
            raise ValueError("secondary_effects must be a list")
        secondary = list(dict.fromkeys(str(item).strip() for item in requested_secondary if str(item).strip()))
        unsupported = set(secondary) - SECONDARY_EFFECTS
        if unsupported:
            raise ValueError(f"unsupported secondary_effects: {sorted(unsupported)}")
        missing = set(secondary) - set(operations)
        if missing:
            raise ValueError(f"secondary_effects must also appear in ae_operations: {sorted(missing)}")
        secondary = [item for item in secondary if item != primary]
    if len(secondary) > 2:
        raise ValueError("at most two secondary effects are allowed")
    return primary, secondary


def _eye_blink_plan(raw: Any, duration: float, eligible: bool) -> dict[str, Any]:
    candidate = raw if isinstance(raw, dict) else {}
    enabled = bool(candidate.get("enabled")) and eligible and duration >= 2.5
    reason = str(candidate.get("reason") or candidate.get("suppress_reason") or "").strip()[:300]
    character = str(candidate.get("character") or "").strip()[:100]
    clean_cues: list[dict[str, Any]] = []
    if enabled:
        cues = candidate.get("cues")
        if not character or not reason or not isinstance(cues, list) or not cues:
            raise ValueError("enabled eye_blink_plan needs character, reason, and cues")
        if len(cues) > 2:
            raise ValueError("eye_blink_plan allows at most two acting cues per scene")
        last = -1.0
        for cue_number, cue in enumerate(cues, 1):
            if not isinstance(cue, dict):
                raise ValueError(f"eye blink cue {cue_number} must be an object")
            at = _number(cue.get("at_seconds"), -1, -1, max(duration, 0))
            close = _number(cue.get("duration_seconds"), 0.12, 0.08, 0.2)
            kind = str(cue.get("type") or "single").strip()
            if kind not in {"single", "double"}:
                raise ValueError("eye blink cue type must be single or double")
            if at < 0.25 or at + close > duration - 0.2 or at <= last:
                raise ValueError("eye blink cues must be ordered and clear of scene boundaries")
            clean_cues.append({"at_seconds": round(at, 3), "duration_seconds": close, "type": kind})
            last = at
    return {
        "enabled": enabled,
        "character": character if enabled else "",
        "reason": reason or ("not selected by scene direction" if eligible else "scene is not an eligible still image"),
        "cues": clean_cues,
        "source": "scene_visual_director",
        "validation": "pending_final_image" if enabled else "not_required",
        "fallback": "skip_blink",
    }


def validate_directorial_plans(
    scenes: list[dict[str, Any]], result: Any, *, direction_profile: str = "standard", require_execution: bool = False,
) -> list[dict[str, Any]]:
    """Validate timed directions without imposing generated storyboard frames."""
    plans = result.get("scene_directions") if isinstance(result, dict) else None
    if not isinstance(plans, list) or len(plans) != len(scenes):
        raise ValueError(f"visual director must return exactly {len(scenes)} scene_directions")
    topic = validate_topic(result.get('topic_direction')) if require_execution else None
    normalized: list[dict[str, Any]] = []
    allowed = ALLOWED_OPERATIONS
    known_layers = {
        "background", "foreground", "character", "character_left", "character_center", "character_right",
        "hand_foreground", "talisman", "reflection_scene", "training_prop", "title_backdrop",
        "debris", "qi_overlay", "ink_splat", "speedlines", "lens_glint", "light_core", "light_rays",
        "pose_sleeping", "pose_waking", "pose_turning", "pose_resting", "blanket", "shoji",
        "prop_focus", "mouth_closed", "mouth_half", "mouth_open",
        "hair_cloth", "atmosphere", "light_overlay",
    }
    consecutive_blinks = 0
    for index, (scene, raw) in enumerate(zip(scenes, plans), 1):
        if not isinstance(raw, dict):
            raise ValueError(f"visual direction {index} must be an object")
        if require_execution:
            # Normalize common structured-response aliases, then run the same strict
            # validation used by production. This repairs field names only; it never
            # changes the chosen effect, timing, camera path, or transition.
            copy_direction=copy.deepcopy(raw)
            beats=copy_direction.get('timed_beats') or copy_direction.get('beats')
            if not copy_direction.get('timed_beats') and isinstance(beats,list):copy_direction['timed_beats']=beats
            if not copy_direction.get('scene_role') and copy_direction.get('role'):copy_direction['scene_role']=copy_direction['role']
            design=copy_direction.get('execution_design') if isinstance(copy_direction.get('execution_design'),dict) else {}
            camera=design.get('camera') if isinstance(design.get('camera'),dict) else {}
            transition=design.get('transition') if isinstance(design.get('transition'),dict) else {}
            if not copy_direction.get('dramatic_intent'):
                copy_direction['dramatic_intent']=str(scene.get('scene_purpose') or scene.get('scene_summary') or scene.get('scene_text') or '').strip()
            if not copy_direction.get('visual_strategy'):
                directions=[str(beat.get('direction') or beat.get('action') or '').strip() for beat in beats or [] if isinstance(beat,dict)]
                directions.extend(str(x).strip() for x in (camera.get('reason'),transition.get('reason')) if str(x or '').strip())
                copy_direction['visual_strategy']=' '.join(directions)[:1200]
            if not isinstance(copy_direction.get('ae_operations'),list):
                operations=['hold' if camera.get('kind')=='hold' else 'camera_move']
                if transition.get('kind')=='crossfade':operations.append('transition')
                copy_direction['ae_operations']=operations
            if not isinstance(copy_direction.get('required_layers'),list):copy_direction['required_layers']=[]
            if not isinstance(copy_direction.get('additional_keyframes'),list):
                copy_direction['additional_keyframes']=copy_direction.get('keyframe_requests') if isinstance(copy_direction.get('keyframe_requests'),list) else []
            if not isinstance(copy_direction.get('continuity_rules'),list):copy_direction['continuity_rules']=[]
            if not isinstance(copy_direction.get('eye_blink_plan'),dict) and isinstance(copy_direction.get('eye_blink'),dict):
                copy_direction['eye_blink_plan']=copy_direction['eye_blink']
            raw=copy_direction
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
            if start < 0 or end <= start or end > duration + 0.001 or start < last_time or not action or not target:
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
        operation_list = list(dict.fromkeys(str(x) for x in operations))
        primary_effect, secondary_effects = _effect_selection(raw, operation_list)
        scene_role = str(raw.get("scene_role") or raw.get("scene_type") or "narration").strip()
        if scene_role not in SCENE_ROLES:
            raise ValueError(f"visual direction {index} has unsupported scene_role: {scene_role}")
        focus_target = _focus_target(raw.get("focus_target"), clean_beats)
        limits = raw.get("effect_limits") if isinstance(raw.get("effect_limits"), dict) else {}
        scene_number = int(scene.get("scene_number") or scene.get("scene_order") or 0)
        eye_blink_plan = _eye_blink_plan(
            raw.get("eye_blink_plan"), duration,
            bool(scene.get("eligible_for_eye_blink")) or scene_number >= 19,
        )
        if eye_blink_plan["enabled"] and consecutive_blinks >= 2:
            eye_blink_plan = {
                **eye_blink_plan, "enabled": False, "character": "", "cues": [],
                "reason": "suppressed to avoid blinking in three adjacent scenes",
                "validation": "not_required",
            }
        consecutive_blinks = consecutive_blinks + 1 if eye_blink_plan["enabled"] else 0
        direction = {
            "contract": "scene_direction_plan/v1",
            "status": "planned",
            "persona": "scene_visual_director",
            "direction_profile": direction_profile,
            "scene_role": scene_role,
            "dramatic_intent": intent,
            "visual_strategy": str(raw.get("visual_strategy") or "").strip(),
            "focus_target": focus_target,
            "primary_effect": primary_effect,
            "secondary_effects": secondary_effects,
            "effect_limits": {
                "intensity": _number(limits.get("intensity"), 0.28, 0.0, 0.65),
                "speed": _number(limits.get("speed"), 0.7, 0.2, 1.5),
                "max_scale_delta": _number(limits.get("max_scale_delta"), 0.04, 0.0, 0.08),
                "max_move_ratio": _number(limits.get("max_move_ratio"), 0.025, 0.0, 0.06),
                "max_rotation_degrees": _number(limits.get("max_rotation_degrees"), 0.5, 0.0, 1.5),
            },
            "eye_blink_plan": eye_blink_plan,
            "source_video_review_status": "reviewed" if raw.get("source_video_reviewed") is True else "pending_upload_review",
            "timed_beats": clean_beats,
            "additional_keyframes": clean_keyframes,
            "keyframe_requests": clean_keyframes,
            "required_layers": [layer["role"] if isinstance(layer, dict) else str(layer).strip() for layer in layers],
            "layer_specs": layers,
            "ae_operations": operation_list,
            "requires_layered_assets": bool(layers or clean_keyframes),
            "continuity_rules": raw.get("continuity_rules") if isinstance(raw.get("continuity_rules"), list) else [],
            "qa_assertions": [str(x).strip() for x in qa if str(x).strip()],
            "fallback": str(raw.get("fallback") or "original_visual").strip(),
        }
        if not direction["visual_strategy"] or not direction["qa_assertions"]:
            raise ValueError(f"visual direction {index} needs visual_strategy and nonempty qa_assertions")
        from speech_bubbles import validate_script as validate_bubbles
        bubble_plan=validate_bubbles(raw,scene)
        if bubble_plan is not None:direction['speech_bubble_plan']=bubble_plan
        direction['depth_effects'] = normalize_depth_finishing(raw,scene,layers)
        direction['depth_effects_reason'] = str(raw.get('depth_effects_reason') or '').strip()
        direction['parallax_plan'] = parallax_selection(scene, direction)
        if topic is not None:
            direction.update(contract=EXECUTION_CONTRACT, topic_direction=topic,
                             execution_design=validate_execution(raw.get('execution_design'), topic, scene))
            kind = direction['execution_design']['camera']['kind']
            if kind != 'hold' and not set(operation_list).intersection({'camera_move','depth_parallax'}):
                raise ValueError('A camera path must be declared in the scene operations')
            poses=direction['execution_design']['camera']['keys']
            if (max(k['scale'] for k in poses)-min(k['scale'] for k in poses) > direction['effect_limits']['max_scale_delta']+1e-7
                    or any(max(k[f] for k in poses)-min(k[f] for k in poses) > direction['effect_limits']['max_move_ratio']+1e-7 for f in ('x','y'))):
                raise ValueError('Camera path exceeds the directed intensity/movement limits')
            if index >= 3 and kind != 'hold' and all(p.get('execution_design', {}).get('camera', {}).get('kind') == kind for p in normalized[-2:]):
                raise ValueError('Three adjacent shots repeat the same camera move; review sequence rhythm')
            effect_kinds={item['type'] for item in direction['execution_design'].get('effects',[])}
            conspicuous={'impact_flash','impact_shake','shock_ring','light_sweep'}
            if index >= 3 and any(
                effect in conspicuous and all(effect in {item['type'] for item in prior.get('execution_design',{}).get('effects',[])}
                                              for prior in normalized[-2:])
                for effect in effect_kinds
            ):
                raise ValueError('Three adjacent shots repeat the same conspicuous finishing effect')
        if 1<=int(scene.get('scene_number') or scene.get('scene_order') or index)<=18:
            from submitted_video_postwork import validate_preparation
            narration=str(scene.get('scene_text') or scene.get('narration') or '')
            value=raw.get('submitted_video_postwork') or {'effects':[],'transition':{'kind':'cut','reason':'Preserve original uploaded clip and narration clock','duration_seconds':0}}
            direction['submitted_video_postwork']=validate_preparation(value,narration)
        validate_purpose_script(scene,direction)
        scene["ae_directorial_plan"] = direction
        scene["scene_direction_plan"] = direction
        normalized.append(direction)
    return normalized
