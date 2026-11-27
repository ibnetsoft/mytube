import copy,shutil,tempfile,unittest
from pathlib import Path
from PIL import Image
from worker.wuxia_hatch import prepare
from worker.ambient_loop import digest,frame_index,prepare_runtime
class HatchTest(unittest.TestCase):
 def test_blink_preserves_source_and_protected_pixels(self):
  with tempfile.TemporaryDirectory() as root:
   root=Path(root);source=root/'source.png';Image.new('RGB',(320,180),'gray').save(source);sha=digest(source)
   spec=dict(source_reviewed=True,source_sha256=sha,reason='주먹에 힘을 주는 긴장',region=[.05,.55,.4,.9],protected_regions=[[.5,.1,.9,.5]],start_ms=100,duration_ms=1400)
   loop=prepare(source,spec,root/'out')
   self.assertEqual(digest(source),sha)
   self.assertEqual([frame_index(loop,t) for t in [99,100,299,300,499,500,1499,1500]],[None,0,0,1,1,0,0,None])
   for frame in loop['frames']:frame['gcs_path']=frame['local_path']
   runtime=prepare_runtime(source,[loop],root/'runtime',lambda:None,lambda f,p:shutil.copyfile(f['gcs_path'],p))
   with Image.open(runtime[0]['files'][0]) as visible:
    self.assertIsNotNone(visible.getchannel('A').getbbox());self.assertEqual(visible.getpixel((220,50))[3],0)
   with Image.open(runtime[0]['files'][1]) as blank:self.assertIsNone(blank.getchannel('A').getbbox())
   for patch in [dict(source_sha256='0'*64),dict(blink_interval_ms=40),dict(region=[.4,.1,.8,.5])]:
    with self.subTest(patch=patch),self.assertRaises(ValueError):prepare(source,{**spec,**patch},root/'bad')
