"""Geometry-preserving boundary probe for the preserved scene-29 mask."""
import argparse,copy,json,math,sys
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'worker'))
from effectcraft_render import binary,_execute
OLD=ROOT/'output/effectcraft/psd-3376-scene29-effects-20261021'
D=ROOT/'output/effectcraft/psd-3376-scene29-vignette-fix-20261021';D.mkdir(parents=True,exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('--feather-factor',type=float,default=1);args=parser.parse_args()
label='padding-probe' if args.feather_factor==1 else 'padding-feather-probe'
p=json.loads((OLD/'controls/ec-subtle_vignette.ecproj').read_text(encoding='utf-8'))
for item in p['items'].values():
    comp=item['kind']
    if comp['type']!='Comp':continue
    for layer in comp['layers']:
        if not layer['name'].startswith('ae_effect_subtle_vignette_'):continue
        groups={g['match']:g for g in layer['props']['children']};mask=groups['masks']['children'][0]
        params={g['match']:g for g in mask['children']};f=params['feather']['value']['v']
        f[:]=[v*args.feather_factor for v in f]
        padx,pady=[math.ceil(v*1.5)+3 for v in f]
        solid=p['items'][str(layer['source']['item'])]['kind'];solid['width']+=padx*2;solid['height']+=pady*2
        anchor=next(g for g in groups['transform']['children'] if g['match']=='anchor')['value']['v'];anchor[0]+=padx;anchor[1]+=pady
        for v in params['path']['value']['v']['vertices']:v[0]+=padx;v[1]+=pady
project=D/(label+'.ecproj');project.write_text(json.dumps(p),encoding='utf-8')
_execute(binary(),['render-frame',str(project),'--comp','ae_highlight_parallax_layered_scene','--time','4','--out',str(D/(label+'.png')),'--json'],D,label)
def image(p):return np.asarray(Image.open(p).convert('RGB')).astype(float)
ae=image(OLD/'controls/ae-subtle_vignette.png');off=image(OLD/'controls/ec-baseline4.png');ec=image(D/(label+'.png'));aeoff=image(OLD/'controls/ae-baseline4.png')
print(json.dumps(dict(raw_mae=float(abs(ae-ec).mean()),ec_effect_strength=float(abs(ec-off).mean()),effect_delta_mae=float(abs((ae-aeoff)-(ec-off)).mean()),pad=[padx,pady])),flush=True)
for item in p['items'].values():
    comp=item['kind']
    if comp['type']!='Comp' or item['name']!='ae_highlight_parallax_layered_scene':continue
    comp['background']=[0,0,0]
    for layer in comp['layers']:
        layer['switches']['video']=layer['name'].startswith('ae_effect_subtle_vignette_')
        if not layer['switches']['video']:continue
        p['items'][str(layer['source']['item'])]['kind']['color']=[1,1,1]
        transform=next(g for g in layer['props']['children'] if g['match']=='transform')
        opacity=next(g for g in transform['children'] if g['match']=='opacity');opacity['value']['v']=100;opacity.pop('keys',None)
matte=D/(label+'-matte.ecproj');matte.write_text(json.dumps(p),encoding='utf-8')
_execute(binary(),['render-frame',str(matte),'--comp','ae_highlight_parallax_layered_scene','--time','4','--out',str(D/(label+'-matte.png')),'--json'],D,label+'-matte')
if (D/'ae-vignette-matte.png').exists():
    a=image(D/'ae-vignette-matte.png');b=image(D/(label+'-matte.png'))
    print('Matte MAE:',float(abs(a-b).mean()),'AE/EC matte mean:',float(a.mean()),float(b.mean()),flush=True)
