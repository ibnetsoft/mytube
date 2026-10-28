from pathlib import Path
import dataclasses,json,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'worker'),str(ROOT)]
import prepare_two_topic_mouth_previews as pipeline
from prepared_mouth_layers import ROOT as CACHE,cache_key,prepare_scene
from manga_layer_generation import NativeCodexLayerGenerator
from codex_content_runner import CodexStagedContentRunner
folder=pipeline.BASE/'3377';image=folder/'scene-029.png';receipt=folder/'scene-029-speaker-coordinates.json';saved=json.loads(receipt.read_text(encoding='utf8'));directory=CACHE/cache_key(image,saved['speakers'][0]);backup=directory/'rejected-closed-open-seam';backup.mkdir(exist_ok=True)
for name in ['closed.png','closed.receipt.json','open.png','open.receipt.json']:
 file=directory/name
 if file.exists():file.replace(backup/name)
class CorrectedGenerator(NativeCodexLayerGenerator):
 def generate(self,**args):
  if args['work_dir'].name in ('generate-closed','generate-open'):
   args['prompt']+=' CORRECT THE PREVIOUS FAILED CLOSED/OPEN POSES: they contained an angular dark seam/patch edge from the screen-right lip corner toward the chin. Preserve the black moustache exactly. Paint continuous original matching skin below/right of the lips instead of a dark rectangular edge. Do not reproduce that artifact. Keep the exact sloping PROFILE face silhouette and right-edge background from the reference. Dark mouth interior must stay only inside ONE naturally open lip contour, never form a squared block on chin/skin/background. Preserve the existing skin, lower lip and face-edge ink outside that opening.'
  return super().generate(**args)
runner=CodexStagedContentRunner();runner.config=dataclasses.replace(runner.config,timeout_seconds=240)
saved['mouth_preparation']=prepare_scene(image,saved,runner=runner,generator=CorrectedGenerator(model='gpt-6.1-sol',timeout_seconds=600));pipeline.write(receipt,saved)
print(json.dumps({'topic':3377,'scene':29,'images':saved['mouth_preparation']['state'],'repaired_poses':['closed','open'],'preserved_poses':['half']}),flush=True)
