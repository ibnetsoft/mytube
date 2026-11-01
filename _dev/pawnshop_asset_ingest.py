"""Persist built-in generated originals and validate their actual bitmap properties."""
import argparse,hashlib,json,shutil,time
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/pawnshop-series/episode-01/production'
p=argparse.ArgumentParser();p.add_argument('kind');p.add_argument('key');p.add_argument('source');p.add_argument('--transparent',action='store_true');a=p.parse_args();source=Path(a.source).resolve();assert source.is_file()
folder=OUT/a.kind/a.key;folder.mkdir(parents=True,exist_ok=True);sha=hashlib.sha256(source.read_bytes()).hexdigest();target=folder/(sha[:16]+'.png');shutil.copy2(source,target)
with Image.open(target) as im:
 im.load();assert im.format=='PNG' and min(im.size)>=512
 alpha=im.getchannel('A') if 'A' in im.getbands() else None
 extrema=alpha.getextrema() if alpha else None
 alpha_fraction=sum(v for i,v in enumerate(alpha.histogram()) if i<250)/(im.width*im.height) if alpha else 0
 result={'kind':a.kind,'key':a.key,'path':str(target),'sha256':sha,'width':im.width,'height':im.height,'alpha_extrema':extrema,'nonopaque_fraction':alpha_fraction,'source_file':str(source),'generator':'builtin_image_gen','generated_at':time.time(),'status':'generated_pending_visual_review'}
 if a.transparent and (not alpha or extrema[0]!=0 or alpha_fraction<.05):result['status']='needs_alpha_repair'
receipt=folder/(sha[:16]+'.json');receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
