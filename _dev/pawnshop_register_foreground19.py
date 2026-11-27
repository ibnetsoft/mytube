"""Register three independently generated foreground objects to the approved scene canvas.
This is deterministic AE placement of generated assets, not image synthesis.
"""
from pathlib import Path
import json,sys
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from worker.manga_layer_generation import _normalize
from worker.layered_scene_composite import composite_scene
p=ROOT/'output/pawnshop-series/episode-01/production';source=p/'layers/019-foreground/8a7926454544c6b0.png';target=p/'layers/019-foreground-registered-v2.png'
placements=[{'object':'left_cup','source_box':[440,490,650,675],'target_box':[600,546,675,623]},{'object':'right_cup','source_box':[1030,490,1230,675],'target_box':[870,550,940,622]},{'object':'table_front','source_box':[80,675,1600,941],'target_box':[289,697,1446,941]}]
with Image.open(source) as im:
 im=im.convert('RGBA');canvas=Image.new('RGBA',(1672,941),(0,0,0,0))
 for row in placements:
  piece=im.crop(row['source_box']);bbox=piece.getchannel('A').getbbox();assert bbox;piece=piece.crop(bbox);x,y,r,b=row['target_box'];piece=piece.resize((r-x,b-y),Image.Resampling.LANCZOS);canvas.alpha_composite(piece,(x,y))
 canvas.save(target)
(p/'layers/019-foreground-registration-v2.json').write_text(json.dumps({'source':str(source),'output':str(target),'method':'AE object position and scale registration','canvas':[1672,941],'placements':placements},indent=2))
folder=p/'normalized/19';norm=folder/'019-foreground-registered-v2.png';_normalize(target,norm,'foreground');result=folder/'composite-v3.png';composite_scene(folder/'019-background.png',[folder/'019-character_left.png',folder/'019-character_right.png',norm],result);print(result)
