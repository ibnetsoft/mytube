"""State-aware selective wuxia mouth art; no narration or AE needed to prepare art."""
import copy
import hashlib
import json
import re
from pathlib import Path

AUTOMATION = 'wuxia_mouth_auto/v1'
ROOT = Path(__file__).resolve().parents[1] / 'output/codex-local-console/wuxia-mouths'


def enable_new_package(package, request=None):
    structure = package.get('structure') or {}
    request = request or {}
    if ((structure.get('wuxia_ae_package') or {}).get('contract') == 'wuxia_still_ae_episode/v1'
        or structure.get('image_style') == 'wuxia_webtoon' or request.get('image_style') == 'wuxia_webtoon'):
        structure.setdefault('wuxia_mouth_policy', {
            'contract': 'wuxia_mouth_policy/v1', 'enabled': True, 'auto_prepare': True,
            'selection': 'large_clear_visible_only', 'zero_eligible_valid': True,
            'minimum_face_height_fraction': .20, 'minimum_mouth_width_fraction': .014,
            'no_forced_quota': True})
    return package


def eligible(speaker, sha):
    from mouth_geometry import animatable
    if speaker.get('status') != 'visible':
        return False
    face, mouth = speaker.get('face_box') or [], speaker.get('mouth_box') or []
    return (len(face) == len(mouth) == 4 and face[3]-face[1] >= .20
            and mouth[2]-mouth[0] >= .014 and speaker.get('confidence', 0) >= .9
            and animatable(speaker, sha))


def locate_selective_speakers(runner, identity, scene, image, rows, cast):
    """One feedback repair; rejected geometry remains uncertain, never approved."""
    from ae_mouth import locate_speakers, digest
    import shutil
    requested = list(dict.fromkeys(r['speaker'] for r in rows))
    source_sha = digest(image)
    feedback = None
    for attempt in range(2):
        class ReviewRunner:
            def __init__(self):
                self.context = None
                self.result = None
                self.refined = {}
                self.attachments = []
            def _stage(self, job, name, context, task):
                if feedback:
                    context = {**context, 'previous_geometry_rejection': feedback}
                    task += '\nRepair the rejected markers using actual pixels and this independent feedback. Never force a pass.'
                result = runner._stage(job, name, context, task)
                if name == '03_ae_mouth_crop_localization':
                    self.refined[result['speaker']] = result
                    self.attachments.extend(context.get('_local_image_paths', []))
                if name == '03_ae_mouth_geometry_review':
                    self.context, self.result = context, result
                return result
        proxy = ReviewRunner()
        try:
            return locate_speakers(proxy, identity, scene, image, rows, cast, allow_uncertain=True)
        except ValueError as error:
            # Do not hide execution errors, missing files or malformed contracts.
            numeric_rejection = (str(error) in {
                'Lip landmarks must lie inside actual face contour and mouth patch',
                'Lip center disagrees with lip endpoints',
                'Lip endpoints must describe a visible mouth',
                'Nose/chin geometry degenerate',
                'Mouth must lie anatomically between nose and chin, not on cheek',
                'Proposed lip points lack visible lip-line pixels; possible cheek placement'}
                                 and bool(proxy.refined))
            if not numeric_rejection and (str(error) != 'Original face crop must pass independent geometry review' or not proxy.context or not proxy.result):
                raise
            feedback = {'source_sha256': source_sha, 'reviews': (proxy.result or {}).get('speakers', [])}
            if numeric_rejection:
                feedback.update(validation_error=str(error), proposed_speakers=copy.deepcopy(list(proxy.refined.values())))
            else:
                reviews = feedback['reviews']
                expected = [s['speaker'] for s in proxy.context['speakers']]
                if (not isinstance(reviews, list) or not reviews
                    or [r.get('speaker') for r in reviews] != expected
                    or any(type(r.get('passed')) is not bool or not r.get('reason') for r in reviews)
                    or not any(r['passed'] is False for r in reviews)):
                    raise
            evidence = image.parent / 'rejected-geometry' / str(attempt + 1)
            evidence.mkdir(parents=True, exist_ok=True)
            attachments = (proxy.context or {}).get('_local_image_paths', []) or [str(image), *proxy.attachments]
            for number, attachment in enumerate(attachments):
                src = Path(attachment)
                shutil.copy2(src, evidence / (str(number) + '-' + src.name))
            (evidence / 'review.json').write_text(json.dumps(feedback, ensure_ascii=False), encoding='utf-8')
            if attempt == 0:
                continue
            candidates = {s['speaker']: copy.deepcopy(s) for s in (proxy.context or {}).get('speakers', [])}
            decisions = {r['speaker']: r for r in feedback['reviews']}
            result = []
            for name in requested:
                speaker = candidates.get(name) or copy.deepcopy(proxy.refined.get(name)) or {'speaker': name}
                decision = decisions.get(name, {})
                if name in candidates and decision.get('passed') is True:
                    from mouth_geometry import validate
                    speaker['mouth_geometry']['review'] = {'passed': True, 'reason': decision.get('reason'), 'proof': 'annotated-face-crop-v4'}
                    validate(speaker, source_sha)
                else:
                    speaker.update(status='uncertain', confidence=0,
                        reason='Lip geometry could not be confirmed after one repair: ' + str(feedback.get('validation_error') or decision.get('reason') or speaker.get('reason') or 'unconfirmed face geometry'))
                    speaker['geometry_review_excluded'] = True
                    if isinstance(speaker.get('mouth_geometry'), dict):
                        speaker['mouth_geometry'].update(render_policy='preserve_original',
                            review={'passed': False, 'reason': speaker['reason'], 'proof': 'annotated-face-crop-v4'})
                result.append(speaker)
            return result


