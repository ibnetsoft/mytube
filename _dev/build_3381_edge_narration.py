"""Create a real Japanese narration track and exact subtitle timeline locally."""
import asyncio, hashlib, json, os, re, subprocess, sys, unicodedata
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'.env',override=False)
import requests
from mutagen.mp3 import MP3
import imageio_ffmpeg
from supabase import create_client
from worker.cowork_scene_assets import _download_gcs_bytes,_upload_gcs_file

PROJECT='6b46f709-b4bf-4ccd-ac12-9c8c3981e249';VOICE='Google Translate Japanese';VOICE_ID='google_ja'
BASE=ROOT/'output/codex-local-console/6ae46b7afca84070b36e9e13d7de0a6e/web-package/edge-narration';SEG=BASE/'segments';SEG.mkdir(parents=True,exist_ok=True)
DB=create_client(os.environ['NEXT_PUBLIC_SUPABASE_URL'],os.environ['SUPABASE_SERVICE_ROLE_KEY'])
def speech(v):return re.sub(r'\s+','',unicodedata.normalize('NFKC',str(v or '')))
def h(v):
 if isinstance(v,bytes):raw=v
 elif isinstance(v,str):raw=v.encode()
 else:raw=json.dumps(v,ensure_ascii=False,separators=(',',':')).encode()
 return hashlib.sha256(raw).hexdigest()
async def one(i,text,sem):
 p=SEG/f'{i:04d}.mp3'
 if p.exists() and p.stat().st_size>1000:return p
 for attempt in range(5):
  try:
   def fetch():
    response=requests.get('https://translate.google.com/translate_tts',params={'ie':'UTF-8','client':'tw-ob','tl':'ja','q':text},headers={'User-Agent':'Mozilla/5.0 AIR Studio TTS','Accept':'audio/mpeg,*/*'},timeout=30);response.raise_for_status();p.write_bytes(response.content)
   async with sem: await asyncio.to_thread(fetch)
   if p.stat().st_size>1000:return p
  except Exception:
   if p.exists():p.unlink()
   if attempt==4:raise
   await asyncio.sleep(1.5*(attempt+1))
async def generate(rows):
 sem=asyncio.Semaphore(16);tasks=[asyncio.create_task(one(i,str(r.get('text') or '').strip(),sem)) for i,r in enumerate(rows)]
 done=0
 for task in asyncio.as_completed(tasks):
  await task;done+=1
  if done%25==0:print(f'generated {done}/{len(rows)}',flush=True)
 await asyncio.gather(*tasks)
def main():
 p=DB.table('std_projects').select('*').eq('id',PROJECT).single().execute().data;rows=p['project_payload']['subtitles']
 asyncio.run(generate(rows));parts=[];timeline=[];cursor=0.0
 for i,row in enumerate(rows):
  file=SEG/f'{i:04d}.mp3';duration=float(MP3(file).info.length);start=cursor;end=start+duration;timeline.append({'text':str(row.get('text') or '').strip(),'voice_id':VOICE_ID,'start':start,'end':end});cursor=end;parts.append(file.read_bytes())
 raw=BASE/'std_tts_3381_edge_ja.raw.mp3';raw.write_bytes(b''.join(parts));out=BASE/'std_tts_3381_edge_ja.mp3';subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-v','error','-i',str(raw),'-ac','1','-ar','44100','-b:a','128k',str(out)],check=True);data=out.read_bytes();sha=h(data)
 object_path=f'std/{PROJECT}/tts/{out.name}';bucket,gcs_path,_=_upload_gcs_file(out,object_path,'audio/mpeg');assert h(_download_gcs_bytes(bucket,gcs_path))==sha
 payload=p['project_payload'];new_rows=[]
 for row,t in zip(rows,timeline):new_rows.append({**row,'voice_id':VOICE_ID,'start':t['start'],'end':t['end'],'start_num':t['start'],'end_num':t['end'],'start_time':str(t['start']),'end_time':str(t['end'])})
 payload={**payload,'subtitles':new_rows,'subtitle_source_audio_id':None,'voice_id':VOICE_ID,'tts_provider':'google_free','tts_speed':1,'audio_url':'','tts_url':''}
 script_hash=h(speech(payload.get('script') or ''.join(speech(r.get('text')) for r in new_rows)));subtitle_hash=h(''.join(speech(r.get('text')) for r in new_rows));timeline_rows=[{'text':speech(x['text']),'start':x['start'],'end':x['end'],'voice_id':x['voice_id']} for x in timeline]
 identity={'schema_version':1,'project_id':PROJECT,'topic_queue_id':int(p['topic_queue_id']),'script_revision':f'sha256:{script_hash}','script_sha256':script_hash,'subtitle_text_sha256':subtitle_hash,'asset_type':'audio','scene_id':None,'scene_number':None,'scene_key':None,'visual_sha256':None,'audio_asset_id':None,'timeline_sha256':h(timeline_rows),'parent_asset_ids':[],'generation_job_id':out.name}
 inserted=DB.table('std_project_assets').insert({'project_id':PROJECT,'asset_type':'audio','status':'uploaded','file_name':out.name,'mime_type':'audio/mpeg','file_size':len(data),'metadata':{'kind':'final_narration','storage_provider':'gcs','gcs_bucket':bucket,'gcs_path':gcs_path,'storage_bucket':bucket,'storage_path':gcs_path,'sha256':sha,'provider':'google_free','voice_id':VOICE_ID,'model_id':VOICE,'tts_speed':1,'subtitle_timeline':timeline,'audio_format':'mp3-44100-mono-seekable-v1','duration_seconds':timeline[-1]['end'],'generated_by':'codex','content_identity':identity}}).execute().data[0]
 audio_url=f'/api/std/projects/{PROJECT}/assets/file?assetId={inserted["id"]}';payload.update({'subtitle_source_audio_id':inserted['id'],'audio_url':audio_url,'tts_url':audio_url})
 progress={**(p.get('progress_payload') or {}),'has_tts_audio':True,'tts_generated_at':datetime.now(timezone.utc).isoformat(),'tts_asset_id':inserted['id'],'tts_file_name':out.name,'voice_id':VOICE_ID,'tts_speed':1}
 DB.table('std_projects').update({'project_payload':payload,'progress_payload':progress}).eq('id',PROJECT).execute();DB.table('std_project_assets').update({'status':'replaced'}).eq('project_id',PROJECT).eq('asset_type','audio').neq('id',inserted['id']).in_('status',['uploaded','assigned']).execute()
 receipt={'project_id':PROJECT,'asset_id':inserted['id'],'segments':len(rows),'duration_seconds':timeline[-1]['end'],'sha256':sha,'gcs_bucket':bucket,'gcs_path':gcs_path,'verified':True};(BASE/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
