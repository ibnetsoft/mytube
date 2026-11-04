"""Compile actual still files, editable graphics and voice-bindable AE directions."""
import hashlib
import json
from pathlib import Path

P = Path(__file__).resolve().parent.parent
D = P / 'direction'

SPLITS = [
 [.33,.20,.47],[.28,.26,.46],[.32,.42,.26],[.28,.35,.37],[.27,.32,.41],[.34,.30,.36],
 [.33,.31,.36],[.35,.24,.41],[.28,.35,.37],[.32,.38,.30],[.28,.30,.42],[.31,.37,.32],
 [.35,.35,.30],[.32,.31,.37],[.33,.29,.38],[.31,.39,.30],[.32,.30,.38],[.34,.28,.38],
 [.22,.19,.25,.34],[.31,.27,.42],[.31,.38,.31],[.27,.36,.37],[.30,.30,.40],
 [.34,.27,.39],[.33,.29,.38],[.25,.34,.41]
]

# Semantic cut order is authored, not inferred from image filenames.
ORDERS = {9:[1,3,2],10:[2,1,3]}
SPLITS[8]=[.25,.30,.45]
SPLITS[12]=[.17,.48,.35]
STATIC_CROPS = {'E01_S04_STATE_02':[.14,.60,.85,1.0], 'E01_S07_STATE_03':[.79,.30,1,.65],
                'E01_S13_STATE_01':[.40,.30,1,.90], 'E01_S15_STATE_02':[.40,.05,1,.93]}

# Semantic assignments supersede character-count guesses. These are editorial
# preview timings; exact block/quote bindings remain for the recorded voice.
DIALOGUE_STATES={1:{2:3},2:{2:1,3:2,4:3,5:3},3:{2:2,3:3},5:{2:2},6:{2:3,3:3},7:{2:1},
 8:{2:1,3:3,4:3},9:{2:2},10:{1:2,3:3},11:{1:1,3:3},13:{1:1,2:2},14:{2:2},
 15:{2:3,3:3,4:3},16:{2:1,3:2},18:{1:1},19:{1:1,3:4,4:4},20:{2:3},22:{2:3},
 24:{1:1},25:{2:3},26:{1:1}}
TYPE_STATES={4:[3],8:[2],9:[2],10:[1],11:[3],13:[3],14:[3],16:[3],19:[4],20:[2],
             22:[2],23:[2],25:[2],26:[2,3]}

# These presets determine typography behavior; actual placement can be overridden
# per asset by visual-layout.json after inspecting the original source image.
TYPE_STYLES = {
 'inner_emphasis':{'font':'NotoSansKR-Bold','size':58,'fill':[.97,.97,.91],'stroke':[.05,.09,.13],'stroke_width':3,'entry':'settle','rotation':0,'scale_peak':104},
 'inner_reaction':{'font':'DoHyeon-Regular','size':66,'fill':[.98,.97,.92],'stroke':[.07,.11,.16],'stroke_width':4,'entry':'snap','rotation':-5,'scale_peak':110},
 'sfx':{'font':'BlackHanSans-Regular','size':104,'fill':[1,.94,.78],'stroke':[.09,.11,.15],'stroke_width':5,'entry':'impact','rotation':-8,'scale_peak':116},
 'voiced_reaction':{'font':'DoHyeon-Regular','size':66,'fill':[.98,.97,.92],'stroke':[.07,.11,.16],'stroke_width':4,'entry':'snap','rotation':-5,'scale_peak':110},
 'diegetic_system':{'font':'NotoSansKR-Bold','size':39,'fill':[.67,.97,1],'stroke':[.02,.08,.12],'stroke_width':2,'entry':'reveal','rotation':0,'scale_peak':100},
 'inner_climax':{'font':'BlackHanSans-Regular','size':136,'fill':[.99,.98,.90],'stroke':[.02,.13,.18],'stroke_width':6,'entry':'impact','rotation':-8,'scale_peak':108}
}

