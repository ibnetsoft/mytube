import json,hashlib,html,importlib.util
from pathlib import Path
from PIL import Image
P=Path(__file__).resolve().parent.parent;D=P/'direction'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
src=importlib.util.spec_from_file_location('styles',P.parent/'episode-01/direction/compile_direction.py');styles=importlib.util.module_from_spec(src);src.loader.exec_module(styles)
SPEECH={1:{2:2},2:{2:2},3:{2:1},5:{2:2},6:{2:1},7:{2:2},8:{2:2},9:{2:2},10:{2:1},11:{2:1},13:{2:2},14:{2:2},15:{2:1,3:2},16:{2:1},19:{2:1},20:{2:2},21:{2:1},22:{2:1,3:1},24:{2:1}}
FX={1:[('focus_glow',1,[.7,.55],'돌아오던 손목이 덜컥 멎었습니다.')],2:[('impact_flash',1,[.55,.55],'어깨가 내려오자 얇은 칼날부터 휘었습니다.')],
 7:[('focus_glow',2,[.5,.65],'판 아래가 벌어졌습니다.')],9:[('impact_shake',1,[.45,.65],'돌검이 홈 입구를 찍었습니다.')],
 11:[('impact_shake',2,[.5,.65],'돌검이 놓였습니다.')],13:[('debris_burst',1,[.5,.55],'젖은 나무껍질이 벗겨졌습니다.')],
 14:[('speedline_burst',2,[.4,.6],'이번에는 제 발로 멈춰 섰습니다.')],18:[('speedline_burst',2,[.5,.55],'칼끝에 겉옷 끝이 찢겼습니다.')],
 21:[('impact_shake',2,[.5,.4],'위에서 둔한 소리가 울렸습니다.') ]}
s=read(P/'script-final.json');layout=read(D/'visual-layout.json') if (D/'visual-layout.json').exists() else {}
chars=[sum(len(b['text'])for b in x['blocks'])for x in s['scenes']];weights=[max(15,c/8+2)for c in chars];total=sum(weights);scenes=[];inventory=[]
for n,(sc,w) in enumerate(zip(s['scenes'],weights),1):
 states=[]
 for i,desc in enumerate(sc['visual_states'],1):
  asset=f"{sc['id']}_STATE_{i:02d}";path=P/'images'/(asset+'.png')
  with Image.open(path) as im:width,height=im.size;im.verify()
  slot=layout.get(asset,{})
  states.append({'asset_id':asset,'file':'images/'+path.name,'width':width,'height':height,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
   'description':desc,'start':(i-1)/len(sc['visual_states']),'end':i/len(sc['visual_states']),'camera':'hold','static_crop':slot.get('static_crop'),
   'source_review':slot.get('review','pending')})
 inventory.extend({'asset_id':st['asset_id'],'scene_id':sc['id'],'state_index':i+1,'description':st['description'],'file':st['file'],'exists':True,'sha256':st['sha256']}for i,st in enumerate(states))
 blocks=[];offset=0;length=sum(len(b['text'])for b in sc['blocks'])
 for i,b in enumerate(sc['blocks'],1):
  blocks.append({**b,'block_id':f"{sc['id']}_B{i:02d}",'preview_start':offset/length,'preview_end':(offset+len(b['text']))/length});offset+=len(b['text'])
 groups={}
 for i,b in enumerate(blocks,1):
  if b['kind']=='dialogue':groups.setdefault(SPEECH[n][i],[]).append(b)
 graphics=[]
 for idx,group in groups.items():
  state=states[idx-1];span=state['end']-state['start']
  for i,b in enumerate(group):
   slot=layout.get(state['asset_id'],{}).get('dialogue_slots',{}).get(b['speaker'],{'center':[.5,.13],'size':[.36,.22],'tail':[.30,.35],'placement_review':'pending'})
   graphics.append({'kind':'speech_bubble','block_id':b['block_id'],'speaker':b['speaker'],'text':b['text'],'state_asset_id':state['asset_id'],
    'preview_start':state['start']+span*(.06+.88*i/len(group)),'preview_end':state['start']+span*(.06+.88*(i+1)/len(group)),
    'voice_binding':{'block_id':b['block_id']},'layout':slot,'style':{'font':'NotoSansKR-Bold','size':38,'fill':[.08,.1,.13],'entry':'settle'}})
 for cue in sc['screen_text']:
  found=[b for b in blocks if cue['anchor'] in b['text']];assert len(found)==1,(sc['id'],cue)
  state=states[cue['state_index']-1];span=state['end']-state['start'];same=[g for g in graphics if g['state_asset_id']==state['asset_id']]
  for g in same:g['preview_end']=min(g['preview_end'],state['start']+span*.68)
  at=state['start']+span*(.75 if same else .22)
  graphics.append({'kind':cue['kind'],'text':cue['text'],'state_asset_id':state['asset_id'],'preview_start':at,'preview_end':min(state['end']-.01,at+span*.45),
   'voice_binding':{'block_id':found[0]['block_id'],'exact_anchor':cue['anchor']},'layout':layout.get(state['asset_id'],{}).get('typography_slot',{'center':[.76,.20],'size':[.36,.22],'placement_review':'pending'}),
   'style':styles.TYPE_STYLES[cue['kind']],'intent':cue['treatment']})
 effects=[];text='\n'.join(b['text']for b in sc['blocks'])
 for typ,idx,center,quote in FX.get(n,[]):
  assert quote in text,(n,quote)
  st=states[idx-1];effects.append({'type':typ,'state':idx,'asset_id':st['asset_id'],'center':center,'radius':.12,'intensity':.16,'preview_at':st['start']+.04,
   'duration_seconds':.32 if typ!='focus_glow' else .65,'voice_binding':{'exact_anchor':quote,'phase':'during'},'source_review':st['source_review']})
 scenes.append({'scene_id':sc['id'],'intent':sc['ae'],'states':states,'blocks':blocks,'graphics':graphics,'effects':effects,
  'preview_duration_seconds':round(600*w/total,3),'timing_basis':'normalized_preview_not_recorded_speech','transition':'cut','camera_policy':'fixed_no_slow_zoom','fake_depth':False})
