"""Source-bound local CLI face comparisons; failures stay truthful quality notes."""
import json,sys,hashlib,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env',override=False)
from worker.character_face_distinctness import FaceDistinctnessReviewer,current_cast
from worker.codex_content_runner import CodexContentConfig
OUT=ROOT/'output/pawnshop-series/episode-03';BASE=ROOT/'output/codex-local-console/8b6c78f054e445148286e8ad0c661610'
c=json.loads((BASE/'candidate.json').read_text());a=c['structure']['character_anchors'];chars=[a['main_character'],*a['supporting_characters']]
files=['naoto','owner','cat','fumiko','ono','clerk'];references=[]
for char,name in zip(chars,files):
 p=OUT/'character-references'/f'{name}.png';char['character_key']='pawnshop-series-'+name if name in ('owner','cat') else 'pawnshop-episode03-'+name;char['image_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();references.append((char,p))
reviewer=FaceDistinctnessReviewer(CodexContentConfig.from_environment(),OUT/'face-comparison')
try:
 for char,path in references:
  char['face_distinctness_review']=reviewer.review(char,path,[(other,p) for other,p in references if other['character_key']!=char['character_key']])
  (OUT/'face-review-status.json').write_text(json.dumps({'stage':'comparing','character':char['name'],'passed':char['face_distinctness_review']['passed'],'updated_at':time.time()},ensure_ascii=False))
 (OUT/'face-review-results.json').write_text(json.dumps({'current_cast':current_cast(chars),'characters':chars},ensure_ascii=False,indent=2))
 print('face comparisons complete',current_cast(chars),flush=True)
except Exception as exc:
 (OUT/'face-review-status.json').write_text(json.dumps({'stage':'review incomplete','error_type':type(exc).__name__,'updated_at':time.time()}));raise
