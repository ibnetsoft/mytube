"""Full-duration actual-voice clips for the three independently verified hidden mouths."""
import sys,json,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'worker'),str(ROOT)]
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
import ae_highlight_worker as ae
from ae_media_utils import ffmpeg,run,ref
from ae_mouth import digest
from mouth_geometry import animatable
from content_identity import mouth_output_identity
from submission_pipeline import prepared_scene_direction
base,headers=ae._supabase();job_id='9159c849-ebbf-4d5a-8429-d25b397cca50'
job=ae._request('GET',base+'/rest/v1/std_project_assets',headers,params={'select':'*','id':'eq.'+job_id}).json()[0]
meta=job['metadata'];snapshot=meta['input'];identity=meta['fingerprint'];folder=ROOT/'output/codex-local-console/two-topic-mouths/3377/final-voice'
audio=ROOT/'output/codex-local-console/ae-mouth'/identity/'final-narration.mp3'
if not audio.exists():
 bucket,path=ref(snapshot['audio']);ae._download_gcs_file(ae.GcsRef(bucket,path),audio)
receipts=[]
for n in [23,24,25]:
 scene=next(s for s in snapshot['scenes'] if s['number']==n);image=folder.parent/f'scene-{n:03d}.png'
 assert digest(image)==scene['speaker_regions']['source_sha256']
 assert all(not animatable(s,digest(image)) for s in scene['speaker_regions']['speakers'])
 duration=scene['end']-scene['start'];target=folder/f'scene-{n:03d}-actual-voice-preserved.mp4'
 if not target.exists():run([ffmpeg(),'-y','-loop','1','-i',str(image),'-ss',str(scene['start']),'-i',str(audio),'-t',str(duration),'-vf','scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1','-r','24','-c:v','h264_nvenc','-preset','p4','-cq','18','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-movflags','+faststart',str(target)])
 from ae_mouth_worker import subprocess_probe
 assert abs(subprocess_probe(target)-duration)<.12
 sha=digest(target);path=f'std-projects/{job["project_id"]}/ae-mouth/{identity}/scene-{n}-preserved-{sha[:16]}.mp4'
 existing=ae._request('GET',base+'/rest/v1/std_project_assets',headers,params={'select':'*','project_id':'eq.'+job['project_id'],'asset_type':'eq.video','scene_number':'eq.'+str(n),'metadata->>ae_mouth_fingerprint':'eq.'+identity,'metadata->>render_sha256':'eq.'+sha}).json()
 if existing:asset=existing[0]
 else:
  bucket,path,url=ae._upload_gcs_file(target,path,'video/mp4');_,exclusions=prepared_scene_direction(scene['direction'],scene.get('layered_source'),True)
  metadata={'gcs_bucket':bucket,'gcs_path':path,'storage_bucket':bucket,'storage_path':path,'storage_provider':'gcs','url':url,
   'content_identity':mouth_output_identity(job,scene),'ae_mouth_fingerprint':identity,'timing_locked':True,'voice_synced':True,'timing_mode':'final_voice',
   'artifact_ready':True,'ae_reviewed':False,'pipeline_version':2,'preserve_original':True,'mouth_animation':False,'effect_exclusions':exclusions,
   'duration_seconds':duration,'render_sha256':sha,'source_image_id':scene['image']['id'],'source_audio_id':snapshot['audio']['id'],
   'direction':'Verified occluded mouth. Preserve original pixels with actual finalized scene voice.'}
  asset=ae._request('POST',base+'/rest/v1/std_project_assets',{**headers,'Prefer':'return=representation'},json={'project_id':job['project_id'],'scene_number':n,'asset_type':'video','status':'uploaded','file_name':target.name,'mime_type':'video/mp4','file_size':target.stat().st_size,'metadata':metadata}).json()[0]
 receipt={'scene':n,'asset_id':asset['id'],'duration':duration,'sha256':sha,'local_path':str(target),'preserve_original':True};receipts.append(receipt)
 print(json.dumps(receipt),flush=True)
(folder/'preserved-voice-clips.json').write_text(json.dumps(receipts,indent=2),encoding='utf8')
