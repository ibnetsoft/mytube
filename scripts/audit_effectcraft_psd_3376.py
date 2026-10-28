import argparse,json
from pathlib import Path
import numpy as np,cv2
parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,default=Path(__file__).resolve().parents[1]/'output/effectcraft/psd-3376-scene25-20261021');args=parser.parse_args()
D=args.directory.resolve()
p=json.loads((D/'scene.ecproj').read_text(encoding='utf-8'))
summary=[]
for item in p['items'].values():
    k=item['kind']
    if k['type']!='Comp' or item['name']=='source':continue
    for l in k['layers']:
        groups={g['match']:g for g in l['props']['children']}
        transforms={q['match']:{a:q[a] for a in ['value','keys'] if a in q} for q in groups['transform']['children'] if q['match'] in ['position','scale','rotation','opacity']}
        effects=groups['effects']['children']
        summary.append(dict(layer=l['name'],transforms=transforms,effects=effects))
(D/'project-layer-audit.json').write_text(json.dumps(summary,indent=2))
for s in summary:
    print(s['layer'],[(k,len(v.get('keys',[]))) for k,v in s['transforms'].items()],[(e['name'],[(q.get('name'),q.get('value')) for q in e.get('children',[])]) for e in s['effects']],flush=True)
metrics=json.loads((D/'frame-metrics.json').read_text())
for i,m in enumerate(metrics):
    a=cv2.imdecode(np.fromfile(D/f'ae-reference-{i}.png',dtype=np.uint8),cv2.IMREAD_COLOR);b=cv2.imdecode(np.fromfile(D/f'effectcraft-{i}.png',dtype=np.uint8),cv2.IMREAD_COLOR)
    ag=cv2.cvtColor(cv2.resize(a,(960,540)),cv2.COLOR_BGR2GRAY).astype(np.float32)/255
    bg=cv2.cvtColor(cv2.resize(b,(960,540)),cv2.COLOR_BGR2GRAY).astype(np.float32)/255
    warp=np.eye(2,3,dtype=np.float32)
    corr,warp=cv2.findTransformECC(ag,bg,warp,cv2.MOTION_AFFINE,(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,60,1e-6))
    m.update(ecc_correlation=float(corr),affine_half_resolution=warp.tolist(),mean_rgb_delta_ae_minus_ec=(a[:,:,::-1].astype(float)-b[:,:,::-1].astype(float)).mean(axis=(0,1)).tolist())
(D/'frame-metrics.json').write_text(json.dumps(metrics,indent=2))
print(json.dumps(metrics,indent=2),flush=True)
