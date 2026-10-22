"""Local candidates through Codex only; no production script publication."""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'worker'))


def finalize_sfx(runner, identity, package, notify, snapshot=None):
    from worker.codex_sfx import plan_package_sfx
    existing = []
    if snapshot:
        row = snapshot.get('row') or {}
        settings = (row.get('project_payload') or {}).get('render_settings') or {}
        # Explicit empty lists are intentional user decisions, not missing data.
        existing = settings.get('sfx_cues')
        if not isinstance(existing, list):
            old = snapshot.get('structure') or {}
            existing = (old.get('sfx_plan') or {}).get('cues')
        if not isinstance(existing, list):
            existing = (row.get('progress_payload') or {}).get('sfx_cues') or []
    notify('효과음 자동 구성 · 최종 대본 분석')
    plan = plan_package_sfx(runner, 'local-' + identity, package, existing)
    review_count = sum(bool(c.get('needs_review')) for c in plan['cues'])
    package.setdefault('remaining', []).append('효과음 자막 위치·파일 연결 및 미리보기/렌더 검증')
    if plan['status'] != 'ready':
        package['remaining'].append('효과음 구성 재시도 필요: ' + plan['status'])
    if review_count:
        package['remaining'].append(f'기존 효과음 위치 재검토 {review_count}개')
    notify(f"효과음 구성 {plan['status']} · {len(plan['cues'])}개 · 재검토 {review_count}개")
    return package


def produce(identity, request, snapshot, output, notify, sources=None):
    from worker.script_guidelines import approved_guidelines
    from worker.script_worker_store import ScriptStore
    scope = dict(request)
    if request.get('mode') == 'repair' and snapshot:
        row = snapshot.get('row') or {}
        scope['language'] = row.get('language') or 'ko'
        scope['category'] = request.get('category') or row.get('category') or ''
    rows, instruction = approved_guidelines(ScriptStore(), scope)
    package = _produce(identity, {**request, '_approved_guidance': instruction}, snapshot, output, notify, sources)
    if request.get('mode') in ('new', 'grounded'):
        from worker.elevenlabs_performance import annotate_new_package
        package = annotate_new_package(package, identity, notify)
    package['applied_guidelines'] = [{k: row[k] for k in ('id','version','title','instruction')} for row in rows]
    return package


