import base64,hashlib,importlib.util,json
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('release_wuxia',Path(__file__).resolve().parents[1]/'scripts/std_release_wuxia_download_cache.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

@pytest.mark.parametrize('mismatch',['local','remote',None])
def test_only_reproducible_frozen_download_is_released(tmp_path,mismatch):
 data=b'original-state';p=tmp_path/'state.png';p.write_bytes(data)
 asset={'sha256':hashlib.sha256(data).hexdigest(),'gcs_bucket':'original-bucket','gcs_path':'immutable/state.png'}
 meta={'size':len(data),'md5Hash':base64.b64encode(hashlib.md5(data).digest()).decode(),'generation':'123'}
 if mismatch=='local':asset['sha256']='0'*64
 if mismatch=='remote':meta['md5Hash']='bad'
 if mismatch:
  with pytest.raises(ValueError):module.release(p,asset,meta)
  assert p.read_bytes()==data
 else:
  result=module.release(p,asset,meta)
  assert not p.exists() and result['released']
  receipt=json.loads(p.with_suffix('.download-cache.json').read_text())
  assert receipt['gcs_path']==asset['gcs_path'] and receipt['generation']=='123'
