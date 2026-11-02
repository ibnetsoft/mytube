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

def test_quality_note_continuation_keeps_failed_face_result_truthful():
 a,b=character('A'),character('B');a['image_sha256']='hash-a';b['image_sha256']='hash-b'
 def proof(c,other):
  return {'policy':POLICY,'source_sha256':c['image_sha256'],'passed':False,'pairs':[
   {'candidate_key':c['character_key'],'candidate_sha256':c['image_sha256'],
    'other_key':other['character_key'],'other_sha256':other['image_sha256'],'result':result(False)}]}
 a['face_distinctness_review']=proof(a,b);b['face_distinctness_review']=proof(b,a)
 assert not current_cast([a,b])
 assert current_cast([a,b],allow_quality_notes=True)
 assert not a['face_distinctness_review']['passed']
 b['image_sha256']='changed'
 assert not current_cast([a,b],allow_quality_notes=True)

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

def test_reverse_success_reuses_receipt_without_codex(tmp_path):
 a=pixel(tmp_path,'a','red');b=pixel(tmp_path,'b','blue')
 reviewer=FaceDistinctnessReviewer(None,tmp_path/'reviews')
 identity=[POLICY,TASK,'B',sha(b),'A',sha(a)]
 receipt=reviewer.directory/(hashlib.sha256(json.dumps(identity).encode()).hexdigest()+'.json')
 receipt.write_text(json.dumps({'result':result()}))
 proof=reviewer.review(character('A'),a,[(character('B'),b)])
 assert proof['passed'] and proof['pairs'][0]['candidate_sha256']==sha(a)

def test_frontal_crop_cached_and_invalidated_by_source_pixels(tmp_path,monkeypatch):
 from types import SimpleNamespace
 from worker.character_face_thumbnail import extract_front_face
 import worker.character_face_thumbnail as module
 source=pixel(tmp_path,'sheet','red');calls=[]
 def run(command,**kwargs):
  calls.append(command)
  Path(command[command.index('--output-last-message')+1]).write_text(json.dumps({'front_facing':True,'box':[100,100,600,700]}))
  return SimpleNamespace(returncode=0)
 monkeypatch.setattr(module.subprocess,'run',run)
 config=SimpleNamespace(executable='codex',timeout_seconds=10)
 first,meta=extract_front_face(source,config,tmp_path/'faces')
 assert Image.open(first).size==(512,512) and meta['source_sha256']==sha(source)
 assert extract_front_face(source,None,tmp_path/'faces')[0]==first and len(calls)==1
 pixel(tmp_path,'sheet','blue')
 second,_=extract_front_face(source,config,tmp_path/'faces')
 assert first!=second and len(calls)==2

@pytest.mark.parametrize('count', [3,10])
def test_multiple_faces_use_bounded_batch_calls_and_cache(tmp_path,monkeypatch,count):
 from types import SimpleNamespace
 import worker.character_face_distinctness as module
 config=SimpleNamespace(executable='codex',timeout_seconds=10)
 reviewer=FaceDistinctnessReviewer(config,tmp_path/'reviews')
 monkeypatch.setattr(reviewer,'thumbnail',lambda p:(p,{}))
 candidate=pixel(tmp_path,'candidate','red')
 refs=[(character(str(i)),pixel(tmp_path,str(i),(i,40,90))) for i in range(count)]
 calls=[]
 def run(command,**kwargs):
  calls.append(command)
  n=command.count('--image')-1
  rows=[{'reference_index':i,'result':result(i!=0)} for i in reversed(range(n))]
  Path(command[command.index('--output-last-message')+1]).write_text(json.dumps({'results':rows}))
  return SimpleNamespace(returncode=0)
 monkeypatch.setattr(module.subprocess,'run',run)
 proof=reviewer.review(character('A'),candidate,refs)
 assert len(calls)==(count+7)//8 and len(proof['pairs'])==count
 assert not proof['passed'] and not proof['pairs'][0]['result']['passed']
 reviewer.review(character('A'),candidate,refs)
 assert len(calls)==(count+7)//8

@pytest.mark.parametrize('indices', [[0],[0,0],[0,2],[False,1]])
def test_batch_missing_duplicate_or_unknown_results_cannot_approve(tmp_path,monkeypatch,indices):
 from types import SimpleNamespace
 import worker.character_face_distinctness as module
 reviewer=FaceDistinctnessReviewer(SimpleNamespace(executable='codex',timeout_seconds=10),tmp_path/'reviews')
 monkeypatch.setattr(reviewer,'thumbnail',lambda p:(p,{}))
 candidate=pixel(tmp_path,'candidate','red')
 refs=[(character(str(i)),pixel(tmp_path,str(i),(i,40,90))) for i in range(2)]
 def run(command,**kwargs):
  Path(command[command.index('--output-last-message')+1]).write_text(json.dumps({'results':[{'reference_index':i,'result':result()} for i in indices]}))
  return SimpleNamespace(returncode=0)
 monkeypatch.setattr(module.subprocess,'run',run)
 with pytest.raises(RuntimeError,match='batch facial'):reviewer.review(character('A'),candidate,refs)
 assert not list(reviewer.directory.glob('*.json')) or all(p.name.endswith('.response.json') for p in reviewer.directory.glob('*.json'))
