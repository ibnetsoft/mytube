"""Run existing AE layer normalization/composition for actual generated planes."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from worker.manga_layer_generation import _normalize
from worker.layered_scene_composite import composite_scene
OUT=ROOT/'output/pawnshop-series/episode-01/production'
specs={19:['019-background','019-character_left','019-character_right','019-foreground'],20:['020-background','020-foreground','020-character'],21:['021-background','021-character','021-foreground']}
for n,keys in specs.items():
 folder=OUT/'normalized'/str(n);files=[]
 for key in keys:
  receipts=list((OUT/'layers'/key).glob('*.json'));assert len(receipts)==1
  receipt=json.loads(receipts[0].read_text());target=folder/(key+'.png')
  if not target.exists():_normalize(Path(receipt['path']),target,'background' if key.endswith('background') else 'character' if 'character' in key else 'foreground')
  files.append(target)
 result=folder/'composite-v1.png'
 if not result.exists():composite_scene(files[0],files[1:],result)
 print(n,str(result))
