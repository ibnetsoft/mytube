"""Prepare generated electrical PNG drawings for the real E01_S11 source cut.

Only placement, source-envelope masking and authored opacity are performed here;
the lightning artwork itself comes from the built-in image generation tool.
"""
import argparse,json,sys,hashlib,math,shutil
from pathlib import Path
from PIL import Image,ImageChops,ImageDraw,ImageFilter
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
from wuxia_attack_sprite import validate_alpha,CONTRACT
import ae_highlight_worker as ae

def main():
 p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();r=a.directory.resolve();load_dotenv(ROOT/'worker/connection.env')
 project=json.loads((ROOT/'output/wuxia-attack-repair-20261108/project.json').read_text());scene=project['project_payload']['structure']['wuxia_ae_package']['scenes'][0]
 scene['effects']=[e for e in scene['effects'] if e['type']!='electric_discharge'];state=scene['states'][1]
 mapping=json.loads((ROOT/'output/wuxia-attack-repair-20261108/source-map.json').read_text())
 source=Path(mapping[state['media_url']]);size=Image.open(source).size;w,h=size
 heads=[[.115,.27,.175,.39],[.50,.075,.56,.18],[.24,.27,.29,.38],[.32,.29,.37,.39],[.365,.32,.42,.415],[.62,.30,.68,.40],[.72,.375,.79,.47],[.59,.585,.67,.715],[.77,.605,.85,.755]]
 hands=[[.17,.60,.22,.66],[.49,.88,.58,1],[.62,.79,.68,.88],[.82,.92,.90,1],[.21,.65,.305,.75]]
 region=[.12,.50,.58,1];boxes=heads+hands
 loop=dict(contract='ambient_loop/v1',enabled=True,source_sha256=state['sha256'],role='environment',width=w,height=h,region=region,protected_regions=heads,start_ms=833,end_ms=1333,phase_ms=0,repeat=False,frames=[],attack_sprite=dict(contract=CONTRACT,source_sha256=state['sha256'],source_reviewed=True,frames_reviewed=True,event='Charged blade contacts fractured stone floor at frame 18',reason='User-requested hand-painted white/yellow electrical discharge keys, no procedural electrical vectors',contact_ms=750,protected_boxes=boxes))
 allowed=Image.new('L',size,0);draw=ImageDraw.Draw(allowed);roi=(math.ceil(region[0]*w),math.ceil(region[1]*h),math.floor(region[2]*w),math.floor(region[3]*h));draw.rectangle((roi[0],roi[1],roi[2]-1,roi[3]-1),fill=255)
 protection=Image.new('L',size,255);pd=ImageDraw.Draw(protection)
 for b in boxes:pd.rectangle((math.floor(b[0]*w)-8,math.floor(b[1]*h)-8,math.ceil(b[2]*w)+8,math.ceil(b[3]*h)+8),fill=0)
 soft=protection.filter(ImageFilter.GaussianBlur(12));protection=ImageChops.darker(protection,soft);mask=ImageChops.multiply(allowed,protection)
 frames_dir=r/'prepared';frames_dir.mkdir(exist_ok=True)
 keys=[Image.open(r/'raw'/f'key-{i+1:02d}.png').convert('RGBA') for i in range(3)]
 for key in keys:assert key.getchannel('A').getextrema()[0]==0 and key.getchannel('A').getextrema()[1]>=240,'Generated keys must retain real alpha'
 anchors=[(.50,.675),(.50,.62),(.47,.71)];sizes=[(500,240),(700,360),(620,290)]
 frame_review=[]
 for i,(key_index,opacity,duration) in enumerate(zip([0,1,2,1,2,0],[1,1,.9,.8,.65,.25],[83,83,84,83,83,84])):
  layer=keys[key_index].resize(sizes[key_index],Image.Resampling.LANCZOS);anchor=anchors[key_index]
  x=round(.328*w-layer.width*anchor[0]);y=round(.774*h-layer.height*anchor[1]);canvas=Image.new('RGBA',size);canvas.alpha_composite(layer,(x,y))
  alpha=ImageChops.multiply(canvas.getchannel('A'),mask).point(lambda v:round(v*opacity));canvas.putalpha(alpha);validate_alpha(loop,alpha)
  target=frames_dir/f'frame-{i:02d}.png';canvas.save(target);sha=hashlib.sha256(target.read_bytes()).hexdigest()
  bucket,gcs_path,_=ae._upload_gcs_file(target,'std-motion/wuxia-attack-sprites/'+sha+'.png','image/png');url='/api/std/assets/gcs-file?bucket='+bucket+'&path='+gcs_path
  loop['frames'].append(dict(media_url=url,sha256=sha,duration_ms=duration,gcs_bucket=bucket,gcs_path=gcs_path));mapping[url]=str(target)
  frame_review.append(dict(frame=i,key=key_index,sha256=sha,opacity=opacity,alpha_bounds=alpha.getbbox(),protected_alpha_zero=True))
 state['ambient_loops']=[loop]
 from ambient_loop import validate
 validate(loop)
 for name,data in [('project.json',project),('source-map.json',mapping),('sprite-manifest.json',loop),('sprite-review.json',dict(source_sha256=state['sha256'],canvas=size,contact=[.328,.774],scope='isolated real E01_S11 action source; original episode unchanged',raw_sha256=[hashlib.sha256((r/'raw'/f'key-{i+1:02d}.png').read_bytes()).hexdigest() for i in range(3)],frames=frame_review))]: (r/name).write_text(json.dumps(data,ensure_ascii=False,indent=2))
 print('PREPARED_SIX_SOURCE_BOUND_SPRITE_FRAMES',size)
if __name__=='__main__':main()
