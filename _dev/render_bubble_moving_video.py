import sys,json,copy
from pathlib import Path
import numpy as np
root=Path.cwd();wt=Path('C:/Users/kimse/.codex/worktrees/ae-submitted-video-postwork/LongformGenerator');sys.path[:0]=[str(wt/'worker'),str(wt)]
from ae_flat_scene import prepare
from ae_scene_production import _render_native,_video_info
from ae_media_utils import ffmpeg,run
from ae_video_tracking import track_video
from ae_mouth import digest,decode_scene_audio,amplitude_cues
from speech_bubbles import validate_layout,track_layout
out=root/'_dev/artifacts/bubble-tracked-preview/scene5-moving';out.mkdir(parents=True,exist_ok=True)
base=root/'output/codex-local-console/ae-mouth/4c73538ea33c493ff1e2ad4e742c76416801f281a6386fe3a69d0f13c7f85169';source=base/'scene-5/original-video.mp4';ref=base/'scene-5/verified-seed-4/seed.png';voice=base/'final-narration.mp3'
s=json.loads((root/'_dev/artifacts/bubble-tracked-preview/moving-mouth/speakers.json').read_text(encoding='utf-8'))[0]
seed={k:s[k] for k in ('speaker','face_box','mouth_box')};_,tracked,proof=track_video(source,ref,[seed],out/'mouth-tracking',6,4)
speaker={**s,**tracked[0]};speaker['layers']=s['layers'];speaker['layer_sha256']={k:digest(Path(v)) for k,v in s['layers'].items()};speaker['tracking']=[{**r,'at_seconds':round(r['at_seconds']-4,6)} for r in tracked[0]['tracking']];speaker['visible_from_seconds']=0;speaker['visible_until_seconds']=2
snap=json.loads((root/'_dev/artifacts/ae_supervisor_job.json').read_text(encoding='utf-8'))['metadata']['input'];rows=[{**r,'kind':'dialogue'} for r in snap['subtitles'] if r.get('scene_number')==5 and r.get('speaker')];clip_start=min(r['start'] for r in rows)+4;clip_end=clip_start+2
excerpt_rows=[{**r,'start':max(r['start'],clip_start),'end':min(r['end'],clip_end)} for r in rows if r['start']<clip_end and r['end']>clip_start]
speaker['cues']=amplitude_cues(decode_scene_audio(ffmpeg(),voice,clip_start,2),excerpt_rows,start=clip_start,duration=2,fps=24)
clip=out/'actual-source-4-to-6.mp4';run([ffmpeg(),'-v','error','-y','-ss','4','-i',str(source),'-t','2','-an','-c:v','libx264','-crf','16','-pix_fmt','yuv420p',str(clip)])
runtime={'enabled':True,'speakers':[speaker],'video_source':True,'video_duration':2,'audio_sha256':digest(voice),'blinks':[],'audio_light_cues':[]}
identity={'fit':'contain','keys':[dict(t=t,x=.5,y=.5,scale=1,rotation=0,opacity=100) for t in (0,1)],'effects':[]};scene={'source_kind':'video','start':0,'end':2,'_mouth_runtime':runtime};motion={'aspect':'16:9','fps':24}
# Stage receipt enables review without changing or submitting any project.
(out/'prepared.json').write_text(json.dumps({'runtime':runtime,'tracking_proof':proof,'clip_start':clip_start,'rows':rows},ensure_ascii=False,indent=2),encoding='utf-8')
print('Moving scene prepared; rendering mouth',flush=True)
work=out/'mouth';work.mkdir(exist_ok=True);p=prepare(clip,scene,motion,identity);native=_render_native(p,work,2)
second=rows[-1];cue={'text':second['text'].strip('「」。'),'speaker':speaker['speaker'],'style':'dialogue','reason':'Recorded direct question, no added shout','start_seconds':0,'end_seconds':second['end']-clip_start}
faces=[r['face_box'] for r in tracked[0]['tracking']];own=[min(b[0] for b in faces),min(b[1] for b in faces),max(b[2] for b in faces),max(b[3] for b in faces)]
item={**cue,'box':[.073,.245,.287,.425],'speaker_anchor':[.332,.331],'speaker_face_box':speaker['face_box'],'speaker_mouth_box':speaker['mouth_box'],'protected_boxes':[own,[.585,.14,.69,.355],[.24,.53,.32,.73]],'speaker_evidence':'Actual reviewed reference shows older lantern-holding Otoku at left; recorded speaker is Otoku'}
layout=validate_layout({'status':'ready','evidence':'Body in negative space to left of Otoku, short tail to her cheek; girl face and lantern protected','bubbles':[item]},{'cues':[cue]})
layout=track_layout(native,layout,out/'bubble-tracking',24)
work2=out/'bubbles';work2.mkdir(exist_ok=True);p2=prepare(native,{'source_kind':'video','start':0,'end':2},motion,identity);p2['plan']['speech_bubbles']=layout;rendered=_render_native(p2,work2,2)
output=out/'moving-voice-mouth-bubble.mp4';run([ffmpeg(),'-v','error','-y','-i',str(rendered),'-ss',str(clip_start),'-i',str(voice),'-map','0:v:0','-map','1:a:0','-t','2','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',str(output)])
for t in (.125,.5,1,1.25,1.75):run([ffmpeg(),'-v','error','-y','-ss',str(t),'-i',str(output),'-frames:v','1',str(out/f'actual-{t}.png')])
a=np.array(decode_scene_audio(ffmpeg(),voice,clip_start,2));b=np.array(decode_scene_audio(ffmpeg(),output,0,2));n=min(len(a),len(b));corr=float(np.corrcoef(a[:n],b[:n])[0,1]);assert corr>.99
motion_px=[max(r['offset'][j] for r in speaker['tracking'])-min(r['offset'][j] for r in speaker['tracking']) for j in (0,1)]
receipt={'preview_only':True,'actual_source_excerpt_seconds':[4,6],'actual_final_voice_excerpt_seconds':[clip_start,clip_end],'dialogue_preview_seconds':[0,cue['end_seconds']],'original_voice_correlation':corr,'mouth_tracking_motion_pixels':motion_px,'mouth_keys':len(speaker['cues']),'layout':layout,'info':_video_info(output),'production_data_modified':False};(out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'video':str(output),'correlation':corr,'motion':motion_px}))
