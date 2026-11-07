import subprocess,wave
import numpy as np
import imageio_ffmpeg
from services.ffmpeg_slideshow_service import native_sequence_frame_counts,render_ffmpeg_slideshow


def test_native_boundaries_do_not_accumulate_independent_scene_rounding(tmp_path,monkeypatch):
 ff=imageio_ffmpeg.get_ffmpeg_exe();audio=tmp_path/'voice.wav';sources=[]
 for color in ['red','green','blue','yellow']:
  source=tmp_path/(color+'.mp4');subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','color='+color+':s=32x18:r=24','-frames:v','7','-c:v','libx264',str(source)],check=True);sources.append(str(source))
 with wave.open(str(audio),'wb')as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(48000);f.writeframes(b'\0\0'*49920)
 settings={'motion':{'enabled':True,'fps':24,'scenes':{str(i):{'direction':'Reviewed scene artifact'}for i in range(4)}}}
 output=render_ffmpeg_slideshow(temp_dir=str(tmp_path),images=sources,durations=[.26]*4,audio_path=str(audio),subtitles=[],subtitle_settings=settings,image_effects=['none']*4,transition_effects=['none']*4,resolution=(32,18),use_gpu=False)
 reader=imageio_ffmpeg.read_frames(output);meta=next(reader);frames=list(reader)
 assert meta['fps']==24 and len(frames)==25
 colors=np.array([[255,0,0],[0,128,0],[0,0,255],[255,255,0]])
 labels=[int(np.argmin(np.linalg.norm(colors-np.frombuffer(f,dtype=np.uint8)[:3],axis=1)))for f in frames]
 assert [labels.count(i)for i in range(4)]==[7,6,6,6] # old duration trimming yields [6,6,6,6]
 assert native_sequence_frame_counts([.26]*4,24)==[7,6,6,6]
