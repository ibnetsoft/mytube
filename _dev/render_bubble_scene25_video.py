import sys,json,hashlib
from pathlib import Path
root=Path.cwd();wt=Path('C:/Users/kimse/.codex/worktrees/ae-submitted-video-postwork/LongformGenerator');sys.path[:0]=[str(wt/'worker'),str(wt)]
from ae_flat_scene import prepare
from ae_scene_production import _render_native,_video_info
from ae_media_utils import ffmpeg,run
from speech_bubbles import validate_layout,track_layout
from ae_mouth import decode_scene_audio
import numpy as np
out=root/'_dev/artifacts/bubble-tracked-preview/scene25';out.mkdir(parents=True,exist_ok=True)
source=root/'output/codex-local-console/ae-mouth/bc4c29de2593671d4e9a852c3a6ff4985deb2298d5658314466a17ab3d2c94a5/scene-25/ae-mouth-preview.mp4'
v=json.loads((root/'_dev/artifacts/inspect_3381_bubbles_before.json').read_text(encoding='utf-8'));rows=[s for s in v['subtitles'] if s.get('scene_number')==25];row=next(r for r in rows if r.get('dialogue_kind')=='dialogue');start=rows[0]['start'];a=row['start']-start;b=row['end']-start
cue={'text':row['text'],'speaker':row['dialogue_speaker'],'style':'dialogue','reason':'Actual recorded quiet admission','start_seconds':a,'end_seconds':b}
item={**cue,'box':[.456,.30,.646,.46],'speaker_anchor':[.419,.385],'speaker_face_box':[.24,.17,.42,.465],'speaker_mouth_box':[.305,.39,.35,.42],'protected_boxes':[[.24,.17,.42,.465],[.674,.145,.827,.463],[.04,.71,.96,1]],'speaker_evidence':'Saved verified coordinates identify left suited Kenta; actual video was inspected'}
layout=validate_layout({'status':'ready','evidence':'Short tail beside visible left cheek; both faces and meal clear','bubbles':[item]},{'cues':[cue]});layout=track_layout(source,layout,out/'tracking',24)
info=_video_info(source);duration=info['duration'];scene={'source_kind':'video','start':0,'end':duration};direction={'fit':'contain','keys':[dict(t=t,x=.5,y=.5,scale=1,rotation=0,opacity=100) for t in (0,1)],'effects':[]};p=prepare(source,scene,{'aspect':'16:9','fps':24},direction);p['plan']['speech_bubbles']=layout
native=_render_native(p,out,duration);mp4=out/'scene25-voice-mouth-bubble.mp4';run([ffmpeg(),'-v','error','-y','-i',str(native),'-i',str(source),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','copy','-movflags','+faststart',str(mp4)])
for t in (11,11.4,12,12.8,13.1):run([ffmpeg(),'-v','error','-y','-ss',str(t),'-i',str(mp4),'-frames:v','1',str(out/f'actual-{t}.png')])
pcm1=np.array(decode_scene_audio(ffmpeg(),source,0,duration));pcm2=np.array(decode_scene_audio(ffmpeg(),mp4,0,duration));assert np.array_equal(pcm1,pcm2),'Existing voice changed'
receipt={'preview_only':True,'source_video':str(source),'finalized_scene_dialogue':[a,b],'audio_decoded_exact_match':True,'layout':layout,'info':_video_info(mp4)};(out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'video':str(mp4),'audio_exact':True}))
