"""Publish completed cached renders after a transport failure; never rerender."""
import sys,json,subprocess,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'worker'),str(ROOT)]
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
import ae_highlight_worker as ae
from ae_mouth import digest
from ae_mouth_worker import subprocess_probe
from content_identity import mouth_output_identity
from ae_media_utils import ffmpeg
base,headers=ae._supabase()
for topic,job_id in [(3376,'0db3979f-cded-4f78-899d-687123bffb87'),(3377,'9159c849-ebbf-4d5a-8429-d25b397cca50')]:
 job=ae._request('GET',base+'/rest/v1/std_project_assets',headers,params={'select':'*','id':'eq.'+job_id}).json()[0];meta=job['metadata'];snapshot=meta['input'];identity=meta['fingerprint']
 for result in meta.get('results',[]):
  if result.get('skip_reason')!='automatic_processing_failed' or result.get('reason')!='GCS upload failed after bounded retries':continue
  n=result['number'];scene=next(s for s in snapshot['scenes'] if s['number']==n);duration=scene['end']-scene['start']
  if len(sys.argv)>1 and str(n)!=sys.argv[1]:continue
  file=ROOT/'output/codex-local-console/ae-mouth'/identity/f'scene-{n}/ae-mouth-preview.mp4';assert file.exists()
  sha=digest(file);receipt=json.loads(file.with_name(file.name+'.gcs-upload.json').read_text());assert receipt['sha256']==sha and receipt['size']==file.stat().st_size
  assert abs(subprocess_probe(file)-duration)<.12
  existing=ae._request('GET',base+'/rest/v1/std_project_assets',headers,params={'select':'id','project_id':'eq.'+job['project_id'],'asset_type':'eq.video','scene_number':'eq.'+str(n),'metadata->>ae_mouth_fingerprint':'eq.'+identity,'metadata->>render_sha256':'eq.'+sha}).json()
  if existing:print(json.dumps({'topic':topic,'scene':n,'reused_asset':existing[0]['id']}),flush=True);continue
  original_sha=sha;original=file;web=file.with_name('ae-mouth-web.mp4')
  if not web.exists():subprocess.run([ffmpeg(),'-y','-v','error','-i',str(original),'-map','0:v:0','-map','0:a:0','-c:v','h264_nvenc','-preset','p6','-cq','20','-b:v','0','-bf','3','-pix_fmt','yuv420p','-c:a','copy','-movflags','+faststart',str(web)],check=True,timeout=120)
  web_sha=digest(web);quality_file=web.with_suffix('.quality.json');saved_quality=json.loads(quality_file.read_text()) if quality_file.exists() else {}
  if saved_quality.get('source')==original_sha and saved_quality.get('web')==web_sha:ssim=saved_quality['ssim']
  else:
   quality=subprocess.run([ffmpeg(),'-hide_banner','-i',str(original),'-i',str(web),'-lavfi','ssim','-an','-f','null','NUL'],capture_output=True,text=True,check=True,timeout=120)
   ssim=float(re.findall(r'All:([0-9.]+)',quality.stderr)[-1]);quality_file.write_text(json.dumps({'source':original_sha,'web':web_sha,'ssim':ssim}))
  assert ssim>=.99,(topic,n,ssim)
  file=web;sha=web_sha;assert abs(subprocess_probe(file)-duration)<.12
  existing_web=ae._request('GET',base+'/rest/v1/std_project_assets',headers,params={'select':'id','project_id':'eq.'+job['project_id'],'asset_type':'eq.video','scene_number':'eq.'+str(n),'metadata->>ae_mouth_fingerprint':'eq.'+identity,'metadata->>render_sha256':'eq.'+sha}).json()
  if existing_web:print(json.dumps({'topic':topic,'scene':n,'reused_asset':existing_web[0]['id']}),flush=True);continue
  bucket,path,url=ae._upload_gcs_file(file,f'std-projects/{job["project_id"]}/ae-mouth/{identity}/scene-{n}-{sha[:16]}-web.mp4','video/mp4')
  metadata={'gcs_bucket':bucket,'gcs_path':path,'storage_bucket':bucket,'storage_path':path,'storage_provider':'gcs','url':url,
    'content_identity':mouth_output_identity(job,scene),'ae_mouth_fingerprint':identity,'timing_locked':True,'voice_synced':True,'timing_mode':'final_voice',
    'artifact_ready':True,'ae_reviewed':False,'pipeline_version':2,'duration_seconds':duration,'render_sha256':sha,
    'source_image_id':scene['image']['id'],'source_audio_id':snapshot['audio']['id'],'effect_exclusions':result.get('effect_exclusions',[]),
    'delivery_variant':'web_cq20','original_render_sha256':original_sha,'web_copy_ssim':ssim,
    'direction':'Recovered upload of cached finalized-voice mouth render; original image and generated poses preserved.'}
  asset=ae._request('POST',base+'/rest/v1/std_project_assets',{**headers,'Prefer':'return=representation'},json={'project_id':job['project_id'],'scene_number':n,'asset_type':'video','status':'uploaded','file_name':f'actual-voice-scene-{n}.mp4','mime_type':'video/mp4','file_size':file.stat().st_size,'metadata':metadata}).json()[0]
  print(json.dumps({'topic':topic,'scene':n,'recovered_asset':asset['id'],'bytes':file.stat().st_size}),flush=True)
