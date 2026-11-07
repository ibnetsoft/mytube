import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from render_input_pins import RenderInputPins

def test_source_pins_are_reused_and_released_without_changing_bytes_or_permissions(tmp_path):
 source=tmp_path/'final-voice.mp3';source.write_bytes(b'verified narration')
 before=source.stat().st_mode;pins=RenderInputPins();pins.pin(source);pins.pin(source)
 assert len(pins.handles)==1 and source.read_bytes()==b'verified narration'
 handle=next(iter(pins.handles.values()));assert not handle.closed
 if os.name=='nt':
  try:source.unlink()
  except PermissionError:pass
  else:raise AssertionError('Active Windows render input was not protected')
 pins.close();assert handle.closed and source.stat().st_mode==before
 assert source.read_bytes()==b'verified narration';source.unlink();assert not source.exists()
