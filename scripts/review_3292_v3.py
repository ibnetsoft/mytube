"""Independent read-only review of the exact user-approved v3."""
import hashlib
import json
from datetime import datetime, timezone
from draft_3292_scoped import OUT, save
from codex_content_runner import CodexStagedContentRunner, CodexContentConfig
from senior_script_guard import contract, review_issues
from listener_review import review

c=json.loads((OUT/'candidate-v3.json').read_text(encoding='utf-8'))
sections=c['sections']
sha=hashlib.sha256('\n\n'.join(s['text'].strip() for s in sections).encode()).hexdigest()
assert sha=='e34ba4ef3bde813515948c8fccf0c45c71cb45b6bc52e984c93036d44816b842'
if not (OUT/'approval-v3.json').exists():
    save('approval-v3.json',{'recorded_at':datetime.now(timezone.utc).isoformat(),
        'user_message':'이걸로 진행해','script_sha256':sha,'published':False})
runner=CodexStagedContentRunner(CodexContentConfig.from_environment())
def stage(name,context,task):
    print(name,flush=True)
    value=runner._stage('3292_approved_v3',name,context,task)
    save('v3-'+name+'.json',value)
    return value
context={'title':'떨어진 귀걸이가 부른 일, 그 집안 3대에 걸친 저주','sections':sections}
senior=stage('02_senior_independent',{**context,'narrative_blueprint':c['narrative_blueprint']},
    'Review independently. Do not rewrite or inspect other files. Blueprint is a cross-check, not permission to fill gaps absent from narration. '
    'User specifies respectful ~습니다 declarative narration; do not reject that voice simply because endings repeat, '
    'but flag genuinely disconnected or awkward prose. '+contract({'category_id':2})+' Return the report object directly.')
listeners=review(stage,context['title'],sections)
errors=review_issues(senior)
passed=not errors and all(x['verdict']=='pass' for x in listeners.values())
save('v3-independent-review.json',{'script_sha256':sha,'senior':senior,'listeners':listeners,
    'passed':passed,'senior_validation_issues':errors,'production_changed':False})
print(json.dumps({'passed':passed,'senior':senior.get('score'),
    'listeners':{k:v['verdict'] for k,v in listeners.items()}},ensure_ascii=False),flush=True)
