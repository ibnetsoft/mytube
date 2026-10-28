import sys,shutil
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'worker'))
from effectcraft_render import binary,_execute
D=ROOT/'output/effectcraft/psd-3376-scene29-residual-fix-20261021'
p=D/'light-feather-trial.ecproj';shutil.copy2(D/'calibrated-rich.ecproj',p)
code="""var l=app.project.itemByID(75).layer('ae_effect_light_sweep_0');
var m=l.property('ADBE Mask Parade').property(1),f=m.property('ADBE Mask Feather'),v=f.value;
f.setValue([v[0]*.75,v[1]*.75]);"""
jsx=D/'light-feather-trial.jsx';jsx.write_text(code)
_execute(binary(),['script',str(jsx),'--project',str(p),'--save','--json'],D,'light-feather-trial')
_execute(binary(),['render-frame',str(p),'--comp','ae_highlight_parallax_layered_scene','--time','4','--out',str(D/'light-feather-trial.png'),'--json'],D,'light-feather-trial-frame')
a=np.array(Image.open(D/'ae-rich-4.png').convert('RGB')).astype(float)
b=np.array(Image.open(D/'light-feather-trial.png')).astype(float)
print('Full rich lossless MAE',abs(a-b).mean(),'bias',(a-b).mean((0,1)),flush=True)
