import json,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'worker'))
from PIL import Image,ImageDraw
from ambient_loop import prepare_gif,prepare_runtime,frame_index,jsx,digest

class AmbientLoopTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.source=self.root/'source.png';Image.new('RGB',(100,100),'navy').save(self.source)
  frames=[]
  for color in ('red','green','blue'):
   image=Image.new('RGB',(100,100),color);frames.append(image)
  self.gif=self.root/'test.gif';frames[0].save(self.gif,save_all=True,append_images=frames[1:],duration=[100,200,50],loop=0,disposal=2)
  self.loop=prepare_gif(self.source,self.gif,self.root/'prepared',region=[0,0,.2,.2],protected_regions=[[.4,.3,.7,.8]],role='background',start_ms=100,end_ms=1000)
  for f in self.loop['frames']:f['gcs_path']=str(self.root/'prepared'/f['local_path'])
 def tearDown(self):self.tmp.cleanup()
 def runtime(self,loop=None):
  return prepare_runtime(self.source,[loop or self.loop],self.root/'runtime',lambda:None,lambda f,p:shutil.copyfile(f['gcs_path'],p))
 def test_pixels_preserve_rest_and_gif_durations(self):
  self.assertEqual([f['duration_ms'] for f in self.loop['frames']],[100,200,50])
  runtime=self.runtime()
  for file,color in zip(runtime[0]['files'],('red','green','blue')):
   with Image.open(file) as patch:
    self.assertEqual(patch.getchannel('A').getbbox(),(0,0,20,20))
    with Image.open(self.source) as base:
     composed=Image.alpha_composite(base.convert('RGBA'),patch)
     self.assertEqual(composed.getpixel((50,50)),(0,0,128,255))
  self.assertEqual([frame_index(self.loop,t) for t in [99,100,199,200,399,400,449,450,999,1000]],[None,0,0,1,1,2,2,0,1,None])
 def test_actual_pixels_escape_and_hash_mutation_rejected(self):
  f=self.loop['frames'][0];path=Path(f['gcs_path'])
  with Image.open(path) as original:image=original.copy()
  image.putpixel((80,80),(255,0,0,255));image.save(path)
  with self.assertRaisesRegex(ValueError,'checksum'):self.runtime()
  f['sha256']=digest(path)
  with self.assertRaisesRegex(ValueError,'escaped'):self.runtime()
 def test_source_mutation_rejected(self):
  Image.new('RGB',(100,100),'white').save(self.source)
  with self.assertRaisesRegex(ValueError,'base image changed'):self.runtime()
 def test_js_python_timing_parity_and_ae_hold_keys(self):
  times=[i/24*1000 for i in range(24)]+[100,200,400,450,1000]
  js="const m=require('./tests/load-ts-module.cjs')('lib/stdAmbientLoop.ts');const x=JSON.parse(process.argv[1]);console.log(JSON.stringify(x.times.map(t=>m.ambientFrameIndex(x.loop,t))));"
  out=subprocess.check_output(['node','-e',js,json.dumps({'loop':self.loop,'times':times})],cwd=ROOT/'auth-web',text=True)
  self.assertEqual(json.loads(out),[frame_index(self.loop,t) for t in times])
  script=jsx(self.runtime(),1,24)
  self.assertIn('KeyframeInterpolationType.HOLD',script)
  from ae_flat_scene import write_jsx
  plan={'width':100,'height':100,'output':{'width':1920,'height':1080},'camera':[{'t':t,'x':.5,'y':.5,'scale':1,'rotation':0,'opacity':100} for t in (0,1)],'fit':'cover','layers':[{'id':'original','role':'background','motion':[{'t':t,'x':0,'y':0,'scale':1,'rotation':0,'opacity':100} for t in (0,1)]}],'effects':[],'ambient_runtime':self.runtime()}
  target=self.root/'scene.jsx';write_jsx(plan,{'original':self.source},self.root/'scene.aep',self.root/'native.avi',target,1)
  text=target.read_text();self.assertLess(text.index('var AMBIENT='),text.index('applySceneEffects(source,semanticLayers)'))
  self.assertIn('ambient_\'',text)

