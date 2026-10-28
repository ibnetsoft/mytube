import sys,json,copy
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
for f in ['.env','.env.local','auth-web/.env.local']:load_dotenv(ROOT/f)
from worker.script_worker_store import ScriptStore
from worker.ae_mouth_worker import input_matches
store=ScriptStore();pid='e9233112-f0d7-4b35-91bf-2f892844eb30'
def read(t,p):return store.request('GET',t,params={'select':'*',**p})[0]
job=read('std_project_assets',{'project_id':'eq.'+pid,'metadata->>kind':'eq.ae_mouth_job','order':'created_at.desc','limit':'1'})[0]
meta=copy.deepcopy(job['metadata']);assert meta['state']=='failed' and meta['phase']=='render',meta['state']
assert input_matches(meta['input'],read('std_projects',{'id':'eq.'+pid})[0],read('std_project_assets',{'project_id':'eq.'+pid,'order':'created_at.desc'}),read('std_project_scenes',{'project_id':'eq.'+pid,'order':'scene_number.asc'})),'Inputs changed'
assert sum(r['status']=='direction_approved' for r in meta['results'])==16
assert all(next(r for r in meta['results'] if r['number']==n)['status']=='skipped' for n in [53,57,59,84])
(ROOT/'_dev/artifacts/image_repair_3373/ae-render-retry.before.json').write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf8')
meta.update(state='direction_approved',phase='render',error='')
saved=store.request('PATCH','std_project_assets',params={'id':'eq.'+job['id'],'updated_at':'eq.'+job['updated_at']},body={'metadata':meta,'updated_at':datetime.now(timezone.utc).isoformat()},prefer='return=representation')[0]
assert len(saved)==1,'Job changed'
print(json.dumps({'job_id':job['id'],'state':saved[0]['metadata']['state'],'approved_scenes':16,'excluded_scenes':[53,57,59,84]}))
