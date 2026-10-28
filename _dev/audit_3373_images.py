import sys,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse,parse_qs
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
for f in ['.env','.env.local','auth-web/.env.local']:load_dotenv(ROOT/f)
import ae_highlight_worker as ae
from PIL import Image,ImageDraw
out=ROOT/'output/codex-local-console/image-repair-3373';out.mkdir(parents=True,exist_ok=True)
backup=ROOT/'_dev/artifacts/image_repair_3373'
assets=json.loads((backup/'assets.before.json').read_text(encoding='utf8'))
scenes=json.loads((backup/'scenes.before.json').read_text(encoding='utf8'))
topic=json.loads((backup/'topic.before.json').read_text(encoding='utf8'))[0]
refs=json.loads((backup/'characters.before.json').read_text(encoding='utf8'))
jobs=[]; manifest=[]
for s in scenes:
 n=s['scene_number']
 if n<19:continue
 a=next(x for x in assets if x['scene_number']==n and x['asset_type']=='image' and x['status'] in ['uploaded','assigned'])
 m=a['metadata'];target=out/f'scene-{n:03}.png'
 jobs.append((ae.GcsRef(m.get('gcs_bucket') or m.get('storage_bucket'),m.get('gcs_path') or m.get('storage_path')),target))
 manifest.append({'number':n,'scene_id':s['id'],'asset_id':a['id'],'text':s['scene_text'],'image_prompt':s['image_prompt'],'path':str(target)})
for c in refs:
 q=parse_qs(urlparse(c['image_url']).query);target=out/f"reference-{c['name']}.png"
 jobs.append((ae.GcsRef(q['bucket'][0],q['path'][0]),target))
def fetch(job):
 ref,target=job
 if not target.exists():ae._download_gcs_file(ref,target)
 return target
with ThreadPoolExecutor(max_workers=6) as pool:
 for path in pool.map(fetch,jobs):print(path.name,flush=True)
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
for start in range(0,len(manifest),12):
 batch=manifest[start:start+12];sheet=Image.new('RGB',(1600,984),(30,30,30));d=ImageDraw.Draw(sheet)
 for i,item in enumerate(batch):
  im=Image.open(item['path']).convert('RGB');im.thumbnail((400,225));x=(i%4)*400;y=(i//4)*328
  sheet.paste(im,(x,y+24));d.text((x+8,y+5),f"Scene {item['number']}",fill='white')
  prompt=item['image_prompt'];focus=prompt.split(f"Scene {item['number']}:")[-1].split('Specific story')[0][:130]
  import textwrap
  for j,line in enumerate(textwrap.wrap(focus,48)[:4]):d.text((x+5,y+252+j*15),line,fill='white')
 sheet.save(out/f'contact-{batch[0]["number"]:03}-{batch[-1]["number"]:03}.jpg')
print('READY',out,flush=True)
