"""Independent native impulse controls; no scene-specific brightness fitting."""
import json,sys
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'worker'))
from effectcraft_render import binary,_execute
from effectcraft_compatibility import AE_COLOR
D=ROOT/'output/effectcraft/psd-3376-scene29-residual-fix-20261021'
cli=binary();p=D/'blur-controls.ecproj'
_execute(cli,['script','--eval','null','--empty','--save-as',str(p),'--json'],D,'blur-init')
q=json.dumps(str(D/'impulse.png').replace('\\','/'))
code='var source=app.project.importFile(new ImportOptions(new File('+q+')));\n'
cases=[]
for amount in [.7,1,1.2,1.4,2]:
    name='native'+str(amount);cases.append(name)
    code+="var c=app.project.items.addComp("+json.dumps(name)+",64,64,1,1,24),l=c.layers.add(source),f=l.property('ADBE Effect Parade').addProperty('ADBE Gaussian Blur 2');f.property(1).setValue("+str(amount)+");\n"
for sigma in [.3,.325,.35,.375,.4,.45,.5,.6]:
    name='kernel'+str(sigma);cases.append(name)
    side=np.exp(-.5/sigma**2);v=np.array([side,1,side]);v/=v.sum();kernel=np.outer(v,v).flatten().tolist()
    code+="var c=app.project.items.addComp("+json.dumps(name)+",64,64,1,1,24),l=c.layers.add(source),f=l.property('ADBE Effect Parade').addProperty('ec.color.cckernel');var weights="+json.dumps(kernel)+";for(var k=0;k<9;k++)f.property('k'+(k+1)).setValue(weights[k]);f.property('scale').setValue(1);f.property('offset').setValue(0);\n"
jsx=D/'blur-controls.jsx';jsx.write_text(code,encoding='utf-8')
_execute(cli,['script',str(jsx),'--project',str(p),'--save','--json'],D,'blur-build')
_execute(cli,['exec','file.projectSettings','--params',json.dumps(AE_COLOR),'--project',str(p),'--save','--json'],D,'blur-color')
for name in cases:
    path=D/('ec-'+name+'.png')
    _execute(cli,['render-frame',str(p),'--comp',name,'--time','0','--out',str(path),'--json'],D,'ec-'+name)
    a=np.asarray(Image.open(path).convert('RGB'))[:,:,0]
    print(name,a[32,29:36].tolist(),int(a.sum()),flush=True)
