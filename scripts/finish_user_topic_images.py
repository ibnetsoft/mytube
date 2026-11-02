"""Continue one explicitly authorized saved script into its scene-image assets."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'worker')]
from worker import cowork_scene_assets as assets, image_recovery

JOB = 'a41ef96abe8243ab9a9e2a6d8955c712'
BASE = ROOT / 'output' / 'codex-local-console' / JOB / 'delivery'
ART = BASE / 'image-production'
ART.mkdir(parents=True, exist_ok=True)


def write(value):
    target = ART / 'status.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    for attempt in range(8):
        try:
            temporary.replace(target)
            return
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(.1 * (attempt + 1))


def grid(job):
    references = job.get('references') or []
    info = []
    for item in references:
        path = Path(item.get('local_file') or '')
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item.get('sha256'):
            raise ValueError('Missing or changed character reference for ' + str(item.get('name')))
        info.append({'key': item.get('character_key'), 'name': item.get('name'),
                     'sha256': item['sha256'], 'path': str(path.resolve())})
    fingerprint = hashlib.sha256(json.dumps({'prompt': job['prompt'], 'references': info},
        sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    work = ART / 'native-grids' / job['id'] / fingerprint
    if os.name == 'nt' and len(str(work.resolve() / 'source.png')) >= 230:
        import worker_config
        work = worker_config.TEMP_DIR / 'native-grid-requests' / fingerprint
    work.mkdir(parents=True, exist_ok=True)
    source, receipt, response = work / 'source.png', work / 'receipt.json', work / 'response.json'
    if source.exists() and receipt.exists():
        old = json.loads(receipt.read_text(encoding='utf-8'))
        if old.get('fingerprint') == fingerprint and old.get('sha256') == hashlib.sha256(source.read_bytes()).hexdigest():
            return source
        raise ValueError('Generated grid changed; preserve it for inspection')
    if source.exists() or response.exists():
        raise FileExistsError('Incomplete previous image generation; preserve existing output')
    copies = []
    # The native generator accepts at most five reference files per request.
    for i, ref in enumerate(info[:5]):
        dst = work / f'reference-{i:03d}.png'
        shutil.copyfile(ref['path'], dst)
        copies.append({'character_key': ref['key'], 'name': ref['name'], 'path': str(dst)})
    task = ('Use the imagegen skill and the built-in image_gen tool to generate exactly one image. '
        'Use the provided character PNG paths as referenced_image_paths, each with its named identity. '
        'Generate the exact four-panel scene grid in the supplied visual direction, with original '
        'period setting and named characters. Use color in the approved art style unless the scene specifically calls for monochrome. '
        'Do not add text, watermarks, captions or extra panel borders. '
        'Do not switch to external APIs or fallback models. Copy the actual built-in generated image '
        'unchanged to source.png in this working directory. On unavailable or refusal, return status unavailable; '
        'do not invent a file. Return JSON only: {"status":"ready","image_file":"source.png"}.\n'
        + json.dumps({'references': copies, 'additional_characters': [
            {'character_key': ref['key'], 'name': ref['name']} for ref in info[5:]],
            'visual_direction': job['prompt']}, ensure_ascii=False))
    cmd = ['codex', 'exec', '--ephemeral', '--skip-git-repo-check', '--sandbox', 'workspace-write',
           '--color', 'never', '-C', str(work), '--output-last-message', str(response), task]
    result = subprocess.run(cmd, cwd=work, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=1800)
    (work / 'stdout.log').write_text(result.stdout or '', encoding='utf-8')
    (work / 'stderr.log').write_text(result.stderr or '', encoding='utf-8')
    if result.returncode or not response.is_file() or not source.is_file():
        raise RuntimeError('Built-in image generator did not produce the requested grid')
    raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', response.read_text(encoding='utf-8').strip())
    value = json.loads(raw)
    if value.get('status') != 'ready' or value.get('image_file') != 'source.png':
        raise RuntimeError('Built-in image generator did not confirm the output')
    from PIL import Image
    with Image.open(source) as image:
        image.verify()
    receipt.write_text(json.dumps({'fingerprint': fingerprint, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}), encoding='utf-8')
    return source


def check_not_canceled():
    from worker.script_worker_store import ScriptStore
    job = ScriptStore().get(JOB).get('job') or {}
    if job.get('status') == 'canceled':
        raise RuntimeError('Source job was canceled; preserving all generated assets')


def prepare_requested_scene_states(manifest, images, topic_id):
    """Prepare requested story-supported state source images; timings remain proposals."""
    import copy
    from concurrent.futures import ThreadPoolExecutor
    from worker.character_states import prepare_scene_states
    from worker.manga_layer_generation import NativeCodexLayerGenerator
    from codex_content_runner import CodexStagedContentRunner
    requested = []
    for scene in manifest.get('scene_specs') or []:
        number = int(scene.get('scene_number') or 0)
        direction = scene.get('scene_direction_plan') or scene.get('ae_directorial_plan') or {}
        request = direction.get('scene_state_request') or {}
        if 19 <= number <= 50 and request.get('count') in (2, 3):
            requested.append((scene, request))
    def make(item):
        scene, request = item
        number = int(scene['scene_number'])
        base_receipt = json.loads((images / f'scene-{number:03d}-planes.json').read_text(encoding='utf-8'))
        directory = images / 'scene-state-sources' / f'scene-{number:03d}'
        receipt_path = directory / 'receipt.json'
        source_key = hashlib.sha256(json.dumps({'scene_text': request.get('scene_text'),
            'count': request['count'], 'planes': base_receipt['files']}, sort_keys=True,
            ensure_ascii=False).encode()).hexdigest()
        if receipt_path.exists():
            result = json.loads(receipt_path.read_text(encoding='utf-8'))
            if result.get('source_key') != source_key:
                raise ValueError(f'scene {number}: state inputs changed')
            for item in result.get('files') or []:
                path = directory / item['file']
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
                    raise ValueError(f'scene {number}: state source changed')
            return result
        # Reuse the exact cached plan and source edits after interruption. The
        # state preparation helper refuses to overwrite differing pixels.
        directory.mkdir(parents=True, exist_ok=True)
        layers, files = [], []
        for index, role in enumerate(base_receipt['files']):
            if role != 'background' and not role.startswith('character-'):
                continue
            identity = f'plane_{index}'
            actual_role = 'background' if role == 'background' else 'character'
            path = images / f'scene-{number:03d}-{role}.png'
            layers.append({'id': identity, 'role': actual_role, 'name': role, 'z_index': index})
            files.append({'role': 'background_plate' if actual_role == 'background' else 'layer',
                          'layer_id': identity, 'path': path})
        plan = {'width': 1920, 'height': 1080, 'layers': layers}
        runner, generator = CodexStagedContentRunner(), NativeCodexLayerGenerator()
        if number == 19:
            native_generator = generator
            class Scene19VisibilityGenerator:
                def generate(self, *, prompt, role, reference, work_dir):
                    expected = 'e7089ab456bf88cb834fc32d99639b139c39102d72d1d46f18f122f3776992b1'
                    if (role == 'prop_focus' and reference and
                            hashlib.sha256(Path(reference).read_bytes()).hexdigest() == expected and
                            '完全に見えなくなる' in prompt):
                        # A separated character leaving the frame is a visibility change,
                        # not an AI image edit. Keep every other plane untouched.
                        from PIL import Image
                        out = directory / 'scene-state-2-visibility-source.png'
                        if not out.exists():
                            with Image.open(reference) as original:
                                Image.new('RGBA', original.size, (0, 0, 0, 0)).save(out)
                        with Image.open(out) as check:
                            if check.getchannel('A').getextrema() != (0, 0):
                                raise ValueError('Scene 19 visibility source is not transparent')
                        return out
                    return native_generator.generate(prompt=prompt, role=role, reference=reference, work_dir=work_dir)
            generator = Scene19VisibilityGenerator()
        generated_plan, _, generated = prepare_scene_states(plan, files, request, runner, generator, directory)
        state_plan = copy.deepcopy(generated_plan.get('scene_state_plan') or {})
        # Normalized cue proposals are not finalized without narration audio.
        state_plan['timing_status'] = 'unconfirmed'
        result = {'scene_number': number, 'source_key': source_key, 'plan': state_plan,
                  'files': [{'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                            for path in generated]}
        receipt_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return result
    results, failures = [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        from concurrent.futures import as_completed
        futures = {pool.submit(make, item): item for item in requested}
        for future in as_completed(futures):
            item = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                failures.append({'scene_number': item[0]['scene_number'],
                                 'error': str(exc), 'error_type': type(exc).__name__})
    return results, failures


def register_scene_state_sources(topic_id, images, results):
    """Publish authored source files under immutable names and merge with CAS."""
    for result in results:
        check_not_canceled()
        number = result['scene_number']
        source_dir = images / 'scene-state-sources' / f'scene-{number:03d}'
        uploaded = []
        for item in result.get('files') or []:
            path = source_dir / item['file']
            object_name = f"topics/{topic_id}/layers/scene-{number:03d}-{path.stem}-{item['sha256']}.png"
            bucket, object_path, url = assets._upload_gcs_file(path, object_name, 'image/png')
            uploaded.append({'gcs_bucket': bucket, 'gcs_path': object_path, 'media_url': url,
                             'sha256': item['sha256']})
        row, structure, base, headers = assets._topic(topic_id)
        scenes = structure.get('scenes') or []
        pairs = [(i, s) for i, s in enumerate(scenes, 1) if isinstance(s, dict)
                 and assets._scene_number(s, i) == number]
        if len(pairs) != 1:
            raise ValueError(f'scene {number}: missing or ambiguous saved scene')
        index, scene = pairs[0]
        image_asset = dict((scene.get('metadata') or {}).get('cowork_image_asset') or {})
        if not image_asset or not scene.get('image_url'):
            raise ValueError(f'scene {number}: base image is missing')
        image_asset['scene_state_sources'] = {'plan': result['plan'], 'assets': uploaded,
                                               'timing_status': 'unconfirmed'}
        patch = {'image_url': scene['image_url'], 'asset_status': 'ready',
                 'metadata': {'cowork_image_asset': image_asset}}
        assets._patch_topic_scene_assets(topic_id, [{'scene_number': number,
            'expected_source': assets._publish_source_snapshot(scene, index),
            'expected_assets': assets._scene_asset_snapshot(scene), 'asset_patch': patch}], base, headers)


def prepare_face_motion_sources(manifest, images, structure):
    """Prepare only requested speech/blink image poses; never infer cue timing."""
    from concurrent.futures import ThreadPoolExecutor
    from worker.manga_layer_generation import NativeCodexLayerGenerator, _normalize
    selected = set((manifest.get('mouth_work_selection') or {}).get('scene_numbers') or [])
    dialogues = {int(row.get('scene_number') or 0): row.get('spans') or []
                 for row in (structure.get('dialogue_annotations') or {}).get('scenes', [])}
    casts = {int(row.get('scene_number') or 0): row.get('characters') or []
             for row in manifest.get('scene_cast') or []}
    reference_names = {}
    for item in manifest.get('character_references') or []:
        for name in [item.get('name'), item.get('character_key'), *(item.get('aliases') or [])]:
            if name:
                reference_names[str(name).strip().casefold()] = item.get('character_key')
    jobs, unresolved = [], []
    for scene in manifest.get('scene_specs') or []:
        number = int(scene.get('scene_number') or 0)
        if not 19 <= number <= 50:
            continue
        direction = scene.get('scene_direction_plan') or scene.get('ae_directorial_plan') or {}
        blink = direction.get('eye_blink_plan') or {}
        speakers = {str(span.get('speaker') or '').strip() for span in dialogues.get(number, [])
                    if span.get('status') == 'confirmed' and str(span.get('text') or '').strip() and str(span.get('speaker') or '').strip()} if number in selected else set()
        blink_character = str(blink.get('character') or '').strip() if blink.get('enabled') is True else ''
        if not speakers and not blink_character:
            continue
        receipt = json.loads((images / f'scene-{number:03d}-planes.json').read_text(encoding='utf-8'))
        role_keys = receipt.get('character_keys') or {}
        roles = list(role_keys)
        scene_names = casts.get(number) or []
        for name in speakers | ({blink_character} if blink_character else set()):
            key = reference_names.get(name.casefold())
            role = next((r for r in roles if role_keys[r] == key), None) if key else None
            if role is None and name in scene_names:
                index = scene_names.index(name)
                candidate = f'character-{index+1:02d}'
                role = candidate if candidate in role_keys else None
            if role is None and len(roles) == 1:
                role = roles[0]
            if role is None:
                unresolved.append({'scene_number': number, 'character': name, 'reason': 'character plane is ambiguous'})
                continue
            poses = (['mouth_closed','mouth_half','mouth_open'] if name in speakers else [])
            if name == blink_character:
                poses.append('eyes_closed')
            existing = next((job for job in jobs if job['scene_number'] == number and job['role'] == role), None)
            if existing:
                existing['poses'] = list(dict.fromkeys(existing['poses'] + poses))
            else:
                jobs.append({'scene_number': number, 'role': role, 'character': name,
                             'character_key': role_keys[role], 'poses': poses})
    def make(job):
        number, role = job['scene_number'], job['role']
        source = images / f'scene-{number:03d}-{role}.png'
        source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        directory = images / 'face-motion-sources' / f'scene-{number:03d}-{role}'
        directory.mkdir(parents=True, exist_ok=True)
        receipt_path = directory / 'receipt.json'
        record = json.loads(receipt_path.read_text(encoding='utf8')) if receipt_path.exists() else {'source_sha256':source_sha,'poses':{}}
        if record.get('source_sha256') != source_sha:
            raise ValueError(f'scene {number}: character plane changed')
        generator = NativeCodexLayerGenerator()
        descriptions = {'mouth_closed':'lips naturally closed', 'mouth_half':'lips slightly parted',
                        'mouth_open':'mouth open as if speaking', 'eyes_closed':'both eyelids naturally closed'}
        for pose in job['poses']:
            target = directory / f'{pose}.png'
            prior = record['poses'].get(pose)
            if target.exists():
                if not prior or prior != hashlib.sha256(target.read_bytes()).hexdigest():
                    raise ValueError(f'scene {number}: existing {pose} source differs')
                continue
            raw = generator.generate(role='character', reference=source, work_dir=directory / ('request-'+pose),
                prompt=('Edit only the mouth or eyelids specified here: '+descriptions[pose]+'. '
                    'Keep the entire original character, exact 16:9 canvas registration, pose, clothing, face and lighting. '
                    'Transparent background. No scenery, text or extra person. No timing instructions.'))
            temporary = target.with_suffix('.png.tmp')
            _normalize(raw, temporary, 'character')
            temporary.replace(target)
            record['poses'][pose] = hashlib.sha256(target.read_bytes()).hexdigest()
            receipt_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf8')
        return {**job, 'directory': str(directory), 'poses_sha256': record['poses'],
                'source_sha256': source_sha, 'timing_status': 'unconfirmed', 'identity_review': 'not_requested'}
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(make, jobs))
    return results, unresolved


def register_face_motion_sources(topic_id, results):
    grouped = {}
    for result in results:
        number = result['scene_number']
        sources = []
        for pose, sha in result['poses_sha256'].items():
            path = Path(result['directory']) / f'{pose}.png'
            object_name = f"topics/{topic_id}/layers/scene-{number:03d}-{result['role']}-{pose}-{sha}.png"
            bucket, object_path, url = assets._upload_gcs_file(path, object_name, 'image/png')
            sources.append({'pose':pose,'gcs_bucket':bucket,'gcs_path':object_path,'media_url':url,'sha256':sha})
        grouped.setdefault(number, []).append({'character':result['character'], 'character_key':result['character_key'],
            'source_sha256':result['source_sha256'], 'timing_status':'unconfirmed',
            'identity_review':'not_requested', 'assets':sources})
    for number, records in grouped.items():
        check_not_canceled()
        row, structure, base, headers = assets._topic(topic_id)
        pairs = [(i,s) for i,s in enumerate(structure.get('scenes') or [],1)
                 if isinstance(s,dict) and assets._scene_number(s,i)==number]
        if len(pairs)!=1:
            raise ValueError(f'scene {number}: missing or ambiguous saved scene')
        index, scene = pairs[0]
        image_asset = dict((scene.get('metadata') or {}).get('cowork_image_asset') or {})
        if not image_asset or not scene.get('image_url'):
            raise ValueError(f'scene {number}: base image is missing')
        image_asset['face_motion_sources'] = records
        assets._patch_topic_scene_assets(topic_id, [{'scene_number':number,
            'expected_source':assets._publish_source_snapshot(scene,index),
            'expected_assets':assets._scene_asset_snapshot(scene),
            'asset_patch':{'image_url':scene['image_url'],'asset_status':'ready',
                           'metadata':{'cowork_image_asset':image_asset}}}], base, headers)


def main():
    write({'stage': 'waiting_for_script_registration', 'source_job_id': JOB})
    receipt_path = BASE / 'registration-receipt.json'
    from worker.script_delivery_status import active as active_supervisor
    while not receipt_path.exists():
        if not active_supervisor(ROOT / 'output' / 'codex-local-console', JOB):
            raise RuntimeError('Script recovery supervisor stopped before topic registration')
        time.sleep(20)
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    if receipt.get('source_job_id') != JOB:
        raise ValueError('Registration receipt is for another script')
    assets._supabase()  # Load the same configured storage/database environment as the publisher.
    check_not_canceled()
    topic_id = str(receipt['topic_id'])
    manifest = ART / 'manifest.json'
    if not manifest.exists():
        previous = assets._topic
        def topic_with_requested_policy(value):
            row, structure, base, headers = previous(value)
            if str(value) != topic_id:
                raise ValueError('Topic identity changed')
            structure['skip_face_identity_review'] = True
            return row, structure, base, headers
        from worker import character_reference_preflight as character_preflight
        original_preflight = character_preflight.ensure_character_references
        def preserve_saved_identity(row, structure, directory, **kwargs):
            anchors = structure.get('character_anchors') or {}
            identity = {'main_character': anchors.get('main_character') or structure.get('main_character'),
                        'supporting_characters': anchors.get('supporting_characters') or structure.get('supporting_characters') or [],
                        'scene_cast': structure.get('scene_cast') or anchors.get('scene_cast')}
            if not identity['main_character'] or not isinstance(identity['scene_cast'], list):
                raise ValueError('Saved character designs or scene cast are missing; do not replace them')
            from worker.character_continuity import validate_character_identity
            validate_character_identity(identity, structure.get('scenes') or [])
            from codex_content_runner import CodexContentConfig
            class SavedIdentityRunner:
                config = CodexContentConfig.from_environment()
                def finalize_character_identity(self, job_id, context, setting):
                    return identity
            return original_preflight(row, structure, directory, runner=SavedIdentityRunner(), **kwargs)
        assets._topic = topic_with_requested_policy
        character_preflight.ensure_character_references = preserve_saved_identity
        write({'stage': 'preparing_character_references', 'topic_id': topic_id})
        try:
            assets.export_manifest(topic_id, manifest, assets.DEFAULT_BUCKET)
        finally:
            assets._topic = previous
            character_preflight.ensure_character_references = original_preflight
    value = assets._manifest(manifest)
    scope = value.get('effect_scene_range')
    if scope != {'start': 19, 'end': 50}:
        raise ValueError('Saved topic is missing its confirmed 19–50 effect scope')
    recovery = image_recovery.state_path(manifest)
    image_recovery.ensure_state(manifest)
    while True:
        state = json.loads(recovery.read_text(encoding='utf-8'))
        summary = image_recovery.summary(state)
        if summary['complete']:
            break
        if summary['attention']:
            raise RuntimeError('Image generation needs attention: ' + json.dumps(summary['attention'], ensure_ascii=False))
        jobs = summary['runnable']
        if not jobs:
            time.sleep(5)
            continue
        check_not_canceled()
        batch = jobs[:3]
        write({'stage': 'generating_scene_grids', 'topic_id': topic_id,
               'job_ids': [job['id'] for job in batch], 'ready_grids': len(summary['ready'])})
        for job in batch:
            image_recovery.update_file(recovery, lambda s, j=job: image_recovery.transition(s, {'action':'start','job_id':j['id']}))
        from concurrent.futures import ThreadPoolExecutor, as_completed
        failures = []
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(grid, job): job for job in batch}
            for future in as_completed(futures):
                job = futures[future]
                try:
                    image = future.result()
                    image_recovery.update_file(recovery, lambda s, j=job, p=image: image_recovery.transition(s, {'action':'result',
                        'job_id':j['id'], 'outcome':'generated', 'image_file':str(p)}))
                    image_recovery.update_file(recovery, lambda s, j=job: image_recovery.transition(s, {'action':'accept',
                        'job_id':j['id'], 'visual_review':'Not performed: user requested no identity review; PNG integrity checked only.'}))
                except Exception as exc:
                    state = json.loads(recovery.read_text(encoding='utf-8'))
                    current = image_recovery.get_job(state, job['id'])
                    if current.get('status') == 'running':
                        image_recovery.update_file(recovery, lambda s, j=job, e=exc: image_recovery.transition(s, {'action':'result',
                            'job_id':j['id'], 'outcome':'unknown', 'reason':str(e)}))
                    failures.append(f"{job['id']}: {type(exc).__name__}: {exc}")
        if failures:
            raise RuntimeError('; '.join(failures))
    check_not_canceled()
    write({'stage':'generating_independent_planes_and_composites', 'topic_id':topic_id})
    images = ART / 'images'
    assets.crop_grids(manifest, ART / 'native-grids', images)
    check_not_canceled()
    write({'stage':'publishing_scene_images_and_original_planes', 'topic_id':topic_id})
    urls = assets.publish(manifest, images, False, reuse_existing=True)
    expected = int(value['scene_count'])
    if len(urls) != expected:
        raise RuntimeError(f'Published {len(urls)} of {expected} scenes')
    write({'stage':'preparing_requested_scene_state_sources','topic_id':topic_id,'published_count':len(urls)})
    states, state_failures = prepare_requested_scene_states(value, images, topic_id)
    register_scene_state_sources(topic_id, images, states)
    if state_failures:
        (ART / 'scene-state-failures.json').write_text(json.dumps(state_failures, ensure_ascii=False, indent=2), encoding='utf-8')
    write({'stage':'preparing_requested_mouth_and_blink_sources','topic_id':topic_id,'published_count':len(urls)})
    _, saved_structure, _, _ = assets._topic(topic_id)
    faces, unresolved = prepare_face_motion_sources(value, images, saved_structure)
    register_face_motion_sources(topic_id, faces)
    if state_failures:
        raise RuntimeError('Some scene state sources remain unavailable; see scene-state-failures.json')
    if unresolved:
        raise RuntimeError('Some requested face-motion sources could not be assigned: ' + json.dumps(unresolved, ensure_ascii=False))
    write({'stage':'published_requery_required','topic_id':topic_id,'published_count':len(urls),
           'quality_note':'Face identity review was not requested and was not performed.'})
    row, structure, _, _ = assets._topic(topic_id)
    scenes = structure.get('scenes') or []
    ready = [s for s in scenes if s.get('image_url') and s.get('asset_status') == 'ready']
    if len(ready) != expected:
        raise RuntimeError(f'Requery found {len(ready)} of {expected} images')
    by_number = {int(s.get('scene_number') or s.get('scene_order') or 0): s for s in scenes}
    verified_planes = 0
    for number in range(scope['start'], min(scope['end'], expected) + 1):
        item = by_number.get(number) or {}
        metadata = ((item.get('metadata') or {}).get('cowork_image_asset') or {}).get('independent_planes') or {}
        remote = {entry.get('role'): entry for entry in metadata.get('assets') or []}
        local_path = images / f'scene-{number:03d}-planes.json'
        if not local_path.is_file():
            raise RuntimeError(f'Scene {number}: original plane receipt is missing')
        local = json.loads(local_path.read_text(encoding='utf-8'))
        for role, sha in (local.get('files') or {}).items():
            value = remote.get(role) or {}
            if value.get('sha256') != sha or not value.get('gcs_bucket') or not value.get('gcs_path'):
                raise RuntimeError(f'Scene {number}: saved {role} plane was not found on requery')
            verified_planes += 1
    for item in faces:
        saved = by_number.get(item['scene_number']) or {}
        records = ((saved.get('metadata') or {}).get('cowork_image_asset') or {}).get('face_motion_sources') or []
        matching = [r for r in records if r.get('character_key') == item['character_key']]
        if not matching or matching[0].get('timing_status') != 'unconfirmed':
            raise RuntimeError(f"Scene {item['scene_number']}: face-motion sources were not found on requery")
        saved_hashes = {entry.get('sha256') for entry in matching[0].get('assets') or []}
        if not set(item['poses_sha256'].values()).issubset(saved_hashes):
            raise RuntimeError(f"Scene {item['scene_number']}: a face-motion source is missing")
    for item in states:
        saved = by_number.get(item['scene_number']) or {}
        metadata = ((saved.get('metadata') or {}).get('cowork_image_asset') or {}).get('scene_state_sources') or {}
        if metadata.get('timing_status') != 'unconfirmed' or len(metadata.get('assets') or []) != len(item['files']):
            raise RuntimeError(f"Scene {item['scene_number']}: state sources were not found on requery")
    write({'stage':'completed','topic_id':topic_id,'scene_count':expected,'requeried_count':len(ready),
           'requeried_plane_count':verified_planes,'prepared_scene_state_count':len(states),'prepared_face_motion_count':len(faces),
           'quality_note':'Face identity review was not requested and was not performed.'})


if __name__ == '__main__':
    import requests
    lock = (ART / 'image-supervisor.lock').open('a+b')
    lock.write(b'0'); lock.flush(); lock.seek(0)
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    retry_count = 0
    while True:
        try:
            main()
            break
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, PermissionError) as exc:
            retry_count += 1
            delay = min(300, 10 * 2 ** min(retry_count, 5))
            write({'stage':'retry_wait','error_type':type(exc).__name__,'error':str(exc),
                   'retry':retry_count,'retry_after_seconds':delay})
            time.sleep(delay)
        except Exception as exc:
            write({'stage':'failed','error_type':type(exc).__name__,'error':str(exc)})
            raise
