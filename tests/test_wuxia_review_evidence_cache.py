import sys,json
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from wuxia_render_cache import release_review_evidence

def test_derived_evidence_can_be_recreated_without_deleting_master(tmp_path,monkeypatch):
 monkeypatch.setenv('AIR_WUXIA_RELEASE_NATIVE_TEMP','1')
 master=tmp_path/'master.mp4';master.write_bytes(b'authoritative movie')
 frame=tmp_path/'caption-3-middle.jpg';frame.write_bytes(b'derived pixels')
 clip=tmp_path/'review-1.mp4';clip.write_bytes(b'derived excerpt')
 release_review_evidence([str(frame)],clip,tmp_path,1,master)
 assert master.read_bytes()==b'authoritative movie' and not frame.exists() and not clip.exists()
 r=json.loads((tmp_path/'review-evidence-1.json').read_text());assert len(r['files'])==2


def test_invalid_cache_entry_preserves_every_file(tmp_path,monkeypatch):
 monkeypatch.setenv('AIR_WUXIA_RELEASE_NATIVE_TEMP','1')
 master=tmp_path/'master.mp4';master.write_bytes(b'master')
 frame=tmp_path/'caption-3-middle.jpg';frame.write_bytes(b'frame')
 clip=tmp_path/'review-1.mp4';clip.write_bytes(b'clip')
 with pytest.raises(ValueError):release_review_evidence([str(frame),str(master)],clip,tmp_path,1,master)
 assert frame.exists() and clip.exists() and master.read_bytes()==b'master'
