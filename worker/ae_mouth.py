"""Reviewed mouth and user-selected eye overlays for submitted still scenes.

This is stylized three-pose speaking motion, not phoneme-level lip sync.
Semantic dialogue and visible-speaker decisions come from the local Codex CLI.
"""
from __future__ import annotations

import array
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

from ae_stage_timing import stage_timing

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

POSES = ('closed', 'half', 'open')


def direction_text(speakers: list[dict], rows: list[dict], start: float) -> str:
    visible = {s['speaker'] for s in speakers}
    turns = [f"{r['speaker']} {r['start'] - start:.2f}~{r['end'] - start:.2f}초: {r['text'][:90]}"
             for r in rows if r['speaker'] in visible]
    direction = ('씬 시작 기준 ' + '; '.join(turns) + '. 해당 화자의 입만 닫힘·반열림·열림으로 전환하고 '
            '입술과 턱 주변의 원래 그림체를 유지합니다. 내레이션·쉼·상대 화자의 대사에서는 입을 다뭅니다. '
            '화면의 구도와 기존 AE 효과를 유지해 합성하며, 최종 음성 길이와 재생 속도는 바꾸지 않습니다.')
    windows = [s for s in speakers if s.get('visible_until_seconds') is not None or s.get('visible_from_seconds', 0)]
    if windows:
        spans = ['%s %.3f~%s초' % (s['speaker'], s.get('visible_from_seconds', 0),
                 ('%.3f' % s['visible_until_seconds']) if s.get('visible_until_seconds') is not None else '대사 끝') for s in windows]
        direction += (' 합성 입 움직임은 검증된 추적 구간(' + '; '.join(spans) + ')에만 적용합니다. '
                      '이 구간 밖에서는 화자가 계속 보이더라도 합성 입 레이어를 숨기고 원본 영상의 얼굴과 입을 그대로 유지합니다.')
    return direction


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dialogue_rows(result: dict, subtitles: list[dict]) -> list[dict]:
    rows = result.get('rows')
    if not isinstance(rows, list) or len(rows) != len(subtitles):
        raise ValueError('Dialogue assessment must cover every supplied subtitle')
    selected = []
    for actual, source in zip(rows, subtitles):
        if actual.get('index') != source['index'] or actual.get('text') != source['text']:
            raise ValueError('Dialogue assessment changed subtitle text or order')
        state = actual.get('kind')
        if state not in ('dialogue', 'narration', 'uncertain') or not str(actual.get('reason') or '').strip():
            raise ValueError('Dialogue assessment is missing evidence')
        if source['kind'] in ('dialogue', 'narration') and state != source['kind']:
            raise ValueError('Dialogue assessment contradicts the saved subtitle classification')
        speaker = str(actual.get('speaker') or '').strip()
        if state == 'dialogue' and not speaker:
            raise ValueError('Dialogue needs an identified speaker')
        if source.get('speaker') and state == 'dialogue' and speaker != source['speaker']:
            raise ValueError('Dialogue assessment contradicts the saved speaker')
        selected.append({**source, 'kind': state, 'speaker': speaker, 'reason': actual['reason']})
    return selected


def assess_dialogue(runner, identity: str, snapshot: dict) -> list[dict]:
    numbers = {s['number'] for s in snapshot['scenes']} if 'scenes' in snapshot else {
        s['scene_number'] for s in snapshot['subtitles'] if s['scene_number'] >= 19}
    subtitles = [s for s in snapshot['subtitles'] if s['scene_number'] in numbers]
    if not subtitles:
        return []
    # Submission uses the user's saved classification and exact speaker assignment.
    return [{**row, 'kind': row['kind'] if row.get('kind') in ('dialogue', 'narration') and (row['kind'] != 'dialogue' or row.get('speaker')) else 'uncertain',
             'reason': 'User-confirmed saved dialogue/speaker assignment' if row.get('kind') else 'Saved classification needs confirmation'} for row in subtitles]


def visible_speakers(response: dict, speakers: list[str]) -> list[dict]:
    rows = response.get('speakers')
    if not isinstance(rows, list) or len(rows) != len(speakers):
        raise ValueError('Visible speaker assessment is incomplete')
    accepted = []
    for row, speaker in zip(rows, speakers):
        if row.get('speaker') != speaker or row.get('status') not in ('visible', 'offscreen', 'occluded', 'uncertain'):
            raise ValueError('Visible speaker assessment changed the cast')
        confidence = row.get('confidence')
        if not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or confidence < .9:
            raise ValueError('Visible speaker confidence needs review')
        if row['status'] == 'uncertain' or not str(row.get('reason') or '').strip():
            raise ValueError('Speaker identity or mouth visibility needs review')
        if row['status'] == 'visible':
            box = row.get('mouth_box')
            if not isinstance(box, list) or len(box) != 4 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in box):
                raise ValueError('Mouth bounds are invalid')
            l, t, r, b = box
            if not (0 <= l < r <= 1 and 0 <= t < b <= 1 and .005 <= r - l <= .20 and .005 <= b - t <= .12):
                raise ValueError('Mouth bounds must cover only a small lip and skin region')
            face = row.get('face_box')
            if face is not None:
                if not isinstance(face, list) or len(face) != 4 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in face):
                    raise ValueError('Face bounds are invalid')
                fl, ft, fr, fb = face
                if not (0 <= fl <= l < r <= fr <= 1 and 0 <= ft <= t < b <= fb <= 1):
                    raise ValueError('Mouth must be inside the face')
            for other in accepted:
                if other['status'] == 'visible':
                    a, c, d, e = other['mouth_box']
                    if l < d and r > a and t < e and b > c:
                        raise ValueError('Speaker mouth regions overlap')
        accepted.append(row)
    return accepted


