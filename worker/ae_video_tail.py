"""Preserve video speed; extend only its final frame in After Effects."""
import math

VIDEO_TAIL_POLICY = "normal_speed_ae_freeze_zoom_v1"


def pending_video_tail(scene, payload):
    plan = scene.get('ae_motion_plan') or {}
    if not plan.get('enabled') or scene.get('visual_type') != 'video':
        return False
    number = int(scene.get('scene_number') or scene.get('scene_order') or 0)
    if any(int(r.get('scene_number') or 0) == number and r.get('dialogue_kind') == 'dialogue'
           for r in (payload or {}).get('subtitles',[])):
        return False  # Tracked-mouth rendering already owns this video's frozen zoom tail.
    source_duration = float(scene.get('duration_seconds') or plan.get('duration_seconds') or 5)
    duration = recorded_scene_duration(payload, number, source_duration)
    asset = (scene.get('metadata') or {}).get('ae_motion_asset') or {}
    if duration <= source_duration + .12 or asset.get('status') in {'needs_attention', 'rendering'}:
        return False
    current = asset.get('video_tail_policy') == VIDEO_TAIL_POLICY and abs(float(asset.get('duration_seconds') or 0) - duration) <= .12
    return not (current and asset.get('status') in {'ready', 'review_pending'})


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


def video_tail_jsx(timing_locked=False):
    return '''
  var sourceVideo = (footage instanceof FootageItem && !footage.mainSource.isStill) || mouthRuntime.video_source;
  if (sourceVideo) {
    var sourceEnd = Math.max(0, footage.duration - footage.frameDuration);
    var sourceDuration = mouthRuntime.video_source ? mouthRuntime.video_duration : footage.duration;
    var needsTail = DUR > sourceDuration + 0.12;
    if (needsTail && !mouthRuntime.video_source && (mouthRuntime.enabled || TAIL_TIMING_LOCKED)) throw new Error("Speaking clip needs finalized mouth animation through the full dialogue interval");
    bg.stretch = 100;
    bg.startTime = 0;
    if (needsTail && !mouthRuntime.video_source) {
      bg.timeRemapEnabled = true;
      var remap = bg.property("ADBE Time Remapping");
      while (remap.numKeys > 0) remap.removeKey(1);
      remap.setValueAtTime(0, 0);
      remap.setValueAtTime(sourceEnd, sourceEnd);
      remap.setValueAtTime(DUR, sourceEnd);
      for (var rk = 1; rk <= remap.numKeys; rk++) remap.setInterpolationTypeAtKey(rk, KeyframeInterpolationType.LINEAR, KeyframeInterpolationType.LINEAR);
    }
    bg.outPoint = DUR;
    var videoScale = bg.property("Scale"), videoPosition = bg.property("Position");
    while (videoScale.numKeys > 0) videoScale.removeKey(1);
    while (videoPosition.numKeys > 0) videoPosition.removeKey(1);
    videoScale.setValue([scale, scale]);
    videoPosition.setValue([W / 2, H / 2]);
    if (needsTail) {
      videoScale.setValueAtTime(sourceDuration, [scale, scale]);
      videoScale.setValueAtTime(DUR, [scale * 1.06, scale * 1.06]);
      for (var sk = 1; sk <= videoScale.numKeys; sk++) videoScale.setInterpolationTypeAtKey(sk, KeyframeInterpolationType.LINEAR, KeyframeInterpolationType.LINEAR);
    }
  }
'''.replace('TAIL_TIMING_LOCKED', 'true' if timing_locked else 'false')
