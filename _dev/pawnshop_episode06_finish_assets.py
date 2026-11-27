import copy,hashlib,json,sys,time
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env',override=False)
from worker.script_worker_store import ScriptStore
from worker.codex_character_assets import CharacterAssetStore,digest
from worker.gcs_media_storage import _upload_gcs_file
from worker.cowork_scene_assets import _download_gcs_bytes
EP=ROOT/'output/pawnshop-series/episode-06';P=EP/'image-production';store=ScriptStore();cs=CharacterAssetStore()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2))
def row():
 r=store.request('GET','topics_queue',params={'select':'*','id':'eq.3427'})[0][0]
 initial=json.loads((P/'source-topic.json').read_text());assert r['pregenerated_script']==initial['pregenerated_script']
 assert r['status']=='pending' and not r.get('assigned_employee_email'),'Preserve ownership changes'
 return r
r=row();sha=hashlib.sha256(r['pregenerated_script'].encode()).hexdigest();receipt={'script_sha256':sha,'thumbnail_text':['期限のない借金','断れなくなる']}
for name,role in [('thumbnail-art.png','background'),('thumbnail-final.png','final')]:
 p=EP/name;h=hashlib.sha256(p.read_bytes()).hexdigest();b,k,u=_upload_gcs_file(p,f'topics/3427/thumbnail/{h}.png','image/png');assert hashlib.sha256(_download_gcs_bytes(b,k)).hexdigest()==h
 receipt[role]={'url':u,'bucket':b,'path':k,'sha256':h,'storage_readback_verified':True}
save(EP/'thumbnail-publication-receipt.json',receipt)
identity=json.loads((P/'worker-character-identity.json').read_text());characters=[identity['main_character']]+identity['supporting_characters'];dest=P/'characters';dest.mkdir(exist_ok=True)
mapnames={'三崎奈緒':('cast-sheet-1-v3.png',0,2,2),'三崎修平':('cast-sheet-1-v3.png',1,2,2),'篠原透':('cast-sheet-1-v3.png',2,2,2),'中古機械業者の担当者':('cast-sheet-1-v3.png',3,2,2),'搬出作業員':('cast-sheet-2-v2.png',0,2,1),'配達員':('cast-sheet-2-v2.png',1,2,1),'質屋の店主':('owner-reference.png',0,1,1),'黒猫':('cat-reference.png',0,1,1)}
results=[]
for c in characters:
 name=c['name'];assert name in mapnames,name
 c=copy.deepcopy(c);c['character_key']='codex-'+digest([c.get('id') or name])[:16];file=dest/(c['character_key']+'.png');src,n,cols,rows=mapnames[name]
 with Image.open(P/src) as im:
  w,h=im.size;x=n%cols;y=n//cols;im=im.crop((x*w//cols,y*h//rows,(x+1)*w//cols,(y+1)*h//rows))
  if min(im.size)<512:im=im.resize(tuple(round(v*512/min(im.size)) for v in im.size),Image.Resampling.LANCZOS)
  im.save(file)
 fingerprint=digest({'script_sha256':sha,'reference_sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
 old=cs.request('GET','/rest/v1/topic_character_assets',params={'topic_queue_id':'eq.3427','character_key':'eq.'+c['character_key'],'select':'usage_context'}).json()
 assert not old or old[0]['usage_context']['sha256']==hashlib.sha256(file.read_bytes()).hexdigest()
 row();out=cs.publish(3427,c,file,fingerprint,{'category':2,'image_style':'realistic'})
 assert hashlib.sha256(_download_gcs_bytes(out['gcs_bucket'],out['gcs_path'])).hexdigest()==hashlib.sha256(file.read_bytes()).hexdigest()
 results.append(out);print('character stored',name,flush=True)
save(P/'character-publication-receipt.json',{'characters':results,'storage_and_registry_readbacks_verified':True})
# Wait for independent scene publisher before guarded document merge.
while not (P/'scene-image-publication.json').exists():time.sleep(15)
r=row();old=copy.deepcopy(r['progress_payload']);s=copy.deepcopy(r['pregenerated_structure']);by={c['name']:c for c in results}
def merge(c):return {**c,**by[c['name']]} if isinstance(c,dict) and c.get('name') in by else c
s['main_character']=merge(s['main_character']);s['supporting_characters']=[merge(c) for c in s['supporting_characters']]
a=s['character_anchors'];a['main_character']=merge(a['main_character']);a['supporting_characters']=[merge(c) for c in a['supporting_characters']];s['character_reference_status']='ready'
m=copy.deepcopy(r['publish_metadata']);m['description']+='\n\n※本作はオリジナルのフィクションです。登場人物・団体・取引は架空のものです。';m.update(thumbnail_url=receipt['final']['url'],thumbnail_bg_url=receipt['background']['url'])
progress=copy.deepcopy(old);progress.update(character_anchors=a,publish_metadata=m,thumbnail_url=receipt['final']['url'],thumbnail_final_url=receipt['final']['url'],thumbnail_bg_url=receipt['background']['url'],thumbnail_completed=True,thumbnail_status='completed',thumbnail_text=receipt['thumbnail_text'],thumbnail_source=receipt,scene_image_count=144,basic_scene_images_ready=True,image_generation_status='completed')
s.update(thumbnail_url=receipt['final']['url'],thumbnail_final_url=receipt['final']['url'],thumbnail_bg_url=receipt['background']['url'],thumbnail_status='completed')
params={'id':'eq.3427','status':'eq.pending','assigned_employee_email':'is.null' if r.get('assigned_employee_email') is None else 'eq.'+r['assigned_employee_email'],'progress_payload->>source_script_job_id':'eq.acc3fd2d56b64672a80593c2d9cd4e66','progress_payload->>scene_image_count':('is.null' if old.get('scene_image_count') is None else 'eq.'+str(old['scene_image_count'])),'progress_payload->>thumbnail_url':('is.null' if not old.get('thumbnail_url') else 'eq.'+old['thumbnail_url'])}
res=store.request('PATCH','topics_queue',params=params,body={'pregenerated_structure':s,'progress_payload':progress,'publish_metadata':m},prefer='return=representation')[0];assert len(res)==1,'Concurrent update preserved; retry merge'
r=row();assert all(c.get('image_url') for c in [r['pregenerated_structure']['main_character']]+r['pregenerated_structure']['supporting_characters']);assert r['progress_payload']['thumbnail_completed'];assert len([s for s in r['pregenerated_structure']['scenes'] if s.get('image_url')])==144
save(EP/'publish-metadata.json',m);save(EP/'youtube-packaging.json',{**m,'script_sha256':sha,'thumbnail_text':receipt['thumbnail_text']})
(EP/'YOUTUBE_PACKAGE_JA.md').write_text('# '+r['generated_title']+'\n\n'+m['description']+'\n\n'+', '.join(m['tags'])+'\n\nサムネイル: '+' / '.join(receipt['thumbnail_text'])+'\n')
save(EP/'FINAL_PACKAGE_READBACK.json',{'topic_id':3427,'script_sha256':sha,'images':144,'character_references':len(results),'thumbnail_verified':True,'translations':list(progress.get('script_translations',{})),'metadata':m})
print('Final assets and metadata registered and read back',flush=True)