def locate_speakers(runner, identity: str, scene: dict, image: Path, rows: list[dict], cast: dict) -> list[dict]:
    speakers = list(dict.fromkeys(s['speaker'] for s in rows if s['kind'] == 'dialogue'))
    response = runner._stage(identity, '03_ae_mouth_visibility', {
        '_local_image_paths': [str(image.resolve())], 'source_sha256': digest(image),
        'scene_text': scene['text'], 'cast': cast, 'speakers': speakers,
    }, (
        "Inspect the attached ORIGINAL scene image, then match the requested speakers to visible characters "
        "using the supplied story and cast. Return {speakers:[{speaker:'exact supplied name',status:'visible|offscreen|uncertain',"
        "confidence:0.0, face_box:[left,top,right,bottom], mouth_box:[left,top,right,bottom],reason:'visual evidence'}]} in supplied order. "
        "Coordinates are normalized to the original image. The box must tightly enclose the complete lips "
        "and a small surrounding skin margin so alternate mouth patches cover the original mouth. "
        "Use visible only for a confidently identified unobscured mouth. Tiny, hidden or ambiguous faces "
        "need uncertain. Offscreen means the actual speaker is absent; never assign their speech to a listener. "
        "Do not change composition or identify a character from a name alone. "
        "For each visible or occluded speaker ALSO return mouth_geometry:{version:2,"
        "orientation:'frontal|three_quarter_left|three_quarter_right|profile_left|profile_right',"
        "pitch:'level|up|down',mouth_visibility:'clear|partial|hidden',"
        "render_policy:'animate|preserve_original',face_outline:[[x,y],...],"
        "landmarks:{nose_tip:[x,y],chin:[x,y],lip_left:[x,y],lip_right:[x,y],lip_center:[x,y]},"
        "evidence:'specific visible lip contour, face direction and occluders'}. "
        "All points are normalized ORIGINAL-image coordinates; lip_left/right are screen-left/right. "
        "Only clearly visible complete lips may animate. Never infer a mouth behind a hand, hair, "
        "clothes or turned-away face. Use status=occluded and preserve_original for present speakers "
        "whose mouth is partial/hidden; omit lip landmarks rather than guessing them. "
        "Distinguish cheek creases from actual lips using the nose tip, chin and skin contour."
    ))
    # First pass proposes only a face search area. Never treat full-frame
    # approximate coordinates or its confidence as final lip geometry.
    coarse=response.get('speakers')
    if not isinstance(coarse,list) or len(coarse)!=len(speakers):raise ValueError('Face search incomplete')
    accepted=[]
    source_sha=digest(image)
    directory=image.parent / ('geometry-review-v3-'+source_sha[:12])
    directory.mkdir(parents=True,exist_ok=True)
    with Image.open(image) as original:
        for index,(candidate,name) in enumerate(zip(coarse,speakers)):
            if candidate.get('speaker')!=name:raise ValueError('Face search changed speaker')
            if candidate.get('status')=='offscreen':
                accepted.extend(visible_speakers({'speakers':[candidate]},[name]));continue
            face=candidate.get('face_box')
            if not isinstance(face,list) or len(face)!=4 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in face):
                raise ValueError('Face search bounds missing')
            l,t,r,b=face
            if not 0<=l<r<=1 or not 0<=t<b<=1:raise ValueError('Face search bounds invalid')
            dx,dy=(r-l)*.18,(b-t)*.18
            rect=(max(0,round((l-dx)*original.width)),max(0,round((t-dy)*original.height)),
                  min(original.width,round((r+dx)*original.width)),min(original.height,round((b+dy)*original.height)))
            crop_path=directory/f'face-{index}.png';original.crop(rect).save(crop_path)
            refined=runner._stage(identity+'-'+str(index),'03_ae_mouth_crop_localization',{
                '_local_image_paths':[str(crop_path.resolve())],
                'speaker':name,'cast':cast,'source_sha256':source_sha,
                'coarse_proposal':candidate,'crop_rect_pixels':rect,
            }, 'The ONLY attached image is the enlarged TARGET FACE. '
               'Locate features on this attached face crop with precision. Return {speaker:exact_name,status:visible|occluded|uncertain,'
               'confidence:number,face_box:[l,t,r,b],mouth_box:[l,t,r,b],reason:visual_evidence,mouth_geometry:{'
               'version:2,orientation:frontal|three_quarter_left|three_quarter_right|profile_left|profile_right,'
               'pitch:level|up|down,mouth_visibility:clear|partial|hidden,render_policy:animate|preserve_original,'
               'face_outline:[[x,y],...],landmarks:{nose_tip:[x,y],chin:[x,y],lip_left:[x,y],lip_right:[x,y],lip_center:[x,y]},evidence:string}}. '
               'ALL coordinates must be normalized to THIS FACE CROP ONLY. Do not copy the coarse full-image proposal. '
               'Find actual lip edges, not cheek lines, under the true nose tip and above chin. '
               'For hidden lips use occluded+preserve_original and do not invent mouth points. '
               'If unsure use uncertain with honest confidence; no blind approval.')
            if refined.get('speaker')!=name:raise ValueError('Face refinement changed speaker')
            def mapped(p):return [(rect[0]+p[0]*(rect[2]-rect[0]))/original.width,(rect[1]+p[1]*(rect[3]-rect[1]))/original.height]
            for key in ('face_box','mouth_box'):
                if refined.get(key):
                    q=refined[key];refined[key]=mapped(q[:2])+mapped(q[2:])
            g=refined.get('mouth_geometry') or {}
            if g.get('face_outline'):g['face_outline']=[mapped(p) for p in g['face_outline']]
            if g.get('landmarks'):g['landmarks']={key:mapped(p) for key,p in g['landmarks'].items()}
            refined['mouth_geometry']=g
            accepted.append(refined)
    accepted=visible_speakers({'speakers':accepted},speakers)
    candidates = [s for s in accepted if s['status'] in ('visible', 'occluded')]
    if not candidates:return accepted
    from mouth_geometry import validate
    attachments=[str(image.resolve())]
    with Image.open(image) as original:
        for index,speaker in enumerate(candidates):
            speaker['mouth_geometry']['source_sha256']=source_sha
            validate(speaker,source_sha,require_review=False)
            if speaker['mouth_geometry']['render_policy']=='animate':
                from mouth_geometry import validate_image_evidence
                validate_image_evidence(speaker,original)
            if speaker.get('face_box'):
                box=speaker['face_box'];rect=tuple(round(v*(original.width if i%2==0 else original.height)) for i,v in enumerate(box))
                crop=original.crop(rect)
                target=directory/f'original-face-{index}.png';crop.save(target);attachments.append(str(target.resolve()))
                marked=crop.convert('RGB');draw=ImageDraw.Draw(marked)
                mb=speaker.get('mouth_box')
                if mb:draw.rectangle([mb[0]*original.width-rect[0],mb[1]*original.height-rect[1],mb[2]*original.width-rect[0],mb[3]*original.height-rect[1]],outline='lime',width=2)
                for key,p in (speaker['mouth_geometry'].get('landmarks') or {}).items():
                    x,y=p[0]*original.width-rect[0],p[1]*original.height-rect[1]
                    draw.ellipse([x-2,y-2,x+2,y+2],fill='red');draw.text((x+3,y+3),key,fill='yellow')
                marked_path=directory/f'annotated-face-{index}.png';marked.save(marked_path);attachments.append(str(marked_path.resolve()))
    review=runner._stage(identity,'03_ae_mouth_geometry_review',{
        '_local_image_paths':attachments,'source_sha256':source_sha,'speakers':candidates,
    }, 'Independently inspect the ORIGINAL and each paired unmarked/ANNOTATED face crop. '
       'Green rectangles are proposed mouth patches, red dots and yellow labels are proposed landmarks. '
       'Check the DRAWN markers against the actual pixels, not just numeric plausibility. '
       'Reject markers above/below actual lips, dots on a cheek/eye instead of nose, or missed lip corners. '
       'Coordinates remain normalized to '
       'the ORIGINAL, never crop-local. Verify each lip endpoint and center against actual lip lines, '
       'nose/chin/face contour, head direction, tilt and occlusion. A cheek crease is not a mouth. '
       'For profile/downward faces check visible lip silhouette specifically. Hidden/partial mouths '
       'must preserve original. Return {speakers:[{speaker:exact_name,passed:true|false,reason:visual_evidence}]} '
       'in supplied order. Reject guesses, wrong person, wrong side, and ambiguous contours.')
    reviewed=review.get('speakers') or []
    if len(reviewed)!=len(candidates):raise ValueError('Geometry review must cover every visible face')
    for speaker,result in zip(candidates,reviewed):
        if result.get('speaker')!=speaker['speaker']:raise ValueError('Geometry review changed speaker')
        speaker['mouth_geometry']['review']={'passed':result.get('passed'),'reason':result.get('reason'),'proof':'annotated-face-crop-v4'}
        validate(speaker,source_sha)
    return accepted


