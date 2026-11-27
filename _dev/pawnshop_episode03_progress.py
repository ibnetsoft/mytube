"""Reflect verified basic-image counts without replacing any scene or project."""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env',override=False)
from worker.script_worker_store import ScriptStore
OUT=ROOT/'output/pawnshop-series/episode-03';JOB='8b6c78f054e445148286e8ad0c661610';store=ScriptStore();last=-1;errors=0
while True:
 try:
  count=len(list((OUT/'scene-images').glob('grid-*-publication.json')))*4
  if count!=last and (OUT/'registration-receipt.json').exists():
   topic=str(json.loads((OUT/'registration-receipt.json').read_text())['topic_id'])
   rows,_=store.request('GET','topics_queue',params={'select':'id,status,assigned_employee_email,progress_payload','id':'eq.'+topic})
   assert len(rows)==1;row=rows[0];p=row['progress_payload'];assert p['local_script_job_id']==JOB
   if row['status']!='pending' or row.get('assigned_employee_email'):
    print('Topic claimed; preserve user progress. Verified scene receipts remain local.',flush=True);break
   prior=p.get('scene_image_count');p.update(scene_image_count=count,image_generation_status='completed' if count==144 else 'in_progress',basic_scene_images_ready=count==144,scene_assets_ready=False)
   patched,_=store.request('PATCH','topics_queue',params={'id':'eq.'+topic,'status':'eq.pending','assigned_employee_email':'eq.','progress_payload->>local_script_job_id':'eq.'+JOB,'progress_payload->>scene_image_count':'is.null' if prior is None else 'eq.'+str(prior)},body={'progress_payload':p},prefer='return=representation')
   if patched:
    check,_=store.request('GET','topics_queue',params={'select':'id,progress_payload','id':'eq.'+topic})
    assert check[0]['progress_payload']['scene_image_count']==count
    last=count;(OUT/'web-image-count-readback.json').write_text(json.dumps({'topic_id':topic,'verified_scene_image_count':count,'updated_at':time.time(),'basic_scene_images_ready':count==144,'tts_completed':False,'ae_render_completed':False}));print('verified image count',count,flush=True)
  if count==144 and last==144:break
  errors=0;time.sleep(20)
 except Exception as exc:
  errors+=1;print('progress update deferred',type(exc).__name__,flush=True)
  if errors>=3:raise
  time.sleep(min(60,20*errors))