def prepare_selected_poses(image, chosen, runner):
    """A rejected composite preserves that face, without blocking other speakers."""
    import uuid
    import prepared_mouth_layers as cache
    kept, entries, rejected = [], [], []
    prefix = 'Generated mouth layers need review:'
    for speaker in chosen:
        if cache.is_excluded(image, speaker):
            rejected.append({'speaker':speaker['speaker'],'reason':'user_excluded','source_preserved':True})
            continue
        directory = cache.ROOT / cache.cache_key(image, speaker)
        try:
            if not (directory/'reviewed.json').exists():
                prior = sorted(cache.ROOT.glob(directory.name+'.invalid-*/quality-note.txt'))
                if prior and prior[-1].read_text(encoding='utf-8').startswith(prefix):
                    raise ValueError(prior[-1].read_text(encoding='utf-8'))
            art = cache.prepare_scene(image, {'state':'ready','source_sha256':speaker['mouth_geometry'].get('source_sha256'),
                                             'speakers':[speaker]}, runner=runner)
        except ValueError as error:
            if not str(error).startswith(prefix):
                raise
            evidence = None
            if directory.exists() and not (directory/'reviewed.json').exists():
                (directory/'quality-note.txt').write_text(str(error), encoding='utf-8')
                evidence = directory.with_name(directory.name+'.invalid-'+uuid.uuid4().hex[:8])
                directory.rename(evidence)
            if evidence is None:
                notes = sorted(cache.ROOT.glob(directory.name+'.invalid-*/quality-note.txt'))
                evidence = notes[-1].parent if notes else None
            rejected.append({'speaker':speaker['speaker'],'reason':str(error),
                             'source_preserved':True,'rejected_pose_evidence':str(evidence) if evidence else None})
            continue
        if len(art.get('entries', [])) != 1:
            raise RuntimeError('Eligible mouth art was not fully prepared')
        kept.append(speaker);entries.extend(art['entries'])
    return kept, {'entries':entries}, rejected


