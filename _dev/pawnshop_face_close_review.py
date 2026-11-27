import json,sys,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env')
from worker.codex_content_runner import CodexStagedContentRunner
OUT=ROOT/'output/pawnshop-series/episode-01/production';folder=ROOT/'output/codex-local-console/9a74a481741948aaa8bf4cf8bd27734b/face-close-review';folder.mkdir(exist_ok=True)
for source,name in [(OUT/'characters/nao.png','nao.png'),(OUT/'existing-reference-pixels/23.png','registry-23.png')]:shutil.copy2(source,folder/name)
result=CodexStagedContentRunner()._stage('pawnshop-3387','03_close_face_comparison_23',{'_local_image_paths':[str(folder/'nao.png'),str(folder/'registry-23.png')],'image_roles':['New character Nao reference sheet','Existing different topic registry character #23 full resolution'],'previous_contact_sheet_concern':'Both share tapered oval outline and almond-shaped eyes; contact sheet review did not establish enough independent structural differences. Full resolution is now supplied.'},'Compare actual underlying facial structure of these two fictional character designs at FULL supplied resolution, ignoring hair, clothes, background, age texture and viewpoint. Return JSON {verdict:"distinct|similar|uncertain",differences:[{axis:"face_shape|eyes|nose|mouth|jaw|proportions",evidence:"specific observed substantial difference"}],reason:"explain whether same base identity",repair_instruction:"if similar or uncertain, exact geometry changes required"}. Require three substantial independent axes for distinct, do not count generic ethnic features as identity, do not invent measurements or percentages. Do not rubber-stamp earlier conclusion; use actual newly supplied pixels. If resolution still insufficient mark uncertain. No media generation.')
(OUT/'face-close-review-23.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False),flush=True)
