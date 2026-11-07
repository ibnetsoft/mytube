import json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from wuxia_render_cache import release_temporary_movie

def test_only_generated_temporary_is_released_after_complete_decode(tmp_path,monkeypatch):
 monkeypatch.setenv('AIR_WUXIA_RELEASE_NATIVE_TEMP','1');src=tmp_path/'native.mp4';out=tmp_path/'base.mp4';src.write_bytes(b'native');out.write_bytes(b'encoded');calls=[]
 def verify(p):calls.append(p);return dict(width=1920,height=1080,duration=7)
 release_temporary_movie(src,out,tmp_path,verify=verify)
 assert calls==[src,out] and out.read_bytes()==b'encoded' and not src.exists()
 receipt=json.loads((tmp_path/'native-temporary-receipt.json').read_text());assert receipt['released'] and receipt['full_decode_verified']

def test_decode_failure_preserves_native_for_recovery(tmp_path,monkeypatch):
 monkeypatch.setenv('AIR_WUXIA_RELEASE_NATIVE_TEMP','1');src=tmp_path/'native.mp4';out=tmp_path/'base.mp4';src.write_bytes(b'native');out.write_bytes(b'broken')
 def fail(p):raise ValueError('decode failed')
 with pytest.raises(ValueError):release_temporary_movie(src,out,tmp_path,verify=fail)
 assert src.read_bytes()==b'native'

def test_source_media_and_opt_out_are_preserved(tmp_path,monkeypatch):
 src=tmp_path/'uploaded-original.mp4';out=tmp_path/'base.mp4';src.write_bytes(b'original');out.write_bytes(b'encoded')
 monkeypatch.delenv('AIR_WUXIA_RELEASE_NATIVE_TEMP',raising=False);release_temporary_movie(src,out,tmp_path);assert src.exists()
 monkeypatch.setenv('AIR_WUXIA_RELEASE_NATIVE_TEMP','1')
 with pytest.raises(ValueError):release_temporary_movie(src,out,tmp_path)
 assert src.read_bytes()==b'original'
