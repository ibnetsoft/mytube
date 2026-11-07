"""Resume the three known native jobs on an updated AE host; inspect by default."""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
import worker_config  # Load the AE host environment/settings before queue access.
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env')
from worker.script_worker_store import ScriptStore
from worker.wuxia_worker_contract import claim_acknowledgement
JOBS=('91c265fe-12cf-4788-ba1d-e3eae9a3b2fe', '13f6e0a5-ab9f-4750-aa3e-0d5b895694dc', '9df7ce21-e660-4553-8577-778fc02b02f9')

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--enqueue',action='store_true');args=parser.parse_args()
 if args.enqueue:
  from adobe_tools import find_afterfx,find_aerender
  assert find_afterfx() and find_aerender(),'Run on the updated native AE host after restarting its supervisor'
 store=ScriptStore();out=ROOT/'output/wuxia-worker-version-repair';out.mkdir(parents=True,exist_ok=True)
 for jid in JOBS:
  rows,_=store.request('GET','std_project_assets',params={'id':'eq.'+jid,'select':'id,project_id,metadata,updated_at','limit':1})
  assert len(rows)==1;job=rows[0];meta=job['metadata']
  if meta.get('state')!='awaiting_worker_update':
   print(json.dumps({'job_id':jid,'state':meta.get('state'),'skipped':True}));continue
  assert meta.get('enabled') is False and meta.get('kind')=='motion_automation'
  projects,_=store.request('GET','std_projects',params={'id':'eq.'+job['project_id'],'select':'employee_email,status','limit':1})
  assert projects[0]['employee_email']=='supapitmusic@gmail.com' and projects[0]['status']=='review_requested'
  snapshot=json.loads(meta['input']['snapshot_json'])
  ack=claim_acknowledgement(snapshot,meta,'preflight-only')
  assert ack['worker_contract_ack']['contract']=='wuxia_native_timeline/v3'
  print(json.dumps({'job_id':jid,'scenes':len(snapshot['scenes']),'native_contract_preflight':True,'enqueue':args.enqueue}))
  if not args.enqueue:continue
  (out/(jid+'-before.json')).write_text(json.dumps(job,ensure_ascii=False),encoding='utf-8')
  # Reject cached passthrough output, retain immutable frozen inputs and archived evidence.
  meta.update(state='queued',enabled=True,phase='native_worker_recovery',error=None,
   progress='갱신된 AE 워커에서 저장된 무협 연출 다시 제작',results=[],plans=[],quality_notes=[],
   worker_recovery_at=datetime.now(timezone.utc).isoformat())
  for key in ('worker_contract_ack','worker_token','retry_after','heartbeat_at'):meta.pop(key,None)
  changed,_=store.request('PATCH','std_project_assets',params={'id':'eq.'+jid,'updated_at':'eq.'+job['updated_at'],
   'metadata->>state':'eq.awaiting_worker_update'},body={'metadata':meta},prefer='return=representation')
  assert len(changed)==1,'Concurrent job change; inspect before resuming'
  (out/(jid+'-resumed.json')).write_text(json.dumps({'job_id':jid,'state':'queued','frozen_fingerprint':meta['fingerprint']},indent=2))

if __name__=='__main__':main()