def _produce(identity, request, snapshot, output, notify, sources=None):
    from codex_content_runner import (CodexStagedContentRunner, CodexContentConfig,
        _category_narration_voice, _script_rhythm_contract, _resolve_script_style_directive,
        _script_rhythm_warnings)
    from codex_dialogue import ASTRA_MODEL, DIALOGUE_TASK, validate_dialogue
    from listener_review import improve_for_listener
    from senior_script_guard import text_issues, review_issues

    class ReportingRunner(CodexStagedContentRunner):
        def _stage(self, job_id, name, context, task):
            notify(name)
            return super()._stage(job_id, name, context, task)

    config = CodexContentConfig.from_environment()
    # The script/review/dialogue runner itself pins Astra; general model config
    # remains untouched for other existing content stages.
    runner = ReportingRunner(config)
    old_structure = (snapshot or {}).get('structure') or {}
    if request.get('mode') == 'repair' and old_structure.get('script_style') == 'japanese_historical_documentary':
        request = {**request, 'script_style': old_structure['script_style'],
                   'historical_sources': old_structure.get('historical_sources'), 'language': 'ja'}
    if request.get('youtube_url') and request.get('script_style')=='japanese_domestic_drama' and not request.get('web_brief'):
        request={**request,'web_topic_id':identity,'web_brief':{**request,'story':request.get('notes') or request.get('title','')}}
    if request.get('web_brief'):
        from worker.web_topic_submissions import prepare_brief
        prepared_notes = prepare_brief(request, output, runner, notify)
        request = {**request, 'notes': prepared_notes}
    if request.get('_approved_guidance'):
        request = {**request, 'notes': request.get('notes', '') + '\n\n' + request['_approved_guidance']}
        notify('승인된 개선 지침 적용 · 작성 및 검수')
    from worker.japanese_historical_documentary import prepare_request
    request = prepare_request(request)
    from worker.nonverbal_preschool import applies, MODE
    source_nonverbal = bool(snapshot and applies(snapshot.get('structure') or {}))
    if applies(request) or source_nonverbal:
        if request['mode'] not in ('new','repair'):
            raise ValueError('논버벌 모드는 신규 생성·논버벌 기획 수정에서 사용하세요.')
        source = snapshot or {}
        old = source.get('structure') or {}
        seconds = request.get('duration_seconds') or (old.get('target_duration_seconds') if source_nonverbal else None) or request['duration_minutes'] * 60
        payload = {**request,'production_mode':MODE,'topic':request.get('title') or source.get('summary',{}).get('title',''),
                   'target_duration_seconds':seconds,'user_direction':request.get('notes',''),
                   'existing_nonverbal_plan':old if source_nonverbal else {}}
        package = runner.generate('local-' + identity, payload, script_only=True)
        package['script_style'] = MODE
        if source.get('fingerprint'): package['source_fingerprint'] = source['fingerprint']
        return package
    moving = request.get('production_mode') == 'moving_comic'
    if moving:
        from worker.comic_plan import DIRECTIVE, plan_comic
        request = {**request, 'notes': request.get('notes', '') + '\n' + DIRECTIVE}
    def finish(package, source=None):
        if moving:
            package = plan_comic(runner, identity, package, notify)
        from worker.japanese_historical_documentary import enforce_package, finalize_evidence
        package = finalize_evidence(runner, 'local-' + identity, package, request)
        return enforce_package(finalize_sfx(runner, identity, package, notify, source), request)
    if request['mode'] == 'topics':
        from worker.source_topics import produce_topics
        return produce_topics(identity, request, sources or [], runner, notify)
    if request['mode'] == 'grounded':
        if request.get('grounded_type') == 'sermon':
            from worker.sermon_chapters import produce_sermon
            return produce_sermon(identity, request, sources or [], runner, notify, output)
        from worker.grounded_script import produce_grounded
        return produce_grounded(identity, request, sources or [], runner, notify)
    if request['mode'] == 'new':
        # Existing script gates, stopped before native image/storage work.
        # Do not route through Hermes/legacy queues.
        from worker.content_language import resolve_setting
        setting = resolve_setting(request)
        payload = {'topic': request['title'], 'upload_title': request['title'],
                   'category': request['category'], 'category_name': request['category'],
                   'category_id': request['category_id'], 'language': setting['language'],
                   'setting_country': setting['setting_country'],
                   'era_region': setting['era_region'],
                   'image_style': setting['image_style_en'],
                   'content_setting': setting,
                   'production_mode': request.get('production_mode') or 'standard',
                   'direction_profile': request.get('direction_profile') or 'auto',
                   'image_layer_mode': request.get('image_layer_mode') or 'hybrid',
                   'image_layer_scene_start': request.get('image_layer_scene_start'),
                   'image_layer_scene_end': request.get('image_layer_scene_end'),
                   'required_video_scene_count': request.get('required_video_scene_count', 18),
                   'ae_scene_delivery': request.get('ae_scene_delivery') or 'local',
                   'script_style': request.get('script_style') or 'story',
                   'target_duration_seconds': request.get('duration_seconds') or request['duration_minutes'] * 60,
                   'legacy_stage_directives': 'Use the current category narration and senior listening contracts. '
                                              f"Use the selected image style ({setting['image_style']}) for the category and era.",
                   'legacy_quality_contract': 'Use scene budgets and preserve the planned scene count.',
                   'user_direction': request['notes'],
                   'source_reference':{k:request.get('web_brief',{}).get(k) for k in ('youtube_url','source_video_id','source_duration_seconds','source_duration_verified')},
                   'source_localization_map':request.get('source_localization_map',[])}
        if 'historical_sources' in request:
            payload['historical_sources'] = request['historical_sources']
        package = runner.generate('local-' + identity, payload, script_only=True)
        package['language'] = setting['language']
        package['setting_country'] = setting['setting_country']
        package['era_region'] = setting['era_region']
        package['image_style'] = setting['image_style']
        package['script_style'] = payload['script_style']
        package['content_setting'] = setting
        package['direction_profile'] = package.get('structure', {}).get('direction_profile')
        package['ae_scene_delivery'] = payload['ae_scene_delivery']
        package['structure']['ae_scene_delivery'] = payload['ae_scene_delivery']
        package['render_settings'] = {
            **package.get('render_settings', {}),
            'ae_scene_delivery': payload['ae_scene_delivery'],
        }
        from worker.codex_bgm import plan_package_bgm
        plan_package_bgm(runner, 'local-' + identity, package,
                         enabled=request.get('generate_bgm_prompt') is True)
        package['remaining'] = [f"배경 설정: {setting['summary_label']} (저장 완료)",
                                '캐릭터 참고 이미지 생성·저장 (위 배경 설정 적용 예정)',
                                ('무빙툰 장면별 이미지·선택 영상 연출' if moving else f"장면 이미지·첫 {payload['required_video_scene_count']}씬 영상 프롬프트 (위 배경 설정 적용 예정)"),
                                '메타데이터·썸네일 기획', '전체 장면 이미지 실제 생성·게시', '썸네일 배경 실제 생성·게시',
                                '토픽 패키지/유저웹 연결', '사용자 썸네일 최종 저장']
        return finish(package)

    from scripts.repair_existing_topic_scripts import _repair_with_codex, _repair_scene_budgets, _duration_seconds
    row = copy.deepcopy(snapshot['row'])
    if snapshot['kind'] == 'project':
        project = row.get('project_payload') or {}
        row.update(topic=snapshot['summary']['title'], generated_title=snapshot['summary']['title'],
                   pregenerated_script=snapshot['script'], pregenerated_structure=snapshot['structure'],
                   category_id=project.get('category_id'), assigned_script_style=project.get('script_style') or 'story')
    category = request['category'] or str(row.get('category_id') or '')
    row['_material_repair_feedback'] = request['notes']
    from worker.japanese_historical_documentary import applies as documentary, SOURCE_POLICY
    if documentary(request):
        row['assigned_script_style'] = request['script_style']
        row['_material_repair_feedback'] += '\n' + SOURCE_POLICY + '\n' + str(request.get('historical_sources'))
    notify('Astra 수정안 작성 · 시니어 독립 검수')
    sections, report = _repair_with_codex(row, category, output, ASTRA_MODEL, force=True)
    scenes = copy.deepcopy(snapshot['structure']['scenes'])
    payload = {'category_name': category, 'category_id': row.get('category_id'),
               'language': row.get('language') or 'ko', 'topic': snapshot['summary']['title'],
               'upload_title': snapshot['summary']['title'],
               'target_duration_seconds': _duration_seconds(row, scenes),
               'user_direction': request['notes'],
               'source_reference':snapshot['structure'].get('source_reference') or {},
               'source_localization_map':snapshot['structure'].get('source_localization_map') or []}
    if documentary(request):
        payload.update(script_style=request['script_style'], language='ja',
                       historical_sources=request.get('historical_sources'), documentary_source_policy=SOURCE_POLICY)
    budgets = _repair_scene_budgets(scenes, payload, [
        {**section, 'current_text': section['text']} for section in sections])
    stage = lambda name, context, task: runner._stage('local-' + identity, name,
        {**context, **({key: payload[key] for key in ('historical_sources', 'documentary_source_policy')}
                      if documentary(request) else {})}, task)
    sections, listener = improve_for_listener(stage, snapshot['summary']['title'], sections, budgets)
    # Recheck final prose after listener revisions, without reusing author scores.
    context = {**payload, 'sections': sections, 'script': '\n\n'.join(s['text'] for s in sections),
               'category_narration_voice': _category_narration_voice(payload),
               'script_rhythm_contract': _script_rhythm_contract(payload),
               'script_style_directive': _resolve_script_style_directive(row.get('assigned_script_style')),
               'scene_budgets': budgets}
    review = stage('02i_post_listener_review', context,
                   'Independently review the complete final script under the mandatory senior listening contract. '
                   'Return script_quality_report with profile, verdict, score, critical_issues and evidence-backed checks. '
                   'Do not rewrite or use author scores.')
    errors = text_issues(sections, payload) + _script_rhythm_warnings(sections) + review_issues(review.get('script_quality_report'))
    if len(sections) != len(scenes) or [s.get('scene_order') for s in sections] != list(range(1, len(scenes) + 1)):
        errors.append('Scene structure changed')
    if errors:
        raise ValueError('Final repair rejected')
    for scene, section in zip(scenes, sections):
        scene.update(scene_text=section['text'], narration=section['text'])
    dialogue = stage('02e_dialogue', {**context, 'scenes': scenes}, DIALOGUE_TASK)
    annotations = validate_dialogue(dialogue, scenes)
    structure = copy.deepcopy(snapshot['structure'])
    structure['scenes'] = scenes
    # Repairs use the same final-scene census as new drafts. Save new recurring
    # designs now while retaining every previously approved reference image.
    from worker.content_language import resolve_setting
    from worker.character_continuity import character_design_anchors
    source = snapshot.get('row') or {}
    source_payload = source.get('project_payload') or source.get('progress_payload') or {}
    setting = resolve_setting({**source, **source_payload, **(source_payload.get('content_setting') or {}),
                               **(structure.get('content_setting') or {}), 'language': payload['language']})
    existing = (structure.get('character_anchors') or source_payload.get('character_anchors')
                or {'main_character': structure.get('main_character') or source_payload.get('main_character'),
                    'supporting_characters': structure.get('supporting_characters') or source_payload.get('supporting_characters') or []})
    identity_design = runner.finalize_character_identity('local-' + identity,
        {**context, 'scenes': scenes, 'dialogue_annotations': annotations, 'existing_character_anchors': existing}, setting)
    anchors = character_design_anchors(identity_design)
    structure.update(main_character=anchors['main_character'], supporting_characters=anchors['supporting_characters'],
                     character_anchors=anchors, scene_cast=anchors['scene_cast'],
                     character_reference_status='ready' if anchors['character_image_generation']['status'] == 'ready'
                        else 'descriptions_ready_images_pending')
    package = {'script': context['script'], 'sections': sections, 'structure': structure, 'script_model': ASTRA_MODEL,
            'main_character': anchors['main_character'], 'supporting_characters': anchors['supporting_characters'],
            'character_anchors': anchors, 'scene_cast': anchors['scene_cast'],
            'script_quality_report': review['script_quality_report'], 'listener_quality_report': listener,
            'dialogue_annotations': annotations, 'repair_report': report,
            'source_fingerprint': snapshot['fingerprint'],
            'remaining': ['사용자 대본 승인', '장면별 이미지·프롬프트 영향 평가', '최신 메타데이터·썸네일 검증',
                          '오래된 자막/음성 연결 정리', '대상 프로젝트에 승인본 적용',
                          '패키지·제출 건 동기화 확인', '유저웹 재접속 검증']}
    return finish(package, snapshot)
