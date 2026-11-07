"""Resume a NEW script-worker package through the active web topic readiness contract.

Only a topic carrying this exact source job marker may be written. Media plans
are distinguished from actual generated media; this does not enqueue a render.
"""
import copy
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def expand_direction_templates(value):
    """Compile only explicitly AI-authored template references, never infer a plan."""
    templates = value.get('scene_direction_templates')
    if templates is None:
        return value
    if not isinstance(templates, dict):
        raise ValueError('Direction templates must be an authored object')
    def merge(base, override):
        result = copy.deepcopy(base)
        for key, item in override.items():
            result[key] = merge(result[key], item) if isinstance(result.get(key), dict) and isinstance(item, dict) else copy.deepcopy(item)
        return result
    output = []
    for row in value.get('scene_directions') or []:
        if not isinstance(row, dict):
            raise ValueError('Every authored direction must be an object')
        reference = row.get('template_id')
        if reference is None:
            output.append(copy.deepcopy(row)); continue
        if not isinstance(reference, str) or reference not in templates or not isinstance(templates[reference], dict):
            raise ValueError('Unknown authored direction template')
        if 'scene_number' in templates[reference] or 'scene_order' in templates[reference] or type(row.get('scene_number')) is not int:
            raise ValueError('Every template use needs its own explicit scene number')
        output.append(merge(templates[reference], row))
    return {**value, 'scene_directions': output}


def chunked_direction(stage, identity, name, context, task, batch_size=20):
    """Bound long direction responses without changing any narration or timing."""
    from purpose_direction import direct_with_repair
    from scene_visual_director import validate_directorial_plans
    scenes = context['scenes']
    combined = []
    topic = None
    prior = (context.get('validation_feedback') or {}).get('previous_directions')
    if not prior:
        from worker_config import OUTPUT_DIR
        for path in sorted((OUTPUT_DIR/'codex_stage_requests').glob(f'{identity}.{name}.*.attempt-*.response.json')):
            input_path = Path(str(path).split('.attempt-')[0] + '.input.json')
            if input_path.exists() and json.loads(input_path.read_text(encoding='utf-8')) == context:
                prior = json.loads(path.read_text(encoding='utf-8'))
                break
    prior_error = None
    if prior:
        try:
            validate_directorial_plans(scenes, copy.deepcopy(prior),
                direction_profile=context.get('direction_profile', {}).get('id'), require_execution=True)
            return prior
        except ValueError as error:
            prior_error = str(error)
        topic = prior.get('topic_direction')
    for offset in range(0, len(scenes), batch_size):
        batch = copy.deepcopy(scenes[offset:offset+batch_size])
        current = copy.deepcopy(context)
        current['scenes'] = batch
        structure = current.get('structure') or {}
        current['structure'] = {**structure, 'scenes': batch, 'scene_count': len(batch)}
        for key in ('dialogue_annotations', 'audio_performance'):
            value = current['structure'].get(key)
            if isinstance(value, dict) and isinstance(value.get('scenes'), list):
                numbers = {s.get('scene_number') for s in batch}
                current['structure'][key] = {**value, 'scenes': [s for s in value['scenes'] if s.get('scene_number') in numbers]}
        current['locked_topic_direction'] = topic
        current.pop('validation_feedback', None)
        if prior_error:
            current['validation_feedback'] = {'error': prior_error,
                'previous_directions': (prior.get('scene_directions') or [])[offset:offset+batch_size],
                'scope': 'Repair only the requested scene batch; preserve already authored intentions and final narration.'}
        last_raw = {}
        def validate_batch(result):
            if result.get('_template_expansion_error'):
                raise ValueError(result['_template_expansion_error'])
            rows = result.get('scene_directions') or []
            if rows and all('scene_number' in row for row in rows):
                if [row['scene_number'] for row in rows] != [scene.get('scene_number') for scene in batch]:
                    raise ValueError('Direction batch changed the requested scene numbers/order')
            return validate_directorial_plans(batch, result,
                direction_profile=context.get('direction_profile', {}).get('id'), require_execution=True)
        def author(job_id, stage_name, data, instruction):
            nonlocal last_raw
            stage_name = f'{name}_batch_{offset+1:03d}_{offset+len(batch):03d}_{stage_name}'
            # A response authored under the equivalent uncompressed contract is
            # reusable only with identical inputs and the SAME strict validator.
            from worker_config import OUTPUT_DIR
            for path in sorted((OUTPUT_DIR/'codex_stage_requests').glob(f'{job_id}.{stage_name}.*.attempt-*.response.json')):
                input_path = Path(str(path).split('.attempt-')[0] + '.input.json')
                if input_path.exists() and json.loads(input_path.read_text(encoding='utf-8')) == data:
                    try:
                        cached = expand_direction_templates(json.loads(path.read_text(encoding='utf-8')))
                        if topic is not None:
                            cached = {**cached, 'topic_direction': topic}
                        validate_batch(copy.deepcopy(cached))
                        last_raw = cached
                        return last_raw
                    except ValueError:
                        pass
            raw = stage(job_id, stage_name, data,
                instruction + '\nBATCH SCOPE: Return scene_directions ONLY for the exact ordered context.scenes. '
                'The full script/blueprint is continuity context, not additional requested scenes. '
                'Reuse locked_topic_direction exactly when supplied; never rewrite narration or scene timing. '
                'Every scene MUST include execution_design under the supplied v2 contract, even a hold. '
                'Plan normalized keys and explicit source dependencies; missing actual artwork means pending review, '
                'not permission to omit the execution design. Never claim source_video_reviewed without actual supplied frames. '
                'COMPACT AUTHORING: Avoid repeating identical large JSON objects. You may return '
                'scene_direction_templates:{template_id:{complete shared fields including execution_design}} '
                'and explicit scene_directions:[{scene_number,template_id,dramatic_intent,visual_strategy,timed_beats,...overrides}]. '
                'A template reference explicitly includes those authored fields; dictionaries merge recursively and arrays replace. '
                'Author every template yourself in this response, no implicit defaults. Keep scene-specific intentions, timings, '
                'unique voice quotes and evidence individualized. Expanded scenes must pass the exact same full contract.')
            try:
                last_raw = expand_direction_templates(raw)
            except ValueError as error:
                # Feed malformed references to the bounded repair stage rather
                # than retrying the same cached invalid response forever.
                last_raw = {**raw, '_template_expansion_error': str(error)}
            if topic is not None:
                last_raw = {**last_raw, 'topic_direction': topic}
            return last_raw
        direct_with_repair(author, identity, current, task, validate_batch)
        if topic is None:
            topic = last_raw['topic_direction']
        combined.extend(last_raw['scene_directions'])
    if len(combined) != len(scenes):
        raise ValueError('Batched direction lost scene coverage')
    return {'topic_direction': topic, 'scene_directions': combined}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    import time
    for attempt in range(8):
        try:
            temp.replace(path)
            break
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(.1 * (attempt + 1))


