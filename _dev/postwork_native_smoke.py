import sys,os,json,wave,math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from dotenv import load_dotenv
root=Path(sys.argv[1]);sys.path.insert(0,str(root));sys.path.insert(0,str(root/'worker'));load_dotenv('C:/Projects/에어스튜디오/LongformGenerator/.env');os.environ['USE_GPU_RENDER']='false'
from ae_media_utils import ffmpeg,run
from ae_mouth import digest,amplitude_cues
from ae_flat_scene import prepare
from ae_scene_production import _render_native,_video_info
from submitted_video_postwork import apply_transitions,CONTRACT
from motion_automation_worker import assemble_master,pcm
import imageio_ffmpeg
out=Path('C:/Projects/에어스튜디오/LongformGenerator/_dev/artifacts/submitted-video-postwork').resolve();out.mkdir(parents=True,exist_ok=True)
w,h,fps,duration=640,360,24,2
source=out/'moving-original.mp4';writer=imageio_ffmpeg.write_frames(str(source),(w,h),fps=fps,codec='libx264',pix_fmt_in='rgb24',pix_fmt_out='yuv420p',macro_block_size=1);writer.send(None)
for frame in range(duration*fps):
 t=frame/fps;cx=260+40*t;im=Image.new('RGB',(w,h),(8,14,24));d=ImageDraw.Draw(im);d.ellipse((520,25,565,70),fill=(130,135,145));d.ellipse((cx-50,120,cx+50,220),fill=(180,150,100));d.ellipse((cx-21,150,cx-11,160),fill='black');d.ellipse((cx+11,150,cx+21,160),fill='black');d.line((cx-14,200,cx+14,200),fill='black',width=2);writer.send(np.asarray(im))
writer.close();layers={}
for pose in ('closed','half','open'):
 im=Image.new('RGB',(30,20),(180,150,100));d=ImageDraw.Draw(im)
 if pose=='closed':d.line((1,10,29,10),fill='black',width=2)
 else:d.ellipse((4,4 if pose=='open' else 7,26,17 if pose=='open' else 14),fill='black')
 path=out/(pose+'.png');im.save(path);layers[pose]=str(path)
full=np.zeros(32000,dtype=np.int16)
for begin in (.5,2.5):
 a=int(begin*8000);b=int((begin+1)*8000);full[a:b]=(6000*np.sin(2*np.pi*220*np.arange(b-a)/8000)).astype(np.int16)
voice=out/'final-voice.wav'
with wave.open(str(voice),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(full.tobytes())
rows=[{'speaker':'hero','start':.5,'end':1.5}]
speaker={'speaker':'hero','mouth_box':[245/w,190/h,275/w,210/h],'layers':layers,'layer_sha256':{k:digest(Path(v)) for k,v in layers.items()},'cues':amplitude_cues(full[:16000].astype(float).tolist(),rows,start=0,duration=2,fps=24),'tracking':[{'at_seconds':i/fps,'offset':[40*i/fps,0],'scale':100,'rotation':0,'face_box':[(210+40*i/fps)/w,120/h,(310+40*i/fps)/w,220/h]} for i in range(48)]}
scene={'number':1,'start':0,'end':2,'source_kind':'video','_mouth_runtime':{'enabled':True,'speakers':[speaker],'video_source':True,'video_duration':2,'blinks':[],'audio_light_cues':[]}}
direction={'fit':'contain','keys':[{'t':t,'x':.5,'y':.5,'scale':1,'rotation':0,'opacity':100} for t in (0,1)],'effects':[{'type':'fireflies','story_quote':'Fireflies glow','reason':'Synthetic native effect smoke fixture','start':0,'end':1,'count':8,'size':.004,'speed':.01,'center':[.12,.25],'radius':.1,'color':[1,.9,.3],'intensity':.35,'protected_regions':[[.3,.3,.7,.65]]}]}
prepared=prepare(source,scene,{'aspect':'16:9','fps':24},direction);native=_render_native(prepared,out,2);info=_video_info(native);assert info['frames']==48 and info['fps']==24
clip=out/'voice-synced.mp4';run([ffmpeg(),'-v','error','-y','-i',str(native),'-i',str(voice),'-map','0:v:0','-map','1:a:0','-t','2','-c:v','copy','-c:a','aac',str(clip)])
counts=[];centers=[]
for tag,t in [('closed',.25),('open',.7),('after',1.75)]:
 frame=out/(tag+'-actual.png');run([ffmpeg(),'-v','error','-y','-ss',str(t),'-i',str(native),'-frames:v','1',str(frame)]);im=Image.open(frame).resize((w,h));pixels=np.asarray(im);cx=260+40*t;crop=pixels[190:210,int(cx)-15:int(cx)+15];counts.append(int(np.all(crop<60,axis=2).sum()));face=(pixels[:,:,0]>110)&(pixels[:,:,1]>90)&(pixels[:,:,2]<150);face[:120,:]=False;face[220:,:]=False;face[:,450:]=False;yy,xx=np.where(face);centers.append(float(xx.mean()));im.close()
assert counts[1]>counts[0]+40,(counts,centers)
assert abs((centers[2]-centers[0])-60)<3,centers
snapshot={'submitted_video_postwork':CONTRACT,'motion':{'enabled':True,'fps':24,'aspect':'16:9'},'scenes':[{'number':1,'start':0,'end':2},{'number':2,'start':2,'end':4}], 'subtitles':[{'text':'Fireflies glow','start':0,'end':.5,'scene_number':1},{'text':'Speaking','start':.5,'end':1.5,'scene_number':1},{'text':'Speaking again','start':2.5,'end':3.5,'scene_number':2}]}
plans=[{'number':1,'scene':{'transition':'fade_black','transition_seconds':.3}},{'number':2,'scene':{'transition':'cut'}}];ordered=[{'number':1,'path':str(clip)},{'number':2,'path':str(clip)}]
ordered=apply_transitions(snapshot,ordered,plans,out/'transitions',lambda:None)
finaldir=out/'final';finaldir.mkdir(exist_ok=True)
final=assemble_master(snapshot,sources={1:source,2:source},plans=plans,voice=voice,ordered=ordered,settings={'motion':{'enabled':True,'fps':24}},cues=[],overlay=None,final_dir=finaldir,fresh=lambda:None,ai_sources={})
final_info=_video_info(final);original_audio=pcm(voice);actual_audio=pcm(final);n=min(len(original_audio),len(actual_audio));corr=float(np.corrcoef(original_audio[:n],actual_audio[:n])[0,1]);assert corr>.98,corr
assert abs(final_info['duration']-4)<.05,final_info
receipt={'native':str(native),'final':str(final),'native_info':info,'final_info':final_info,'mouth_black_pixels_closed_open_after':counts,'face_centers':centers,'final_voice_correlation':corr,'source_sha256':digest(source),'final_voice_sha256':digest(voice),'synthetic_fixture_only':True};(out/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps(receipt))
