"""Revise the existing draft, keeping its source snapshot and scene clock."""
import copy
import hashlib
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'worker')]
import worker_config  # loads worker environment
from worker.script_worker_store import ScriptStore
from worker.codex_local_console import digest
from codex_content_runner import CodexStagedContentRunner, _scene_char_budgets
from codex_dialogue import DIALOGUE_TASK, validate_dialogue
from senior_script_guard import contract as senior_contract, review_issues

ID = 'd57947df4af3479b85185c7ca0610a60'
OUT = ROOT / 'output' / 'codex-local-console' / ID
store = ScriptStore()
bundle = store.get(ID)
original = copy.deepcopy(bundle['candidate'])
source_hash = digest(original)
runner = CodexStagedContentRunner()

def update(stage, status='running', error=''):
    b = store.get(ID)
    if b['job'].get('status') == 'canceled':
        raise RuntimeError('작업 취소됨')
    if digest(b['candidate']) != source_hash:
        raise RuntimeError('수정 중 원본 대본이 변경되었습니다.')
    b['job'].update(stage=stage, status=status, error=error, updated_at=time.time())
    store.save(b)
    (OUT / 'job.json').write_text(json.dumps(b['job'], ensure_ascii=False, indent=2), encoding='utf-8')

try:
    (OUT / f'before-story-repair-{source_hash[:12]}.json').write_text(json.dumps(original, ensure_ascii=False, indent=2), encoding='utf-8')
    scenes = copy.deepcopy(original['structure']['scenes'])
    sections = [{'scene_order': i, 'text': s.get('scene_text') or s.get('narration')}
                for i, s in enumerate(scenes, 1)]
    payload = {'language': 'ja', 'category_id': '13', 'category_name': '日本昔話',
               'target_duration_seconds': 2234, 'topic': original.get('generated_title')}
    budgets = _scene_char_budgets(scenes, payload)
    context = {**payload, 'sections': sections, 'scene_budgets': budgets,
               'story_core': original['structure'].get('story_core'),
               'review_notes': original['structure'].get('quality_notes'),
               'speech_style_policy': original['structure'].get('speech_style_policy')}
    update('기존 대본 수정 · 결말 반복과 주인공 연결')
    revised = runner._stage('repair-' + ID, '02_story_targeted_repair', context,
        'Revise the supplied existing Japanese script to address the review notes: connect the opening protagonist’s '
        'desire and decisions to the final character’s choice from early scenes, so the shift in viewpoint is earned; '
        'remove repeated explanations, interrogation and extended repetitive ending. Use any freed scene time for '
        'distinct causal developments and character choices. Specifically, scenes 103–125 must advance the '
        'investigation once per fact: consolidate questioning, distinguish destinations and show the departure '
        'only once. In scenes 139–151, state the decision to live separately only once and close with the box '
        'and welcoming a neighbor; remove duplicated packing, departure and explanation. Redistribute freed '
        'space to distinct earlier causal actions, not repeated resolution. Crucial continuity: scene 51 says '
        'Okuni was elsewhere while Osumi took out the old letter; in scene 139 Okuni must NOT claim to have '
        'seen or learned that action without an explicitly established source. She may speak only of the letter '
        'being found in the box, and distinguish observed facts from inference. Review every character’s knowledge '
        'and evidence provenance. In scenes 103–130 remove repeated interviews and prolonged sorting of funeral '
        'items; distribute unique, consequential new actions before the resolution, with no invented new facts '
        'that undermine established chronology. In 139–151 eliminate repeated independent-living and packing '
        'statements; show the decision once, then a brief meaningful closing. Do not use filler to meet length. '
        'Preserve the story, Edo Japan setting, cast, original '
        '151 ordered scene boundaries and each scene budget. Indirect narration is preferred; through scene 50 '
        'direct speech is optional only when dramatically necessary; from 51 onward character speech must be '
        'indirect narrator report only. Do not add headings. Return JSON {sections:[{scene_order:1,text:"..."},...]}.')
    result = revised.get('sections')
    if not isinstance(result, list) or len(result) != len(scenes):
        raise ValueError('수정안의 씬 수가 원본과 다릅니다.')
    invalid = []
    for i, (row, budget) in enumerate(zip(result, budgets), 1):
        text = str(row.get('text') or '').strip()
        if row.get('scene_order') != i or not text or not budget['min_chars'] <= len(text) <= max(budget['max_chars'] * 2, budget['max_chars'] + 30):
            invalid.append({'scene_order': i, 'text': text, 'budget': budget})
    if invalid:
        update('수정 대본 씬 길이 보정')
        fixed = runner._stage('repair-' + ID, '02_story_budget_repair',
            {**payload, 'sections': result, 'invalid_sections': invalid},
            'Repair ONLY the listed invalid_sections to satisfy each min_chars and max_chars, preserving their '
            'meaning, Japanese narration and order. Scene 51 onward uses only indirect reported speech. '
            'Return JSON {sections:[{scene_order:n,text:"..."},...]} for exactly the listed sections.')
        replacements = fixed.get('sections') if isinstance(fixed, dict) else None
        if not isinstance(replacements, list) or {r.get('scene_order') for r in replacements} != {r['scene_order'] for r in invalid}:
            raise ValueError('씬 길이 보정 결과가 불완전합니다.')
        for row in replacements:
            result[row['scene_order'] - 1] = row
    for i, (row, scene, budget) in enumerate(zip(result, scenes, budgets), 1):
        text = str(row.get('text') or '').strip()
        if row.get('scene_order') != i or not text or not budget['min_chars'] <= len(text) <= max(budget['max_chars'] * 2, budget['max_chars'] + 30):
            raise ValueError(f'{i}씬 순서 또는 시간 예산 오류')
        scene.update(scene_text=text, narration=text)
    update('수정 대본 독립 검토')
    review = runner._stage('repair-' + ID, '02_story_independent_review',
        {**context, 'sections': result},
        'Independently review the revised script. Check especially whether the opening protagonist’s wishes '
        'connect to the final character’s choice and whether the ending and investigation repeat. '
        'Do not rewrite or claim a pass without evidence. Return {script_quality_report:{...}}.\n' + senior_contract(payload))
    report = review.get('script_quality_report') or {}
    review_errors = review_issues(report)
    update('수정 대본 화법 검증')
    dialogue = runner._stage('repair-' + ID, '02e_dialogue',
                             {**payload, 'scenes': scenes, 'script': '\n\n'.join(x['text'] for x in result)}, DIALOGUE_TASK)
    annotations = validate_dialogue(dialogue, scenes)
    violations = [r['scene_number'] for r in annotations['scenes'] if r['scene_number'] > 50 and r['spans']]
    if violations:
        raise ValueError('51씬 이후 직접 발화 또는 불확실한 발화: ' + str(violations))
    package = copy.deepcopy(original)
    structure = package['structure']
    structure['scenes'] = scenes
    structure['dialogue_annotations'] = annotations
    structure['video_dialogue_postwork_index'] = annotations['video_dialogue_postwork_index']
    structure.pop('audio_performance', None)
    for scene, annotation in zip(scenes, annotations['scenes']):
        scene['has_character_dialogue'] = bool(annotation['spans'])
        scene['dialogue_spans'] = annotation['spans']
    structure.setdefault('quality_notes', []).append({'stage': 'story_repair_independent_review',
        'passed': not review_errors, 'issues': review_errors, 'actual_review': report})
    structure['scene_visual_direction_status'] = 'needs_revalidation_after_script_repair'
    package['script'] = '\n\n'.join(x['text'].strip() for x in result)
    package['script_quality_report'] = report
    package.setdefault('remaining', []).append('수정 대본 기준 장면 연출·음성 연기·효과음 재검증')
    (OUT / 'story-repair-report.json').write_text(json.dumps({'review': report, 'issues': review_errors,
        'source_sha256': source_hash, 'scene_count': len(scenes), 'duration_seconds': 2234}, ensure_ascii=False, indent=2), encoding='utf-8')
    b = store.get(ID)
    if digest(b['candidate']) != source_hash or b['job'].get('status') == 'canceled':
        raise RuntimeError('원본이 변경 또는 취소되어 저장하지 않았습니다.')
    b['candidate'] = package
    b['job'].update(status='awaiting_approval', stage='수정 대본 저장 · 독립 검토 기록', error='',
                    candidate_hash=digest(package), updated_at=time.time(), remaining=package['remaining'])
    store.save(b)
    (OUT / 'candidate.json').write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'candidate.md').write_text(package['script'], encoding='utf-8')
    (OUT / 'job.json').write_text(json.dumps(b['job'], ensure_ascii=False, indent=2), encoding='utf-8')
except Exception as exc:
    (OUT / 'story-repair-error.txt').write_text(traceback.format_exc(), encoding='utf-8')
    try:
        update('기존 대본 수정 중단 · 오류 확인 필요', 'failed', str(exc)[:500])
    except Exception:
        pass
