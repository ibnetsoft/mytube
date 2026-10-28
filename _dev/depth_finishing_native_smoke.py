import sys,json
from pathlib import Path
from PIL import Image,ImageDraw
import numpy as np
root=Path(sys.argv[1]);sys.path.insert(0,str(root));sys.path.insert(0,str(root/'worker'))
from ae_scene_production import _render_native,_video_info
from ae_media_utils import ffmpeg,run
from script_parallax import require_depth_motion
out=Path(__file__).parent/'artifacts/depth-finishing-native';out.mkdir(parents=True,exist_ok=True)
files={}
for role,color,box in [('background',(15,25,80,255),None),('character',(220,30,30,255),(260,100,330,220)),('foreground',(20,220,40,255),(40,220,140,340))]:
 im=Image.new('RGBA',(640,360),color if box is None else (0,0,0,0))
 if box:ImageDraw.Draw(im).rectangle(box,fill=color)
 if box is None:
  for x in range(0,640,8):ImageDraw.Draw(im).rectangle((x,0,x+3,359),fill=(50,70,140,255))
 target=out/(role+'.png');im.save(target);files[role]=target
layers=[]
for i,role in enumerate(files):
 layer=dict(id=role,role=role,source_ids=[role],z_index=i,anchor=[.5,.5],parallax=0)
 if i:layer['motion']=[dict(t=t,x=t*(.006 if i==1 else .025),y=0,scale=1,rotation=0,opacity=100) for t in (0,1)]
 layers.append(layer)
plan=dict(contract='ae_scene/v1',schema_version='ae_scene/v1',timing='normalized',width=640,height=360,output={'width':1920,'height':1080},camera=[dict(t=t,x=.5,y=.5,scale=1,rotation=0) for t in (0,1)],layers=layers,lights=[],effects=[],transition={'in':'cut','out':'cut','fraction':0})
plan['continuity']={k:'Synthetic static canvas and separate colored planes.' for k in ('entry','exit','screen_direction','light_direction')};plan['qa_assertions']=['Preserve separate plane motion and canvas.']

for layer in plan['layers']:layer.pop('motion',None)
plan['effects']=[dict(type=kind,target_layer=target,blur_pixels=12,start=0,end=1,intensity=.35,center=[.5,.5],radius=1,color=[.8,.85,.9],reason='Synthetic depth-plane native smoke') for kind,target in [('depth_background_blur','background'),('depth_foreground_blur','foreground'),('depth_background_haze','background')]]
video=_render_native({'plan':plan,'layers':files},out,2)
frames=[]
for t in (0,1):
 target=out/('frame-'+str(t)+'.png');run([ffmpeg(),'-v','error','-y','-ss',str(t),'-i',str(video),'-frames:v','1',str(target)]);frames.append(np.asarray(Image.open(target).convert('RGB')).astype(float))
a,b=frames;character_delta=float(np.abs(a[330:600,810:960]-b[330:600,810:960]).mean());bg_delta=float(np.abs(a[100:250,300:1500]-b[100:250,300:1500]).mean());bg_contrast=[float(f[100:250,300:1500,2].std()) for f in frames]
assert character_delta<2,character_delta
assert bg_delta>3 and bg_contrast[1]<bg_contrast[0]*.8,(bg_delta,bg_contrast)
receipt={'synthetic_fixture_only':True,'video':str(video.resolve()),'info':_video_info(video),'character_delta':character_delta,'background_delta':bg_delta,'background_contrast_before_after':bg_contrast};(out/'receipt.json').write_text(json.dumps(receipt));print(json.dumps(receipt))