def visible_blink_eyes(response: dict, character: str) -> dict:
    row = response.get('eye_blink') if isinstance(response, dict) else None
    if not isinstance(row, dict) or row.get('character') != character:
        raise ValueError('Eye blink assessment changed or omitted the planned character')
    if row.get('status') not in ('visible', 'offscreen', 'uncertain'):
        raise ValueError('Eye blink visibility is invalid')
    confidence = row.get('confidence')
    if not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or confidence < .9:
        raise ValueError('Eye blink confidence needs review')
    if row['status'] != 'visible' or not str(row.get('reason') or '').strip():
        raise ValueError('Planned character eyes are not safely visible')
    boxes = []
    for key in ('left_eye_box', 'right_eye_box'):
        box = row.get(key)
        if not isinstance(box, list) or len(box) != 4 or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in box):
            raise ValueError('Both eye boxes are required')
        left, top, right, bottom = box
        if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1
                and .005 <= right - left <= .14 and .004 <= bottom - top <= .10):
            raise ValueError('Eye boxes must tightly cover only the visible eyes')
        boxes.append(box)
    left, right = boxes
    if left[0] < right[2] and left[2] > right[0] and left[1] < right[3] and left[3] > right[1]:
        raise ValueError('Left and right eye boxes overlap')
    return row


