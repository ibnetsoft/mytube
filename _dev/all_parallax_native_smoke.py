import sys,json
from pathlib import Path
from PIL import Image,ImageDraw
import numpy as np
root=Path(sys.argv[1]);sys.path.insert(0,str(root));sys.path.insert(0,str(root/'worker'))
from ae_scene_production import _render_native,_video_info
from ae_media_utils import ffmpeg,run
from script_parallax import require_depth_motion
out=Path(__file__).parent/'artifacts/all-parallax-native';out.mkdir(parents=True,exist_ok=True)
files={}
for role,color,box in [('background',(15,25,80,255),None),('character',(220,30,30,255),(260,100,330,220)),('foreground',(20,220,40,255),(40,220,140,340))]:
 im=Image.new('RGBA',(640,360),color if box is None else (0,0,0,0))
 if box:ImageDraw.Draw(im).rectangle(box,fill=color)
 target=out/(role+'.png');im.save(target);files[role]=target
layers=[]
for i,role in enumerate(files):
 layer=dict(id=role,role=role,source_ids=[role],z_index=i,anchor=[.5,.5],parallax=0)
 if i:layer['motion']=[dict(t=t,x=t*(.006 if i==1 else .025),y=0,scale=1,rotation=0,opacity=100) for t in (0,1)]
 layers.append(layer)
plan=dict(contract='ae_scene/v1',schema_version='ae_scene/v1',timing='normalized',width=640,height=360,output={'width':1920,'height':1080},camera=[dict(t=t,x=.5,y=.5,scale=1,rotation=0) for t in (0,1)],layers=layers,lights=[],effects=[],transition={'in':'cut','out':'cut','fraction':0})
plan['continuity']={k:'Synthetic static canvas and separate colored planes.' for k in ('entry','exit','screen_direction','light_direction')};plan['qa_assertions']=['Preserve separate plane motion and canvas.']
require_depth_motion(plan)
video=_render_native({'plan':plan,'layers':files},out,2)
centers=[]
for t in (.1,1.8):
 target=out/('frame-'+str(t)+'.png');run([ffmpeg(),'-v','error','-y','-ss',str(t),'-i',str(video),'-frames:v','1',str(target)])
 a=np.asarray(Image.open(target).convert('RGB'));red=(a[:,:,0]>150)&(a[:,:,1]<80);green=(a[:,:,1]>150)&(a[:,:,0]<80);centers.append([float(np.where(red)[1].mean()),float(np.where(green)[1].mean())])
travel=[centers[1][i]-centers[0][i] for i in (0,1)]
assert travel[1]>travel[0]+20,travel
receipt={'synthetic_fixture_only':True,'video':str(video.resolve()),'info':_video_info(video),'middle_foreground_travel_pixels':travel};(out/'receipt.json').write_text(json.dumps(receipt));print(json.dumps(receipt))
