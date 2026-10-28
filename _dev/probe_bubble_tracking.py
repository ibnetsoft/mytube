import sys,json
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'worker'))
from ae_video_tracking import track_video
p=Path('output/codex-local-console/ae-mouth/bc4c29de2593671d4e9a852c3a6ff4985deb2298d5658314466a17ab3d2c94a5/scene-25/ae-mouth-preview.mp4')
s={'speaker':'高橋健太','face_box':[.24,.17,.42,.465],'mouth_box':[.305,.39,.35,.42]}
a,ss,report=track_video(p,Path('_dev/artifacts/bubble-tracked-preview/source-11.2.png'),[s],Path('_dev/artifacts/bubble-tracked-preview/probe'),12.97,11.2)
rows=ss[0]['tracking'];print(json.dumps({'keys':len(rows),'first':rows[0],'last':rows[-1],'range_px':[max(r['offset'][i] for r in rows)-min(r['offset'][i] for r in rows) for i in (0,1)]}))
