"""Render deterministic test layers through the installed EC engine; no production job is modified."""
import json,runpy,sys,os,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from ae_media_utils import ffmpeg,run
from effectcraft_render import PIN,render_scene
if '--release' in sys.argv:
    from effectcraft_render import binary
    os.environ['EFFECTCRAFT_CLI']=str(binary())
    release=Path(ROOT/'_dev/artifacts/project_completion_release_root.txt').read_text().strip()
    spec=importlib.util.spec_from_file_location('released_ec_renderer',Path(release)/'worker/effectcraft_render.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    PIN,render_scene=module.PIN,module.render_scene
import ec_supplemental_assets as ec
from PIL import Image
import numpy as np

directory=ROOT/'output'/'codex-local-console'/('ec-supplement-smoke-release' if '--release' in sys.argv else 'ec-supplement-smoke')
directory.mkdir(parents=True,exist_ok=True)
fixture=runpy.run_path(str(ROOT/'tests/test_ec_supplemental_assets.py'))
s,scene,plan,source,voice=fixture['setup'](directory)
scene['end']=2;s['subtitles'][0].update(start=.5,end=1.5)
s['renderer']={'engine':'effectcraft','revision':PIN['revision']}
s['motion'].update(aspect='16:9',scenes={'1':{}})
plan['scene'].update(source='image',fit='contain',direction='Test source plus timed supplemental layer',transition='cut')
run([ffmpeg(),'-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=2','-ar','48000',str(voice)])
original_hash=ec.sha(source);voice_hash=ec.sha(voice)
package=ec.prepare(s,scene,plan,source,source,voice,fixture['Runner'](),directory/'assets',generator=fixture['Generator']())
plan['_supplemental_package']=package
output=render_scene(s,scene,plan,source,directory/'render',lambda:None)
colors=[]
for at,name in ((.1,'before'),(1.,'during'),(1.9,'after')):
    target=directory/(name+'.png')
    run([ffmpeg(),'-v','error','-y','-ss',str(at),'-i',str(output),'-frames:v','1',str(target)])
    with Image.open(target) as im:
        pixels=np.asarray(im.convert('RGB'));colors.append(pixels[pixels.shape[0]//2,pixels.shape[1]//2].astype(int).tolist())
assert colors[0][2]>colors[0][0] and colors[1][0]>180 and colors[1][2]<50 and colors[2][2]>colors[2][0],colors
assert ec.sha(source)==original_hash and ec.sha(voice)==voice_hash
result=dict(engine='effectcraft',output=str(output),source_unchanged=True,voice_unchanged=True,timing=[.5,1.5],center_rgb=colors,
            note='Generation and semantic review use explicit deterministic test doubles; EC rendering and decoded-frame checks use the installed native engine.')
(directory/'smoke-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