def locate_blink_eyes(runner, identity: str, scene: dict, image: Path, plan: dict, cast: dict) -> dict:
    character = str(plan.get('character') or '').strip()
    if not character:
        raise ValueError('Eye blink plan has no character')
    response = runner._stage(identity, '03_ae_eye_visibility', {
        '_local_image_paths': [str(image.resolve())], 'source_sha256': digest(image),
        'scene_text': scene.get('scene_text') or scene.get('narration') or scene.get('text') or '',
        'cast': cast, 'character': character, 'eye_blink_plan': plan,
    }, (
        "Inspect the attached ORIGINAL final scene image. Find only the exact planned character using the "
        "supplied cast and story. Return {eye_blink:{character:'exact supplied name',"
        "status:'visible|offscreen|uncertain',confidence:0.0,left_eye_box:[left,top,right,bottom],"
        "right_eye_box:[left,top,right,bottom],reason:'specific visual evidence'}}. Coordinates are normalized "
        "to the original image and each box must tightly enclose one complete visible eye with minimal skin. "
        "Use visible only when both eyes are unobscured, large enough for a clean closed-eye patch, and the "
        "identity is certain. Side profile, hair occlusion, tiny eyes, closed eyes, or ambiguous identity must "
        "be uncertain. Offscreen means the planned character is absent. Never select a different character."
    ))
    return visible_blink_eyes(response, character)


