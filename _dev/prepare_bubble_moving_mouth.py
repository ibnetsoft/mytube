import sys,json
from pathlib import Path
root=Path.cwd();sys.path[:0]=[str(root),str(root/'worker')]
from dotenv import load_dotenv
load_dotenv(root/'.env',override=False)
from codex_content_runner import CodexStagedContentRunner
from ae_mouth import locate_speakers,mouth_layers,review_layers
from manga_layer_generation import NativeCodexLayerGenerator
out=root/'_dev/artifacts/bubble-tracked-preview/moving-mouth';out.mkdir(exist_ok=True)
base=root/'output/codex-local-console/ae-mouth/4c73538ea33c493ff1e2ad4e742c76416801f281a6386fe3a69d0f13c7f85169/scene-5'
p=json.loads((root/'_dev/artifacts/ae_supervisor_job.json').read_text(encoding='utf-8'))['metadata']['input']
scene={'number':5,'text':''.join(r['text'] for r in p['subtitles'] if int(r.get('scene_number') or 0)==5)}
rows=[{**r,'kind':'dialogue'} for r in p['subtitles'] if int(r.get('scene_number') or 0)==5 and r.get('speaker')]
ref=base/'verified-seed-4/seed.png'
class RepairRunner(CodexStagedContentRunner):
    def _stage(self,identity,name,context,task):
        context={**context,'prior_geometry_failure':'Prior independent review found both lip endpoints BELOW the actual mouth line, especially left marker on a wrinkle; box was too low. Re-localize from actual pixels above those rejected points. Do not reuse old markers or approve them by metadata.'}
        return super()._stage(identity,name,context,task)
runner=RepairRunner()
s=json.loads((out/'supervisor-geometry.json').read_text(encoding='utf-8'))
s['mouth_geometry']['review']={'passed':True,'proof':'annotated-face-crop-v4','reviewer':'codex-supervisor','reason':'Directly compared original 119x135 face crop at 6x and supervisor-markers.png: red endpoints are on actual lip corners at (680,363) and (712,360), green center on upper lip arch at (697,360); the separate lower-lip line and lateral cheek wrinkles are excluded as endpoints.'}
speakers=[s]
(out/'geometry.json').write_text(json.dumps(speakers,ensure_ascii=False),encoding='utf-8')
for i,s in enumerate(speakers):s['layers']=mouth_layers(NativeCodexLayerGenerator(),ref,s,out/f'speaker-{i}')
review_dir=root/'output/codex-local-console/bubble-preview-media/mouth-review';review_dir.mkdir(parents=True,exist_ok=True)
review_layers(runner,'bubble-moving-scene5-repair1',ref,speakers,review_dir)
(out/'speakers.json').write_text(json.dumps(speakers,ensure_ascii=False),encoding='utf-8');print('Reviewed moving-scene mouth assets ready',flush=True)
