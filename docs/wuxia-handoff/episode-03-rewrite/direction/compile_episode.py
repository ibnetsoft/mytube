import json,hashlib,math,subprocess
from pathlib import Path
from PIL import Image
P=Path(__file__).resolve().parent.parent;D=P/'direction';ROOT=P.parents[2]
read=lambda p:json.loads(p.read_text());write=lambda p,x:p.write_text(json.dumps(x,ensure_ascii=False,indent=2))
s=read(P/'script-final.json');styles={
'inner_emphasis':{'font':'NotoSansKR-Bold','size':58,'fill':[.97,.97,.91],'stroke':[.05,.09,.13],'stroke_width':3,'entry':'settle','rotation':0,'scale_peak':104},
'inner_reaction':{'font':'DoHyeon-Regular','size':66,'fill':[.98,.97,.92],'stroke':[.07,.11,.16],'stroke_width':4,'entry':'snap','rotation':-5,'scale_peak':110},
'sfx':{'font':'BlackHanSans-Regular','size':104,'fill':[1,.94,.78],'stroke':[.09,.11,.15],'stroke_width':5,'entry':'impact','rotation':-8,'scale_peak':116},
'diegetic_system':{'font':'NotoSansKR-Bold','size':39,'fill':[.67,.97,1],'stroke':[.02,.08,.12],'stroke_width':2,'entry':'reveal','rotation':0,'scale_peak':100}}
weights=[max(16,sum(len(b['text'])for b in sc['blocks'])/8+2)for sc in s['scenes']];scenes=[];inventory=[];reviews=[]
for sc,w in zip(s['scenes'],weights):
 review=read(D/'art-review'/f"{sc['id']}.json");reviews.append(review);length=sum(len(b['text'])for b in sc['blocks']);offset=0;blocks=[]
 for i,b in enumerate(sc['blocks'],1):blocks.append({**b,'block_id':f"{sc['id']}_B{i:02d}",'preview_start':offset/length,'preview_end':(offset+len(b['text']))/length});offset+=len(b['text'])
 cuts=sorted(review['state_cuts'],key=lambda x:x['state_index']);assert len(cuts)==len(sc['visual_states'])
 starts=[]
 for i,cut in enumerate(cuts):
  matches=[b for b in blocks if cut['exact_anchor'] in b['text']];assert len(matches)==1,(sc['id'],cut);b=matches[0];cut['block_index']=blocks.index(b)+1;starts.append(0 if i==0 else b['preview_start']+b['text'].index(cut['exact_anchor'])/length)
 assert all(a<b for a,b in zip(starts,starts[1:])),(sc['id'],starts)
 states=[]
 for i,(desc,r)in enumerate(zip(sc['visual_states'],review['states']),1):
  aid=f"{sc['id']}_STATE_{i:02d}";path=P/'images'/f'{aid}.png';assert r['asset_id']==aid
  with Image.open(path)as im:width,height=im.size;im.verify()
  boxes=r['head_boxes'];assert all(len(b)==4 and 0<=b[0]<b[2]<=1 and 0<=b[1]<b[3]<=1 for b in boxes),(aid,boxes)
  state={'asset_id':aid,'file':f'images/{aid}.png','width':width,'height':height,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'description':desc,'start':starts[i-1],'end':starts[i]if i<len(starts)else 1,'camera':'hold','static_crop':None,'source_review':'reviewed_with_quality_notes','face_exclusion_boxes':boxes,'speaker_mouths':r.get('speaker_mouths',{}),'face_review':'actual stored source pixels inspected by local Codex vision; conservative head boxes','voice_binding':{'block_id':blocks[cuts[i-1]['block_index']-1]['block_id'],'exact_anchor':cuts[i-1]['exact_anchor']},'quality_notes':r.get('quality_notes',[])}
  states.append(state);inventory.append({'asset_id':aid,'scene_id':sc['id'],'state_index':i,'file':state['file'],'sha256':state['sha256'],'exists':True})
 graphics=[]
 for b in blocks:
  if b['kind']!='dialogue':continue
  # Bubble type follows delivery: whispers in hiding, impact shouts only for actual exclamations.
  n=int(sc['id'][-2:]);preset='whisper'if n<=5 else('shout'if '!'in b['text']or '！'in b['text']else 'dialogue')
  for st in states:
   start=max(b['preview_start'],st['start']);end=min(b['preview_end'],st['end'])
   if end<=start:continue
   graphics.append({'kind':'speech_bubble','bubble_style':preset,'block_id':b['block_id'],'speaker':b['speaker'],'text':b['text'],'state_asset_id':st['asset_id'],'preview_start':start,'preview_end':end,'voice_binding':{'block_id':b['block_id'],'exact_anchor':b['text']},'style':{'font':'NotoSansKR-Bold','size':38,'fill':[.08,.1,.13],'entry':'settle','rotation':0,'scale_peak':100}})
 for cue in sc.get('screen_text',[]):
  b=next(b for b in blocks if cue['anchor']in b['text']);anchor=b['preview_start']+b['text'].index(cue['anchor'])/length;st=next(x for x in states if x['start']<=anchor<x['end']);kind=cue['kind'];kind={'reaction':'inner_reaction','thought':'inner_emphasis','system':'diegetic_system'}.get(kind,kind)
  assert kind in styles,(sc['id'],kind)
  graphics.append({'kind':kind,'text':cue['text'],'state_asset_id':st['asset_id'],'preview_start':anchor,'preview_end':min(st['end'],max(anchor+.025,b['preview_end'])),'voice_binding':{'block_id':b['block_id'],'exact_anchor':cue['anchor']},'style':dict(styles[kind]),'intent':cue['treatment']})
 scenes.append({'scene_id':sc['id'],'intent':sc['ae'],'states':states,'blocks':blocks,'graphics':graphics,'effects':[],'preview_duration_seconds':round(600*w/sum(weights),3),'timing_basis':'normalized_preview_not_recorded_speech','transition':'cut','camera_policy':'fixed_no_slow_zoom','fake_depth':False})
