"""Apply the production compatibility path to the preserved scene, without changing its baseline."""
import json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from effectcraft_render import binary,_execute
from effectcraft_compatibility import prepare_project
OLD=ROOT/'output/effectcraft/psd-3376-scene25-20261021'
D=ROOT/'output/effectcraft/psd-3376-scene25-fix-20261021';D.mkdir(parents=True,exist_ok=True)
shutil.copy2(OLD/'scene.ecproj',D/'scene.ecproj')
for file in ['ae-reference.mp4','original-config.json','provenance.json']:
    shutil.copy2(OLD/file,D/file)
cli=binary();receipt=prepare_project(cli,D/'scene.ecproj',D,_execute)
print(json.dumps(receipt),flush=True)
_execute(cli,['render',str(D/'scene.ecproj'),'--comp','ae_highlight_parallax_layered_scene_sustained','--out',str(D/'effectcraft.mp4'),'--format','h264','--audio','off','--fps','24','--json'],D,'render')
print('Fixed 10-second render completed',flush=True)
