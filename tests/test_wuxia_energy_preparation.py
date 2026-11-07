import copy,hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
from worker.wuxia_energy_preparation import enable_new_package,selection,prepare_state
from worker.ambient_loop import frame_index,prepare_runtime,digest

class EnergyTests(unittest.TestCase):
 def test_new_only_and_optout(self):
  p={'structure':{'image_style':'wuxia_webtoon'}}
  self.assertNotIn('wuxia_energy_policy',enable_new_package(copy.deepcopy(p),{'mode':'edit'})['structure'])
  self.assertNotIn('wuxia_energy_policy',enable_new_package(copy.deepcopy(p),{'mode':'new','wuxia_auto_energy':False})['structure'])
  self.assertTrue(enable_new_package(p,{'mode':'new'})['structure']['wuxia_mouth_policy']['energy_auto']['auto_prepare'])
 def test_uncertain_or_missing_evidence_never_becomes_absent(self):
  for v in [{'source_sha256':'a'*64,'decision':'uncertain','reason':'occluded','regions':[{}]},{'source_sha256':'b'*64,'decision':'absent','reason':'nothing','regions':[]}]:
   with self.assertRaises(ValueError):selection(v,'a'*64)
 def test_actual_generic_energy_protected_and_full_lifetime(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'original.png';plate=root/'plate.png'
   im=Image.new('RGB',(512,512),(20,22,25));d=ImageDraw.Draw(im);d.rectangle((220,130,280,460),fill=(170,50,40));im.save(plate)
   d.line((310,130,345,300,315,450),fill=(255,200,60),width=12);im.save(source);sha=digest(source)
   region={'kind':'body','region':[.55,.2,.75,.95],'energy_polygons':[[[.55,.2],[.75,.2],[.75,.95],[.55,.95]]],'protected_polygons':[[[.4,.2],[.55,.2],[.55,.95],[.4,.95]]],'amplitude_px':5,'reason':'Visible golden body qi beside stationary torso'}
   class Runner:
    def _stage(self,job,name,context,task):
     self.assertion(context)
     if name=='energy_actual_selection':return {'source_sha256':sha,'decision':'present','reason':'Golden qi visible at right of body','regions':[region]}
     return dict(source_sha256=sha,passed=True,people_fixed=True,blade_fixed=True,lettering_fixed=True,energy_only=True,no_ghosts_or_seams=True,evidence='Actual composed phases reviewed')
    def assertion(self,c):
     assert all(Path(p).is_file() for p in c['_local_image_paths'])
   class Generator:
    def generate(self,**kw):return plate
   published={}
   def upload(path,sha):
    published[sha]=path
    return dict(gcs_bucket='qa',gcs_path=sha+'.png',media_url='https://example.test/'+sha+'.png',sha256=sha)
   def download(ref,path):path.write_bytes(source.read_bytes())
   with patch('worker.wuxia_energy_preparation.ROOT',root/'prepared'):
    r=prepare_state({'sha256':sha,'gcs_bucket':'qa','gcs_path':'original.png'}, {},'test',download,upload,runner=Runner(),generator=Generator())
   loop=r['loops'][0];self.assertTrue(loop['repeat']);self.assertEqual(len(loop['frames']),16)
   self.assertIsNotNone(frame_index(loop,8999));self.assertIsNotNone(frame_index(loop,57000))
   self.assertGreater(len({f['sha256'] for f in loop['frames']}),1)
   for path in published.values():
    merged=im.convert('RGBA');merged.alpha_composite(Image.open(path));self.assertEqual(merged.crop((220,130,280,460)).tobytes(),im.convert('RGBA').crop((220,130,280,460)).tobytes())
   prepare_runtime(source,[loop],root/'runtime',lambda:None,lambda f,p:p.write_bytes(published[f['sha256']].read_bytes()))
   cached_state=dict(sha256=sha,gcs_bucket='qa',gcs_path='original.png',energy_preparation={k:v for k,v in r.items() if k!='loops'},ambient_loops=r['loops'])
   with patch('worker.wuxia_energy_preparation.ROOT',root/'reuse'):
    reused=prepare_state(cached_state,{},'test',lambda f,p:p.write_bytes((source if f.get('sha256')==sha else published[f['sha256']]).read_bytes()),lambda *_:self.fail('Reviewed cache must not republish'),runner=object(),generator=object())
   self.assertEqual(reused['loops'],r['loops'])

 def test_absent_skips_generation_and_publication(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'source.png';Image.new('RGB',(512,512),'blue').save(p);sha=digest(p)
   class Runner:
    def _stage(self,*args):return {'source_sha256':sha,'decision':'absent','reason':'Flat blue clothing; no emitted energy','regions':[]}
   with patch('worker.wuxia_energy_preparation.ROOT',root/'out'):
    r=prepare_state(dict(sha256=sha,gcs_bucket='qa',gcs_path='s'),{},'test',lambda ref,out:out.write_bytes(p.read_bytes()),lambda *_:self.fail('Absent must not upload'),runner=Runner(),generator=object())
   self.assertEqual(r['decision'],'absent');self.assertEqual(r['loops'],[])
if __name__=='__main__':unittest.main()

def test_uncertain_actual_selection_is_a_quality_note_not_absence(tmp_path,monkeypatch):
 from worker import wuxia_energy_preparation as w
 source=tmp_path/'source.png';Image.new('RGB',(512,512),'gray').save(source);sha=digest(source)
 class Runner:
  def _stage(self,*args):return dict(source_sha256=sha,decision='uncertain',reason='Actual luminous rim could be reflected light; preserve source',regions=[])
 monkeypatch.setattr(w,'ROOT',tmp_path/'cache')
 result=w.prepare_state(dict(sha256=sha,gcs_bucket='qa',gcs_path='s'),{},'uncertain',lambda _,p:p.write_bytes(source.read_bytes()),lambda *_:(_ for _ in ()).throw(AssertionError('Uncertain must not publish')),runner=Runner(),generator=object())
 assert result['decision']=='uncertain' and result['quality_notes'] and result['loops']==[]
