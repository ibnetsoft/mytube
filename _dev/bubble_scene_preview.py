import sys,json
from pathlib import Path
root=Path.cwd();sys.path[:0]=[str(root/'worker'),str(root)]
from ae_flat_scene import prepare
from ae_scene_production import _render_native,_video_info
from ae_media_utils import ffmpeg,run
from speech_bubbles import validate_layout
out=root/'_dev/artifacts/bubble-scene-preview';out.mkdir(parents=True,exist_ok=True)
source=root/'output/codex-local-console/ae-video-review/6b46f709-b4bf-4ccd-ac12-9c8c3981e249-25-comparison/source-comparison-1.jpg'
v=json.loads((root/'_dev/artifacts/inspect_3381_bubbles_before.json').read_text(encoding='utf-8'))
row=next(s for s in v['subtitles'] if s.get('scene_number')==25 and s.get('dialogue_kind')=='dialogue')
cue={'text':row['text'],'speaker':row['dialogue_speaker'],'style':'dialogue','reason':'Quiet admission of difficulty in the recorded script; no shout or impact','start_seconds':.5,'end_seconds':3.5}
response={'status':'ready','evidence':'Left suited man is the recorded speaker Kenta; empty window between faces; both faces, hands and meal protected. Isolated preview of a real scene frame, not a production job.','bubbles':[{**cue,'box':[.46,.07,.65,.26],'speaker_anchor':[.408,.39],'protected_boxes':[[.235,.15,.438,.49],[.674,.145,.827,.463],[.04,.71,.96,1]],'speaker_evidence':'Existing scene-25 speaker coordinate receipt identifies left suited man as 高橋健太; same visible hand beside his cheek.'}]}
layout=validate_layout(response,{'cues':[cue]})
scene={'source_kind':'image','start':0,'end':4};motion={'aspect':'16:9','fps':24};direction={'fit':'contain','keys':[dict(t=t,x=.5,y=.5,scale=1,rotation=0,opacity=100) for t in (0,1)],'effects':[]}
p=prepare(source,scene,motion,direction);p['plan']['speech_bubbles']=layout
video=_render_native(p,out,4)
frame=out/'scene-25-bubble.png';run([ffmpeg(),'-v','error','-y','-ss','2','-i',str(video),'-frames:v','1',str(frame)])
mp4=out/'scene-25-preview.mp4';run([ffmpeg(),'-v','error','-y','-i',str(video),'-an','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(mp4)])
receipt={'preview_only':True,'source_frame':str(source),'actual_recorded_dialogue':row,'preview_cue_seconds':[.5,3.5],'production_data_modified':False,'layout':layout,'info':_video_info(mp4)}
(out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'preview':str(frame),'video':str(mp4),'info':receipt['info']}))
