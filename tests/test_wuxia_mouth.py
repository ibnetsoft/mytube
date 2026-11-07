import copy,json,shutil,sys,tempfile,unittest
from pathlib import Path
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from wuxia_mouth import prepare
from ambient_loop import digest
from wuxia_native_timeline import jsx

class SelectedMouthTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.source=self.root/'source.png';Image.new('RGB',(200,100),'navy').save(self.source)
  self.audio={'id':'audio','metadata':{'sha256':'a'*64}}
  self.mouth={'contract':'wuxia_dialogue_mouth/v1','enabled':True,'source_sha256':digest(self.source),'audio_asset_id':'audio','audio_sha256':'a'*64,'width':200,'height':100,'face_box':[.1,.1,.6,.8],'mouth_box':[.2,.3,.4,.5],'review':{'mouth_fully_visible':True,'face_large_enough':True,'occluded':False,'identity_preserved':True},'poses':{}}
  for pose in ['closed','half','open']:
   im=Image.new('RGBA',(200,100));ImageDraw.Draw(im).rectangle((41,31,78,48),fill='red');path=self.root/(pose+'.png');im.save(path);self.mouth['poses'][pose]={'sha256':digest(path),'gcs_bucket':'local','gcs_path':str(path)}
 def tearDown(self):self.tmp.cleanup()
 def run_prepare(self,mouth=None,audio=None):return prepare(self.source,[mouth or self.mouth],self.root/'prepared',lambda:None,lambda f,p:shutil.copyfile(f['gcs_path'],p),audio or self.audio)
 def test_zero_is_valid_and_reviewed_patches_are_checked(self):
  self.assertEqual(prepare(self.source,[],self.root,lambda:None,None,None),[])
  self.assertEqual(len(self.run_prepare()),1)
 def test_occlusion_small_face_and_stale_recording_are_rejected(self):
  for change in [dict(face_box=[.1,.3,.6,.4]),dict(review={**self.mouth['review'],'occluded':True}),dict(audio_sha256='b'*64)]:
   with self.assertRaisesRegex(ValueError,'conditions changed'):self.run_prepare({**self.mouth,**change})
 def test_actual_alpha_outside_lips_is_rejected_even_with_valid_hash(self):
  m=copy.deepcopy(self.mouth);path=Path(m['poses']['open']['gcs_path']);im=Image.open(path).copy();im.putpixel((190,90),(255,255,255,255));im.save(path);m['poses']['open']['sha256']=digest(path)
  with self.assertRaisesRegex(ValueError,'escaped'):self.run_prepare(m)
 def test_ae_uses_frozen_speaker_window_and_removes_patch_on_cut(self):
  m=self.run_prepare()[0]
  timeline={'states':[{'asset_id':'a','file':str(self.source),'ambient_runtime':[],'mouth_runtime':[m]}],
   'graphics':{},'samples':[{'at':0,'state':'a','mouths':[]},{'at':.1,'state':'a','mouths':[{'mouth':0,'pose':'open'}]},{'at':.2,'state':'a','mouths':[{'mouth':0,'pose':'closed'}]},{'at':.3,'state':'a','mouths':[]}]}
  source,_=jsx(timeline,1,24);data=json.loads(source.split('var WT=',1)[1].split(';\n',1)[0]);patches=data['states'][0]['patches'];self.assertEqual(patches[0]['keys'],[[.2,100],[.3,0]]);self.assertEqual(patches[2]['keys'],[[.1,100],[.2,0]])
if __name__=='__main__':unittest.main()
