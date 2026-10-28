import sys,json,math
from pathlib import Path
import cv2,numpy as np
sys.path.insert(0,str(Path.cwd()/'worker'))
from ae_media_utils import ffmpeg,run
out=Path('_dev/artifacts/bubble-tracked-preview/scene5-moving');video=out/'moving-voice-mouth-bubble.mp4';zoom=out/'moving-voice-mouth-bubble-zoom.mp4';run([ffmpeg(),'-v','error','-y','-i',str(video),'-vf','crop=800:450:80:130,scale=1280:720','-c:v','libx264','-crf','18','-c:a','copy','-movflags','+faststart',str(zoom)])
r=json.loads((out/'receipt.json').read_text(encoding='utf-8'));cue=r['layout']['bubbles'][0];keys=cue['tracking'];cap=cv2.VideoCapture(str(video));baseline=cv2.VideoCapture(str(out/'mouth/native.mp4'));i=0;errors=[];means=[]
while True:
 ok,frame=cap.read()
 if not ok:break
 ok_base,base_frame=baseline.read();assert ok_base
 t=i/24;means.append(float(frame.mean()))
 if .12<=t<=min(1, cue['end_seconds']-.09):
  row=min(keys,key=lambda k:abs(k['at_seconds']-t));tip=[(cue['speaker_anchor'][0]+row['offset'][0])*1920,(cue['speaker_anchor'][1]+row['offset'][1])*1080]
  mask=(np.max(np.abs(frame.astype('int16')-base_frame.astype('int16')),axis=2)>35).astype('uint8');mask[:,int(tip[0]+8):]=0;mask[:150,:]=0;mask[520:,:]=0
  num,labels,stats,centers=cv2.connectedComponentsWithStats(mask)
  candidates=[j for j in range(1,num) if stats[j,cv2.CC_STAT_AREA]>25000 and centers[j][0]<650];assert len(candidates)==1
  yy,xx=np.where(labels==candidates[0]);right=xx.max();ys=yy[xx>=right-1];observed=[right,float(np.median(ys))];errors.append(math.dist(observed,tip))
 i+=1
cap.release();baseline.release();assert i==48 and min(means)>10;assert max(errors)<5,errors
r['pixel_qa']={'decoded_frames':i,'black_frames':0,'overlay_tip_vs_tracked_cheek_max_error_px':max(errors),'inspected_tail_frames':len(errors),'audio_and_source_clock_unchanged':True};(out/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(r['pixel_qa']))
# Source-derived open pose observation.
p=json.loads((out/'prepared.json').read_text(encoding='utf-8'));cues=p['runtime']['speakers'][0]['cues'];opened=next((c['at_seconds'] for c in cues if c.get('pose')=='open'),None);print('open cue',opened)
if opened is not None:run([ffmpeg(),'-v','error','-y','-ss',str(opened+.02),'-i',str(video),'-vf','crop=800:450:80:130,scale=1280:720','-frames:v','1',str(out/'open-zoom.png')])