def web_readiness(topic, directory):
    """Run the actual deployed-source predicate, not a weaker Python substitute."""
    path = directory / 'web-topic.json'
    write(path, topic)
    code = r'''
const fs=require('fs'),path=require('path');
const root=process.argv[1], file=process.argv[2];
const ts=require(path.join(root,'auth-web/node_modules/typescript'));
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{
compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText,f);
const {isPreparedUserTopic,hasReadySceneMediaPrompts}=require(path.join(root,'auth-web/lib/preparedTopic.ts'));
const topic=JSON.parse(fs.readFileSync(file,'utf8'));
console.log(JSON.stringify({ready:isPreparedUserTopic(topic),prompts_ready:hasReadySceneMediaPrompts(topic)}));
'''
    result = subprocess.run(['node', '-e', code, str(ROOT), str(path)], capture_output=True,
                            text=True, encoding='utf-8', timeout=30, check=True)
    return json.loads(result.stdout)


def complete_candidate(identity, candidate, request, runner, directory, notify=lambda stage: None):
    from worker.codex_content_runner import (CodexContentError, _validate_video_prompt, _plan_image_generation_efficiency)
    from worker.content_language import resolve_setting, visual_setting_prompt
    from worker.character_continuity import scene_continuity_prompt
    from worker.scene_composition import normalize_scene_shot_design, apply_scene_shot_design
    from services.image_grid_prompts import (grid_windows, build_compact_image_grid_prompts,
        validate_scene_image_prompt_readiness, validate_image_grid_prompt_readiness)
    package = copy.deepcopy(candidate)
    structure = package['structure']
    scenes = structure['scenes']
    if not scenes or not package.get('script'):
        raise ValueError('Actual final script and scenes are required')
    required = int(request.get('required_video_scene_count', 18))
    setting = resolve_setting(request)
    # Downstream image generation must use the same confirmed country, era and style.
    structure['content_setting'] = copy.deepcopy(setting)
    anchors = package.get('character_anchors') or {}
    seen = set()
    for offset in range(0, len(scenes), 12):
        batch = scenes[offset:offset + 12]
        numbers = [int(s.get('scene_number') or s.get('scene_order') or offset+i+1) for i, s in enumerate(batch)]
        context = {'content_setting': setting, 'character_anchors': anchors,
                   'required_video_scene_count': required, 'scenes': batch,
                   'user_requirements': request.get('notes', '')}
        task = (
            'Author production prompts for these EXACT final scenes; do not rewrite speech or scene order. '
            'When visual_action exists, use it as authoritative image-making staging alongside spoken text. '
            'Silent visual cuts still need artwork. Never copy image instructions into narration or add speech to fill duration. '
            'Return {scenes:[{scene_number,shot_design:{shot_size,camera_angle,subject_presence,subject_scale,composition,repetition_reason},'
            'image_prompt,video_prompt,grid_panel_prompt}]}. Preserve names, locked visual DNA, clothing, hair and historical setting. '
            'Use ONLY actually present participants; scenery/object-only scenes need no person. Image prompts must be unique '
            'English prompts >=120 characters, detailed and grounded in each scene, no captions/text. Each grid_panel_prompt '
            'must be a unique >=80-character English concise visual brief. shot_design values follow the existing scene '
            'composition contract. Support existing AE directions and independent full-canvas background/foreground/prop layers. '
            'Only scenes <=required_video_scene_count require >=300-character English video_prompt with exactly one '
            'approved camera movement (slow push-in, slow pull-back, gentle pan, gentle tilt, slow dolly, slow tracking shot, '
            'locked-off shot, subtle crane movement, slow drift) and literal guards '
            'no dialogue, no narration, no subtitles, no captions, no music, no sound effects, no audio. '
            'Other scenes must omit video_prompt. These are prompts, not generated media. '
            'Allowed shot_size: extreme_wide,wide,medium,close_up,detail; camera_angle: eye_level,high_angle,low_angle,overhead,oblique; '
            'subject_presence: character_required,character_optional,environment_only,object_insert; subject_scale: none,small,medium,large,detail.')
        notify(f'유저웹 장면 프롬프트 {offset+1}~{offset+len(batch)}/{len(scenes)}')
        last = ''
        for attempt in range(3):
            reply = runner._stage('delivery-' + identity, f'03_web_media_{offset:04d}',
                                  {**context, **({'validation_failure': last} if last else {})}, task)
            try:
                rows = reply.get('scenes') or []
                if len(rows) != len(batch) or [r.get('scene_number') for r in rows] != numbers:
                    raise ValueError('Media must cover exact requested scene numbers in order')
                for number, row in zip(numbers, rows):
                    prompt = row.get('image_prompt') or ''
                    if len(prompt.strip()) < 120 or prompt in seen:
                        raise ValueError('Missing, short or duplicate actual scene prompt')
                    if len(str(row.get('grid_panel_prompt') or '').strip()) < 80:
                        raise ValueError('Missing actual grid panel prompt')
                    normalize_scene_shot_design(row.get('shot_design'), number, prompt)
                    if number <= required:
                        _validate_video_prompt(row.get('video_prompt') or '', number)
                break
            except (ValueError, TypeError, CodexContentError) as error:
                last = str(error)
                if attempt == 2:
                    raise
        for number, scene, row in zip(numbers, batch, rows):
            seen.add(row['image_prompt'])
            design = normalize_scene_shot_design(row['shot_design'], number, row['image_prompt'])
            lock = scene_continuity_prompt(anchors, [number])
            scene.update(scene_order=number, scene_number=number, shot_design=design,
                image_prompt=apply_scene_shot_design(row['image_prompt'], design) + ('\n' + lock if lock else ''),
                media_prompt_status='ready', video_prompt_required=number <= required,
                visual_type='video' if number <= required else 'image', grid_panel_prompt=row['grid_panel_prompt'])
            if number <= required:
                scene.update(video_prompt=row['video_prompt'], video_generation_mode='user_upload')
            else:
                scene.pop('video_prompt', None)
        write(directory/'media-progress.json', {'completed_scenes': offset+len(batch), 'scenes': scenes[:offset+len(batch)]})
    specs = []
    positions = ['Top-Left', 'Top-Right', 'Bottom-Left', 'Bottom-Right']
    for index, (start, end) in enumerate(grid_windows(len(scenes)), 1):
        group = scenes[start:end]
        specs.append({'grid_number': index, 'scene_numbers': [s['scene_number'] for s in group],
            'shared_style': visual_setting_prompt(setting),
            'negative_prompt': 'no text, no captions, no letters, no watermarks, no borders, no grid lines',
            'panels': [{'scene_number': s['scene_number'], 'scene_id': f"scene{s['scene_number']:03d}",
                       'position': positions[i], 'panel_prompt': s['grid_panel_prompt']} for i, s in enumerate(group)]})
    grids = build_compact_image_grid_prompts(specs)
    validate_scene_image_prompt_readiness(scenes)
    validate_image_grid_prompt_readiness(scenes, grids, status='ready', require_status='ready', require_compact_template=True)
    effects = structure.get('ae_effect_plans') or []
    policy = _plan_image_generation_efficiency(scenes, request, effects)
    structure.update(image_grid_prompts=grids, image_grid_prompt_status='ready',
        required_video_scene_count=required, image_layer_mode=request.get('image_layer_mode', 'hybrid'),
        image_generation_policy=policy, psd_layer_prompts=policy.get('psd_layer_prompts', []),
        psd_layer_prompt_status='planned', psd_layer_scene_count=policy.get('psd_layer_scene_count', 0))
    notify('유저웹 설명·태그·썸네일 문구 생성')
    metadata = runner._stage('delivery-' + identity, '04_web_topic_metadata', {
        'language': request.get('language'), 'title': package.get('generated_title') or request['title'],
        'script': package['script'], 'content_setting': setting},
        'Return {publish_metadata:{titles:[exact supplied title],description:viewer-facing text in selected language '
        'at least 150 characters,tags:[at least 5 distinct strings],hashtags:[at least 3 strings]},'
        'thumbnail_hook_texts:[3 distinct short hook texts in selected language],thumbnail_image_prompt:English '
        'text-free thumbnail background prompt at least 120 characters,thumbnail_text_layers:[{text:string}]}. '
        'Faithful to the completed script. Original artwork only. No worker/AI/QA terminology in viewer-facing text. '
        'These are editable copy and prompts; no thumbnail image has been generated.')
    if len(str(metadata.get('publish_metadata', {}).get('description') or '').strip()) < 150:
        raise ValueError('Missing publish description')
    if len(metadata.get('thumbnail_hook_texts') or []) != 3 or len(str(metadata.get('thumbnail_image_prompt') or '')) < 120:
        raise ValueError('Missing thumbnail plan')
    package.update(metadata)
    package.update(production_ready=False, thumbnail_completed=False, required_video_scene_count=required)
    completed_prefixes = ('배경 설정:', '장면 이미지·첫 ', '메타데이터·썸네일 기획')
    package['remaining'] = [item for item in package.get('remaining', [])
                            if not str(item).startswith(completed_prefixes)]
    if candidate['script'] != package['script'] or len(candidate['structure']['scenes']) != len(scenes):
        raise ValueError('Delivery must preserve reviewed script and scene count')
    write(directory/'delivery-package.json', package)
    return package


