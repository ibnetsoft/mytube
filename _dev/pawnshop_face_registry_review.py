"""Review actual candidate and all stored reference pixels through local Codex vision."""
import json,sys,shutil,hashlib
from pathlib import Path
from PIL import Image,ImageDraw
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env')
from worker.codex_content_runner import CodexStagedContentRunner
OUT=ROOT/'output/pawnshop-series/episode-01/production';refs=json.loads((OUT/'existing-reference-pixels.json').read_text());attach=ROOT/'output/codex-local-console/9a74a481741948aaa8bf4cf8bd27734b/face-registry-review';attach.mkdir(exist_ok=True)
names=['shuji','nao','father','mother','neighbor'];canvas=Image.new('RGB',(3000,1024),'#222');draw=ImageDraw.Draw(canvas)
for i,name in enumerate(names):
 im=Image.open(OUT/'characters'/f'{name}.png').convert('RGB');im.thumbnail((600,980));canvas.paste(im,(i*600,0));draw.text((i*600+10,990),name,fill='white')
canvas.save(attach/'new-cast.png')
# Detailed close-up face panels retain substantially more geometry than full-body thumbnails.
face=Image.new('RGB',(3000,700),'#222');draw=ImageDraw.Draw(face)
for i,name in enumerate(names):
 im=Image.open(OUT/'characters'/f'{name}.png').convert('RGB');im=im.crop((int(im.width*.62),0,im.width,im.height));im.thumbnail((600,660));face.paste(im,(i*600,0));draw.text((i*600+10,675),name,fill='white')
face.save(attach/'candidate-faces.png')
for j in range((len(refs)+11)//12):shutil.copy2(OUT/f'reference-contact-{j+1}.jpg',attach/f'reference-contact-{j+1}.jpg')
def one(j):
 rows=refs[j*12:j*12+12];target=OUT/f'face-registry-review-{j+1}.json'
 if target.exists():return json.loads(target.read_text())
 context={'_local_image_paths':[str(attach/'candidate-faces.png'),str(attach/'new-cast.png'),str(attach/f'reference-contact-{j+1}.jpg')],'candidate_order':names,'references':[{'panel':j*12+i+1,'id':r['id'],'topic':r['topic_queue_id'],'name':r['name'],'sha256':r['sha256']} for i,r in enumerate(rows)],'instruction':'Image1 shows large candidate face closeups in labeled order; image2 shows their full sheets; image3 contains the existing registry references, numbered globally. Compare underlying facial shape, eyes, nose, mouth, jaw and proportions. Ignore hairstyle, clothes, background, lighting, gender presentation and wrinkles alone. Do not identify real people.'}
 task='Perform an actual-pixel editorial character identity check. For EVERY reference in image3 compare ALL five candidate identities. Return JSON {reference_checks:[{reference_id:exact supplied numeric id,comparisons:[{candidate_key:"shuji|nao|father|mother|neighbor",verdict:"distinct|similar|uncertain",structural_differences:["specific observed face-shape/eyes/nose/mouth/jaw/proportions difference",...],reason:"short evidence or visibility limitation"}]}],candidate_pair_checks:[{first:"key",second:"key",verdict:"distinct|similar|uncertain",structural_differences:[...],reason:"..."}]}. For distinct require THREE independent substantial facial structural differences; age, hair, clothes, style alone never count. Same ethnicity/art style does not imply same face. If a reference is nonhuman, say so and compare actual structural features; do not invent human anatomy. If a face cannot be read at this resolution mark uncertain for that pair; no false pass. Include each existing reference exactly once and every candidate exactly once per reference. Include each of ten candidate-vs-candidate pairs once. This is not biometric matching; no invented percentages. Do not rewrite story or generate media.'
 result=CodexStagedContentRunner()._stage('pawnshop-3387','03_face_registry_'+str(j+1),context,task)
 assert {x['reference_id'] for x in result['reference_checks']}=={r['id'] for r in rows}
 for item in result['reference_checks']:
  assert {x['candidate_key'] for x in item['comparisons']}==set(names)
  assert all(x['verdict'] in ['distinct','similar','uncertain'] and (x['verdict']!='distinct' or len(x['structural_differences'])>=3) for x in item['comparisons'])
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2));print('Face batch',j+1,'saved',flush=True);return result
with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(one,range((len(refs)+11)//12)))
flagged=[{'reference_id':item['reference_id'],**c} for batch in results for item in batch['reference_checks'] for c in item['comparisons'] if c['verdict']!='distinct'];(OUT/'face-review-followups.json').write_text(json.dumps(flagged,ensure_ascii=False,indent=2));print('Registry comparisons',sum(len(i['comparisons']) for b in results for i in b['reference_checks']),'followups',len(flagged),flush=True)
