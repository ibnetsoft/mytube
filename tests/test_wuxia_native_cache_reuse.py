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
