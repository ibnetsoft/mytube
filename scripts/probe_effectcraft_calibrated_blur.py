"""Probe the independently measured AE 1.2 impulse response on preserved scenes."""
import json,sys,shutil
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'worker'))
from effectcraft_render import binary,_execute
D=ROOT/'output/effectcraft/psd-3376-scene29-residual-fix-20261021'
OLD=D.parent/'psd-3376-scene29-effects-20261021';FIX=D.parent/'psd-3376-scene29-vignette-fix-20261021'
im=np.asarray(Image.open(D/'ae-impulse1.2.png').convert('RGB'))[:,:,0]/255
k=im[31:34,31:34]**2.4
corner=float(np.mean([k[0,0],k[0,2],k[2,0],k[2,2]]));edge=float(np.mean([k[0,1],k[1,0],k[1,2],k[2,1]]))
k=np.array([[corner,edge,corner],[edge,k[1,1],edge],[corner,edge,corner]]);k/=k.sum()
(D/'calibrated-blur-kernel.json').write_text(json.dumps(dict(amount=1.2,gamma=2.4,kernel=k.flatten().tolist()),indent=2))
for name,source in [('baseline',OLD/'controls/ec-baseline4.ecproj'),('rich',FIX/'scene.ecproj')]:
    project=D/('calibrated-'+name+'.ecproj');shutil.copy2(source,project)
    code="var l=app.project.itemByID(75).layer('background'),effects=l.property('ADBE Effect Parade'),original=effects.property(1);original.enabled=false;\n"
    code+="var before=effects.addProperty('ec.color.levels');before.property('gamma').setValue(1/2.4);before.moveTo(1);\n"
    code+="var kernel=effects.addProperty('ec.color.cckernel'),weights="+json.dumps(k.flatten().tolist())+";for(var j=0;j<9;j++)kernel.property('k'+(j+1)).setValue(weights[j]);kernel.property('scale').setValue(1);kernel.property('offset').setValue(0);kernel.moveTo(2);\n"
    code+="var after=effects.addProperty('ec.color.levels');after.property('gamma').setValue(2.4);after.moveTo(3);\n"
    jsx=D/('calibrated-'+name+'.jsx');jsx.write_text(code,encoding='utf8')
    _execute(binary(),['script',str(jsx),'--project',str(project),'--save','--json'],D,'calibrated-'+name)
    _execute(binary(),['render-frame',str(project),'--comp','ae_highlight_parallax_layered_scene','--time','4','--out',str(D/('calibrated-'+name+'.png')),'--json'],D,'calibrated-'+name+'-frame')
    a=np.asarray(Image.open(D/('ae-baseline.png' if name=='baseline' else 'ae-rich-4.png')).convert('RGB')).astype(float)
    b=np.asarray(Image.open(D/('calibrated-'+name+'.png')).convert('RGB')).astype(float)
    print(name,'MAE',abs(a-b).mean(), 'bias',(a-b).mean((0,1)).tolist(),flush=True)
