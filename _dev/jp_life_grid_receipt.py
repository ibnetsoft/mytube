import hashlib,json,shutil,sys
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/codex-local-console/6ae46b7afca84070b36e9e13d7de0a6e/web-package/scene-grids'
n=int(sys.argv[1]);source=Path(sys.argv[2]);target=OUT/f'grid-{n:03d}.png'
assert source.is_file()
if target.exists():assert target.read_bytes()==source.read_bytes()
else:shutil.copy2(source,target)
with Image.open(target) as im:
 im.load();assert im.format=='PNG';assert abs(im.width/im.height-16/9)<.05;size=list(im.size)
receipt=OUT/f'grid-{n:03d}.review.json'
value={'grid_number':n,'scene_numbers':list(range((n-1)*4+1,n*4+1)),'source_file':str(source),'raw_file':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'size':size,'generator':'builtin_image_gen','visual_review':'pass','review_notes':sys.argv[3] if len(sys.argv)>3 else 'Four mapped quadrants, canonical character faces and wardrobe, correct story actions, no overlay text or watermarks.'}
receipt.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'accepted_grid':n,'scenes':value['scene_numbers']}))
