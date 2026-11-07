#!/usr/bin/env python3
"""Bind reviewed generated mouth PNGs to unchanged source art and recorded dialogue."""
import argparse,copy,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'worker'))
from ae_mouth import decode_scene_audio,amplitude_cues,digest
from ae_media_utils import ffmpeg

def prepare(project,assets,targets,audio_path,output,upload=False):
 payload=project['project_payload'];package=copy.deepcopy(payload['structure']['wuxia_ae_package']);rows=payload['subtitles']
 audio=next(a for a in assets if a['id']==payload['subtitle_source_audio_id'])
 if digest(audio_path)!=audio['metadata']['sha256']:raise ValueError('Saved narration checksum mismatch')
 def compact(s):return re.sub(r'[^\w]','',s)
 receipts=[]
 for target in targets:
  scene=next(s for s in package['scenes'] if int(re.search(r'S(\d+)$',s['scene_id'])[1])==target['scene'])
  state=next(s for s in scene['states'] if s['asset_id']==target['state']);width,height=target['source_size']
  graphs=[g for g in scene['graphics'] if g.get('block_id') in target['blocks'] and g.get('speaker')==target['speaker'] and g.get('state_asset_id')==target['state'] and g['kind']=='speech_bubble']
  if len(graphs)!=len(target['blocks']):raise ValueError('Authored dialogue binding changed')
  bindings=[]
  for g in graphs:
   wanted=compact(g['text']);matched=[r for r in rows if r['scene_number']==target['scene'] and r.get('dialogue_kind')=='dialogue' and compact(r['text']) and compact(r['text']) in wanted]
   if ''.join(compact(r['text']) for r in matched)!=wanted:raise ValueError('Exact dialogue rows missing or ambiguous')
   bindings.extend({'id':r['id'],'text':r['text'],'start':float(r['start_num']),'end':float(r['end_num']),'voice_id':r['voice_id'],'dialogue_speaker':r['dialogue_speaker']} for r in matched)
  for b in bindings:
   index=next(i for i,r in enumerate(rows) if r['id']==b['id']);recorded=audio['metadata']['subtitle_timeline'][index]
   if recorded['text']!=b['text'] or recorded['voice_id']!=b['voice_id'] or abs(recorded['start']-b['start'])>.001 or abs(recorded['end']-b['end'])>.001:raise ValueError('Selected dialogue differs from its actual saved recording')
  sr=[r for r in rows if r['scene_number']==target['scene']];start=min(float(r['start_num']) for r in sr);end=max(float(r['end_num']) for r in sr)
  samples=decode_scene_audio(ffmpeg(),audio_path,start,end-start)
  cues=amplitude_cues(samples,bindings,start=start,duration=end-start)
  for c in cues:c['at_seconds']=round(c['at_seconds']+start,6)
  poses={}
  for pose,f in target['poses'].items():
   path=Path(f['local_path']);sha=digest(path)
   if sha!=f['sha256']:raise ValueError('Reviewed patch changed')
   if upload:
    from ae_highlight_worker import _upload_gcs_file
    bucket,key,url=_upload_gcs_file(path,f'std/{project["id"]}/wuxia-mouth/{state["sha256"]}/{pose}-{sha}.png','image/png')
   else:bucket,key,url='__local__',str(path.resolve()),'/api/std/local-review/'+path.name
   poses[pose]={'sha256':sha,'gcs_bucket':bucket,'gcs_path':key,'media_url':url}
  norm=lambda box:[v/(width if i%2==0 else height) for i,v in enumerate(box)]
  entry={'id':target['id'],'contract':'wuxia_dialogue_mouth/v1','enabled':True,'speaker':target['speaker'],'block_ids':target['blocks'],'source_sha256':state['sha256'],'width':width,'height':height,
   'audio_asset_id':audio['id'],'audio_sha256':audio['metadata']['sha256'],'mouth_box':norm(target['mouth']),'face_box':norm(target['face']),'bindings':bindings,'cues':cues,'poses':poses,
   'review':{'reviewer':'codex_actual_source_and_pose_composites','mouth_fully_visible':True,'face_large_enough':True,'occluded':False,'identity_preserved':True,'evidence':target['reason']},
   'timing_method':'saved_recording_amplitude_gated_three_pose/v1','generation_method':'builtin_imagegen_reviewed_atlas','quality_notes':['Stylized three-pose speech motion; not phoneme-level lip sync.']}
  state['dialogue_mouths']=[m for m in state.get('dialogue_mouths',[]) if m['id']!=entry['id']]+[entry]
  receipts.append({'scene':target['scene'],'state':state['asset_id'],'speaker':target['speaker'],'rows':[b['id'] for b in bindings],'cue_count':len(cues),'source_sha256':state['sha256']})
 output=Path(output);output.mkdir(parents=True,exist_ok=True)
 (output/'wuxia-package-with-mouths.json').write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding='utf-8')
 (output/'mouth-preparation-receipt.json').write_text(json.dumps({'contract':'wuxia_mouth_preparation_receipt/v1','project_id':project['id'],'topic_id':project['topic_queue_id'],'selected':receipts,'uploaded':upload,'audio_sha256':audio['metadata']['sha256'],'zero_eligible_is_valid':True},ensure_ascii=False,indent=2),encoding='utf-8')
 return package,receipts

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('project','assets','targets','audio','output'):p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--upload',action='store_true');a=p.parse_args()
 if a.upload:
  from dotenv import load_dotenv
  load_dotenv(ROOT/'worker/connection.env',override=False)
 package,receipts=prepare(json.loads(a.project.read_text()),json.loads(a.assets.read_text()),json.loads(a.targets.read_text()),a.audio,a.output,a.upload)
 print(json.dumps({'selected_mouths':len(receipts),'uploaded':a.upload,'scenes':[r['scene'] for r in receipts]}))
if __name__=='__main__':main()