def topic_row(identity, package, request):
    structure = package['structure']
    return {'topic': package.get('generated_title') or request['title'],
        'generated_title': package.get('generated_title') or request['title'], 'category_id': int(request['category_id']),
        'language': request['language'], 'status': 'pending', 'assigned_at': None, 'assigned_employee_email': '',
        'assigned_script_style': request.get('script_style', 'story'), 'assigned_image_style': request.get('image_style'),
        'recommended_duration_minutes': request['duration_minutes'], 'assigned_duration_minutes': request['duration_minutes'],
        'total_scenes': len(structure['scenes']), 'video_scenes': request.get('required_video_scene_count', 18),
        'image_scenes': max(0, len(structure['scenes'])-request.get('required_video_scene_count', 18)),
        'pregenerated_script': package['script'], 'pregenerated_script_status': 'ready',
        'pregenerated_structure': structure, 'pregenerated_structure_status': 'ready',
        'publish_metadata': package['publish_metadata'], 'narrative_blueprint': package.get('narrative_blueprint', {}),
        'script_quality_report': package.get('script_quality_report', {}),
        'progress_payload': {'source_script_job_id': identity, 'prepared_topic_ready': True,
            'script_translations': package.get('script_translations', {}),
            'required_video_scene_count': request.get('required_video_scene_count', 18),
            'character_anchors': package.get('character_anchors', {}), 'sfx_plan': package.get('sfx_plan'),
            'sfx_cues': package.get('sfx_cues', []), 'bgm_prompt': package.get('bgm_prompt') or structure.get('bgm_prompt'),
            'publish_metadata': package['publish_metadata'], 'thumbnail_hook_texts': package['thumbnail_hook_texts'],
            'thumbnail_image_prompt': package['thumbnail_image_prompt'], 'thumbnail_completed': False,
            'image_generation_status': 'not_started', 'quality_notes': package.get('script_quality_report', {})}}


