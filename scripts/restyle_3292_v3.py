"""User-directed narration restyle, local draft only."""
import copy
import hashlib
import json
import re
from draft_3292_scoped import OUT, save
from codex_content_runner import CodexStagedContentRunner, CodexContentConfig

old=json.loads((OUT/'candidate-v2.json').read_text(encoding='utf-8'))
request=json.loads((OUT/'request.json').read_text(encoding='utf-8'))
runner=CodexStagedContentRunner(CodexContentConfig.from_environment())
result=runner._stage('3292_v3','02_user_narration_style',
    {'title':request['title'],'sections':old['sections'],'scene_budgets':request['scene_budgets']},
    'Rewrite the COMPLETE Korean narration to the user specified voice. '
    'Default narration must use natural respectful declarative ~습니다 / ~했습니다 / ~있었습니다. '
    'Remove forced ~했지요, ~했고요, ~주었고요, ~게요, ~답니다 and explanatory ~거든요 endings from narration. '
    'Do not simply swap endings: join actions naturally with causal flow and smooth read-aloud rhythm. '
    'Keep genuine emotional rhetorical sentences, especially scene14 "도둑의 딸이라는 소리를 피해 살아왔건만, 이제 제 딸 차례라니요." exactly. '
    'Preserve every quoted direct dialogue substring EXACTLY, with curly quotation marks. '
    'Preserve ALL facts, people, clues (including 반달꼴 땜 자국), custody, timing, scene order, and ending. '
    'No new events or evidence. Exactly 53 sections, each within supplied character budget. '
    'Return {sections:[{scene_order:1,text:"complete scene text"}]}. No self-scoring, no stage directions.')
sections=result['sections']
assert len(sections)==53 and [s['scene_order'] for s in sections]==list(range(1,54))
# Explicit subjects avoid ambiguity introduced while joining sentences.
sections[19]['text']='그런데 사흘 뒤, 최 부자는 금례가 귀걸이를 훔쳤다며 들이닥쳤습니다. 금례가 글을 찾는 동안 어린 순덕의 이불까지 마당에 던졌습니다.'
sections[40]['text']='최 서방 어머니는 돌려받은 귀걸이를 다른 한 짝과 저고리 주머니에 넣었습니다. 둘 다 해진 틈으로 안감에 빠졌고, 어머니가 죽은 뒤 궤짝에 묵은 옷을 최 서방이 전날 꺼냈습니다.'
issues=[]
for previous,now,b in zip(old['sections'],sections,request['scene_budgets']):
    text=now['text'].strip();now['text']=text
    assert re.findall('“[^”]*”',previous['text'])==re.findall('“[^”]*”',text), f"dialogue changed {now['scene_order']}"
    if not b['min_chars']<=len(text)<=b['max_chars']:issues.append({'scene':now['scene_order'],'length':len(text),'budget':b})
    narration=re.sub('“[^”]*”','',text)
    if re.search(r'(?:지요|고요|게요|답니다|거든요)[.!?…]',narration):issues.append({'scene':now['scene_order'],'unwanted_ending':True})
assert '도둑의 딸이라는 소리를 피해 살아왔건만, 이제 제 딸 차례라니요.' in sections[13]['text']
candidate=copy.deepcopy(old);candidate['sections']=sections
candidate['narrative_blueprint_status']='inherited_v2_facts; quote references require final revalidation'
save('candidate-v3.json',candidate)
script='\n\n'.join(s['text'] for s in sections)
save('v3-status.json',{'status':'draft_for_review','published':False,'approved':False,
    'script_sha256':hashlib.sha256(script.encode()).hexdigest(),'validation_issues':issues,
    'scene_count':53,'target_seconds':900,'script_chars':len(script),
    'dialogue_preserved':True,'independent_review':'not_run_on_v3'})
lines=['# 떨어진 귀걸이가 부른 일, 그 집안 3대에 걸친 저주','',
    '문체 수정본 v3 · ~습니다체 중심 · 53씬 / 15분 목표 · 운영 DB 미반영','',
    '사건과 인물·증거는 v2에서 유지했습니다. 직접 대사는 원문 그대로 보존했습니다. 실제 음성 길이와 독립 재검수는 아직 확인 전입니다.','',
    '## 전체 대본','',script,'','## 씬별 시간 계획과 대본','']
elapsed=0
for s,t in zip(sections,request['schedule']):
    end=elapsed+t['duration_seconds']
    lines += [f"### 씬 {s['scene_order']} · {elapsed//60:02d}:{elapsed%60:02d}–{end//60:02d}:{end%60:02d}",'',s['text'],'']
    elapsed=end
(OUT/'문체수정-전체대본-v3.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps({'chars':len(script),'issues':issues},ensure_ascii=False),flush=True)
