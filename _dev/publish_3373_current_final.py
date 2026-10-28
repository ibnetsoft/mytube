import sys,json,uuid,shutil,hashlib,subprocess
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
for f in ['.env','.env.local','auth-web/.env.local']:load_dotenv(ROOT/f)
from worker.script_worker_store import ScriptStore
from worker.lipsync_video_worker import ffmpeg
from services.remote_render_service import _probe_media_duration
from worker.ae_highlight_worker import _upload_gcs_file,_gcs_credentials
from remote_drive_worker import RemoteDriveWorker
out=ROOT/'_dev/artifacts/final_3373_current_v4';video=out/'output.mp4';assert video.exists() and video.stat().st_size>10000000
config=json.loads((out/'config.json').read_text(encoding='utf8'));duration=_probe_media_duration(ffmpeg(),str(video));assert abs(duration-config['audio_duration'])<.15,(duration,config['audio_duration'])
assert len(config['images'])==101 and config['render_settings']['timing_locked_indices']==[22,23,31,44,99]
for n,t in [(23,config['image_timing_starts'][22]+2),(45,config['image_timing_starts'][44]+2),(62,config['image_timing_starts'][61]+1),(100,config['image_timing_starts'][99]+4),(101,duration-2)]:
 subprocess.run([ffmpeg(),'-y','-ss',str(t),'-i',str(video),'-frames:v','1',str(out/f'qa_scene_{n:03}.jpg')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
qa={'duration':duration,'resolution':[1920,1080],'scene_count':101,'ae_mouth_scenes':[23,24,32,45,100],'fallback_original_scenes':[25,30,33,36,39,42,43,47,62,96,98],'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'file_bytes':video.stat().st_size}
(out/'final_qa.json').write_text(json.dumps(qa,indent=2),encoding='utf8');print('QA_OK',json.dumps(qa),flush=True)
if '--publish' not in sys.argv:sys.exit(0)
store=ScriptStore();previous=store.request('GET','remote_render_queue',params={'select':'*','id':'eq.9cef1649-3c12-497e-9c27-90d01b0d1d79'})[0][0]
receipt_file=out/'published_receipt.json'
if receipt_file.exists():print('Already published');sys.exit(0)
queue_id=str(uuid.uuid4());bucket,path,_=_upload_gcs_file(video,f'std-renders/{queue_id}/3373_current_final_v4.mp4','video/mp4')
creds,_=_gcs_credentials();signed=RemoteDriveWorker._generate_gcs_signed_url(None,creds,bucket,path)
assert signed,'Signed result URL required'
thumb=ROOT/'_dev/artifacts/final_3373_ae_v3/thumbnail.png';tb,tp,_=_upload_gcs_file(thumb,f'std-renders/{queue_id}/thumbnail.png','image/png');thumb_url=RemoteDriveWorker._generate_gcs_signed_url(None,creds,tb,tp)
now=datetime.now(timezone.utc).isoformat()
metadata={'source':'std_web_current_state_final','std_web_project_id':'e9233112-f0d7-4b35-91bf-2f892844eb30','topic_queue_id':3373,'render_version':4,'previous_render_queue_id':previous['id'],'storage_provider':'gcs','gcs_bucket':bucket,'gcs_path':path,'storage_bucket':bucket,'storage_path':path,'gcs_public_url':signed,'result_public_url':signed,'gcs_thumbnail_url':thumb_url,'admin_publish_ready':True,'admin_publish_status':'ready_for_upload','queue_scope':'standard','visibility_control':'admin_only','ae_mouth_scenes':qa['ae_mouth_scenes'],'ae_current_state_exception':{'authorized_by':'user request in current chat','report':'docs/AE_3373_current_state_render_20261005.md','incomplete_ae_uses_original':qa['fallback_original_scenes'],'original_exclusions':[53,57,59,84]},'local_output_path':str(video),'final_qa':qa}
row={'id':queue_id,'project_id':previous['project_id'],'project_name':previous['project_name'],'email':previous['email'],'status':'completed','progress':100,'message':'현재 상태 최종 렌더 v4 완료 · AE 입모양 5씬 적용, 미완료 11씬 원본 사용','created_at':now,'updated_at':now,'completed_at':now,'render_mode':'gcs_api','result_file_id':f'gcs:{bucket}/{path}','result_file_name':'3373_current_final_v4.mp4','metadata':metadata,'job_type':previous.get('job_type') or 'render','worker_group':previous.get('worker_group') or 'default'}
saved=store.request('POST','remote_render_queue',body=row,prefer='return=representation')[0];assert len(saved)==1
receipt={'queue_id':queue_id,'gcs_bucket':bucket,'gcs_path':path,'local_output':str(video),'duration':duration,'sha256':qa['sha256']}
receipt_file.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
print('PUBLISHED',json.dumps(receipt,ensure_ascii=False),flush=True)
