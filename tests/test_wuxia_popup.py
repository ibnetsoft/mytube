import copy,json,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
from PIL import Image
from worker.wuxia_popup import prepare,enable_new_package
from worker.ambient_loop import digest,frame_index,prepare_runtime

ROOT=Path(__file__).resolve().parents[1]
class PopupTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.source=self.root/'source.png';Image.new('RGB',(320,180),'navy').save(self.source)
  self.pkg={'scenes':[{'scene_id':f'S{i+1:02}', 'preview_start_seconds':i*10,'preview_duration_seconds':10,
    'states':[dict(asset_id='a',sha256=digest(self.source),start=0,end=1)]} for i in range(30)]}
  self.cut=dict(scene_id='S01',state_asset_id='a',source_path=str(self.source),reviewed_source_sha256=digest(self.source),
    source_reviewed=True,reason='살기 감지의 눈빛',crop=[.1,.1,.6,.5],region=[.05,.55,.45,.95],
    protected_regions=[[.6,.1,.9,.5]],start_ms=1000,duration_ms=2200)
  self.plan=dict(contract='wuxia_popup_plan/v1',cuts=[self.cut])
 def tearDown(self):self.tmp.cleanup()
 def upload(self,path,key):return 'local',str(path),'https://example.com/'+key
 def test_source_unchanged_and_shared_clock_runtime(self):
  before=copy.deepcopy(self.pkg);sha=digest(self.source)
  package,report=prepare(self.pkg,self.plan,self.root/'out',self.upload)
  self.assertEqual(self.pkg,before);self.assertEqual(digest(self.source),sha)
  loop=package['scenes'][0]['states'][0]['ambient_loops'][0]
  self.assertFalse(loop['repeat'])
  times=[999,1000,1059,1060,1119,1120,3199,3200]
  expected=[None,0,0,1,1,2,8,None]
  self.assertEqual([frame_index(loop,t) for t in times],expected)
  js="const m=require('./tests/load-ts-module.cjs')('lib/stdAmbientLoop.ts');const x=JSON.parse(process.argv[1]);console.log(JSON.stringify(x.times.map(t=>m.ambientFrameIndex(x.loop,t))));"
  out=subprocess.check_output(['node','-e',js,json.dumps(dict(loop=loop,times=times))],cwd=ROOT/'auth-web',text=True)
  self.assertEqual(json.loads(out),expected)
  runtime=prepare_runtime(self.source,[loop],self.root/'runtime',lambda:None,lambda f,p:shutil.copyfile(f['gcs_path'],p))
  with Image.open(runtime[0]['files'][-1]) as patch:
   self.assertEqual(patch.getpixel((250,50))[3],0)
  self.assertEqual(report['count'],1)
  project={'project_payload':{'structure':{'wuxia_ae_package':{'contract':'wuxia_still_ae_episode/v1',**package}}}}
  source=dict(metadata=dict(sha256=sha,gcs_bucket='local',gcs_path=str(self.source)))
  for state in package['scenes'][0]['states']:
   state['media_url']='https://example.com/source.png'
  js="const m=require('./tests/load-ts-module.cjs')('lib/stdWuxiaNative.ts');const x=JSON.parse(process.argv[1]);console.log(JSON.stringify(m.freezeWuxiaScene(x.project,1,[],0,10,24,x.source)));"
  timeline=json.loads(subprocess.check_output(['node','-e',js,json.dumps(dict(project=project,source=source))],cwd=ROOT/'auth-web',text=True))
  sys.path.insert(0,str(ROOT/'worker'))
  from wuxia_native_timeline import prepare as native_prepare,jsx
  native=native_prepare(timeline,self.root/'native',lambda:None,lambda f,p:shutil.copyfile(f['gcs_path'],p),10,24)
  script,_=jsx(native,10,24)
  self.assertIn('KeyframeInterpolationType.HOLD',script)
  data=json.loads(script.split('var WT=',1)[1].split(';\n',1)[0])
  keys=[key for patch in data['states'][0]['patches'] for key in patch['keys']]
  self.assertTrue(any(opacity==100 and 1.12<=at<3.2 for at,opacity in keys))
  self.assertTrue(any(opacity==0 and 3.2<=at<3.3 for at,opacity in keys))
 def test_sliding_exit_and_protected_travel(self):
  for exit_style in ('left','down'):
   plan=copy.deepcopy(self.plan);plan['cuts'][0]['exit']=exit_style
   package,_=prepare(self.pkg,plan,self.root/exit_style,self.upload)
   loop=package['scenes'][0]['states'][0]['ambient_loops'][0]
   self.assertEqual(sum(f['duration_ms'] for f in loop['frames']),2200)
   self.assertLessEqual(len(loop['frames']),16)
   runtime=prepare_runtime(self.source,[loop],self.root/(exit_style+'-runtime'),lambda:None,lambda f,p:shutil.copyfile(f['gcs_path'],p))
   with Image.open(runtime[0]['files'][-1]) as image:self.assertIsNone(image.getchannel('A').getbbox())
  bad=copy.deepcopy(self.plan);bad['cuts'][0].update(exit='left',protected_regions=[[0,.6,.04,.9]])
  with self.assertRaises(ValueError):prepare(self.pkg,bad,self.root/'overlap')
 def test_new_wuxia_only_preserves_opt_out(self):
  self.assertNotIn('wuxia_popup_policy',enable_new_package({},dict(image_style='watercolor'))['structure'])
  p=enable_new_package({},dict(image_style='wuxia_webtoon'))
  self.assertTrue(p['structure']['wuxia_popup_policy']['auto_prepare'])
  p['structure']['wuxia_popup_policy']['enabled']=False
  self.assertFalse(enable_new_package(p,dict(image_style='wuxia_webtoon'))['structure']['wuxia_popup_policy']['enabled'])
 def test_local_only_and_zero_candidate(self):
  package,report=prepare(self.pkg,self.plan,self.root/'local')
  self.assertIsNone(package);self.assertFalse(report['published'])
  _,report=prepare(self.pkg,dict(contract='wuxia_popup_plan/v1',cuts=[]),self.root/'empty')
  self.assertEqual(report['status'],'not_required')
 def test_reject_overlap_stale_source_exposure_and_excess(self):
  cases=[]
  for field,value in [('region',[.5,.1,.9,.5]),('reviewed_source_sha256','0'*64),('start_ms',9600),('source_reviewed',False),('duration_ms',900)]:
   bad=copy.deepcopy(self.plan);bad['cuts'][0][field]=value;cases.append(bad)
  bad=copy.deepcopy(self.plan);bad['cuts']*=6;cases.append(bad)
  bad=copy.deepcopy(self.plan);bad['cuts'].append({**self.cut,'scene_id':'S02'});cases.append(bad)
  for plan in cases:
   with self.subTest(plan=plan),self.assertRaises(ValueError):prepare(self.pkg,plan,self.root/'bad')
