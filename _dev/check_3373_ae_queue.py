import sys, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
for f in ['.env','.env.local','auth-web/.env.local']:load_dotenv(ROOT/f)
from worker.script_worker_store import ScriptStore
s=ScriptStore(); pid='e9233112-f0d7-4b35-91bf-2f892844eb30'
def read(t,p):return s.request('GET',t,params=p)[0]
project=read('std_projects',{'select':'id,status,submitted_at,updated_at,project_payload','id':'eq.'+pid})[0]
print('PROJECT',json.dumps({k:project.get(k) for k in ['id','status','submitted_at','updated_at']},ensure_ascii=False))
print('AE_ENABLED',project['project_payload'].get('ae_mouth'))
jobs=read('std_project_assets',{'select':'id,created_at,updated_at,metadata','project_id':'eq.'+pid,'metadata->>kind':'eq.ae_mouth_job','order':'created_at.desc','limit':'4'})
for job in jobs:
 m=job['metadata'];results=m.get('results',[]);counts={state:sum(r.get('status')==state for r in results) for state in set(r.get('status') for r in results)}
 print('JOB',json.dumps({'id':job['id'],'created_at':job['created_at'],'updated_at':job['updated_at'],'state':m.get('state'),'phase':m.get('phase'),'error':m.get('error'),'counts':counts,'results':[{k:r.get(k) for k in ['number','status','reason']} for r in results]},ensure_ascii=False))
print('JOB_COUNT',len(jobs))
