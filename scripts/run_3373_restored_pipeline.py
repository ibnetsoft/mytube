"""Continue only the authorized restored 3373 AE job and final render; never publish."""
import sys,json,time,subprocess,logging,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'worker'),str(ROOT)]
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
# This CLI account successfully completed a live gpt-5.5 request on 2026-10-14;
# its default gpt-6.1-sol name was rejected. Scope this override to this job.
os.environ['CODEX_CONTENT_MODEL']='gpt-5.5'
# A real image review succeeded over this documented HTTP Responses transport;
# the installed CLI's default WebSocket connection repeatedly disconnected.
_subprocess_run=subprocess.run
def _job_codex_http_run(command,*args,**kwargs):
 if isinstance(command,(list,tuple)) and Path(str(command[0])).name.lower() in ('codex','codex.exe','codex.cmd','codex.ps1'):
  command=list(command)+['-c','model_provider="openai_http"',
   '-c','model_providers.openai_http.name="OpenAI HTTP"',
   '-c','model_providers.openai_http.wire_api="responses"',
   '-c','model_providers.openai_http.requires_openai_auth=true',
   '-c','model_providers.openai_http.supports_websockets=false']
 return _subprocess_run(command,*args,**kwargs)
subprocess.run=_job_codex_http_run
import ae_mouth_worker as mouth
from ae_mouth_runtime import instance_lock,Heartbeat
import worker_config
from shutdown_flag import clear_shutdown_flag
from remote_drive_worker import RemoteDriveWorker
JOB='9824529b-32f6-4513-a39e-678d496522fc'
PROJECT='e9233112-f0d7-4b35-91bf-2f892844eb30'
DIR=ROOT/'output/project-recovery-e9233112'
base,headers=mouth.ae._supabase()
def status(**values):
 (DIR/'restored-render-progress.json').write_text(json.dumps({**values,'updated_at':time.time()},ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps(values,ensure_ascii=False),flush=True)
def job():
 rows=mouth.ae._request('GET',base+'/rest/v1/std_project_assets',headers,params={'id':'eq.'+JOB,'select':'*'}).json()
 if not rows:raise RuntimeError('Targeted AE job missing')
 return rows[0]
try:
 with instance_lock(worker_config.STATE_DIR/'ae_mouth_worker.lock'):
  clear_shutdown_flag('ae_mouth_worker')
  with Heartbeat(worker_config.STATE_DIR/'ae_mouth_worker.json',worker_config.WORKER_INSTANCE_ID) as heartbeat:
   for phase in range(12):
    current=job();meta=current['metadata'];results=meta.get('results',[])
    status(stage='ae',state=meta['state'],phase=meta.get('phase'),reviewed=sum(r['status']=='approved' for r in results),skipped=sum(r['status']=='skipped' for r in results),total=len(meta['input']['scenes']))
    if meta.get('auto_render_queue_id'):break
    if meta['state']=='reviewed':
     unresolved=[r for r in results if r.get('skip_reason') in ('automatic_processing_failed','automatic_review_failed')]
     if unresolved:raise RuntimeError('Scene repairs required before final render: '+json.dumps([{'number':r['number'],'reason':r.get('reason')} for r in unresolved],ensure_ascii=False))
     result=subprocess.run(['node',str(ROOT/'scripts/std_continue_submission.cjs'),PROJECT,'--enqueue'],cwd=ROOT,text=True,capture_output=True,timeout=600)
     if result.returncode:raise RuntimeError('Reviewed render enqueue failed: '+result.stderr[-1000:])
     current=job();meta=current['metadata'];break
    if meta['state'] in ('failed','obsolete'):raise RuntimeError('AE job '+meta['state']+': '+str(meta.get('error')))
    if not mouth.process_one(report=heartbeat.update,job_id=JOB):raise RuntimeError('Targeted AE phase is not claimable; no other job was started.')
   else:raise RuntimeError('AE phase count exceeded; preserve completed outputs for inspection.')
 queue_id=meta.get('auto_render_queue_id')
 if not queue_id:raise RuntimeError('Final render was not queued')
 worker=RemoteDriveWorker();queued=worker.get_job(queue_id)
 status(stage='render',queue_id=queue_id,state=queued.get('status'))
 if queued.get('status')=='pending':
  if not worker.claim_job(queued):raise RuntimeError('Final render is already claimed by another worker')
  worker.process_job(worker.get_job(queue_id))
 final=worker.get_job(queue_id)
 if final.get('status')!='completed' or not final.get('result_file_id'):raise RuntimeError('Final render not completed: '+str(final.get('message')))
 (DIR/'restored-final-render-receipt.json').write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding='utf8')
 status(stage='completed',queue_id=queue_id,topic=3373,upload_executed=False)
except Exception as exc:
 status(stage='failed',error=str(exc))
 raise
