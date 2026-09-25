"""Review the approved exact draft without changing it or production data."""
import hashlib
import json
from datetime import datetime, timezone
from draft_3292_scoped import OUT, save
from codex_content_runner import CodexStagedContentRunner, CodexContentConfig
from senior_script_guard import contract, review_issues
from listener_review import review

candidate = json.loads((OUT/'candidate.json').read_text(encoding='utf-8'))
sections = candidate['sections']
script = '\n\n'.join(s['text'].strip() for s in sections)
assert hashlib.sha256(script.encode()).hexdigest() == '2cc3e541333b8ba4573ebd943fce8073dfd9d8a42131a11c16297eb520f6ffd8'
save('approval-v1.json', {'approved_at_recorded':datetime.now(timezone.utc).isoformat(),
    'user_message':'진행해', 'scope':'approve presented full draft v1 and continue repair',
    'script_sha256':hashlib.sha256(script.encode()).hexdigest(), 'published':False})
runner=CodexStagedContentRunner(CodexContentConfig.from_environment())
def stage(name,context,task):
    print(name,flush=True)
    value=runner._stage('3292_approved_v1',name,context,task)
    save(name+'.json',value)
    return value
context={'title':'떨어진 귀걸이가 부른 일, 그 집안 3대에 걸친 저주','sections':sections}
senior=stage('02_senior_independent',context,
    'Review the complete supplied fictional Korean folktale independently. Read only supplied text; do not inspect other files or infer missing facts. Do not rewrite. '+contract({'category_id':2})+
    ' Return the script_quality_report object directly.')
listeners=review(stage,context['title'],sections)
issues=review_issues(senior)
save('independent-review.json',{'script_sha256':hashlib.sha256(script.encode()).hexdigest(),
    'senior':senior,'senior_validation_issues':issues,'listeners':listeners,
    'passed':not issues and all(r['verdict']=='pass' for r in listeners.values()),
    'production_changed':False})
print(json.dumps({'senior':senior.get('verdict'),'issues':issues,
    'listeners':{k:v['verdict'] for k,v in listeners.items()}},ensure_ascii=False),flush=True)
