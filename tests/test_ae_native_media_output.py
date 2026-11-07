from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
import ae_scene_production as production

@pytest.mark.parametrize('duration_delta',[0,-1])
def test_native_ae_writes_to_media_drive_and_rejects_truncated_output(tmp_path,monkeypatch,duration_delta):
 import motion_media_storage,adobe_tools,ae_highlight_worker,ae_flat_scene
 work=tmp_path/'project/output/codex-local-console/motion-automation/job/scene-25/attempt-0';work.mkdir(parents=True)
 monkeypatch.setattr(motion_media_storage,'ROOT',tmp_path/'project')
 monkeypatch.setenv('AIR_MOTION_MEDIA_ROOT',str(tmp_path/'media'))
 monkeypatch.setattr(adobe_tools,'find_afterfx',lambda:'afterfx')
 monkeypatch.setattr(adobe_tools,'find_aerender',lambda:'aerender')
 capture={}
 def writer(plan,layers,project,native,jsx,duration,fps):capture.update(project=project,native=native,jsx=jsx)
 monkeypatch.setattr(ae_flat_scene,'write_jsx',writer)
 monkeypatch.setattr(ae_highlight_worker,'_run_afterfx_script',lambda *a,**k:None)
 def render(args,**kwargs):
  assert Path(args[args.index('-output')+1])==capture['native']
  capture['native'].with_suffix('.mp4').write_bytes(b'native-output-test')
 monkeypatch.setattr(ae_highlight_worker,'_run_checked',render)
 monkeypatch.setattr(production,'_video_info',lambda path:{'duration':3+duration_delta})
 prepared={'plan':{'camera':[]},'layers':{},'flat_media':True,'fps':24}
 if duration_delta:
  with pytest.raises(ValueError,match='approved scene duration'):production._render_native(prepared,work,3)
 else:
  result=production._render_native(prepared,work,3)
  assert result==tmp_path/'media/job/scene-25/attempt-0/native.mp4'
 assert capture['project'].parent==work and capture['jsx'].parent==work