if __name__=='__main__':unittest.main()

class WuxiaNativeTest(unittest.TestCase):
 setUp=AmbientLoopTest.setUp
 tearDown=AmbientLoopTest.tearDown
 def test_multiple_state_cuts_lettering_and_ambient_share_clock(self):
  from wuxia_native_timeline import prepare,jsx as native_jsx
  other=self.root/'other.png';Image.new('RGB',(100,100),'orange').save(other)
  timeline={'contract':'wuxia_native_timeline/v1','states':[
   {'asset_id':'a','sha256':digest(self.source),'gcs_bucket':'local','gcs_path':str(self.source),'ambient_loops':[self.loop]},
   {'asset_id':'b','sha256':digest(other),'gcs_bucket':'local','gcs_path':str(other),'ambient_loops':[]}],
   'graphics':{},'samples':[{'at':i/24,'state':'a' if i<12 else 'b','graphics':[],'ambient':([{'loop':0,'frame':frame_index(self.loop,i/24*1000)}] if i<12 and frame_index(self.loop,i/24*1000) is not None else [])} for i in range(24)]}
  runtime=prepare(timeline,self.root/'native',lambda:None,lambda f,p:shutil.copyfile(f['gcs_path'],p),1,24)
  source,graphics=native_jsx(runtime,1,24)
  data=json.loads(source.split('var WT=',1)[1].split(';\n',1)[0])
  self.assertEqual(data['states'][0]['keys'],[[0,100],[.5,0]])
  self.assertEqual(data['states'][1]['keys'],[[.5,100]])
  self.assertTrue(any(p['keys'] for p in data['states'][0]['patches']))
  for patch in data['states'][0]['patches']:
   self.assertTrue(all(t<=.5 for t,opacity in patch['keys']))
  self.assertIn('source.layers.add',source)
  self.assertIn('comp.layers.addText',graphics)
 def test_ambient_cannot_bypass_native_scene_render(self):
  from uploaded_video_passthrough import eligible
  direction={'keys':[dict(t=t,x=.5,y=.5,scale=1,rotation=0,opacity=100) for t in (0,1)],'effects':[],'transition':'cut'}
  self.assertFalse(eligible({'source_kind':'image','ambient_loops':[self.loop]},{'scene':direction},runtime_resolved=True))
  self.assertFalse(eligible({'source_kind':'image','wuxia_timeline':{'contract':'wuxia_native_timeline/v1'}},{'scene':direction},runtime_resolved=True))
 def test_full_ae_writer_keeps_authored_lettering_after_camera_binding(self):
  from ae_flat_scene import write_jsx
  timeline={'states':[{'asset_id':'a','file':str(self.source),'ambient_runtime':[]}],
            'graphics':{},'samples':[{'at':i/24,'state':'a','graphics':[],'ambient':[]} for i in range(24)]}
  plan={'width':100,'height':100,'output':{'width':1920,'height':1080},'camera':[{'t':t,'x':.5,'y':.5,'scale':1,'rotation':0,'opacity':100} for t in (0,1)],'fit':'cover','layers':[{'id':'original','role':'background','motion':[{'t':t,'x':0,'y':0,'scale':1,'rotation':0,'opacity':100} for t in (0,1)]}],'effects':[],'wuxia_runtime':timeline}
  target=self.root/'native-scene.jsx';write_jsx(plan,{'original':self.source},self.root/'scene.aep',self.root/'native.avi',target,1)
  text=target.read_text()
  self.assertIn('comp.layers.addText',text)
  self.assertIn('semanticLayers.original.enabled=false',text)
  self.assertIn('whold(op);whold(sc);whold(rot)',text)
  subprocess.run(['node','--check'],input=text,text=True,capture_output=True,check=True)
