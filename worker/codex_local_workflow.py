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
    if request['mode'] == 'topics':
        from worker.source_topics import produce_topics
        return produce_topics(identity, request, sources or [], runner, notify)
    if request['mode'] == 'grounded':
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
                   'script_style': 'story',
                   'target_duration_seconds': request['duration_minutes'] * 60,
                   'legacy_stage_directives': 'Use the current category narration and senior listening contracts. '
                                              'Use photorealistic images matching the category and era.',
                   'legacy_quality_contract': 'Use scene budgets and preserve the planned scene count.',
                   'user_direction': request['notes']}
        package = runner.generate('local-' + identity, payload, script_only=True)
        package['language'] = setting['language']
        package['setting_country'] = setting['setting_country']
        package['era_region'] = setting['era_region']
        package['image_style'] = setting['image_style']
        package['content_setting'] = setting
        from worker.codex_bgm import plan_package_bgm
        plan_package_bgm(runner, 'local-' + identity, package,
                         enabled=request.get('generate_bgm_prompt') is True)
        package['remaining'] = [f"배경 설정: {setting['summary_label']} (저장 완료)",
                                '캐릭터 참고 이미지 생성·저장 (위 배경 설정 적용 예정)',
                                '장면 이미지·첫 12씬 영상 프롬프트 (위 배경 설정 적용 예정)',
                                '메타데이터·썸네일 기획', '전체 장면 이미지 실제 생성·게시', '썸네일 배경 실제 생성·게시',
                                '토픽 패키지/유저웹 연결', '사용자 썸네일 최종 저장']
        return finalize_sfx(runner, identity, package, notify)

    from scripts.repair_existing_topic_scripts import _repair_with_codex, _repair_scene_budgets, _duration_seconds
    row = copy.deepcopy(snapshot['row'])
    if snapshot['kind'] == 'project':
        project = row.get('project_payload') or {}
        row.update(topic=snapshot['summary']['title'], generated_title=snapshot['summary']['title'],
                   pregenerated_script=snapshot['script'], pregenerated_structure=snapshot['structure'],
                   category_id=project.get('category_id'), assigned_script_style=project.get('script_style') or 'story')
    category = request['category'] or str(row.get('category_id') or '')
    row['_material_repair_feedback'] = request['notes']
    notify('Astra 수정안 작성 · 시니어 독립 검수')
    sections, report = _repair_with_codex(row, category, output, ASTRA_MODEL, force=True)
    scenes = copy.deepcopy(snapshot['structure']['scenes'])
    payload = {'category_name': category, 'category_id': row.get('category_id'),
               'language': row.get('language') or 'ko', 'topic': snapshot['summary']['title'],
               'upload_title': snapshot['summary']['title'],
               'target_duration_seconds': _duration_seconds(row, scenes)}
    budgets = _repair_scene_budgets(scenes, payload, [
        {**section, 'current_text': section['text']} for section in sections])
    stage = lambda name, context, task: runner._stage('local-' + identity, name, context, task)
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
    package = {'script': context['script'], 'sections': sections, 'structure': structure, 'script_model': ASTRA_MODEL,
            'script_quality_report': review['script_quality_report'], 'listener_quality_report': listener,
            'dialogue_annotations': annotations, 'repair_report': report,
            'source_fingerprint': snapshot['fingerprint'],
            'remaining': ['사용자 대본 승인', '장면별 이미지·프롬프트 영향 평가', '최신 메타데이터·썸네일 검증',
                          '오래된 자막/음성 연결 정리', '대상 프로젝트에 승인본 적용',
                          '패키지·제출 건 동기화 확인', '유저웹 재접속 검증']}
    return finalize_sfx(runner, identity, package, notify, snapshot)
