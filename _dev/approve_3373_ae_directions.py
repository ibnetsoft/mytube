import sys, json, copy
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
for f in ['.env','.env.local','auth-web/.env.local']:load_dotenv(ROOT/f)
from worker.script_worker_store import ScriptStore
from worker.ae_mouth_worker import input_matches
store=ScriptStore();pid='e9233112-f0d7-4b35-91bf-2f892844eb30'
def read(table,params):return store.request('GET',table,params={'select':'*',**params})[0]
jobs=read('std_project_assets',{'project_id':'eq.'+pid,'metadata->>kind':'eq.ae_mouth_job','order':'created_at.desc','limit':'1'})
job=jobs[0];meta=copy.deepcopy(job['metadata'])
assert meta['state']=='direction_pending',meta['state']
project=read('std_projects',{'id':'eq.'+pid})[0]
assets=read('std_project_assets',{'project_id':'eq.'+pid,'order':'created_at.desc'})
scenes=read('std_project_scenes',{'project_id':'eq.'+pid,'order':'scene_number.asc'})
assert input_matches(meta['input'],project,assets,scenes),'Inputs changed; approval cannot be reused'
uncertain={r['number'] for r in meta['results'] if r['status']=='needs_review'}
assert uncertain=={53,57,59,84},uncertain
out=ROOT/'_dev/artifacts/image_repair_3373'
(out/'ae-direction-approval.before.json').write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf8')
approved=[]
for row in meta['results']:
 if row['number'] in uncertain:
  row.update(status='skipped',reason='화자 또는 입 위치가 불확실하여 사용자 요청으로 입모양 작업에서 제외합니다.',excluded_by_user=True)
 elif row['status']=='direction_pending':
  row['status']='direction_approved';approved.append(row['number'])
 else:assert row['status']=='skipped',row['status']
assert len(approved)==16,approved
meta.update(state='direction_approved',phase='render',error='')
saved=store.request('PATCH','std_project_assets',params={'id':'eq.'+job['id'],'updated_at':'eq.'+job['updated_at']},body={'metadata':meta,'updated_at':datetime.now(timezone.utc).isoformat()},prefer='return=representation')[0]
assert len(saved)==1,'Job changed during approval'
receipt={'job_id':job['id'],'approved_scenes':approved,'excluded_scenes':sorted(uncertain),'state':saved[0]['metadata']['state']}
(out/'ae-direction-approval.receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(receipt,ensure_ascii=False))
