"""Submitted, frozen ElevenLabs SFX prompts -> durable assets -> bounded mix cues.
No provider request occurs during authoring. Keep successful audio across render retries.
"""
from pathlib import Path
import hashlib,json,math,os,re,subprocess,uuid,wave
import requests
CONTRACT='elevenlabs_sfx_frozen/v1'
MODEL='eleven_text_to_sound_v2'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
 path=Path(path);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8');tmp.replace(path)
def validate(plan):
 if not plan:return []
 if plan.get('contract')!=CONTRACT or not re.fullmatch(r'[0-9a-fA-F-]{36}',str(plan.get('project_id',''))) or not isinstance(plan.get('cues'),list) or len(plan['cues'])>120:raise ValueError('Invalid frozen sound-effect plan')
 seen=set()
 for c in plan['cues']:
  if not isinstance(c.get('id'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',c['id']) or c['id'] in seen or not isinstance(c.get('prompt'),str) or not 1<=len(c['prompt'].strip())<=2000:raise ValueError('Invalid sound-effect cue')
  seen.add(c['id'])
  for key in ('duration_seconds','offset_seconds','volume_db','start','end'):
   if type(c.get(key)) not in (int,float) or not math.isfinite(c[key]):raise ValueError('Invalid sound-effect timing')
  if not .5<=c['duration_seconds']<=30 or not -60<=c['volume_db']<=0 or c['offset_seconds']<0 or c['start']<0 or c['end']<=c['start'] or type(c.get('scene_number')) is not int or c['scene_number']<1:raise ValueError('Sound effect exceeds recorded scene')
 return plan['cues']
def generate(cue,raw,ticket):
 if raw.exists():return
 if ticket.exists():raise RuntimeError('Previous ElevenLabs request has an unknown result; retain request receipt and reconcile before resending')
 key=os.getenv('ELEVENLABS_API_KEY')
 if not key:
  from config import Config
  key=Config.ELEVENLABS_API_KEY
 if not key:raise RuntimeError('ElevenLabs API key is not configured on this integrated worker')
 save(ticket,{'state':'requesting','cue_id':cue['id'],'model':MODEL})
 try:r=requests.post('https://api.elevenlabs.io/v1/sound-generation',headers={'xi-api-key':key,'Content-Type':'application/json'},json={'text':cue['prompt'],'duration_seconds':cue['duration_seconds'],'model_id':MODEL,'loop':False},timeout=(10,120))
 except requests.RequestException as exc:raise RuntimeError('ElevenLabs request outcome unknown; preserved request receipt') from exc
 if r.status_code in (400,401,403,422,429):ticket.unlink(missing_ok=True)
 if not r.ok:raise RuntimeError('ElevenLabs sound generation HTTP '+str(r.status_code))
 if not r.content or len(r.content)>20_000_000:raise RuntimeError('Invalid ElevenLabs audio response')
 tmp=raw.with_suffix('.tmp');tmp.write_bytes(r.content);tmp.replace(raw);ticket.unlink(missing_ok=True)
def decode(raw,clean):
 from worker.ae_media_utils import ffmpeg,run
 temp=clean.with_suffix('.decode.wav')
 run([ffmpeg(),'-y','-v','error','-i',str(raw),'-vn','-af','silenceremove=start_periods=1:start_duration=0.005:start_threshold=-50dB','-ac','1','-ar','48000','-c:a','pcm_s16le',str(temp)])
 with wave.open(str(temp),'rb') as wav:duration=wav.getnframes()/wav.getframerate()
 if not .02<=duration<=31:raise ValueError('Generated sound is silent, corrupt or outside duration limits')
 temp.replace(clean);return duration
def ensure(plan,directory,*,ae=None,base=None,headers=None,fresh=None,existing=()):
 cues=validate(plan)
 if not cues:return []
 if ae is None:
  import sys
  worker_path=str(Path(__file__).resolve().parent)
  if worker_path not in sys.path:sys.path.insert(0,worker_path)
  import ae_highlight_worker as ae
 if base is None:base,headers=ae._supabase()
 if fresh is None:
  def fresh():
   rows=ae._request('GET',base+'/rest/v1/std_projects',headers,params={'id':'eq.'+plan['project_id'],'select':'status,submitted_at'}).json()
   from worker.workflow_roles import assert_project,POSTPRODUCTION
   if len(rows)!=1:raise ValueError('Submitted project missing')
   assert_project(rows[0],POSTPRODUCTION)
 root=Path(directory)/'generated-sfx';root.mkdir(parents=True,exist_ok=True);result=[];receipts=[]
 suppressed={str(c.get('generated_sfx_id') or c.get('id')) for c in existing}
 for cue in cues:
  if cue['id'] in suppressed:continue
  fresh()
  fingerprint=hashlib.sha256(json.dumps([MODEL,cue['prompt'],cue['duration_seconds']],ensure_ascii=False).encode()).hexdigest()
  asset_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'generated-sfx:'+plan['project_id']+':'+fingerprint))
  clean=root/(fingerprint+'.wav');raw=root/(fingerprint+'.raw');receipt=root/(fingerprint+'.json');ticket=root/(fingerprint+'.request.json')
  rows=ae._request('GET',base+'/rest/v1/std_project_assets',headers,params={'id':'eq.'+asset_id,'project_id':'eq.'+plan['project_id'],'select':'id,metadata,status'}).json()
  if rows:
   meta=rows[0]['metadata']
   if rows[0]['status'] not in ('uploaded','assigned') or meta.get('kind')!='generated_sfx' or meta.get('fingerprint')!=fingerprint:raise ValueError('Stored sound-effect identity mismatch')
   if not clean.exists() or sha(clean)!=meta['sha256']:
    fresh();ae._download_gcs_file(ae.GcsRef(meta['gcs_bucket'],meta['gcs_path']),clean)
   if sha(clean)!=meta['sha256']:raise ValueError('Stored sound-effect checksum mismatch')
   with wave.open(str(clean),'rb') as wav:duration=wav.getnframes()/wav.getframerate()
   if not .02<=duration<=31:raise ValueError('Stored sound-effect duration invalid')
  else:
   if clean.exists() and receipt.exists():
    cached=json.loads(receipt.read_text());duration=cached['duration_seconds']
    if sha(clean)!=cached['sha256']:raise ValueError('Cached sound-effect changed')
   else:
    fresh();generate(cue,raw,ticket);fresh();duration=decode(raw,clean)
    save(receipt,{'sha256':sha(clean),'duration_seconds':duration})
   fresh();bucket,key,_=ae._upload_gcs_file(clean,'generated-sfx/'+plan['project_id']+'/'+fingerprint+'.wav','audio/wav')
   verify=root/(fingerprint+'.verify.wav');ae._download_gcs_file(ae.GcsRef(bucket,key),verify)
   if sha(verify)!=sha(clean):raise ValueError('Uploaded sound-effect checksum mismatch')
   verify.unlink();meta={'kind':'generated_sfx','audio_role':'sfx','workflow_stage':'postproduction','fingerprint':fingerprint,'provider':'elevenlabs','model_id':MODEL,'prompt':cue['prompt'],'duration_seconds':duration,'sha256':sha(clean),'gcs_bucket':bucket,'gcs_path':key,'storage_provider':'gcs'}
   fresh();ae._request('POST',base+'/rest/v1/std_project_assets',{**headers,'Prefer':'resolution=merge-duplicates'},params={'on_conflict':'id'},json={'id':asset_id,'project_id':plan['project_id'],'scene_number':cue['scene_number'],'asset_type':'other','status':'uploaded','file_name':fingerprint+'.wav','mime_type':'audio/wav','file_size':clean.stat().st_size,'metadata':meta})
  verified=ae._request('GET',base+'/rest/v1/std_project_assets',headers,params={'id':'eq.'+asset_id,'project_id':'eq.'+plan['project_id'],'select':'id,metadata,status'}).json()
  if len(verified)!=1 or verified[0]['metadata'].get('sha256')!=sha(clean):raise ValueError('Sound asset database readback failed')
  fresh();mix={'id':cue['id'],'generated_sfx_id':cue['id'],'asset_id':asset_id,'scene_number':cue['scene_number'],'cut_id':cue['cut_id'],'path':str(clean.resolve()),'start':cue['start'],'duration':min(duration,cue['duration_seconds'],cue['end']-cue['start']),'volume_db':cue['volume_db'],'source':'elevenlabs-postsubmission-v1','enabled':True}
  result.append(mix);receipts.append({**mix,'sha256':sha(clean),'fingerprint':fingerprint})
 placement={'contract':CONTRACT,'project_id':plan['project_id'],'cues':[{k:v for k,v in c.items() if k!='path'} for c in receipts]}
 save(root/'placement-receipt.json',placement)
 placement_hash=hashlib.sha256(json.dumps(placement,sort_keys=True).encode()).hexdigest()
 fresh();bucket,key,_=ae._upload_gcs_file(root/'placement-receipt.json','generated-sfx/'+plan['project_id']+'/placements/'+placement_hash+'.json','application/json')
 ae._request('POST',base+'/rest/v1/std_project_assets',{**headers,'Prefer':'resolution=merge-duplicates'},params={'on_conflict':'id'},json={'id':str(uuid.uuid5(uuid.NAMESPACE_URL,'sfx-placement:'+plan['project_id']+':'+placement_hash)),'project_id':plan['project_id'],'asset_type':'other','status':'uploaded','file_name':'generated-sfx-placement.json','mime_type':'application/json','metadata':{'kind':'generated_sfx_placement','workflow_stage':'postproduction','gcs_bucket':bucket,'gcs_path':key,'sha256':sha(root/'placement-receipt.json'),'cue_bindings':placement['cues']}})
 return result
