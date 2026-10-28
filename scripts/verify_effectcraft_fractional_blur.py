import copy,json,sys
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from effectcraft_render import binary,_execute
from effectcraft_compatibility import prepare_project
OLD=ROOT/'output/effectcraft/psd-3376-scene25-20261021'
D=ROOT/'output/effectcraft/psd-3376-scene25-fix-20261021'
original=json.loads((OLD/'scene.ecproj').read_text(encoding='utf-8'))
comp='ae_highlight_parallax_layered_scene_sustained';cli=binary();results=[]
def blur(p):
    for item in p['items'].values():
        if item['name']!=comp:continue
        for layer in item['kind']['layers']:
            if layer['name']!='background':continue
            return next(g for g in layer['props']['children'] if g['match']=='effects')['children'][0]
def pixels(p):return np.asarray(Image.open(p).convert('RGB')).astype(float)
for amount in [.35,.7,1.0]:
    directory=D/('radius-'+str(amount));directory.mkdir(exist_ok=True)
    data=copy.deepcopy(original);data['settings'].update(working_space='Rec709',output_space='Rec709',bit_depth='Bpc16')
    blur(data)['children'][0]['value']['v']=amount
    before=directory/'before.ecproj';before.write_text(json.dumps(data),encoding='utf-8')
    off=copy.deepcopy(data);blur(off)['enabled']=False
    (directory/'off.ecproj').write_text(json.dumps(off),encoding='utf-8')
    after=directory/'after.ecproj';after.write_text(json.dumps(data),encoding='utf-8')
    receipt=prepare_project(cli,after,directory,_execute)
    for label in ['off','before','after']:
        _execute(cli,['render-frame',str(directory/(label+'.ecproj')),'--comp',comp,'--time','1','--out',str(directory/(label+'.png')),'--json'],directory,label)
    a,b,c=[pixels(directory/(n+'.png')) for n in ['off','before','after']]
    result=dict(amount=amount,before_changed_pixels=int(np.any(a!=b,axis=2).sum()),after_changed_pixels=int(np.any(a!=c,axis=2).sum()),after_mean_difference=float(abs(c-a).mean()),kernel=receipt['fractional_gaussian'][0]['kernel'])
    results.append(result);print(json.dumps(result),flush=True)
assert results[1]['before_changed_pixels']==0 and results[1]['after_changed_pixels']>0
(D/'fractional-blur-validation.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
before=json.loads((OLD/'scene.ecproj').read_text(encoding='utf-8'));after=json.loads((D/'scene.ecproj').read_text(encoding='utf-8'))
transforms=lambda p:[(item['id'],[(l['id'],l['name'],next(g for g in l['props']['children'] if g['match']=='transform')) for l in item['kind'].get('layers',[])]) for item in p['items'].values() if item['kind']['type']=='Comp']
assert transforms(before)==transforms(after),'Layer order or authored camera transforms changed'
print('Original layer order and transform keys preserved',flush=True)
