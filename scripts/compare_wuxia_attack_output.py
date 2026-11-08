"""Compare every decoded actual-AE frame with the actual React preview capture."""
import argparse,json,subprocess
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--ffmpeg',type=Path,required=True);a=p.parse_args();r=a.directory.resolve();movie=r/'actual-ae.mp4';frames=r/'ae-frames';frames.mkdir(exist_ok=True)
subprocess.run([str(a.ffmpeg.resolve()),'-v','error','-y','-i',str(movie),'-vsync','0','-start_number','0',str(frames/'frame-%03d.png')],check=True)
snapshot=json.loads((r/'probe-snapshot.json').read_text());timeline=snapshot['scenes'][0]['wuxia_timeline'];samples=timeline['samples'];fps=snapshot['motion']['fps']
actual=list(frames.glob('frame-*.png'));assert len(actual)==len(samples),(len(actual),len(samples))
load=lambda folder,i:np.asarray(Image.open(folder/f'frame-{i:03d}.png').convert('RGB')).astype(np.int16)
web=r/'web-frames';states={s['asset_id']:s for s in timeline['states']};quiet={}
for i,s in enumerate(samples):
 if not s.get('effects',{}).get('overlays') and not s.get('ambient'):quiet.setdefault(s['state'],i)
assert set(quiet)==set(states),'Need quiet controls for each source state'
base={sid:(load(web,i),load(frames,i)) for sid,i in quiet.items()};records=[];visible_expected=[];visible_actual=[]
for i,s in enumerate(samples):
 w,n=load(web,i),load(frames,i);assert w.shape==n.shape==(1080,1920,3)
 bw,bn=base[s['state']];wm=np.max(np.abs(w-bw),axis=2)>24;nm=np.max(np.abs(n-bn),axis=2)>24
 wp,npix=int(wm.sum()),int(nm.sum());union=int((wm|nm).sum());inter=int((wm&nm).sum());iou=inter/union if union else 1
 if wp>=100:visible_expected.append(i)
 if npix>=100:visible_actual.append(i)
 bounds=lambda m:None if not m.any() else [int(np.nonzero(m)[1].min()),int(np.nonzero(m)[0].min()),int(np.nonzero(m)[1].max()),int(np.nonzero(m)[0].max())]
 wb,nb=bounds(wm),bounds(nm);bbox_error=max(abs(x-y) for x,y in zip(wb,nb)) if wb and nb else 0 if wb==nb else 1920
 protection=[]
 for accent in s.get('effects',{}).get('action_accents',[]):
  for b in accent['protected_boxes']:
   x0,y0,x1,y1=[int(v*(1920 if k%2==0 else 1080)) for k,v in enumerate(b)];x0+=4;y0+=4;x1-=4;y1-=4
   if x1>x0 and y1>y0:protection.append(float(np.abs(n[y0:y1,x0:x1]-bn[y0:y1,x0:x1]).mean()))
 records.append({'frame':i,'time':round(i/fps,6),'effects':s.get('effects',{}).get('active',[])+[f"ambient:{v['loop']}:{v['frame']}" for v in s.get('ambient',[])],'web_effect_pixels':wp,'ae_effect_pixels':npix,'mask_iou':iou,'effect_bbox_error_px':bbox_error,'rgb_mae':float(np.abs(w-n).mean()),'protected_mean_delta':max(protection,default=0)})
active=[v for v in records if v['web_effect_pixels']>=100]
report={'scope':'All decoded actual Adobe output frames vs actual production React component; isolated actual E01_S11 action state-cut probe','fps':fps,'frames':len(samples),'duration_seconds':len(samples)/fps,'expected_visible_effect_frames':visible_expected,'actual_visible_effect_frames':visible_actual,'timing_identical':visible_actual==visible_expected,'effect_mask_min_iou':min(v['mask_iou'] for v in active),'effect_mask_mean_iou':float(np.mean([v['mask_iou'] for v in active])),'maximum_effect_bbox_error_px':max(v['effect_bbox_error_px'] for v in active),'maximum_protected_mean_delta':max(v['protected_mean_delta'] for v in records),'frame_rgb_mae_mean':float(np.mean([v['rgb_mae'] for v in records])),'lossless_pixel_equality_claimed':False,'frames_detail':records}
report['passed']=report['timing_identical'] and report['effect_mask_min_iou']>=.85 and report['maximum_effect_bbox_error_px']<=3 and report['maximum_protected_mean_delta']<=4
(r/'pixel-timing-comparison.json').write_text(json.dumps(report,indent=2))
indices=[13,18,20,23,31,32];sheet=Image.new('RGB',(960*3,570*4),'#111820');draw=ImageDraw.Draw(sheet)
for k,i in enumerate(indices):
 col,row=k%3,k//3
 for j,folder in enumerate((web,frames)):
  x,y=col*960,(row*2+j)*570;im=Image.open(folder/f'frame-{i:03d}.png').convert('RGB').resize((960,540),Image.Resampling.LANCZOS);sheet.paste(im,(x,y+30));draw.text((x+10,y+8),f'{"WEB" if j==0 else "ACTUAL AE"} frame {i} / {i/fps:.3f}s',fill='white')
sheet.save(r/'web-vs-actual-ae-contact-sheet.jpg',quality=93)
print(json.dumps({k:v for k,v in report.items() if k!='frames_detail'},indent=2))
if not report['passed']:raise SystemExit(1)