def publish_topic(identity, package, request, store, directory):
    if hasattr(store, 'get'):
        source = store.get(identity)
        if source['job'].get('status') == 'canceled' or source.get('request', {}).get('mode') != 'new':
            raise ValueError('Source job canceled or not a new topic')
        if source.get('candidate', {}).get('script') != package.get('script'):
            raise ValueError('Source script changed before publication')
    query = {'select': '*', 'progress_payload->>source_script_job_id': 'eq.' + identity}
    rows, _ = store.request('GET', 'topics_queue', params=query)
    if len(rows) > 1:
        raise ValueError('Duplicate source-job topics require repair; never modify another topic')
    row = topic_row(identity, package, request)
    if not web_readiness(row, directory)['ready']:
        raise ValueError('Active web topic readiness contract rejected package')
    acknowledged = False
    owned = False
    if rows:
        existing = rows[0]
        receipt_path = directory/'registration-receipt.json'
        prior = json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.exists() else {}
        acknowledged = (prior.get('source_job_id') == identity and prior.get('topic_id') == existing['id']
                        and prior.get('script_sha256') == hashlib.sha256(package['script'].encode()).hexdigest())
        owned = existing.get('assigned_at') or existing.get('assigned_employee_email') or existing.get('status') != 'pending'
        if owned and (not acknowledged or existing.get('status') == 'canceled'):
            raise ValueError('Topic is already owned or canceled; never overwrite it')
        # An acknowledged delivery is immutable on retry, not a blind upsert.
        if existing.get('pregenerated_script') != package['script']:
            raise ValueError('Existing registered script differs')
        registered = existing
    else:
        try:
            result, _ = store.request('POST', 'topics_queue', body=row, prefer='return=representation')
            registered = result[0]
        except Exception:
            # Recover an unknown POST outcome by its durable provenance marker.
            result, _ = store.request('GET', 'topics_queue', params=query)
            if len(result) != 1:
                raise
            registered = result[0]
    result, _ = store.request('GET', 'topics_queue', params={'select': '*', 'id': 'eq.'+str(registered['id'])})
    verified = result[0]
    if verified.get('progress_payload', {}).get('source_script_job_id') != identity:
        raise ValueError('Registered topic provenance changed')
    if verified.get('pregenerated_script') != package['script']:
        raise ValueError('Persisted topic script differs from final package')
    # First registration must read back the complete package, not just a row
    # satisfying the prompt predicate. Later recovery never rewrites user work.
    if not acknowledged:
        for field in ('pregenerated_structure', 'publish_metadata'):
            if verified.get(field) != row.get(field):
                raise ValueError('Persisted topic package differs: ' + field)
        if verified.get('progress_payload', {}).get('script_translations') != row['progress_payload'].get('script_translations'):
            raise ValueError('Persisted topic translations differ')
    readiness_row = verified
    if rows and owned and acknowledged:
        readiness_row = {**verified, 'status': 'pending', 'assigned_at': None, 'assigned_employee_email': ''}
    check = web_readiness(readiness_row, directory)
    if not check['ready']:
        raise ValueError('Persisted topic is not eligible for the user web')
    receipt = {'topic_id': verified['id'], 'source_job_id': identity, 'web_readiness': check,
               'script_sha256': hashlib.sha256(package['script'].encode()).hexdigest(),
               'scene_count': len(package['structure']['scenes']), 'existing_topics_modified': False}
    write(directory/'registration-receipt.json', receipt)
    if not owned and (verified['pregenerated_structure'].get('wuxia_mouth_policy') or {}).get('auto_prepare') is True:
        from worker.wuxia_mouth_worker import prepare_topic
        receipt['mouth_preparation'] = prepare_topic(verified['id'], verified['pregenerated_structure'], store)
        write(directory/'registration-receipt.json', receipt)
    elif acknowledged and prior.get('mouth_preparation'):
        receipt['mouth_preparation'] = prior['mouth_preparation']
        write(directory/'registration-receipt.json', receipt)
    return receipt