# One authored attention/impact location per dramatic event. Coordinates are
# normalized to the inspected frame, not guessed face tracking or generated audio.
FX = {
 9:[{'type':'focus_glow','state':2,'center':[.59,.82],'radius':.09,'intensity':.12,'quote':'봉함 밑으로 이어진 가느다란 돌못이 빠지는 것을 서진이 보았습니다.'}],
 10:[{'type':'impact_flash','state':1,'center':[.76,.21],'radius':.10,'intensity':.20,'quote':'검이 먼저 부러졌습니다.'}],
 11:[{'type':'impact_flash','state':3,'center':[.27,.72],'radius':.13,'intensity':.18,'quote':'도겸이 있던 자리에 돌검이 박혔습니다.'},{'type':'impact_shake','state':3,'center':[.27,.72],'radius':.13,'intensity':.22,'quote':'도겸이 있던 자리에 돌검이 박혔습니다.'}],
 13:[{'type':'focus_glow','state':2,'center':[.58,.67],'radius':.14,'intensity':.16,'quote':'더 짙어진 기운이 검신을 덮자'}],
 14:[{'type':'debris_burst','state':1,'center':[.72,.48],'radius':.15,'intensity':.24,'quote':'빗나간 돌검이 측벽을 부쉈습니다.'}],
 15:[{'type':'impact_shake','state':3,'center':[.45,.45],'radius':.10,'intensity':.12,'quote':'검 손잡이가 서진의 입가를 때렸습니다.'}],
 16:[{'type':'focus_glow','state':3,'center':[.62,.52],'radius':.08,'intensity':.10,'quote':'잠금쇠가 걸렸습니다.'}],
 19:[{'type':'debris_burst','state':4,'center':[.65,.53],'radius':.16,'intensity':.22,'quote':'등 뒤에서 수레가 산산이 부서졌습니다.'},{'type':'impact_shake','state':4,'center':[.65,.53],'radius':.16,'intensity':.22,'quote':'등 뒤에서 수레가 산산이 부서졌습니다.'}],
 20:[{'type':'impact_shake','state':2,'center':[.45,.65],'radius':.07,'intensity':.10,'quote':'돌조각이 서진의 옆구리를 때렸습니다.'}],
 22:[{'type':'focus_glow','state':2,'center':[.65,.24],'radius':.17,'intensity':.10,'quote':'눈앞에 낯선 글자가 떠올랐습니다.'}],
 23:[{'type':'impact_flash','state':2,'center':[.56,.53],'radius':.08,'intensity':.16,'quote':'돌에 부딪힌 단도 끝이 튕겨 나갔습니다.'}],
 26:[{'type':'speedline_burst','state':2,'center':[.43,.59],'radius':.18,'intensity':.18,'quote':'어깨를 낮추고'},{'type':'impact_shake','state':2,'center':[.72,.74],'radius':.12,'intensity':.14,'quote':'검이 그의 등 뒤 바닥을 때렸습니다.'}]
}

def text_windows(scene):
    """Preview fractions only. Production seconds require actual voice alignment."""
    chars = sum(len(b['text']) for b in scene['blocks'])
    offset = 0
    result = []
    for n,b in enumerate(scene['blocks'],1):
        end = offset + len(b['text'])
        result.append({'block_id':scene['id']+'_B'+str(n).zfill(2),'kind':b['kind'],
                       'speaker':b.get('speaker'),'text':b['text'],
                       'preview_start':offset/chars,'preview_end':end/chars})
        offset = end
    return result

