"""Portable validation of actual AE evidence receipts, independent of Adobe/DB.

Mirror these contracts in the web submission gate. A `passed` flag alone never
authorizes publication, cache reuse, or final-render registration.
"""
import math
import re

from ae_scene_animation import canonical_plan_sha256

RENDER_CHECKS = ('source_identity', 'layer_seams', 'camera_path', 'deformation',
                 'lighting', 'transition', 'visual_quality', 'narration_integrity')
BOUNDARY_CHECKS = ('character_identity', 'screen_direction', 'action_continuity',
                   'lighting_continuity', 'edit_intent', 'visual_quality')


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _hash(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _close(left, right, tolerance=1e-6):
    return _number(left) and _number(right) and abs(left - right) <= tolerance


def valid_review(response, required):
    if not isinstance(response, dict) or response.get('passed') is not True or response.get('critical_issues') != []:
        return False
    checks = response.get('checks')
    if not isinstance(checks, list) or len(checks) != len(required):
        return False
    ids = [check.get('id') for check in checks if isinstance(check, dict)]
    return (all(isinstance(identity, str) for identity in ids) and
            len(ids) == len(set(ids)) and set(ids) == set(required) and
            all(check.get('passed') is True and isinstance(check.get('evidence'), str) and
                check['evidence'].strip() for check in checks))


def sample_times(plan, duration, fps=24):
    keys = {0., 1., .25, .5, .75}
    timelines = [plan['camera']]
    for layer in plan['layers']:
        if layer.get('motion'):
            timelines.append(layer['motion'])
        if layer.get('bend'):
            timelines.append(layer['bend']['keys'])
    timelines.extend(light['keys'] for light in plan.get('lights', []))
    for timeline in timelines:
        keys.update(row['t'] for row in timeline)
        keys.update((left['t'] + right['t']) / 2 for left, right in zip(timeline, timeline[1:]))
    for effect in plan.get('effects', []):
        span = effect['end'] - effect['start']
        keys.update((effect['start'], effect['start'] + span * .15,
                     effect['start'] + span * .7, effect['end']))
    transition = plan['transition']
    if transition['in'] == 'fade':
        keys.update((transition['fraction'] / 2, transition['fraction']))
    if transition['out'] == 'fade':
        keys.update((1 - transition['fraction'], 1 - transition['fraction'] / 2))
    last_frame = max(0, math.ceil(duration * fps - 1e-7) - 1)
    # JavaScript Math.round for nonnegative authored time values.
    return sorted({min(last_frame, max(0, math.floor(t * duration * fps + .5))) / fps for t in keys})


def render_review_matches(scene, audio, review, render_sha256):
    """Require matching source/voice/timing and complete sampled pixel evidence."""
    try:
        result = scene['ae_scene']['metadata']['result']
        plan = result['plan']
        duration = scene['end'] - scene['start']
        if (not _number(duration) or duration <= 0 or not _hash(render_sha256) or
                not isinstance(review, dict) or review.get('passed') is not True or type(review.get('version')) is not int or review['version'] != 1 or
                review.get('method') != 'sampled_actual_frames_and_decoded_final_audio' or
                review.get('render_sha256') != render_sha256 or
                not _hash(result.get('source_sha256')) or review.get('source_sha256') != result['source_sha256'] or
                not _hash(result.get('plan_sha256')) or review.get('plan_sha256') != result['plan_sha256'] or
                canonical_plan_sha256(plan) != result['plan_sha256']):
            return False
        source_previews = [item for item in result['files'] if item.get('role') == 'source_preview']
        if (len(source_previews) != 1 or not _hash(source_previews[0].get('sha256')) or
                review.get('source_preview_sha256') != source_previews[0]['sha256']):
            return False
        voice = review.get('audio') or {}
        if (not audio.get('id') or voice.get('source_audio_id') != audio['id'] or
                not _hash(voice.get('final_audio_sha256')) or
                voice.get('method') != 'decoded_pcm_integrity_not_audio_audition' or voice.get('sample_rate') != 8000 or
                not _close(voice.get('scene_start_seconds'), scene['start']) or
                not _close(voice.get('scene_end_seconds'), scene['end']) or
                not _number(voice.get('correlation')) or not .9 <= voice['correlation'] <= 1.00001 or
                not _number(voice.get('rms_ratio')) or not .8 <= voice['rms_ratio'] <= 1.2):
            return False
        expected_audio_hash = (audio.get('metadata') or {}).get('sha256')
        if expected_audio_hash and voice['final_audio_sha256'] != expected_audio_hash:
            return False
        for key in ('source_samples', 'output_samples'):
            value = voice.get(key)
            if not _number(value) or value <= 0 or int(value) != value or abs(value - duration * 8000) > 960:
                return False
        video = review.get('video') or {}
        output = plan.get('output') or {'width': 1920, 'height': 1080}
        if (not _close(video.get('fps'), 24, .001) or not _number(video.get('frames')) or
                video['frames'] < 1 or int(video['frames']) != video['frames'] or
                not _close(video.get('duration'), video['frames'] / video['fps']) or
                not _close(video['duration'], duration, 1 / 24 + .01) or
                any(video.get(key) != output[key] for key in ('width', 'height'))):
            return False
        batches = review.get('batches')
        if not isinstance(batches, list) or not batches:
            return False
        observed = []
        for batch in batches:
            if not isinstance(batch, dict) or not valid_review(batch.get('review'), RENDER_CHECKS):
                return False
            times, frames = batch.get('seconds'), batch.get('frames')
            if not isinstance(times, list) or not times or not isinstance(frames, list) or len(frames) != len(times):
                return False
            for timestamp, frame in zip(times, frames):
                if (not _number(timestamp) or not 0 <= timestamp < duration or not isinstance(frame, dict) or
                        not _close(frame.get('seconds'), timestamp) or not _hash(frame.get('sha256'))):
                    return False
            observed.extend(times)
        return all(any(_close(expected, actual, 1e-5) for actual in observed)
                   for expected in sample_times(plan, duration))
    except (KeyError, AttributeError, TypeError, ValueError, OverflowError, ZeroDivisionError):
        return False


def visible_sequence(scenes):
    ordered = sorted(scenes, key=lambda scene: scene['number'])
    if len({scene['number'] for scene in ordered}) != len(ordered):
        raise ValueError('Sequence contains duplicate scene numbers')
    visible = []
    for scene in ordered:
        start, end = scene.get('start'), scene.get('end')
        if not _number(start) or not _number(end) or start < 0 or end < start:
            raise ValueError('Sequence contains invalid finalized timing')
        if end - start <= .001:
            if scene.get('ae_scene'):
                raise ValueError('Required AE scene has no final screen time')
            continue
        visible.append(scene)
    return visible


def sequence_review_matches(scenes, outcomes, review):
    """Require every actual adjacent cut and bind inspected media to frozen inputs."""
    try:
        ordered = visible_sequence(scenes)
        ae_numbers = [scene['number'] for scene in ordered if scene.get('ae_scene')]
        expected = [(left, right) for left, right in zip(ordered, ordered[1:]) if left.get('ae_scene') or right.get('ae_scene')]
        if (not isinstance(review, dict) or review.get('passed') is not True or type(review.get('version')) is not int or review['version'] != 1 or
                review.get('method') != 'sampled_actual_adjacent_frames' or review.get('ae_scene_numbers') != ae_numbers):
            return False
        boundaries = review.get('checked_boundaries')
        if not isinstance(boundaries, list) or len(boundaries) != len(expected):
            return False
        for boundary, (left, right) in zip(boundaries, expected):
            if (boundary.get('from') != left['number'] or boundary.get('to') != right['number'] or
                    not valid_review(boundary.get('review'), BOUNDARY_CHECKS)):
                return False
            evidence = boundary.get('evidence')
            if not isinstance(evidence, list) or len(evidence) != 2:
                return False
            for actual, scene in zip(evidence, (left, right)):
                if actual.get('number') != scene['number'] or not _hash(actual.get('media_sha256')):
                    return False
                rows = [row for row in outcomes if row.get('number') == scene['number']]
                if len(rows) > 1:
                    return False
                row = rows[0] if rows else {}
                if row and row.get('status') != 'skipped':
                    if (not _hash(row.get('render_sha256')) or actual.get('kind') != 'actual_postprocessed_output' or
                            actual['media_sha256'] != row['render_sha256']):
                        return False
                else:
                    if scene.get('ae_scene'):
                        return False
                    selected = scene.get('selected_media') if 'selected_media' in scene else scene.get('original_video') or scene.get('image')
                    if not isinstance(selected, dict):
                        return False
                    metadata = selected.get('metadata') or {}
                    video = selected.get('asset_type') == 'video' if 'selected_media' in scene else bool(scene.get('original_video'))
                    if actual.get('kind') != ('original_video' if video else 'original_image'):
                        return False
                    if actual.get('source_asset_id') != selected.get('id'):
                        return False
                    expected_sha = metadata.get('render_sha256') or metadata.get('sha256')
                    if expected_sha and actual['media_sha256'] != expected_sha:
                        return False
                    storage = actual.get('source_storage') or {}
                    path = metadata.get('gcs_path') or metadata.get('storage_path')
                    bucket = metadata.get('gcs_bucket') or metadata.get('storage_bucket')
                    if path and storage.get('gcs_path') != path or bucket and storage.get('gcs_bucket') != bucket:
                        return False
                frames = actual.get('frames')
                if not isinstance(frames, list) or not frames:
                    return False
                for frame in frames:
                    if (not isinstance(frame, dict) or not _hash(frame.get('sha256')) or
                            not _number(frame.get('seconds')) or not 0 <= frame['seconds'] < scene['end'] - scene['start']):
                        return False
        return True
    except (KeyError, AttributeError, TypeError, ValueError, OverflowError):
        return False