cfg={'contract':'wuxia_still_ae_episode/v1','episode':2,'width':1920,'height':1080,'fps':24,'script_sha256':hashlib.sha256((P/'script-final.json').read_bytes()).hexdigest(),
 'scenes':scenes,'video_clip_count':0,'narration_verbatim_captions':False,'all_text_editable':True,'timing':'Provisional preview only. Bind source quote/block anchors to actual recording.','ae_execution_verified':False}
write(D/'ae-scene-package.json',cfg);write(P/'image-inventory.json',inventory)
count=sum(len(x['graphics'])for x in scenes)
write(D/'source-verification.json',{'actual_unique_pngs':len(inventory),'scenes':len(scenes),'editable_graphics':count,'source_reviews_complete':all(st['source_review']!='pending'for sc in scenes for st in sc['states']),
 'placements_complete':all(g['layout']['placement_review']!='pending'for sc in scenes for g in sc['graphics']),'video_clips':0,'actual_audio_sync_verified':False,'ae_execution_verified':False})
cards=[]
for sc in s['scenes']:
 art=''.join(f'<figure><a href="../{st["file"]}"><img loading="lazy" src="../{st["file"]}"></a><figcaption>{html.escape(st["asset_id"]+" · "+st["description"])}</figcaption></figure>' for st in next(x['states']for x in scenes if x['scene_id']==sc['id']))
 cards.append(f'<section><h2>{sc["id"]} · {html.escape(sc["location"])}</h2><div class="grid">{art}</div><p>{html.escape(sc["ae"])}</p></section>')
cast=''.join(f'<figure><img src="../character-sheets/{c["id"]}-v1.png"><figcaption>{c["name"]}</figcaption></figure>'for c in s['cast'])
(D/'storyboard.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>돌아오는 검 · 원화</title><style>body{background:#111b26;color:#eef5f8;font:15px/1.7 system-ui;margin:24px auto;max-width:1500px;padding:20px}a{color:#7de0d3}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:16px}figure{margin:0}img{width:100%}figcaption{font-size:12px;color:#aabed0}section{border-top:1px solid #354658;margin-top:30px;padding-top:12px}</style><h1>2화 「돌아오는 검」</h1><p>24장면 · 실제 원화 48컷 · 영상클립 0</p><a href="motion-preview.html">장면 연출 미리보기</a><section><h2>같은 연작의 캐릭터 기준</h2><div class="grid">'+cast+'</div></section>'+''.join(cards),encoding='utf-8')
print(json.dumps({'scenes':len(scenes),'stills':len(inventory),'editable_graphics':count}))
