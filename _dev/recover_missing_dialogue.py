import sys,json,copy,hashlib,os,requests
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
import worker_config
from script_worker_store import ScriptStore
from codex_content_runner import CodexStagedContentRunner
class RecoveryStore(ScriptStore):
 def request(self,method,table,*,params=None,body=None,prefer='count=exact'):
  url=(os.getenv('NEXT_PUBLIC_SUPABASE_URL') or os.getenv('SUPABASE_URL')).rstrip('/')
  key=os.environ['SUPABASE_SERVICE_ROLE_KEY']
  response=requests.request(method,url+'/rest/v1/'+table,params=params,json=body,headers={'apikey':key,'Authorization':'Bearer '+key,'Prefer':prefer},timeout=(30,180))
  response.raise_for_status()
  return (response.json() if response.content else []),None
store=RecoveryStore();pid='e9233112-f0d7-4b35-91bf-2f892844eb30'
def get():return store.request('GET','std_projects',params={'select':'*','id':'eq.'+pid})[0][0]
p=get();payload=p['project_payload'];original=payload['subtitles'];pending=[r for r in original if r.get('restored_audio_pending')]
voices={r['dialogue_speaker']:{'voice_id':r['voice_id'],'voice_name':r.get('voice_name','')} for r in original if not r.get('restored_audio_pending') and r.get('dialogue_speaker') and r.get('voice_id')}
narrator=next(r for r in original if not r.get('restored_audio_pending') and r.get('dialogue_kind')=='narration')
identity=hashlib.sha256(json.dumps([(r['id'],r['text']) for r in pending],ensure_ascii=False).encode()).hexdigest()
result=CodexStagedContentRunner()._stage(identity,'01_missing_scene_dialogue_recovery',{'cast':payload.get('structure',{}).get('scene_cast',[]),'known_speakers':list(voices),'scenes':payload.get('structure',{}).get('scenes',[]),'rows':[{'id':r['id'],'text':r['text'],'scene_number':r['scene_number']} for r in pending]},'Classify recovered Japanese story subtitles in full scene context. Return {rows:[{id:exact input ID,parts:[{text:exact consecutive substring of original input text,kind:"narration|dialogue",speaker:exact known_speakers name for dialogue or empty for narration}]}]}. Preserve all IDs, order, punctuation and every character; concatenate parts to exactly reproduce each original row. Split mixed narration and speech at their exact boundaries. Only actual spoken words animate a character; internal thoughts, letters and quoted writing are narration. Resolve each speaker from story context, not quotation marks alone. If speaker is ambiguous return kind="uncertain",speaker=""; never guess. Do not generate translations or rewrite the story.')
rows=result.get('rows',[]);assert len(rows)==len(pending)
by={r['id']:r for r in rows};assert len(by)==len(pending)
new=[];uncertain=[]
for r in original:
 if not r.get('restored_audio_pending'):new.append(r);continue
 parts=by[r['id']]['parts'];assert ''.join(x['text'] for x in parts)==r['text']
 for i,part in enumerate(parts):
  kind=part['kind'];assert kind in ['narration','dialogue','uncertain']
  if kind=='uncertain':uncertain.append(r['id'])
  voice=voices.get(part.get('speaker')) if kind=='dialogue' else narrator
  assert voice or kind=='uncertain'
  x={**r,'id':r['id']+f'-part-{i+1}','text':part['text'],'dialogue_kind':kind,'dialogue_speaker':part.get('speaker','') if kind=='dialogue' else '', 'voice_id':voice['voice_id'] if voice else narrator['voice_id'],'voice_name':voice.get('voice_name','') if voice else narrator.get('voice_name',''),'voice_assignment_pending':kind=='uncertain'}
  new.append(x)
(ROOT/'_dev/artifacts/missing_dialogue_classified_rows.json').write_text(json.dumps(new,ensure_ascii=False),encoding='utf-8')
latest=get();assert latest['project_payload']['subtitles']==original,'Subtitles changed while classifying; no overwrite'
updated={**latest['project_payload'],'subtitles':new};res=store.request('PATCH','std_projects',params={'id':'eq.'+pid,'updated_at':'eq.'+latest['updated_at']},body={'project_payload':updated,'updated_at':datetime.now(timezone.utc).isoformat()},prefer='return=representation')[0];assert len(res)==1
assert get()['project_payload']['subtitles']==new,'Read-back verification failed'
print(json.dumps({'rows':len(new),'classified_recovered_rows':len(pending),'uncertain':uncertain}),flush=True)
