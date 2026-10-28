import sys,json,copy,hashlib
from pathlib import Path
from PIL import Image
import numpy as np
root=Path(sys.argv[1]);sys.path.insert(0,str(root));sys.path.insert(0,str(root/'worker'))
from ae_scene_production import _render_native,_video_info
from ae_media_utils import ffmpeg,run
from purpose_direction import policy,repair,apply_native_repair,validate_native
from scene_direction_policy import bind_prepared_camera
out=Path(__file__).parent/'artifacts/purpose-repair-native';out.mkdir(parents=True,exist_ok=True)
files={role:Path(__file__).parent/'artifacts/all-parallax-native'/(role+'.png') for role in ('background','character','foreground')}
source_hashes={role:hashlib.sha256(path.read_bytes()).hexdigest() for role,path in files.items()}
keys=[dict(t=t,x=.5+t*.02,y=.5,scale=1.06,rotation=0,opacity=100) for t in (0,1)]
design={'camera':{'kind':'pan_right','reason':'Slow location reveal','keys':keys},'effects':[],'transition':{'kind':'cut','reason':'Stable clock','duration_seconds':0},'graphics':{'speedlines':False}}
p=policy({},'location');creative={'contract':'scene_direction_plan/v2','purpose_policy':p,'execution_design':design}
plan=dict(contract='ae_scene/v1',schema_version='ae_scene/v1',timing='normalized',width=640,height=360,output={'width':1920,'height':1080},camera=[{k:v for k,v in row.items() if k!='opacity'} for row in keys],layers=[dict(id=role,role=role,source_ids=[role],z_index=i,anchor=[.5,.5],parallax=(0,.3,.8)[i]) for i,role in enumerate(files)],lights=[],effects=[],transition={'in':'cut','out':'cut','fraction':0},continuity={k:'Synthetic stable source and depth planes' for k in ('entry','exit','screen_direction','light_direction')},qa_assertions=['Preserve source drawing and original duration'],direction_policy=creative)
prepared={'plan':plan,'layers':files};scene={'purpose_policy':p,'creative_reference':copy.deepcopy(creative),'prepared_direction':{'source':'psd','keys':copy.deepcopy(keys),'effects':[],'transition':'cut'},'start':0,'end':2,'source':{'id':'synthetic'}}
travel=[];infos=[]
for mode in ('original','repaired'):
 current=prepared
 if mode=='repaired':
  repair(scene,1,'Synthetic failed review: camera overemphasizes the location')
  current=bind_prepared_camera(prepared,scene,scene['prepared_direction']);current=apply_native_repair(scene,current)
 validate_native(scene,current['plan']);directory=out/mode;directory.mkdir(exist_ok=True)
 video=_render_native(current,directory,2);infos.append(_video_info(video));centers=[]
 for t in (.1,1.8):
  frame=directory/('frame-'+str(t)+'.png');run([ffmpeg(),'-v','error','-y','-ss',str(t),'-i',str(video),'-frames:v','1',str(frame)]);a=np.asarray(Image.open(frame).convert('RGB'));red=(a[:,:,0]>150)&(a[:,:,1]<80);centers.append(float(np.where(red)[1].mean()))
 travel.append(abs(centers[1]-centers[0]))
assert .4<travel[1]/travel[0]<.6,travel
assert all(i['duration']==2 and i['frames']==48 for i in infos)
assert source_hashes=={role:hashlib.sha256(path.read_bytes()).hexdigest() for role,path in files.items()}
receipt={'synthetic_fixture_only':True,'camera_travel_before_after_pixels':travel,'info':infos,'source_hashes_unchanged':True};(out/'receipt.json').write_text(json.dumps(receipt));print(json.dumps(receipt))
