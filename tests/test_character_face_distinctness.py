import sys,copy,json,hashlib
from pathlib import Path
import pytest
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from worker.character_face_distinctness import *
from worker.codex_character_assets import generate_character_references

def result(passed=True):return {'passed':passed,'similarity':'low' if passed else 'high','differences':[{'axis':a,'evidence':'Observed structural '+a} for a in ('eyes','nose','jaw')] if passed else [],'reason':'Actual face comparison','repair_instruction':'' if passed else 'Replace the narrow angular jaw and closely spaced almond eyes with a rounded jaw and wide set eyes; preserve age.'}
def character(name):return {'name':name,'character_key':name,'visual_dna_en':'Adult face '+name,'wardrobe_en':'Everyday clothes','hair_design_en':'Short hair'}
def pixel(tmp_path,name,color):
 p=tmp_path/(name+'.png');Image.new('RGB',(512,512),color).save(p);return p

def test_no_approval_from_clothes_or_missing_structural_evidence():
 for value in ({**result(),'differences':[{'axis':'clothes','evidence':'Different shirt'}]}, {**result(),'differences':result()['differences'][:2]}, {**result(),'similarity':'uncertain'}):
  with pytest.raises(RuntimeError):validate(value)
 assert validate(result())['passed']

def test_identical_actual_pixels_rejected_without_any_model(tmp_path):
 p=pixel(tmp_path,'same','red');r=FaceDistinctnessReviewer(None,tmp_path/'review').review(character('A'),p,[(character('B'),p)])
 assert not r['passed'] and r['pairs'][0]['result']['similarity']=='high'

def test_comparison_unavailable_cannot_publish_a_different_bitmap(tmp_path):
 a=pixel(tmp_path,'a','red');b=pixel(tmp_path,'b','blue')
 with pytest.raises(RuntimeError,match='required'):FaceDistinctnessReviewer(None,tmp_path/'review').review(character('A'),a,[(character('B'),b)])

class Reviewer:
 def __init__(self,reject=None):self.reject=reject;self.calls=[]
 def review(self,c,p,refs):
  self.calls.append((c['name'],Path(p).name,[o['name'] for o,_ in refs]));pairs=[]
  for o,r in refs:pairs.append({'candidate_key':c['character_key'],'candidate_sha256':sha(p),'other_key':o['character_key'],'other_sha256':sha(r),'result':result(not self.reject or not self.reject(c,p))})
  return {'policy':POLICY,'source_sha256':sha(p),'passed':all(v['result']['passed'] for v in pairs),'pairs':pairs}
class Store:
 def __init__(self):self.published=[];self.saved=[]
 def publish(self,topic,c,p,fingerprint,payload):
  self.published.append(Path(p).name);return {**c,'image_url':'/'+Path(p).name,'gcs_path':Path(p).name,'reference_fingerprint':fingerprint}
 def save_design(self,topic,c,*args):self.saved.append(copy.deepcopy(c))
class Generator:
 def __init__(self,d):self.d=d;self.count={};self.prompts=[]
 def generate(self,prompt):
  self.prompts.append(prompt);name='B' if 'Character: B;' in prompt else 'A';i=self.count.get(name,0);self.count[name]=i+1;return pixel(self.d,name+str(i),(i*30,20 if name=='A' else 80,100))
def context():return {'script':'final','main_character':character('A'),'supporting_characters':[character('B')]}
def test_failed_candidate_is_repaired_before_publish_and_final_cast_is_hash_bound(tmp_path):
 g=Generator(tmp_path);store=Store();review=Reviewer(lambda c,p:Path(p).stem=='B0')
 ready=generate_character_references(context(),{'topic_queue_id':1},None,tmp_path,generator=g,store=store,reviewer=review)
 assert store.published==['A0.png','B1.png'] and 'FACE IDENTITY REPAIR' in g.prompts[-1]
 cast=[ready['main_character'],*ready['supporting_characters']];assert current_cast(cast)
 stale=copy.deepcopy(cast);stale[1]['image_sha256']='0'*64;assert not current_cast(stale)
 assert all(c['face_distinctness_review']['pairs'] for c in store.saved[-2:])
def test_retry_limit_stops_and_never_publishes_similar_candidate(tmp_path):
 g=Generator(tmp_path);store=Store()
 with pytest.raises(RuntimeError,match='two repairs'):generate_character_references(context(),{'topic_queue_id':1},None,tmp_path,generator=g,store=store,reviewer=Reviewer(lambda c,p:c['name']=='B'))
 assert g.count['B']==3 and store.published==['A0.png']
def test_saved_similar_cast_cannot_use_reuse_fast_path(tmp_path):
 path=pixel(tmp_path,'same','red')
 class Saved(Store):
  def load_references(self,t):return [{**character(n),'image_url':'/'+n,'gcs_path':n} for n in ('A','B')]
  def load_portrait(self,c,d):return path
 store=Saved()
 with pytest.raises(RuntimeError,match='Saved character faces'):generate_character_references(context(),{'topic_queue_id':1},None,tmp_path,generator=Generator(tmp_path),store=store)
 assert not store.published and not store.saved
