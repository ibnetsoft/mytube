"""Apply explicitly authorized copyedit, then independent gates; no DB writes."""
import copy,hashlib,json
from datetime import datetime,timezone
from draft_3292_scoped import OUT,save
from codex_content_runner import CodexStagedContentRunner,CodexContentConfig
from listener_review import review
from senior_script_guard import contract,review_issues
c=json.loads((OUT/'candidate-v3.json').read_text(encoding='utf-8'))
c['sections'][5]['text']=c['sections'][5]['text'].replace('훔쳤다 쫓겨났는데','훔쳤다가 쫓겨났는데')
c['sections'][40]['text']='오래전, '+c['sections'][40]['text']
script='\n\n'.join(s['text'] for s in c['sections'])
sha=hashlib.sha256(script.encode()).hexdigest()
save('candidate-final.json',c)
save('approval-final.json',{'user_message':'고쳐서 진행해. 그리고 이미지생성DB반영을 이어서 해',
    'recorded_at':datetime.now(timezone.utc).isoformat(),'script_sha256':sha,'published':False})
r=CodexStagedContentRunner(CodexContentConfig.from_environment())
def stage(name,ctx,task):
    print(name,flush=True)
    value=r._stage('3292_authorized_final',name,ctx,task)
    save('approved-final-'+name+'.json',value)
    return value
listeners=review(stage,'떨어진 귀걸이가 부른 일, 그 집안 3대에 걸친 저주',c['sections'])
senior=stage('02_senior',{'title':'떨어진 귀걸이가 부른 일, 그 집안 3대에 걸친 저주','sections':c['sections'],'narrative_blueprint':c['narrative_blueprint']},
    'Review supplied fictional folktale independently, no rewrite. Respect ~습니다 narration. '+contract({'category_id':2})+' Return report directly.')
errors=review_issues(senior)
passed=not errors and all(x['verdict']=='pass' for x in listeners.values())
save('approved-final-quality.json',{'passed':passed,'script_sha256':sha,'senior':senior,'listeners':listeners,'errors':errors})
print(json.dumps({'passed':passed,'score':senior.get('score')},ensure_ascii=False),flush=True)
