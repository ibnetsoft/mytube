import sys,json
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'worker'))
from effectcraft_render import binary,_execute
OLD=ROOT/'output/effectcraft/psd-3376-scene25-20261021';D=ROOT/'output/effectcraft/psd-3376-scene25-fix-20261021'
data=json.loads((OLD/'scene.ecproj').read_text(encoding='utf-8'))
data['settings'].update(working_space='Rec709',output_space='Rec709',bit_depth='Bpc16')
project=D/'color-trial.ecproj';project.write_text(json.dumps(data),encoding='utf-8')
_execute(binary(),['render-frame',str(project),'--comp','ae_highlight_parallax_layered_scene_sustained','--time','1','--out',str(D/'color-trial.png'),'--json'],D,'color-trial')
a=np.array(Image.open(OLD/'ae-reference-2.png').convert('RGB')).astype(float)
b=np.array(Image.open(D/'color-trial.png').convert('RGB')).astype(float)
print(dict(mae=float(abs(a-b).mean()),delta=(a-b).mean((0,1)).tolist()),flush=True)
