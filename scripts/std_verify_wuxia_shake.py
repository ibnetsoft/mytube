"""Measure 10 Hz shake in the native Wuxia series' actual 1920x1080 output.

Use --snapshot with the frozen motion-job JSON; omit --scene for a whole master.
Phase correlation checks every active frame plus adjacent quiet frames against
that frozen schedule. Exit nonzero for missing windows or timing/position drift.
Requires opencv-python and numpy on the verification machine.
"""
import argparse,json,math
from pathlib import Path
import cv2,numpy as np
p=argparse.ArgumentParser();p.add_argument('movie');p.add_argument('--snapshot',required=True);p.add_argument('--output',required=True);p.add_argument('--scene',type=int);args=p.parse_args()
snapshot=json.loads(Path(args.snapshot).read_text());cap=cv2.VideoCapture(args.movie);fps=cap.get(cv2.CAP_PROP_FPS)
assert cap.isOpened(), 'Cannot open rendered output'
assert (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))==(1920,1080), 'This series verifier requires a 1920x1080 master'
assert abs(fps-snapshot['motion']['fps'])<.001
reports=[]
for sc in snapshot['scenes']:
 if args.scene and sc['number']!=args.scene:continue
 samples=sc['wuxia_timeline']['samples'];active=[i for i,s in enumerate(samples)if any(a.startswith('impact_shake')for a in s.get('effects',{}).get('active',[]))]
 if not active:continue
 # Probe files start at this scene's first frame. Master verification uses the saved final scene boundaries.
 start=0 if args.scene else sc['start'];count=min(len(samples),active[-1]+3)
 start_frame=0 if args.scene else math.ceil(start*fps-1e-7)
 window_start=max(0,active[0]-2)
 cap.set(cv2.CAP_PROP_POS_FRAMES,start_frame+window_start);frames={}
 for i in range(window_start,count):
  ok,f=cap.read()
  if not ok:raise ValueError('Movie ended before the complete shake window')
  # Compare at one common scale so the 2% edge-cover zoom cannot masquerade as translation.
  ref_scale=samples[active[len(active)//2]]['effects'].get('scale',1)
  scale=ref_scale/samples[i]['effects'].get('scale',1)
  if abs(scale-1)>1e-8:
   h,w=f.shape[:2];f=cv2.warpAffine(f,cv2.getRotationMatrix2D((w/2,h/2),0,scale),(w,h))
  frames[i]=cv2.cvtColor(f[300:1000,200:1500],cv2.COLOR_BGR2GRAY).astype(np.float32)
 ref_index=active[len(active)//2];ref=samples[ref_index]['effects'];axis='dy' if any(samples[i]['effects']['dy'] for i in active) else 'dx';dim=1 if axis=='dy' else 0
 reference=frames[ref_index];positions=[];errors=[];responses=[]
 for i in active:
  shift,response=cv2.phaseCorrelate(reference,frames[i]);positions.append(float(shift[dim]+ref[axis]));errors.append(abs(shift[dim]-(samples[i]['effects'].get(axis,0)-ref[axis])));responses.append(response)
 signs=[int(np.sign(v))for v in positions];segments=[v for i,v in enumerate(signs)if not i or v!=signs[i-1]]
 row={'scene':sc['number'],'fps':fps,'measured_shake_seconds':len(active)/fps,'measured_round_trips':len(segments)/2,'measured_hz':len(segments)/2/(len(active)/fps),'axis':'vertical'if dim else'horizontal','max_position_error_px':float(max(errors)),'mean_position_error_px':float(np.mean(errors)),'mean_correlation_response':float(np.mean(responses)),'checked_active_frames':len(active)}
 # Check the adjacent quiet frames independently of the authored active-window count.
 outside=[i for i in range(window_start,count) if i not in active and samples[i]['state']==samples[ref_index]['state']]
 outside_errors=[]
 for i in outside:
  shift,response=cv2.phaseCorrelate(reference,frames[i])
  outside_errors.append(abs(shift[dim]-(samples[i]['effects'].get(axis,0)-ref[axis])))
 row.update(master_start_frame=start_frame,quiet_boundary_frames=len(outside),quiet_boundary_max_error_px=float(max(outside_errors,default=0)))
 row['passed']=abs(row['measured_hz']-10)<.01 and row['max_position_error_px']<2 and row['quiet_boundary_max_error_px']<2
 reports.append(row)
Path(args.output).write_text(json.dumps({'movie':str(Path(args.movie).resolve()),'method':'decoded-frame phase correlation against frozen AE positions','results':reports,'passed':bool(reports)and all(r['passed']for r in reports)},indent=2))
print(json.dumps(reports))
cap.release()
if not reports or not all(r['passed']for r in reports):raise SystemExit(1)
