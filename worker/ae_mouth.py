"""Mouth-only AE overlays for submitted still scenes, driven by the final voice.

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

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

POSES = ('closed', 'half', 'open')


def direction_text(speakers: list[dict], rows: list[dict], start: float) -> str:
    visible = {s['speaker'] for s in speakers}
    turns = [f"{r['speaker']} {r['start'] - start:.2f}~{r['end'] - start:.2f}초: {r['text'][:90]}"
             for r in rows if r['speaker'] in visible]
    return ('씬 시작 기준 ' + '; '.join(turns) + '. 해당 화자의 입만 닫힘·반열림·열림으로 전환하고 '
            '입술과 턱 주변의 원래 그림체를 유지합니다. 내레이션·쉼·상대 화자의 대사에서는 입을 다뭅니다. '
            '화면의 구도와 기존 AE 효과를 유지해 합성하며, 최종 음성 길이와 재생 속도는 바꾸지 않습니다.')


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
        if row.get('speaker') != speaker or row.get('status') not in ('visible', 'offscreen', 'uncertain'):
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
        "Do not change composition or identify a character from a name alone."
    ))
    return visible_speakers(response, speakers)


def normalize_patch(source: Path, target: Path, reference: Path, box: list[float]) -> None:
    """Fit generated mouth art only into its verified region; preserve all other pixels."""
    with Image.open(reference) as base, Image.open(source) as patch:
        if patch.format != 'PNG' or min(patch.size) < 512:
            raise ValueError('Mouth generator must return an actual PNG of at least 512px per edge')
        rect = tuple(round(v * (base.width if i % 2 == 0 else base.height)) for i, v in enumerate(box))
        width, height = rect[2] - rect[0], rect[3] - rect[1]
        if min(width, height) < 8:
            raise ValueError('Mouth is too small for a clean patch')
        rgba = patch.convert('RGBA').resize((width, height), Image.Resampling.LANCZOS)
        if rgba.getchannel('A').getextrema() != (255, 255):
            raise ValueError('Mouth replacement must cover the original lips with opaque matching skin')
        mask = Image.new('L', (width, height))
        ImageDraw.Draw(mask).rounded_rectangle((1, 1, width - 2, height - 2), radius=max(2, min(width, height) // 5), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(min(2, height / 12)))
        rgba.putalpha(mask)
        target.parent.mkdir(parents=True, exist_ok=True)
        rgba.save(target)


def mouth_layers(generator, image: Path, speaker: dict, directory: Path) -> dict[str, str]:
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
            reusable = saved == {'source': source_hash, 'mouth_box': box, 'pose': pose, 'coverage_version': 2, 'sha256': digest(target)}
        if not reusable:
            # A failed native generation is deliberately not silently regenerated/charged.
            raw = generator.generate(role='background', reference=reference, work_dir=directory / f'generate-{pose}', prompt=(
                f"Edit the attached cropped mouth of {speaker['speaker']}. Return the SAME crop with "
                f"the mouth {'fully closed' if pose == 'closed' else 'slightly parted' if pose == 'half' else 'naturally open while speaking'}. "
                "Preserve exact lip center, scale, angle, skin color, lighting, linework and illustration style. "
                "Erase the entire original mouth contour and replace it with exactly ONE mouth in the requested pose. Draw matching opaque skin over all old lip lines, including the corners. No transparency. "
                "Do not add eyes, nose, teeth outside the mouth, a face, characters, text, or a new background. "
                "Match the supplied crop's aspect ratio and keep the crop geometry aligned with it."
            ))
            normalize_patch(raw, target, image, box)
            receipt.write_text(json.dumps({'source': source_hash, 'mouth_box': box, 'pose': pose, 'coverage_version': 2, 'sha256': digest(target)}), encoding='utf-8')
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
  if (mouthRuntime.enabled) {
    var mouthComp = app.project.items.addComp("ae_mouth_source", footage.width, footage.height, 1, DUR, FPS);
    var originalMouthPlate = mouthComp.layers.add(footage);
    originalMouthPlate.property("Position").setValue([footage.width / 2, footage.height / 2]);
    originalMouthPlate.audioEnabled = false;
    if (mouthRuntime.video_source) {
      originalMouthPlate.stretch = 100;
      if (DUR > footage.duration) {
        originalMouthPlate.timeRemapEnabled = true;
        var plateRemap = originalMouthPlate.property("ADBE Time Remapping");
        while (plateRemap.numKeys > 0) plateRemap.removeKey(1);
        var lastFrame = Math.max(0, footage.duration - footage.frameDuration);
        plateRemap.setValueAtTime(0, 0);
        plateRemap.setValueAtTime(lastFrame, lastFrame);
        plateRemap.setValueAtTime(DUR, lastFrame);
        for (var pr = 1; pr <= plateRemap.numKeys; pr++) plateRemap.setInterpolationTypeAtKey(pr, KeyframeInterpolationType.LINEAR, KeyframeInterpolationType.LINEAR);
      }
      originalMouthPlate.outPoint = DUR;
    }
    var mouthPoses = ["closed", "half", "open"];
    for (var ms = 0; ms < mouthRuntime.speakers.length; ms++) {
      var speaker = mouthRuntime.speakers[ms];
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
          mouthOpacity.setValueAtKey(key, cue.pose == pose ? 100 : 0);
          mouthOpacity.setInterpolationTypeAtKey(key, KeyframeInterpolationType.HOLD, KeyframeInterpolationType.HOLD);
        }
      }
    }
    footage = mouthComp;
  }
'''
