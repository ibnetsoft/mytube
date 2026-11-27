"""Download actual existing character pixels for required cross-topic visual review."""
import hashlib,json,sys,os,requests
from urllib.parse import quote
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PIL import Image,ImageOps,ImageDraw
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')];load_dotenv(ROOT/'worker/connection.env')
from worker.cowork_scene_assets import _download_gcs_bytes
OUT=ROOT/'output/pawnshop-series/episode-01/production';folder=OUT/'existing-reference-pixels';folder.mkdir(exist_ok=True)
inventory=json.loads((OUT/'existing-reference-inventory.json').read_text());rows=[r for r in inventory if r.get('storage_object_path') and r.get('image_url')];(OUT/'reference-records-without-images.json').write_text(json.dumps([r['id'] for r in inventory if r not in rows]))
def one(row):
 p=folder/(str(row['id'])+'.png')
 if not p.exists():
  try:data=_download_gcs_bytes(row['storage_bucket'],row['storage_object_path'])
  except RuntimeError:
   base=os.environ['NEXT_PUBLIC_SUPABASE_URL'].rstrip('/');key=os.environ['SUPABASE_SERVICE_ROLE_KEY']
   response=requests.get(base+'/storage/v1/object/'+quote(row['storage_bucket'],safe='')+'/'+quote(row['storage_object_path'],safe='/'),headers={'apikey':key,'Authorization':'Bearer '+key},timeout=40)
   if response.status_code!=200:return {**row,'unavailable_status':response.status_code}
   data=response.content
  p.write_bytes(data)
 with Image.open(p) as im:im.verify()
 return {**row,'local_file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(one,rows))
(OUT/'unavailable-existing-references.json').write_text(json.dumps([r for r in results if r.get('unavailable_status')],ensure_ascii=False,indent=2));results=[r for r in results if r.get('local_file')]
(OUT/'existing-reference-pixels.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
for start in range(0,len(results),12):
 batch=results[start:start+12];canvas=Image.new('RGB',(2400,1800),'#252525');draw=ImageDraw.Draw(canvas)
 for i,row in enumerate(batch):
  im=Image.open(row['local_file']).convert('RGB');im.thumbnail((600,550),Image.Resampling.LANCZOS);x=(i%4)*600+(600-im.width)//2;y=(i//4)*600;canvas.paste(im,(x,y));draw.text(((i%4)*600+10,y+560),str(start+i+1)+' | topic '+str(row['topic_queue_id'])+' | '+str(row['character_key']),fill='white')
 canvas.save(OUT/f'reference-contact-{start//12+1}.jpg',quality=95)
print('Verified actual reference images',len(results),flush=True)