def normalize_patch(source: Path, target: Path, reference: Path, box: list[float]) -> None:
    """Fit generated replacement art only into its verified region; preserve all other pixels."""
    with Image.open(reference) as base, Image.open(source) as patch:
        if patch.format != 'PNG' or min(patch.size) < 512:
            raise ValueError('Layer generator must return an actual PNG of at least 512px per edge')
        rect = tuple(round(v * (base.width if i % 2 == 0 else base.height)) for i, v in enumerate(box))
        width, height = rect[2] - rect[0], rect[3] - rect[1]
        if min(width, height) < 8:
            raise ValueError('Selected feature is too small for a clean patch')
        rgba = patch.convert('RGBA').resize((width, height), Image.Resampling.LANCZOS)
        if rgba.getchannel('A').getextrema() != (255, 255):
            raise ValueError('Replacement must cover the original feature with opaque matching skin')
        mask = Image.new('L', (width, height))
        ImageDraw.Draw(mask).rounded_rectangle((1, 1, width - 2, height - 2), radius=max(2, min(width, height) // 5), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(min(2, height / 12)))
        rgba.putalpha(mask)
        target.parent.mkdir(parents=True, exist_ok=True)
        rgba.save(target)


def mouth_layers(generator, image: Path, speaker: dict, directory: Path) -> dict[str, str]:
    from mouth_geometry import animatable, fingerprint
    if not animatable(speaker,digest(image)):
        raise ValueError('Occluded mouth must preserve original; do not generate mouth patches')
    from mouth_geometry import validate_image_evidence
    with Image.open(image) as original:validate_image_evidence(speaker,original)
    geometry_key=fingerprint(speaker)
    box = speaker['mouth_box']
    # Reserve opaque skin around the entire original lip contour, including its corners.
    if not speaker.get('coverage_version'):
        l, t, r, b = box
        dx, dy = (r - l) * .2, (b - t) * .2
        box = [max(0, l-dx), max(0, t-dy), min(1, r+dx), min(1, b+dy)]
        speaker['mouth_box'] = box
        speaker['coverage_version'] = 2
    directory.mkdir(parents=True, exist_ok=True)
    with Image.open(image) as base:
        rect = tuple(round(v * (base.width if i % 2 == 0 else base.height)) for i, v in enumerate(box))
        reference = directory / 'mouth-reference.png'
        base.crop(rect).save(reference)
    layers = {}
    for pose in POSES:
        target = directory / f'{pose}.png'
        receipt = directory / f'{pose}.receipt.json'
        source_hash = digest(image)
        reusable = False
        if target.exists() and receipt.exists():
            saved = json.loads(receipt.read_text(encoding='utf-8'))
            reusable = saved == {'source': source_hash, 'mouth_box': box, 'pose': pose, 'coverage_version': 2, 'geometry':geometry_key,'sha256': digest(target)}
        if not reusable:
            # A failed native generation is deliberately not silently regenerated/charged.
            with stage_timing(directory / 'stage-timings.jsonl', 'mouth_image_generation', pose=pose):
                raw = generator.generate(role='background', reference=reference, work_dir=directory / f'generate-{pose}', prompt=(
                    f"Edit the attached cropped mouth of {speaker['speaker']}. Return the SAME crop with "
                    f"the mouth {'fully closed' if pose == 'closed' else 'slightly parted' if pose == 'half' else 'naturally open while speaking'}. "
                    "Preserve exact lip center, scale, angle, skin color, lighting, linework and illustration style. "
                    "Erase the entire original mouth contour and replace it with exactly ONE mouth in the requested pose. Draw matching opaque skin over all old lip lines, including the corners. No transparency. "
                    "Do not add eyes, nose, teeth outside the mouth, a face, characters, text, or a new background. "
                    "Match the supplied crop's aspect ratio and keep the crop geometry aligned with it. "
                    + 'Verified face geometry: ' + json.dumps(speaker['mouth_geometry'],ensure_ascii=False)
                ))
            normalize_patch(raw, target, image, box)
            receipt.write_text(json.dumps({'source': source_hash, 'mouth_box': box, 'pose': pose, 'coverage_version': 2, 'geometry':geometry_key,'sha256': digest(target)}), encoding='utf-8')
        layers[pose] = str(target.resolve())
    with Image.open(layers['closed']) as closed, Image.open(layers['open']) as opened:
        if sum(ImageStat.Stat(ImageChops.difference(closed.convert('RGB'), opened.convert('RGB'))).mean) < 3:
            raise ValueError('Generated open and closed mouth patches do not visibly differ')
    return layers


def amplitude_cues(samples: list[int], rows: list[dict], *, start: float, duration: float, fps: int = 24, sample_rate: int = 8000) -> list[dict]:
    """Switch mouth poses within verified spoken intervals; all other intervals stay closed."""
    frames = max(1, round(duration * fps))
    poses = ['closed'] * frames
    for row in rows:
        left, right = float(row['start']) - start, float(row['end']) - start
        if not (0 <= left < right <= duration + .001):
            raise ValueError('Dialogue timing crosses its recorded scene boundary')
        first, last = round(left * fps), min(frames - 1, round(right * fps))
        values = []
        for frame in range(first, last):
            segment = samples[round(frame / fps * sample_rate):round((frame + 1) / fps * sample_rate)]
            values.append(math.sqrt(sum(v * v for v in segment) / len(segment)) if segment else 0)
        peak = max(values, default=0)
        if peak < 32:
            raise ValueError('Spoken interval has no usable final voice samples')
        for offset, rms in enumerate(values):
            # Amplitude gating closes audible pauses; a short alternating cadence avoids a held-open mouth.
            poses[first + offset] = 'closed' if rms < max(32, peak * .08) else ('open' if rms > peak * .35 and (offset // 2) % 2 == 0 else 'half')
    poses[-1] = 'closed'
    cues = [{'at_seconds': 0, 'pose': poses[0]}]
    for frame in range(1, frames):
        if poses[frame] != poses[frame - 1]:
            cues.append({'at_seconds': round(frame / fps, 6), 'pose': poses[frame]})
    return cues


def audio_reactive_light_cues(samples: list[int], rows: list[dict], *, start: float, duration: float,
                              sample_rate: int = 8000, cue_rate: int = 12) -> list[dict]:
    """Return bounded 0..1 RMS cues only inside confirmed dialogue intervals."""
    count = max(1, math.ceil(duration * cue_rate))
    rms_values = [0.0] * count
    for index in range(count):
        left, right = index / cue_rate, min(duration, (index + 1) / cue_rate)
        if not any(float(row['start']) - start < right and float(row['end']) - start > left for row in rows):
            continue
        segment = samples[round(left * sample_rate):round(right * sample_rate)]
        if segment:
            rms_values[index] = math.sqrt(sum(value * value for value in segment) / len(segment))
    audible = sorted(value for value in rms_values if value >= 32)
    reference = audible[min(len(audible) - 1, round((len(audible) - 1) * .95))] if audible else 0
    normalized = []
    for index, value in enumerate(rms_values):
        active = any(float(row['start']) - start < (index + 1) / cue_rate
                     and float(row['end']) - start > index / cue_rate for row in rows)
        level = 0 if reference <= 0 or value < max(32, reference * .08) else min(1.0, value / reference)
        previous = normalized[-1] if normalized else 0
        normalized.append(round(previous * .55 + level * .45, 4) if active else 0.0)
    cues = [{'at_seconds': 0, 'value': 0.0}]
    for index, value in enumerate(normalized):
        at = round(index / cue_rate, 6)
        if value != cues[-1]['value']:
            cues.append({'at_seconds': at, 'value': value})
    if cues[-1]['at_seconds'] != round(duration, 6) or cues[-1]['value'] != 0:
        cues.append({'at_seconds': round(duration, 6), 'value': 0.0})
    return cues


def blink_cues(duration: float, interval: float, close_seconds: float = .12) -> list[dict]:
    """Create restrained deterministic blinks; the open original remains visible between them."""
    if not math.isfinite(duration) or duration <= 0 or not math.isfinite(interval) or not 2 <= interval <= 12:
        raise ValueError('Blink duration or interval is invalid')
    cues = [{'at_seconds': 0, 'opacity': 0}]
    at = min(max(1.0, interval * .55), max(.15, duration * .55))
    while at + close_seconds < duration:
        cues.extend([
            {'at_seconds': round(max(0, at - .055), 6), 'opacity': 0},
            {'at_seconds': round(at, 6), 'opacity': 100},
            {'at_seconds': round(min(duration, at + close_seconds), 6), 'opacity': 0},
        ])
        at += interval
    if cues[-1]['at_seconds'] != round(duration, 6):
        cues.append({'at_seconds': round(duration, 6), 'opacity': 0})
    return cues


def resolved_blink_cues(duration: float, blink: dict) -> list[dict]:
    """Resolve directed exact cues first; retain the manual interval editor as an override/fallback."""
    planned = blink.get('cues') if isinstance(blink, dict) else None
    if planned is None:
        return blink_cues(duration, float(blink['interval_seconds']))
    if not isinstance(planned, list) or not planned:
        raise ValueError('Directed eye blink cues are missing')
    cues = [{'at_seconds': 0, 'opacity': 0}]
    last = -1.0
    for number, cue in enumerate(planned, 1):
        if not isinstance(cue, dict):
            raise ValueError(f'Directed eye blink cue {number} is invalid')
        try:
            at = float(cue.get('at_seconds'))
            close = float(cue.get('duration_seconds', .12))
        except (TypeError, ValueError):
            raise ValueError(f'Directed eye blink cue {number} needs numeric timing')
        kind = str(cue.get('type') or 'single')
        if (not math.isfinite(at) or not math.isfinite(close) or kind not in ('single', 'double')
                or not .08 <= close <= .2 or at < .25 or at + close > duration - .2 or at <= last):
            raise ValueError(f'Directed eye blink cue {number} is outside the safe scene range')
        starts = [at] if kind == 'single' else [at, at + close + .085]
        if starts[-1] + close > duration - .2:
            raise ValueError(f'Directed double blink cue {number} is too close to the scene end')
        for start in starts:
            cues.extend([
                {'at_seconds': round(max(0, start - .055), 6), 'opacity': 0},
                {'at_seconds': round(start, 6), 'opacity': 100},
                {'at_seconds': round(start + close, 6), 'opacity': 0},
            ])
        last = starts[-1]
    if cues[-1]['at_seconds'] != round(duration, 6):
        cues.append({'at_seconds': round(duration, 6), 'opacity': 0})
    return cues


def eye_layers(generator, image: Path, blink: dict, directory: Path) -> dict[str, str]:
    """Generate only user-selected closed-eye patches against an immutable source image."""
    directory.mkdir(parents=True, exist_ok=True)
    layers = {}
    source_hash = digest(image)
    if blink.get('source_sha256') != source_hash:
        raise ValueError('눈 좌표를 지정한 원본 이미지가 변경되었습니다.')
    for side, key in (('left', 'left_eye_box'), ('right', 'right_eye_box')):
        box = blink.get(key)
        if not isinstance(box, list) or len(box) != 4:
            raise ValueError('확정된 양쪽 눈 좌표가 필요합니다.')
        reference = directory / f'{side}-reference.png'
        with Image.open(image) as base:
            rect = tuple(round(v * (base.width if i % 2 == 0 else base.height)) for i, v in enumerate(box))
            base.crop(rect).save(reference)
        target, receipt = directory / f'{side}-closed.png', directory / f'{side}-closed.receipt.json'
        expected = {'source': source_hash, 'character': blink['character'], 'side': side, 'eye_box': box,
                    'version': 1}
        reusable = False
        if target.exists() and receipt.exists():
            saved = json.loads(receipt.read_text(encoding='utf-8'))
            reusable = saved == {**expected, 'sha256': digest(target)}
        if not reusable:
            raw = generator.generate(role='background', reference=reference,
                work_dir=directory / f'generate-{side}-closed', prompt=(
                    f"Edit the attached crop of {blink['character']}'s {side} eye. Return the SAME crop with "
                    "that eye naturally closed in a gentle blink. Preserve the exact eyebrow, face angle, "
                    "skin color, lighting, linework and illustration style. Cover the original open-eye lines "
                    "with matching opaque skin and draw exactly one closed eyelid at the same position. "
                    "Do not add a second eye, face, text, transparency, or change any other feature."
                ))
            normalize_patch(raw, target, image, box)
            receipt.write_text(json.dumps({**expected, 'sha256': digest(target)}, ensure_ascii=False), encoding='utf-8')
        layers[side] = str(target.resolve())
    return layers


def review_eye_layers(runner, identity: str, image: Path, blink: dict, directory: Path) -> None:
    with Image.open(image) as source:
        composite = source.convert('RGBA')
        for side, key in (('left', 'left_eye_box'), ('right', 'right_eye_box')):
            with Image.open(blink['layers'][side]) as patch:
                box = blink[key]
                composite.alpha_composite(patch.convert('RGBA'),
                                           (round(box[0] * source.width), round(box[1] * source.height)))
        preview = directory / 'review-eyes-closed.png'
        composite.convert('RGB').save(preview)
    response = runner._stage(identity, '03_ae_eye_blink_layer_qa', {
        '_local_image_paths': [str(image.resolve()), str(preview.resolve())],
        'source_sha256': digest(image), 'character': blink['character'],
        'left_eye_box': blink['left_eye_box'], 'right_eye_box': blink['right_eye_box'],
        'patch_sha256': {side: digest(Path(path)) for side, path in blink['layers'].items()},
    }, (
        "Inspect the original and closed-eye composite in that order. Verify that the user-selected "
        "character has exactly two naturally closed eyes while identity, brows, face, lighting and linework "
        "remain unchanged. Reject open or doubled eyes, rectangular seams, facial drift, or edits outside "
        "the two supplied eye boxes. Return {passed:true|false,reason:'visual evidence'}."
    ))
    if response.get('passed') is not True or not str(response.get('reason') or '').strip():
        raise ValueError('생성된 눈 깜빡임 레이어 검수가 필요합니다: ' + str(response.get('reason') or 'missing visual QA'))


def decode_scene_audio(ffmpeg: str, audio: Path, start: float, duration: float) -> list[int]:
    result = subprocess.run([ffmpeg, '-v', 'error', '-ss', str(start), '-i', str(audio), '-t', str(duration),
                             '-ac', '1', '-ar', '8000', '-f', 's16le', 'pipe:1'], capture_output=True, timeout=120, check=True)
    pcm = array.array('h')
    pcm.frombytes(result.stdout)
    if len(pcm) < (duration - .12) * 8000:
        raise ValueError('Final narration is shorter than the recorded scene')
    return list(pcm)


def review_layers(runner, identity: str, image: Path, speakers: list[dict], directory: Path) -> None:
    previews = []
    with Image.open(image) as source:
        for pose in POSES:
            composite = source.convert('RGBA')
            for speaker in speakers:
                with Image.open(speaker['layers'][pose]) as patch:
                    box = speaker['mouth_box']
                    composite.alpha_composite(patch.convert('RGBA'), (round(box[0] * source.width), round(box[1] * source.height)))
            path = directory / f'review-{pose}.png'
            composite.convert('RGB').save(path)
            previews.append(str(path.resolve()))
    response = runner._stage(identity, '03_ae_mouth_layer_qa', {
        '_local_image_paths': [str(image.resolve()), *previews], 'source_sha256': digest(image),
        'speakers': [{k: v for k, v in s.items() if k != 'layers'} for s in speakers],
        'patch_sha256': [{p: digest(Path(s['layers'][p])) for p in POSES} for s in speakers],
    }, (
        "Inspect original, closed-mouth, half-mouth, and open-mouth composites in that order. "
        "Verify the intended speakers' mouths change cleanly with consistent identity, position, "
        "skin color, lighting and linework. No doubled lips, visible rectangular patch, facial drift, "
        "changed listener, or missing original-mouth coverage is acceptable. Return "
        "{passed:true|false,reason:'visual evidence'}. If unsure return passed=false."
    ))
    if response.get('passed') is not True or not str(response.get('reason') or '').strip():
        raise ValueError('Generated mouth layers need review: ' + str(response.get('reason') or 'missing visual QA'))


def mouth_jsx(runtime: dict) -> str:
    """Animate patches inside the source precomp so camera/effects cannot detach the lips."""
    return '''
  var mouthRuntime = ''' + json.dumps(runtime, ensure_ascii=True) + ''';
  function applyAudioReactiveLight(comp) {
    if (!mouthRuntime.enabled || !mouthRuntime.audio_light_cues || mouthRuntime.audio_light_cues.length < 2) return;
    var light = comp.layers.addSolid([1.0, 0.93, 0.82], "audio_reactive_dialogue_light", comp.width, comp.height, 1, DUR);
    light.blendingMode = BlendingMode.ADD;
    var opacity = light.property("Opacity");
    for (var lc = 0; lc < mouthRuntime.audio_light_cues.length; lc++) {
      var lightCue = mouthRuntime.audio_light_cues[lc];
      var lightKey = opacity.addKey(lightCue.at_seconds);
      opacity.setValueAtKey(lightKey, Math.max(0, Math.min(4, lightCue.value * 4)));
      opacity.setInterpolationTypeAtKey(lightKey, KeyframeInterpolationType.LINEAR, KeyframeInterpolationType.LINEAR);
    }
  }
  if (mouthRuntime.enabled) {
    var mouthComp = app.project.items.addComp("ae_mouth_source", footage.width, footage.height, 1, DUR, FPS);
    var originalMouthPlate = mouthComp.layers.add(footage);
    originalMouthPlate.property("Position").setValue([footage.width / 2, footage.height / 2]);
    originalMouthPlate.audioEnabled = false;
    if (mouthRuntime.video_source) {
      originalMouthPlate.stretch = 100;
      if (DUR > footage.duration + (footage.frameDuration || 1/24) + .001)
        throw new Error("Video duration insufficient: freeze and loop prohibited; provide original footage covering narration");
      originalMouthPlate.outPoint = DUR;
    }
    var mouthPoses = ["closed", "half", "open"];
    var runtimeSpeakers = mouthRuntime.speakers || [];
    for (var ms = 0; ms < runtimeSpeakers.length; ms++) {
      var speaker = runtimeSpeakers[ms];
      for (var mp = 0; mp < mouthPoses.length; mp++) {
        var pose = mouthPoses[mp];
        var mouthFootage = app.project.importFile(new ImportOptions(new File(speaker.layers[pose])));
        var mouthLayer = mouthComp.layers.add(mouthFootage);
        mouthLayer.name = "mouth_" + ms + "_" + pose;
        mouthLayer.property("Position").setValue([
          Math.round(speaker.mouth_box[0] * footage.width) + mouthFootage.width / 2,
          Math.round(speaker.mouth_box[1] * footage.height) + mouthFootage.height / 2]);
        if (speaker.tracking) {
          var seedPosition = mouthLayer.property("Position").value;
          for (var mt = 0; mt < speaker.tracking.length; mt++) {
            var motion = speaker.tracking[mt];
            mouthLayer.property("Position").setValueAtTime(motion.at_seconds, [seedPosition[0]+motion.offset[0],seedPosition[1]+motion.offset[1]]);
            mouthLayer.property("Scale").setValueAtTime(motion.at_seconds, [motion.scale,motion.scale]);
            mouthLayer.property("Rotation").setValueAtTime(motion.at_seconds, motion.rotation);
          }
        }
        var mouthOpacity = mouthLayer.property("Opacity");
        for (var mc = 0; mc < speaker.cues.length; mc++) {
          var cue = speaker.cues[mc];
          var key = mouthOpacity.addKey(cue.at_seconds);
          var mouthVisible = cue.at_seconds >= (speaker.visible_from_seconds || 0) && (speaker.visible_until_seconds == null || cue.at_seconds <= speaker.visible_until_seconds);
          mouthOpacity.setValueAtKey(key, mouthVisible && cue.pose == pose ? 100 : 0);
          mouthOpacity.setInterpolationTypeAtKey(key, KeyframeInterpolationType.HOLD, KeyframeInterpolationType.HOLD);
        }
      }
    }
    var runtimeBlinks = mouthRuntime.blinks || [];
    var eyeSides = ["left", "right"];
    for (var eb = 0; eb < runtimeBlinks.length; eb++) {
      var blink = runtimeBlinks[eb];
      for (var es = 0; es < eyeSides.length; es++) {
        var side = eyeSides[es];
        var eyeBox = side == "left" ? blink.left_eye_box : blink.right_eye_box;
        var eyeFootage = app.project.importFile(new ImportOptions(new File(blink.layers[side])));
        var eyeLayer = mouthComp.layers.add(eyeFootage);
        eyeLayer.name = "blink_" + eb + "_" + side;
        eyeLayer.property("Position").setValue([
          Math.round(eyeBox[0] * footage.width) + eyeFootage.width / 2,
          Math.round(eyeBox[1] * footage.height) + eyeFootage.height / 2]);
        var eyeOpacity = eyeLayer.property("Opacity");
        for (var ec = 0; ec < blink.cues.length; ec++) {
          var eyeCue = blink.cues[ec];
          var eyeKey = eyeOpacity.addKey(eyeCue.at_seconds);
          eyeOpacity.setValueAtKey(eyeKey, eyeCue.opacity);
          eyeOpacity.setInterpolationTypeAtKey(eyeKey, KeyframeInterpolationType.LINEAR, KeyframeInterpolationType.LINEAR);
        }
      }
    }
    footage = mouthComp;
  }
'''
