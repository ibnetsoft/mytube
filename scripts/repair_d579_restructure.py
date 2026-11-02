"""Reconstruct the existing draft's latter scenes, preserving its first 50 and total clock."""
import copy, json, sys, time, traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'worker')]
import worker_config
from worker.script_worker_store import ScriptStore
from worker.codex_local_console import digest
from codex_content_runner import CodexStagedContentRunner
from codex_dialogue import DIALOGUE_TASK, validate_dialogue
from senior_script_guard import contract as senior_contract, review_issues

ID = 'd57947df4af3479b85185c7ca0610a60'
OUT = ROOT / 'output/codex-local-console' / ID
store, runner = ScriptStore(), CodexStagedContentRunner()
bundle = store.get(ID)
original = copy.deepcopy(bundle['candidate'])
fingerprint = digest(original)

def update(stage, status='running', error=''):
    b = store.get(ID)
    if b['job'].get('status') == 'canceled' or digest(b['candidate']) != fingerprint:
        raise ValueError('작업이 취소되었거나 원본이 변경됐습니다.')
    b['job'].update(status=status, stage=stage, error=error, updated_at=time.time())
    store.save(b)
    (OUT/'job.json').write_text(json.dumps(b['job'], ensure_ascii=False, indent=2), encoding='utf-8')

try:
    (OUT/f'before-restructure-{fingerprint[:12]}.json').write_text(json.dumps(original, ensure_ascii=False, indent=2), encoding='utf-8')
    old = original['structure']['scenes']
    first = copy.deepcopy(old[:100])
    original_seconds = sum(int(s['duration_seconds']) for s in old)
    context = {'language':'ja', 'category_id':'13', 'category_name':'日本昔話',
        'target_duration_seconds':original_seconds,
        'sections':[{'scene_order':i,'text':s.get('scene_text') or s.get('narration')} for i,s in enumerate(old,1)],
        'latest_review':original.get('script_quality_report'), 'story_core':original['structure'].get('story_core')}
    update('사건 이후 결말 집중 압축')
    result = runner._stage('restructure-'+ID, '02_story_restructure', context,
      'Edit the existing Japanese Edo-period narrative. Preserve scenes 1–100 exactly; return ONLY a compact '
      'ending of 3 to 5 rewritten scenes numbered consecutively from 101 as JSON '
      '{sections:[{scene_order:101,text:"..."},...]}. The case is already resolved by scene 100. '
      'Condense the existing 12-scene aftermath to essential, non-repeating actions: a brief farewell, '
      'finding the old letter, choosing the home and welcoming the neighbor. Each action happens once. '
      'Do not repeat explanations, packing, farewells, evidence principles or character decisions. '
      'The final ending should be genuinely brief; do not pad to reach the previous duration. '
      'Okuni did not see Osumi take out the old letter in original scene 51: she cannot claim this without '
      'a verified source. Maintain every character’s knowledge chronology. Use only narrator indirect speech. '
      'Return no headings, only the JSON.')
    rows = result.get('sections')
    if not isinstance(rows,list) or not 3 <= len(rows) <= 5:
        raise ValueError('후반부 씬 재편 결과의 개수가 유효하지 않습니다.')
    for i,row in enumerate(rows,101):
        if row.get('scene_order') != i or not isinstance(row.get('text'),str) or not row['text'].strip():
            raise ValueError(f'{i}씬 재편 결과가 올바르지 않습니다.')
    weights = [len(''.join(row['text'].split())) for row in rows]
    prefix_chars = sum(len(''.join(s['scene_text'].split())) for s in first)
    prefix_seconds = sum(int(s['duration_seconds']) for s in first)
    chars_per_second = prefix_chars / prefix_seconds
    seconds = [max(1,round(w/chars_per_second)) for w in weights]
    scenes = first + [{'scene_number':i,'scene_order':i,'scene_text':row['text'].strip(),
        'narration':row['text'].strip(),'duration_seconds':duration,'target_duration':duration,
        'visual_type':'image','video_prompt_required':False,'video_generation_mode':'image',
        'ae_effect_plan':{'enabled':False,'reason':'outside_effect_scene_range'}}
        for i,(row,duration) in enumerate(zip(rows,seconds),101)]
    sections = [{'scene_order':i,'text':s['scene_text']} for i,s in enumerate(scenes,1)]
    update('재편 대본 독립 검토')
    review = runner._stage('restructure-'+ID,'02_story_independent_review',
        {**context,'sections':sections,'scenes':scenes},
        'Independently review this exact revised draft. Check investigation and ending repetition and whether '
        'each character knows only what they actually witnessed or learned. Check the original review findings. '
        'Do not rewrite; return {script_quality_report:{...}}.\n'+senior_contract(context))
    report=review.get('script_quality_report') or {}
    issues=review_issues(report)
    update('재편 대본 간접화법 검증')
    annotated=runner._stage('restructure-'+ID,'02e_dialogue',
        {'language':'ja','scenes':scenes,'script':'\n\n'.join(s['scene_text'] for s in scenes)},DIALOGUE_TASK)
    annotations=validate_dialogue(annotated,scenes)
    violations=[r['scene_number'] for r in annotations['scenes'] if r['scene_number']>50 and r['spans']]
    if violations: raise ValueError('51씬 이후 직접 발화: '+str(violations))
    package=copy.deepcopy(original); structure=package['structure']
    for scene,row in zip(scenes,annotations['scenes']):
        scene['has_character_dialogue']=bool(row['spans']);scene['dialogue_spans']=row['spans']
    structure.update(scenes=scenes,scene_count=len(scenes),dialogue_annotations=annotations,
        video_dialogue_postwork_index=annotations['video_dialogue_postwork_index'],
        scene_visual_direction_status='needs_revalidation_after_script_repair')
    for k in ('audio_performance','scene_direction_plans','ae_effect_plans','ae_motion_plans','scene_cast'):
        structure.pop(k,None)
    structure.setdefault('quality_notes',[]).append({'stage':'story_restructure_review','passed':not issues,'issues':issues,'actual_review':report})
    package.update(script='\n\n'.join(s['scene_text'] for s in scenes),script_quality_report=report)
    package['remaining']=list(dict.fromkeys(package.get('remaining',[])+['재편 대본 기준 전체 장면 연출·캐릭터 배치·음성 연기·효과음 재생성 및 검증']))
    result_report={'review':report,'issues':issues,'scene_count':len(scenes),'duration_seconds':sum(s['duration_seconds'] for s in scenes),
                   'timing_note':'씬 길이는 대본 글자수 기준 추정치이며 실제 녹음 후 검증 필요'}
    (OUT/'story-restructure-report.json').write_text(json.dumps(result_report,ensure_ascii=False,indent=2),encoding='utf-8')
    b=store.get(ID)
    if b['job'].get('status')=='canceled' or digest(b['candidate'])!=fingerprint: raise ValueError('원본 변경 또는 취소됨')
    b['candidate']=package;b['job'].update(status='awaiting_approval',stage='재편 대본 저장 · 독립 검토 기록',error='',
        candidate_hash=digest(package),updated_at=time.time(),remaining=package['remaining'])
    store.save(b)
    (OUT/'candidate.json').write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'candidate.md').write_text(package['script'],encoding='utf-8')
    (OUT/'job.json').write_text(json.dumps(b['job'],ensure_ascii=False,indent=2),encoding='utf-8')
except Exception as exc:
    (OUT/'story-restructure-error.txt').write_text(traceback.format_exc(),encoding='utf-8')
    try:update('후반부 재편 중단 · 오류 확인 필요','failed',str(exc)[:500])
    except Exception:pass
