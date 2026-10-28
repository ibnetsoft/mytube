"""Attach only verified cached voice artifacts to completed preview-job receipts."""
import sys,json,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'worker'),str(ROOT)]
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
import ae_highlight_worker as ae
from ae_mouth_worker import PREVIEW_PROJECT_SELECT,preview_project_context,input_matches
from std_project_assets import load_project_input_assets
base,headers=ae._supabase();jobs={3376:'0db3979f-cded-4f78-899d-687123bffb87',3377:'9159c849-ebbf-4d5a-8429-d25b397cca50'}
for topic,job_id in jobs.items():
 if len(sys.argv)>1 and str(topic)!=sys.argv[1]:continue
 assert '--reviewed' in sys.argv,'Inspect actual voice-frame montage before sealing'
 folder=ROOT/f'output/codex-local-console/two-topic-mouths/{topic}/final-voice';qa=json.loads((folder/'qa/actual-voice-qa.json').read_text(encoding='utf8'))
 job=ae._request('GET',base+'/rest/v1/std_project_assets',headers,params={'select':'*','id':'eq.'+job_id}).json()[0];meta=job['metadata'];snapshot=meta['input']
 assert meta.get('preview_sync') and meta['state']=='artifact_ready' and not meta.get('auto_pending')
 expected=snapshot['mouth_work_scene_numbers'];assert len(expected)==10 and set(map(int,qa))==set(expected)
 assets=ae._request('GET',base+'/rest/v1/std_project_assets',headers,params={'select':'*','project_id':'eq.'+job['project_id'],'asset_type':'eq.video','status':'in.(uploaded,assigned)','metadata->>ae_mouth_fingerprint':'eq.'+meta['fingerprint'],'order':'created_at.desc,id.desc'}).json()
 by_number={}
 for asset in assets:by_number.setdefault(asset['scene_number'],asset)
 assert set(by_number)==set(expected)
 project=preview_project_context(ae._request('GET',base+'/rest/v1/std_projects',headers,params={'select':PREVIEW_PROJECT_SELECT,'id':'eq.'+job['project_id']}).json()[0])
 current_assets=load_project_input_assets(ae._request,base,headers,job['project_id'])
 scenes=ae._request('GET',base+'/rest/v1/std_project_scenes',headers,params={'select':'scene_number,scene_text,image_prompt','project_id':'eq.'+job['project_id'],'order':'scene_number.asc'}).json()
 assert input_matches(snapshot,project,current_assets,scenes),'Current voice/source no longer matches the reviewed clips'
 rows=[];delivery=[]
 for scene in snapshot['scenes']:
  n=scene['number'];asset=by_number[n];m=asset['metadata'];q=qa[str(n)]
  assert q['decoded'] and q['voice_correlation']>.92 and q['sha256']==m['render_sha256']
  assert m['source_audio_id']==snapshot['audio']['id'] and m['source_image_id']==scene['image']['id'] and m['voice_synced']
  assert abs(m['duration_seconds']-(scene['end']-scene['start']))<.12
  rows.append({'number':n,'status':'artifact_ready','asset_id':asset['id'],'duration':m['duration_seconds'],'render_sha256':m['render_sha256'],
    'preserve_original':bool(m.get('preserve_original')),'effect_exclusions':m.get('effect_exclusions',[]),'recording_verified':True})
  delivery.append({'scene':n,'asset_id':asset['id'],'duration':m['duration_seconds'],'voice_correlation':q['voice_correlation'],'preserve_original':bool(m.get('preserve_original')),'gcs_path':m['gcs_path']})
 final={**meta,'results':rows,'error':'','phase':'complete','auto_pending':False,'actual_voice_verified':{'at':ae._now(),'scope':expected,'audio_id':snapshot['audio']['id'],'clips':10,'source_and_actual_frames_reviewed':True}}
 result=ae._request('PATCH',base+'/rest/v1/std_project_assets',{**headers,'Prefer':'return=representation'},params={'id':'eq.'+job_id,'updated_at':'eq.'+job['updated_at']},json={'metadata':final,'updated_at':ae._now()}).json()
 assert len(result)==1,'Preview job changed during final verification'
 (folder/'actual-voice-delivery.json').write_text(json.dumps({'topic':topic,'job_id':job_id,'audio_id':snapshot['audio']['id'],'scenes':delivery},ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({'topic':topic,'actual_voice_clips':10,'preserved_scenes':[r['scene'] for r in delivery if r['preserve_original']],'sealed':True}),flush=True)
