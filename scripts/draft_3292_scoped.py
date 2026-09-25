"""Read-only production snapshot and approval draft for the specifically authorized project."""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'worker')]
from scripts.audit_active_content import fetch
from codex_content_runner import (CodexStagedContentRunner, CodexContentConfig,
    _pacing_schedule, _scene_char_budgets, _category_narration_voice,
    _resolve_script_style_directive)

OUT = ROOT / 'output/repair-3292-20260915'
PID = 'c525efe2-9c1b-42a4-aad0-f04713a300f9'
UID = 'b6e0f95c-1f32-43f0-a087-ecb501b0a287'

def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    backup = OUT / 'source.json'
    if not backup.exists():
        projects = fetch('std_projects', id=f'eq.{PID}')
        assert len(projects) == 1
        p = projects[0]
        assert p['user_id'] == UID and p['topic_queue_id'] == 3292
        assert p['status'] in ('claimed', 'in_progress') and not p.get('submitted_at')
        snapshot = {'project': p, 'topic': fetch('topics_queue', id='eq.3292'),
            'scene_rows': fetch('std_project_scenes', project_id=f'eq.{PID}'),
            'characters': fetch('topic_character_assets', topic_queue_id='eq.3292'),
            'captured_at': datetime.now(timezone.utc).isoformat()}
        save('source.json', snapshot)
    snapshot = json.loads(backup.read_text(encoding='utf-8'))
    assert snapshot['project']['user_id'] == UID
    schedule = _pacing_schedule(900)
    payload = {'category_name': '옛날이야기', 'category_id': 2, 'target_duration_seconds': 900,
               'language': 'ko', 'narration_pace': 'senior'}
    budgets = _scene_char_budgets(schedule, payload)
    context = {'title': '떨어진 귀걸이가 부른 일, 그 집안 3대에 걸친 저주',
        'category_narration_voice': _category_narration_voice(payload),
        'script_style_directive': _resolve_script_style_directive('story'),
        'schedule': schedule, 'scene_budgets': budgets,
        'brief': 'User approved rebuilding mismatched 258-scene source as a 15-minute fictional Korean folktale matching this title. Do not preserve unrelated graveside daughter-in-law plot or farmer Dolsoe. Three generations must be explicit and causal. Suggested premise: grandmother falsely accused of stealing an earring, daughter raised believing the accusation, granddaughter threatened with the same injustice. The dropped earring is concrete evidence, not a random charm. Choose a coherent family and village history; understandable realistic discovery of proof, no miraculous confession or modern props. Warm oral Korean storytelling, varied natural breathing and complete sentences; not mechanical 어미 rotation, no excessive moralizing. Strong hook then mounting choices, cost, reveal, practical redress and emotionally earned ending. Entire plot must resolve. No real-world factual claims. Draft for approval only.'}
    save('request.json', context)
    print('Snapshot saved. Writing Astra draft, 53 scenes / 900 seconds.', flush=True)
    runner = CodexStagedContentRunner(CodexContentConfig.from_environment())
    result = runner._stage('repair3292_20260915', '02_approval_draft', context,
        'Write a COMPLETE finished Korean narration, not an outline. Return JSON {"characters":[{"name":"","generation":1,"relation":""}],"synopsis":"","sections":[{"scene_order":1,"text":"..."}]}. Exactly 53 ordered sections matching schedule. First12 are each5 seconds. Follow supplied per-scene character budgets; total is a 15-minute target, not measured TTS. No scene labels/timecodes/stage directions in text. Narration and quoted dialogue together form the finished story. Do not return a self-scored quality report.')
    save('candidate.json', result)
    sections = result['sections']
    assert len(sections) == 53 and [s['scene_order'] for s in sections] == list(range(1,54))
    assert all(str(s.get('text') or '').strip() for s in sections)
    script = '\n\n'.join(s['text'].strip() for s in sections)
    digest = hashlib.sha256(script.encode()).hexdigest()
    issues = [{'scene': i+1, 'chars': len(s['text']), 'min': b['min_chars'], 'max': b['max_chars']}
              for i,(s,b) in enumerate(zip(sections,budgets)) if not b['min_chars']<=len(s['text'])<=b['max_chars']]
    save('draft_status.json', {'status':'awaiting_script_approval', 'published':False,
        'script_sha256':digest,'source_sha256':hashlib.sha256(backup.read_bytes()).hexdigest(),
        'scene_count':53,'target_seconds':900,'script_chars':len(script),
        'budget_findings':issues,'independent_qa':'not_yet_run',
        'structure_authorization':'User approved 15-minute title-based reconstruction; old258 scenes remain archived, not remapped by ordinal.',
        'remaining':['script approval','independent QA','character and scene images','prompts','Thai subtitles','metadata','scoped application','web verification']})
    lines = ['# 떨어진 귀걸이가 부른 일, 그 집안 3대에 걸친 저주', '',
        '검토용 초안 v1 · 토픽 3292 · 15분 목표 / 53씬 · 운영 DB 미반영', '',
        '정확한 재생 시간은 음성 생성 후 확인합니다. 독립 품질 검수 및 최종 대본 승인은 아직입니다.', '',
        '## 전체 대본', '', script, '', '## 씬별 대본과 시간 계획', '']
    elapsed = 0
    for s,t in zip(sections,schedule):
        end=elapsed+t['duration_seconds']
        lines += [f"### 씬 {s['scene_order']} · {elapsed//60:02d}:{elapsed%60:02d}–{end//60:02d}:{end%60:02d}", '', s['text'], '']
        elapsed=end
    (OUT/'검토용-전체대본-v1.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'chars':len(script),'scenes':len(sections),'budget_findings':issues,'draft':str(OUT/'검토용-전체대본-v1.md')},ensure_ascii=False),flush=True)

if __name__ == '__main__':
    main()
