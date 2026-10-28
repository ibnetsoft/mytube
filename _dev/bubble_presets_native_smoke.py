import sys,json
from pathlib import Path
from PIL import Image
root=Path(sys.argv[1]);sys.path[:0]=[str(root),str(root/'worker')]
from speech_bubbles import PRESETS
from ae_flat_scene import prepare
from ae_scene_production import _render_native,_video_info
from ae_media_utils import ffmpeg,run
out=Path('C:/Projects/에어스튜디오/LongformGenerator/_dev/artifacts/bubble-presets-native');out.mkdir(exist_ok=True,parents=True)
source=out/'source.png';Image.new('RGB',(1920,1080),(80,110,140)).save(source)
scene={'start':0,'end':2,'source_kind':'image'}
motion={'aspect':'16:9','fps':24}
direction={'fit':'contain','keys':[dict(t=t,x=.5,y=.5,scale=1,rotation=0,opacity=100) for t in (0,1)],'effects':[]}
p=prepare(source,scene,motion,direction);bubbles=[]
for i,style in enumerate(PRESETS):
 x=.04+(i%4)*.24;y=.08+(i//4)*.4;box=[x,y,x+.2,y+.22]
 bubbles.append(dict(text=(style+'\n안녕하세요' if i==0 else '조용히 말해요' if i==3 else 'こんにちは' if i==7 else style),speaker='synthetic',style=style,box=box,start_seconds=0,end_seconds=2,tail_root=[x+.1,y+.22],speaker_anchor=[x+.12,y+.3]))
p['plan']['speech_bubbles']={'bubbles':bubbles}
video=_render_native(p,out,2);frame=out/'eight-presets.png';run([ffmpeg(),'-v','error','-y','-ss','1','-i',str(video),'-frames:v','1',str(frame)])
receipt={'synthetic_fixture_only':True,'presets':list(PRESETS),'info':_video_info(video),'preview':str(frame)};(out/'receipt.json').write_text(json.dumps(receipt));print(json.dumps(receipt))
