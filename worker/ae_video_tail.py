"""Preserve original playback; reject video extension instead of freezing it."""
import math

VIDEO_TAIL_POLICY = "original_speed_no_freeze_no_loop_v1"


def pending_video_tail(scene, payload):
    plan = scene.get('ae_motion_plan') or {}
    if not plan.get('enabled') or scene.get('visual_type') != 'video':
        return False
    number = int(scene.get('scene_number') or scene.get('scene_order') or 0)
    if number not in (payload or {}).get('ae_mouth_effect_excluded_scenes', []) and any(int(r.get('scene_number') or 0) == number and r.get('dialogue_kind') == 'dialogue'
           for r in (payload or {}).get('subtitles',[])):
        return False  # Tracked-mouth rendering enforces the same source-length policy.
    source_duration = float(scene.get('duration_seconds') or plan.get('duration_seconds') or 5)
    duration = recorded_scene_duration(payload, number, source_duration)
    asset = (scene.get('metadata') or {}).get('ae_motion_asset') or {}
    if duration <= source_duration + .12 or asset.get('status') in {'needs_attention', 'rendering'}:
        return False
    from services.video_playback_policy import require_video_duration
    require_video_duration(source_duration,duration,24,number)
    return False


def recorded_scene_duration(payload, number, fallback):
    rows = []
    for row in (payload or {}).get("subtitles", []):
        try:
            start = float(row.get("start_num", row.get("start_time", row.get("start"))))
            end = float(row.get("end_num", row.get("end_time", row.get("end"))))
            if int(row.get("scene_number", 0)) == number and math.isfinite(start + end) and end > start:
                rows.append((start, end))
        except (TypeError, ValueError):
            continue
    return max(end for _, end in rows) - min(start for start, _ in rows) if rows else fallback


def video_tail_jsx(timing_locked=False, directed=False):
    return '''
  var sourceVideo = (footage instanceof FootageItem && !footage.mainSource.isStill) || mouthRuntime.video_source;
  if(sourceVideo) {
    var sourceDuration = mouthRuntime.video_source ? mouthRuntime.video_duration : footage.duration;
    if(DUR > sourceDuration + (footage.frameDuration || 1/24) + .001)
      throw new Error("Video duration insufficient: original-speed playback only; freeze and loop prohibited");
    bg.stretch = 100;
    bg.startTime = 0;
    bg.outPoint = DUR;
  }
'''


def automatic_tail_review(payload, result):
    """Authorize only the submitted-project tail whose real-source/output QA passed."""
    if not ((payload or {}).get('ae_mouth', {}).get('enabled') or (payload or {}).get('content_recovery', {}).get('supervised_repair')):
        return None
    qa = result.get('scene_visual_qa') or {}
    direction = result.get('directorial_plan') or {}
    checks = qa.get('checks') or []
    if (result.get('video_tail_policy') != VIDEO_TAIL_POLICY
            or direction.get('source_video_review_status') != 'reviewed'
            or qa.get('passed') is not True or qa.get('critical_issues') != []
            or not checks or not all(isinstance(c, dict) and c.get('passed') is True and str(c.get('evidence') or '').strip() for c in checks)
            or not all(any(c.get('assertion') == assertion for c in checks) for assertion in direction.get('qa_assertions', []))
            or not result.get('render_sha256')):
        return None
    return {'decision':'approved','reviewer':'Codex automatic worker',
            'note':'Actual uploaded source keyframes and rendered output inspected by local Codex CLI; scene_visual_qa contains evidence.',
            'render_sha256':result['render_sha256']}
