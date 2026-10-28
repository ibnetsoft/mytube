import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
D=Path(__file__).resolve().parents[1]/'output/effectcraft/psd-3376-scene29-effects-20261021';C=D/'controls'
names=['light_sweep','warm_dust_motes','shock_ring','subtle_vignette']
sheet=Image.new('RGB',(1280,4*385),'#111111');draw=ImageDraw.Draw(sheet);rows=[]
def load(name):return np.asarray(Image.open(C/(name+'.png')).convert('RGB')).astype(float)
for index,name in enumerate(names):
    time='baseline45' if name=='shock_ring' else 'baseline4'
    a,b=load('ae-'+name),load('ec-'+name)
    da,db=a-load('ae-'+time),b-load('ec-'+time)
    row=dict(effect=name,time=4.5 if name=='shock_ring' else 4.,raw_pair_mae=float(abs(a-b).mean()),ae_signal_mean_abs=float(abs(da).mean()),ec_signal_mean_abs=float(abs(db).mean()),ae_pixels_delta_gt3=int((abs(da).max(2)>3).sum()),ec_pixels_delta_gt3=int((abs(db).max(2)>3).sum()),effect_delta_mae=float(abs(da-db).mean()))
    if name=='warm_dust_motes':
        points=[]
        f=(4.-.8)/(9.-.8)
        for p in range(8):
            x=round((.82+np.sin(p*2.399)*.24*.7)*1920+1920*.015*f)
            y=round((.38+np.cos(p*2.399)*.24*.7)*1080-1080*.04*f)
            roi=(slice(max(0,y-5),min(1080,y+6)),slice(max(0,x-5),min(1920,x+6)))
            points.append(dict(index=p,expected_xy=[x,y],ae_peak_delta=float(abs(da[roi]).max()),ec_peak_delta=float(abs(db[roi]).max())))
        row['particle_controls']=points
    rows.append(row)
    for col,(label,delta) in enumerate([('AE',da),('EffectCraft',db)]):
        # Absolute difference vs same-engine baseline, x12; diagnostic visualization only.
        picture=Image.fromarray(np.clip(abs(delta)*12,0,255).astype('uint8')).resize((640,360))
        sheet.paste(picture,(640*col,index*385+25));draw.text((640*col+8,index*385+6),name+' | '+label+' | abs effect delta x12',fill='white')
sheet.save(D/'effect-delta-contact.jpg',quality=95)
(D/'effect-control-metrics.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
print(json.dumps(rows,indent=2),flush=True)
project=json.loads((D/'rich.ecproj').read_text(encoding='utf-8'))
comp=next(i['kind'] for i in project['items'].values() if i['name']=='ae_highlight_parallax_layered_scene')
def describe(layer):
    return {k:layer[k] for k in ['id','name','blend_mode','switches','props']}
(D/'rich-layer-audit.json').write_text(json.dumps([describe(l) for l in comp['layers']],indent=2),encoding='utf-8')
# Original artwork layer transforms/order are identical between EC baseline and rich.
base=json.loads((D/'baseline.ecproj').read_text(encoding='utf-8'))
def originals(p):
    comp=next(i['kind'] for i in p['items'].values() if i['name']=='ae_highlight_parallax_layered_scene')
    return [(l['name'],next(g for g in l['props']['children'] if g['match']=='transform')) for l in comp['layers'] if not l['name'].startswith('ae_effect_')]
assert originals(base)==originals(project)
print('Original source-layer transforms and order unchanged',flush=True)
