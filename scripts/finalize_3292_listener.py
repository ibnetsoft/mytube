"""Bounded listener correction; retain approved text except flagged clarity change."""
import json, hashlib
from draft_3292_scoped import OUT, save
from codex_content_runner import CodexStagedContentRunner,CodexContentConfig
from listener_review import improve_for_listener
from senior_script_guard import contract,review_issues
c=json.loads((OUT/'candidate-v3.json').read_text(encoding='utf-8'))
request=json.loads((OUT/'request.json').read_text(encoding='utf-8'))
runner=CodexStagedContentRunner(CodexContentConfig.from_environment())
def stage(name,context,task):
    print(name,flush=True)
    if name=='02g_listener_repair':
        task+=' The only flagged issue is an implicit flashback: add a short past-time cue in scene41, preserve EVERY other wording in that scene if possible. No new facts. Keep narration ~습니다 and exact direct dialogue.'
    result=runner._stage('3292_approved_v3',name,context,task)
    save('final-'+name+'.json',result)
    return result
sections,report=improve_for_listener(stage,request['title'],c['sections'],request['scene_budgets'])
changed=[i+1 for i,(a,b) in enumerate(zip(c['sections'],sections)) if a!=b]
assert set(changed)<= {41}
save('v3-listener-final.json',report)
final={**c,'sections':sections}
save('candidate-v3-final.json',final)
senior=stage('02_final_senior',{'title':request['title'],'sections':sections,'narrative_blueprint':c['narrative_blueprint']},
    'Independently review only supplied final text and ledger. No rewrite. Narration intentionally uses ~습니다. '+contract({'category_id':2})+' Return report directly.')
errors=review_issues(senior)
script='\n\n'.join(s['text'] for s in sections)
save('final-review-status.json',{'passed':not errors,'errors':errors,'changed_scenes':changed,
    'script_sha256':hashlib.sha256(script.encode()).hexdigest(),'published':False,'listener':report,'senior':senior})
print(json.dumps({'passed':not errors,'changed':changed},ensure_ascii=False),flush=True)