def main():
    from PIL import Image
    src = (P/'script-final.json').read_bytes()
    script = json.loads(src)
    layout_path=D/'visual-layout.json'
    layouts=json.loads(layout_path.read_text(encoding='utf-8')) if layout_path.exists() else {}
    chars=[sum(len(b['text']) for b in s['blocks']) for s in script['scenes']]
    duration_weights=[max(16,c/8+2) for c in chars]
    total=sum(duration_weights)
    scenes=[]
    for n,(s,w) in enumerate(zip(script['scenes'],duration_weights),1):
        source_text='\n'.join(b['text'] for b in s['blocks'])
        states=[]
        order=ORDERS.get(n,list(range(1,len(s['visual_states'])+1)))
        cursor=0
        for idx,weight in zip(order,SPLITS[n-1]):
            asset_id=s['id']+'_STATE_'+str(idx).zfill(2)
            path=P/'images'/(asset_id+'.png')
            if not path.is_file():raise ValueError('Actual original missing: '+asset_id)
            with Image.open(path) as im: width,height=im.size; im.verify()
            states.append({'asset_id':asset_id,'file':'images/'+path.name,'width':width,'height':height,
                           'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                           'start':round(cursor,6),'end':round(cursor+weight,6),
                           'camera':'hold','static_crop':STATIC_CROPS.get(asset_id),
                           'source_review':layouts.get(asset_id,{}).get('review','pending')})
            cursor+=weight
        assert abs(cursor-1)<.00001
        blocks=text_windows(s)
        graphics=[]
        # Only actual spoken dialogue becomes a bubble. Narration and unselected
        # thoughts NEVER become automatic verbatim subtitles.
        dialogue_groups={}
        for bi,b in enumerate(blocks,1):
            if b['kind']!='dialogue':continue
            state_idx=DIALOGUE_STATES[n][bi]
            dialogue_groups.setdefault(state_idx,[]).append(b)
        for state_idx,group in dialogue_groups.items():
          for di,b in enumerate(group):
            state=next(x for x in states if x['asset_id'].endswith('STATE_'+str(state_idx).zfill(2)))
            span=state['end']-state['start']
            begin=state['start']+span*(.06+.88*di/len(group))
            end=state['start']+span*(.06+.88*(di+1)/len(group))
            slot=layouts.get(state['asset_id'],{}).get('dialogue_slots',{}).get(b['speaker'])
            if slot is None:
                slot={'center':[.52,.18],'size':[.36,.18],'tail':[.42,.42],'placement_review':'pending'}
            graphics.append({'kind':'speech_bubble','block_id':b['block_id'],'speaker':b['speaker'],
                             'text':b['text'],'state_asset_id':state['asset_id'],
                             'preview_start':round(begin,6),'preview_end':round(end,6),
                             'voice_binding':{'block_id':b['block_id']},'layout':slot,
                             'style':{'font':'NotoSansKR-Bold','size':38,'fill':[.08,.10,.13],'entry':'settle'}})
        for ci,cue in enumerate(s['screen_text']):
            matches=[b for b in blocks if cue['anchor'] in b['text']]
            assert len(matches)==1,(s['id'],cue['anchor'])
            b=matches[0]
            local=b['text'].index(cue['anchor'])
            t=b['preview_start']+(b['preview_end']-b['preview_start'])*local/len(b['text'])
            state_idx=TYPE_STATES[n][ci]
            state=next(x for x in states if x['asset_id'].endswith('STATE_'+str(state_idx).zfill(2)))
            span=state['end']-state['start']
            # Show contextual typography after any dialogue on the same still.
            spoken_here=any(g['state_asset_id']==state['asset_id'] for g in graphics)
            t=state['start']+span*(.77 if spoken_here else .22)
            if spoken_here:
                for g in graphics:
                    if g['state_asset_id']==state['asset_id']:
                        g['preview_end']=min(g['preview_end'],state['start']+span*.70)
            slot=layouts.get(state['asset_id'],{}).get('typography_slot',{'center':[.70,.28],'size':[.40,.22],'placement_review':'pending'})
            graphics.append({'kind':cue['kind'],'text':cue['text'],'state_asset_id':state['asset_id'],
                             'preview_start':round(t,6),'preview_end':round(min(state['end']-.01,t+span*.45),6),
                             'voice_binding':{'block_id':b['block_id'],'exact_anchor':cue['anchor']},
                             'layout':slot,'style':TYPE_STYLES[cue['kind']], 'intent':cue['treatment']})
        effects=[]
        for e in FX.get(n,[]):
            assert e['quote'] in source_text,(s['id'],e['quote'])
            state=next(x for x in states if x['asset_id'].endswith('STATE_'+str(e['state']).zfill(2)))
            effects.append({**e,'asset_id':state['asset_id'],'preview_at':state['start']+.04,
                            'voice_binding':{'exact_anchor':e['quote'],'phase':'during'},
                            'duration_seconds':.32 if e['type']!='focus_glow' else .65,
                            'source_review':layouts.get(state['asset_id'],{}).get('review','pending')})
        scenes.append({'scene_id':s['id'],'intent':s['ae'],'source_sha256':hashlib.sha256(source_text.encode()).hexdigest(),
                       'preview_duration_seconds':round(600*w/total,3),'timing_basis':'normalized_preview_not_recorded_speech',
                       'states':states,'blocks':blocks,'graphics':graphics,'effects':effects,
                       'transition':'cut','camera_policy':'fixed_no_slow_zoom','fake_depth':False})
    result={'contract':'wuxia_still_ae_episode/v1','episode':1,'width':1920,'height':1080,'fps':24,
            'script_sha256':hashlib.sha256(src).hexdigest(),'scenes':scenes,'video_clip_count':0,
            'narration_verbatim_captions':False,'all_text_editable':True,
            'timing':'Preview fractions only. Bind final performance with actual recording intervals; never report preview as voice sync.',
            'audio_alignment_file':'voice-alignment.json','ae_execution_verified':False}
    (D/'ae-scene-package.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'scenes':len(scenes),'stills':sum(len(s['states']) for s in scenes),
                      'editable_text_layers':sum(len(s['graphics']) for s in scenes),
                      'effects':sum(len(s['effects']) for s in scenes)}))

if __name__=='__main__':main()
