"""Prepare a bounded v2 proposal; do not replace approved v1 or publish."""
import json
import hashlib
from draft_3292_scoped import OUT, save
from codex_content_runner import CodexStagedContentRunner, CodexContentConfig

original=json.loads((OUT/'candidate.json').read_text(encoding='utf-8'))
request=json.loads((OUT/'request.json').read_text(encoding='utf-8'))
review=json.loads((OUT/'independent-review.json').read_text(encoding='utf-8'))
context={'title':request['title'],'sections':original['sections'],
    'scene_budgets':request['scene_budgets'], 'findings':review}
runner=CodexStagedContentRunner(CodexContentConfig.from_environment())
result=runner._stage('3292_v2_proposal','02_local_correction',context,
    'Prepare minimal corrections to resolve the reviewers substantive issues, not a new story. '
    'Preserve all 53 scenes, timing, cast and ending. Allowed changed scenes ONLY 19,21,34,41,42,44,46. '
    'Fix exact earring identity with a plausible distinctive mark documented before accusation and identified now, '
    'and account for its return to the wife and later lodging in the lining. Do not rely on a convenient new witness or confession. '
    'Fix scene42 misleading clothing theft accusation, scene46 unclear paid-record wording. '
    'Do not add any external facts. Stay inside exact min_chars/max_chars per changed scene. '
    'Return {patches:[{scene_order:1,text:"full replacement"}],change_summary:[],narrative_blueprint:{cast:[],timeline:[],object_custody:[],character_knowledge:[],clues_and_payoffs:[]}}. '
    'The ledger must reflect the resulting script, never supply facts missing from it. This is a proposal requiring user approval; do not claim independent pass.')
save('v2-corrections.json',result)
candidate=json.loads(json.dumps(original))
seen=set()
for p in result['patches']:
    n=p['scene_order'];assert n in {19,21,34,41,42,44,46} and n not in seen
    seen.add(n)
    candidate['sections'][n-1]['text']=p['text'].strip()
candidate['narrative_blueprint']=result['narrative_blueprint']
save('candidate-v2.json',candidate)
script='\n\n'.join(s['text'] for s in candidate['sections'])
issues=[]
for s,b in zip(candidate['sections'],request['scene_budgets']):
    if not b['min_chars']<=len(s['text'])<=b['max_chars']:issues.append(s['scene_order'])
save('v2-status.json',{'status':'awaiting_reapproval','approved':False,'published':False,
    'changed_scenes':sorted(seen),'budget_findings':issues,'script_sha256':hashlib.sha256(script.encode()).hexdigest(),
    'independent_review':'not_yet_run_on_v2'})
lines=['# 떨어진 귀걸이가 부른 일, 그 집안 3대에 걸친 저주','',
    '검수 보완안 v2 · 53씬 / 15분 목표 · v1 승인 후 발견된 근거 연결 보완 · 재승인 전 미반영','',
    '## 변경 사항','']
for n in sorted(seen):
    lines += [f'### 씬 {n}','', '**v1**',original['sections'][n-1]['text'],'','**v2**',candidate['sections'][n-1]['text'],'']
lines+=['## 전체 대본','',script]
(OUT/'검수보완-전체대본-v2.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps({'changed':sorted(seen),'budget_findings':issues,'chars':len(script)},ensure_ascii=False),flush=True)
