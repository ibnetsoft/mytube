import sys,json,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root),str(root/'worker')]
import worker_config,ae_highlight_worker as ae
from ae_media_utils import ref
from motion_automation_worker import original_preview,verify_recorded_source_reuse
from PIL import Image,ImageOps,ImageDraw
directory=root/'output/submission-watch-3376';audit=json.loads((directory/'video-reuse-audit.json').read_text(encoding='utf-8'))
cache=root/'output/codex-local-console/motion-automation/775248bf-123b-48ef-8517-20845c160d68'
voice=next(cache.glob('final-voice.*'));voice=next(p for p in cache.glob('final-voice.*') if p.suffix!='.sha256')
def download(asset,name):
 bucket,key=ref(asset);target=directory/(name+Path(key).suffix)
 if not target.exists():ae._download_gcs_file(ae.GcsRef(bucket,key),target)
 return target
receipts=[]
for asset in sorted(audit['selected'],key=lambda a:a['scene_number']):
 number=asset['scene_number'];source=download(asset,f'video-{number}')
 preview=original_preview(source,'video',directory/f'video-{number}-preview.png')
 proof=next(r['reuse'] for r in audit['reports'] if r['number']==number)
 result=None
 if proof:
  old_voice=download(proof['audio'],'prior-voice')
  scene={'source':asset,'recorded_source_reuse':proof,'start':proof['current_start'],'end':proof['current_end']}
  result=verify_recorded_source_reuse(scene,source,old_voice,voice,audit['project']['progress_payload']['tts_asset_id'])
 receipts.append({'number':number,'id':asset['id'],'path':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'recorded_voice_comparison':result})
 (directory/'video-file-receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'scene':number,'downloaded':True,'recording_match':result},ensure_ascii=False),flush=True)
for offset in range(0,len(receipts),8):
 batch=receipts[offset:offset+8];sheet=Image.new('RGB',(1120,330*len(batch)),(25,29,34));draw=ImageDraw.Draw(sheet)
 for row,item in enumerate(batch):
  n=item['number']
  for col,path in enumerate([cache/f'original-{n}.png',directory/f'video-{n}-preview.png']):
   with Image.open(path) as pic:tile=ImageOps.contain(pic.convert('RGB'),(550,300));sheet.paste(tile,(col*560,row*330+25))
  draw.text((8,row*330+5),f'Scene {n}: prior submitted source (left) / uploaded video (right)',fill='white')
 sheet.save(directory/f'video-contact-{offset//8+1}.jpg',quality=90)