def prepare_art(structure, identity, download, upload, check=lambda: None, runner=None):
    from PIL import Image
    from ae_mouth import digest, POSES
    from prepared_mouth_layers import reuse_prepared
    from codex_content_runner import CodexStagedContentRunner
    runner = runner or CodexStagedContentRunner()
    package = structure['wuxia_ae_package']
    if not package.get('scenes') or any(not sc.get('states') for sc in package['scenes']):
        raise RuntimeError('waiting_images: state package is not complete')
    result, excluded, reviewed, count = [], [], 0, 0
    for scene in package['scenes']:
        graphics = scene.get('graphics') or []
        for state in scene['states']:
            check()
            graphs = [g for g in graphics if g.get('kind') == 'speech_bubble'
                      and g.get('state_asset_id') == state['asset_id'] and g.get('speaker') and g.get('text')]
            patch = {'scene_id': scene['scene_id'], 'asset_id': state['asset_id'], 'sha256': state.get('sha256'), 'art': []}
            result.append(patch)
            energy_policy=(structure.get('wuxia_mouth_policy') or {}).get('energy_auto') or {}
            if energy_policy.get('enabled') is True and energy_policy.get('auto_prepare') is True:
                from worker.wuxia_energy_preparation import prepare_state
                patch['energy']=prepare_state(state,scene,identity,download,upload,check,runner)
                if patch['energy']['loops']:
                    continue  # Energy-only cuts keep the entire person fixed, including mouth.
            if state.get('energy_only_motion') is True:
                continue
            if not graphs:
                continue
            if not state.get('sha256') or not state.get('gcs_bucket') or not state.get('gcs_path'):
                raise RuntimeError('waiting_images: original state image is not published')
            context = {'sha': state['sha256'], 'graphs': graphs, 'cast': {k: structure.get(k) for k in ('main_character','supporting_characters','character_anchors')}, 'version': 1}
            key = hashlib.sha256(json.dumps(context, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            directory = ROOT / key
            directory.mkdir(parents=True, exist_ok=True)
            image = directory / 'source.png'
            if not image.exists():
                download(state, image)
            if digest(image) != state['sha256']:
                raise ValueError('Original mouth source checksum mismatch')
            geometry_path = directory / 'geometry.json'
            rows = [{'speaker': g['speaker'], 'kind': 'dialogue'} for g in graphs]
            if geometry_path.exists():
                speakers = json.loads(geometry_path.read_text())
            else:
                speakers = locate_selective_speakers(runner, identity+'-'+key, {'text': '\n'.join(g['text'] for g in graphs)}, image, rows, context['cast'])
                check()
                geometry_path.write_text(json.dumps(speakers, ensure_ascii=False))
            expected = list(dict.fromkeys(g['speaker'] for g in graphs))
            if [s['speaker'] for s in speakers] != expected:
                raise ValueError('Incomplete speaker visibility review')
            reviewed += len(speakers)
            chosen = []
            for speaker in speakers:
                if eligible(speaker, state['sha256']):
                    chosen.append(speaker)
                else:
                    excluded.append({'state': state['asset_id'], 'speaker': speaker['speaker'], 'reason': speaker.get('reason') or 'Face too small or lips not fully visible'})
            check()
            chosen, art, pose_rejections = prepare_selected_poses(image, chosen, runner)
            excluded.extend({'state':state['asset_id'], **r} for r in pose_rejections)
            with Image.open(image) as original:
                width, height = original.size
            for speaker in chosen:
                check()
                # prepare_scene may expand the ROI. Reuse exactly the reviewed geometry/patches.
                entry = next(e for e in art['entries'] if e['speaker'] == speaker['speaker'])
                speaker = {**speaker, 'mouth_box': entry['mouth_box'], 'coverage_version': entry['coverage_version']}
                if not reuse_prepared(image, speaker):
                    raise RuntimeError('Reviewed mouth patches cannot be reused')
                poses = {}
                for pose in POSES:
                    target = directory / (hashlib.sha256(speaker['speaker'].encode()).hexdigest()[:12]+'-'+pose+'.png')
                    with Image.open(speaker['layers'][pose]) as crop:
                        canvas = Image.new('RGBA', (width, height))
                        l, t, r, b = [round(v*(width if i%2 == 0 else height)) for i, v in enumerate(speaker['mouth_box'])]
                        if crop.size != (r-l, b-t):
                            raise ValueError('Mouth patch dimensions changed')
                        canvas.paste(crop.convert('RGBA'), (l, t))
                        canvas.save(target)
                    check()
                    poses[pose] = upload(target, digest(target))
                patch['art'].append({'id': 'auto-'+key[:20]+'-'+hashlib.sha256(speaker['speaker'].encode()).hexdigest()[:12],
                    'contract': 'wuxia_mouth_art/v1', 'automation': AUTOMATION, 'enabled': True,
                    'speaker': speaker['speaker'], 'block_ids': [g['block_id'] for g in graphs if g['speaker'] == speaker['speaker']],
                    'source_sha256': state['sha256'], 'width': width, 'height': height,
                    'mouth_box': speaker['mouth_box'], 'face_box': speaker['face_box'], 'poses': poses,
                    'review': {'reviewer': 'local_codex_original_face_crop_and_pose_composites',
                        'mouth_fully_visible': True, 'face_large_enough': True, 'occluded': False,
                        'identity_preserved': True, 'evidence': speaker['mouth_geometry']['evidence']},
                    'generation_method': 'builtin_imagegen_reviewed_three_pose',
                    'quality_notes': ['Stylized amplitude-gated three-pose speech; not phoneme-level lip sync.']})
                count += 1
    return {'states': result, 'report': {'state': 'prepared' if count or any(p.get('energy',{}).get('loops') or p.get('energy',{}).get('decision')=='uncertain' for p in result) else 'not_required', 'selection_complete': True,
            'quality_notes':[{'state':p['asset_id'],'energy_review':p['energy']} for p in result if p.get('energy',{}).get('decision')=='uncertain'],
            'energy_states_reviewed':sum('energy' in p for p in result), 'energy_states_prepared':sum(bool(p.get('energy',{}).get('loops')) for p in result), 'eligible_count': count, 'reviewed_speakers': reviewed, 'excluded': excluded, 'zero_eligible_valid': True}}


def bind_timing(structure, rows, audio, audio_path, art_result):
    """Final recording and exact dialogue identity, never estimated script timings."""
    from ae_mouth import digest, decode_scene_audio, amplitude_cues
    from ae_media_utils import ffmpeg
    if digest(audio_path) != audio['metadata']['sha256']:
        raise ValueError('Final recording checksum mismatch')
    recorded = audio['metadata']['subtitle_timeline']
    compact = lambda value: re.sub(r'[^\w]', '', value)
    result = copy.deepcopy(art_result)
    count = 0
    for patch in result['states']:
        patch['mouths'] = []
        scene = next(s for s in structure['wuxia_ae_package']['scenes'] if s['scene_id'] == patch['scene_id'])
        number = int(re.search(r'S(\d+)$', scene['scene_id'])[1])
        for art in patch['art']:
            cast = [structure.get('main_character') or {}, *(structure.get('supporting_characters') or [])]
            names = {art['speaker']} | {c.get('name') for c in cast if c.get('id') == art['speaker'] or c.get('character_key') == art['speaker']}
            bindings = []
            for block in art['block_ids']:
                g = next(g for g in scene['graphics'] if g['block_id'] == block and g.get('speaker') == art['speaker'] and g.get('state_asset_id') == patch['asset_id'])
                wanted = compact(g['text'])
                matched = [(i,r) for i,r in enumerate(rows) if r.get('scene_number') == number and r.get('dialogue_kind') == 'dialogue'
                           and r.get('dialogue_speaker') in names and compact(r['text']) and compact(r['text']) in wanted]
                if ''.join(compact(r['text']) for _,r in matched) != wanted:
                    raise ValueError('Final dialogue rows missing or ambiguous')
                for i, r in matched:
                    rec = recorded[i]
                    start, end = float(r['start_num']), float(r['end_num'])
                    if (rec['text'] != r['text'] or rec['voice_id'] != r['voice_id']
                        or abs(float(rec['start'])-start) > .001 or abs(float(rec['end'])-end) > .001):
                        raise ValueError('Final dialogue differs from saved recording')
                    bindings.append({'id': r['id'], 'text': r['text'], 'voice_id': r['voice_id'],
                        'dialogue_speaker': r['dialogue_speaker'], 'start': start, 'end': end})
            sr = [r for r in rows if r.get('scene_number') == number]
            start, end = min(float(r['start_num']) for r in sr), max(float(r['end_num']) for r in sr)
            cues = amplitude_cues(decode_scene_audio(ffmpeg(), audio_path, start, end-start), bindings, start=start, duration=end-start)
            for c in cues:
                c['at_seconds'] = round(c['at_seconds']+start, 6)
                if not any(b['start']-.000001 <= c['at_seconds'] < b['end'] for b in bindings):
                    c['pose'] = 'closed'
            mouth = {**art, 'contract': 'wuxia_dialogue_mouth/v1', 'audio_asset_id': audio['id'],
                     'audio_sha256': audio['metadata']['sha256'], 'bindings': bindings, 'cues': cues,
                     'timing_method': 'saved_recording_amplitude_gated_three_pose/v1'}
            if any(c['pose'] != 'closed' and not any(b['start']-.001 <= c['at_seconds'] < b['end'] for b in bindings) for c in cues):
                raise ValueError('Mouth motion outside actual speech')
            patch['mouths'].append(mouth)
            count += 1
    result['report'] = {**result['report'], 'state': 'ready' if count or any(p.get('energy',{}).get('loops') or p.get('energy',{}).get('decision')=='uncertain' for p in result['states']) else 'not_required',
                        'audio_asset_id': audio['id'], 'audio_sha256': audio['metadata']['sha256'],
                        'timing_review': 'exact_recorded_rows_and_waveform_gates', 'bound_count': count}
    return result
