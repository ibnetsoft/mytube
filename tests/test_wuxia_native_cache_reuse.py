import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from services.video_playback_policy import POLICY
from ae_flat_scene import VERSION
from motion_automation_worker import renderer_cache_is_current

def test_frozen_wuxia_native_output_is_never_misclassified_as_source_passthrough(monkeypatch):
 import uploaded_video_passthrough
 monkeypatch.setattr(uploaded_video_passthrough,'eligible',lambda *a,**k:True)
 snapshot={'scenes':[{'number':14,'source_kind':'image','start':0,'end':3,'wuxia_timeline':{'samples':[]}}],'renderer':{'engine':'ae'}}
 record={'number':14,'ambient_renderer':'ambient_loop/v1','video_playback_policy':POLICY,'adobe_flat_renderer':VERSION}
 assert renderer_cache_is_current(snapshot,record)
 assert not renderer_cache_is_current(snapshot,{**record,'adobe_flat_renderer':'outdated'})


def test_actual_short_native_movie_is_repaired_only_where_global_clock_requires_it(tmp_path):
 import subprocess,imageio_ffmpeg
 from motion_automation_worker import native_cache_covers_frame_clock
 movie=tmp_path/'rounded-AE-cut.mp4'
 subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-f','lavfi','-i','color=red:s=32x18:r=24','-frames:v','6','-c:v','libx264',str(movie)],check=True)
 snapshot={'motion':{'fps':24}}
 assert not native_cache_covers_frame_clock(snapshot,{'start':0,'end':.26,'wuxia_timeline':{'samples':[{}]*7}},{'path':str(movie)})
 assert native_cache_covers_frame_clock(snapshot,{'start':.26,'end':.52,'wuxia_timeline':{'samples':[{}]*7}},{'path':str(movie)})
