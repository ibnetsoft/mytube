import json,sys
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'worker'))
from effectcraft_render import binary,_execute
D=ROOT/'output/effectcraft/psd-3376-scene25-20261021'
p=json.loads((D/'scene.ecproj').read_text(encoding='utf-8'));target=None
for item in p['items'].values():
    k=item['kind']
    if k['type']!='Comp' or item['name']=='source':continue
    for layer in k['layers']:
        if layer['name']!='background':continue
        for group in layer['props']['children']:
            if group['match']=='effects':
                for effect in group['children']:
                    effect['enabled']=False;target=effect['name']
assert target=='Gaussian Blur'
(D/'no-blur.ecproj').write_text(json.dumps(p),encoding='utf-8')
cli=binary();comp='ae_highlight_parallax_layered_scene_sustained'
for label,project in [('blur-on','scene.ecproj'),('blur-off','no-blur.ecproj')]:
    _execute(cli,['render-frame',str(D/project),'--comp',comp,'--time','1','--out',str(D/(label+'.png')),'--json'],D,label)
a=np.asarray(Image.open(D/'blur-on.png').convert('RGB')).astype(float)
b=np.asarray(Image.open(D/'blur-off.png').convert('RGB')).astype(float)
result=dict(effect=target,amount=.35,mean_pixel_difference=float(np.abs(a-b).mean()),changed_pixels=int(np.any(a!=b,axis=2).sum()),max_channel_difference=float(np.abs(a-b).max()))
(D/'blur-check.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
for item in p['items'].values():
    k=item['kind']
    if k['type']!='Comp' or item['name']=='source':continue
    for layer in k['layers']:
        if layer['name']!='background':continue
        for group in layer['props']['children']:
            if group['match']=='effects':
                for effect in group['children']:
                    effect['enabled']=True
                    effect['children'][0]['value']['v']=4.0
(D/'diagnostic-blur4.ecproj').write_text(json.dumps(p),encoding='utf-8')
_execute(cli,['render-frame',str(D/'diagnostic-blur4.ecproj'),'--comp',comp,'--time','1','--out',str(D/'diagnostic-blur4.png'),'--json'],D,'diagnostic-blur4')
c=np.asarray(Image.open(D/'diagnostic-blur4.png').convert('RGB')).astype(float)
result['diagnostic_amount4_changed_pixels']=int(np.any(c!=b,axis=2).sum())
result['diagnostic_amount4_mean_difference']=float(np.abs(c-b).mean())
(D/'blur-check.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
