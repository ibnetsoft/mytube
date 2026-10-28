"""Render the existing accepted clips with restored captions; no AE or upload."""
import ast,json,os,sys,time,hashlib,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
from remote_drive_worker import RemoteDriveWorker
from services import ffmpeg_slideshow_service as ff
import subprocess
DIR=ROOT/'output/project-recovery-e9233112'
queue=json.loads((DIR/'subtitle-only-render-receipt.json').read_text(encoding='utf8'))['id']
RUN=DIR/'subtitle-only-encoder'
RUN.mkdir(exist_ok=True)
# Reuse the proven bounded encoder scheduling, without its project edits or QA.
source=ast.parse((ROOT/'scripts/repair_3373_template_render.py').read_text(encoding='utf8'))
functions=[node for node in source.body if isinstance(node,ast.FunctionDef) and node.name in ('limited','batched_render')]
original=ff._run_command
original_render=ff.render_ffmpeg_slideshow
exec(compile(ast.Module(body=functions,type_ignores=[]),'<bounded-encoder>','exec'))
ff._run_command=limited
ff.render_ffmpeg_slideshow=batched_render
from worker import render_asset_cache
download_original=render_asset_cache.download_cached
signed_receipt_path=Path(os.getenv('TEMP'))/'air-render-checkpoints'/queue/'signed-local-receipts.json'
signed_receipts=json.loads(signed_receipt_path.read_text()) if signed_receipt_path.exists() else {}
local_files={}
for file in (ROOT/'output/mouth-video-gallery/media').glob('*.mp4'):
 with file.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
 local_files[digest]=file
def reuse_local(source,destination,credentials,root,expected_sha=None):
 target=Path(destination)
 accepted_sha=expected_sha or signed_receipts.get(source.get('path'))
 if accepted_sha and target.exists():
  with target.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
  if actual==accepted_sha:return target
 if expected_sha in local_files:
  target.parent.mkdir(parents=True,exist_ok=True)
  shutil.copyfile(local_files[expected_sha],target)
  return target
 return download_original(source,destination,credentials,root,expected_sha)
render_asset_cache.download_cached=reuse_local
worker=RemoteDriveWorker()
if '--finish-storage' in sys.argv:
 def prepared(job_id,job,temp_dir,config_file_id):
  from worker.content_identity import validate_render_identity
  config_path=Path(temp_dir)/'config.json'
  validate_render_identity(json.loads(config_path.read_text(encoding='utf8')),job['metadata'])
  checkpoint=json.loads((Path(temp_dir)/'encoder-completed.json').read_text())
  assert checkpoint['config_hash']==hashlib.sha256(config_path.read_bytes()).hexdigest()
  assert checkpoint['bytes']==(Path(temp_dir)/'output.mp4').stat().st_size
  worker.visual_cache_dir=None
 worker._prepare_gcs_manifest_job=prepared
def get():
 rows=worker._request('GET',worker.queue_url,params={'id':'eq.'+queue,'select':'*','limit':'1'}) or []
 if not rows:raise RuntimeError('Target queue missing')
 return rows[0]
job=get()
if '--finish-storage' in sys.argv and job['status']=='failed':
 worker._request('PATCH',worker.queue_url,params={'id':'eq.'+queue,'status':'eq.failed'},json={'status':'pending','worker_id':None,'error_message':None,'message':'완성된 렌더링 결과 저장 재개'})
 job=get()
print(json.dumps({'queue_id':queue,'status':job['status']},ensure_ascii=False),flush=True)
if job['status']=='pending':
 claimed=worker.claim_job(job)
 if claimed:worker.process_job(claimed)
while get()['status']=='rendering':time.sleep(15)
final=get()
(DIR/'subtitle-only-render-final.json').write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding='utf8')
if final['status']!='completed':raise RuntimeError(str(final.get('error_message') or final.get('message')))
print(json.dumps({'status':'completed','queue_id':queue,'result_file_id':final.get('result_file_id'),'upload':False}),flush=True)