write(D/'ae-scene-package.json',{'contract':'wuxia_still_ae_episode/v1','episode':3,'width':1920,'height':1080,'fps':24,'script_sha256':hashlib.sha256((P/'script-final.json').read_bytes()).hexdigest(),'scenes':scenes,'video_clip_count':0,'narration_verbatim_captions':False,'all_text_editable':True,'timing':'Provisional preview; exact quote anchors bind final recorded speech.','ae_execution_verified':False})
write(P/'image-inventory.json',inventory)
write(D/'visual-reviews.json',{'source':'actual local Codex vision image reviews','scene_reviews':reviews,'face_registry':read(D/'face-review-v3/quality-notes.json'),'quality_notes_preserved':True,'no_blanket_visual_pass':True})
write(D/'sound-and-music-direction.json',{'music_generation':'prompt_only','mix_direction':'발화와 낮은 숨을 우선하며 음악은 얇게 유지. 검문에서 말하기 직전 여백.','music':[{'scenes':[1,2,3,4,5],'prompt':'Original instrumental wuxia restrained suspense, sparse low bowed strings and distant wooden ticks, breathing space for whispered Korean dialogue, no vocals or heroic victory.'},{'scenes':[6,7,8,9,10,11,12],'prompt':'Original instrumental wuxia human danger, dry wooden percussion, short tense low strings, silent gaps around impacts and timber drop, no triumphant fanfare.'},{'scenes':[13,14,15,16,17,18],'prompt':'Original instrumental wuxia wounded survivors outdoors, sparse xiao and low strings, fragile human warmth, restrained pulse, no healed hero victory.'},{'scenes':[19,20],'prompt':'Original instrumental wuxia public checkpoint tension, suspended low strings, thinning to silence before survivor speaks, unresolved ending.'}],'scenes':[{'scene_id':sc['id'],'direction':sc['ae'],'ambient':'외부 바람·바퀴·주변 군중'if int(sc['id'][-2:])>=13 else'해당 동작의 숨·옷감·쇠·목재 소리, 사무실은 종이와 붓','status':'direction_only'}for sc in s['scenes']]})
subprocess.run(['node',str(D/'place_graphics.cjs')],check=True,cwd=ROOT)
print('COMPILED',len(scenes),len(inventory))
