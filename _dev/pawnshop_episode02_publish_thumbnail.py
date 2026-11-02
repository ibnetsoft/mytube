"""Publish only the reviewed episode 2 thumbnail, with storage readback."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env')
from worker.gcs_media_storage import _upload_gcs_file
from worker.cowork_scene_assets import _download_gcs_bytes
from PIL import Image
OUT=ROOT/'output/pawnshop-series/episode-02'

def main():
 packaging=json.loads((OUT/'youtube-packaging.json').read_text())
 qa=json.loads((OUT/'thumbnail-review.json').read_text())
 assert qa.get('visual_inspected') is True and qa.get('text_matches') is True
 receipt={'script_sha256':packaging['script_sha256'],'thumbnail_text':packaging['thumbnail_text'],'review':qa}
 for filename,role in [('thumbnail-art.png','background'),('thumbnail-final.png','final')]:
  path=OUT/filename;assert path.is_file()
  with Image.open(path) as im:
   im.verify()
  with Image.open(path) as im:w,h=im.size
  assert w>=1280 and abs(w/h-16/9)<.03,(filename,w,h)
  sha=hashlib.sha256(path.read_bytes()).hexdigest()
  b,k,url=_upload_gcs_file(path,f'content-assets/pawnshop-series/episode-02/thumbnail/{sha}.png','image/png')
  assert hashlib.sha256(_download_gcs_bytes(b,k)).hexdigest()==sha
  receipt[role]={'url':url,'bucket':b,'path':k,'sha256':sha,'width':w,'height':h,'storage_readback_verified':True,'local_path':str(path)}
 (OUT/'thumbnail-publication-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
 print('Thumbnail background and final uploaded and byte-verified',flush=True)
if __name__=='__main__':main()
