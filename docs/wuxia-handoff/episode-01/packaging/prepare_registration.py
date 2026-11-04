import sys,json,hashlib,os,base64
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.parse import quote
P=Path(os.environ.get('WUXIA_EPISODE_DIR') or Path(__file__).resolve().parent.parent).resolve();ROOT=P.parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
import worker_config
from worker.script_worker_store import ScriptStore
from worker.cowork_scene_assets import _upload_gcs_file,_gcs_credentials
import requests
OUT=P/'packaging'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def metadata():
 if all((OUT/name).is_file() for name in ['publish-metadata.json','thumbnail-design.json','packaging-review.json']):return
 title='고수들이 버린 짐꾼, 석상의 약점을 보다 | 나 혼자 무공을 진화시킨다 1화'
 description='''검 여섯 자루가 돌아오면, 사람들은 무사한 탐사였다고 했다. 돌아오지 못한 짐꾼의 이름은 장부에서 지워졌다.

내공을 모으지 못하는 짐꾼 서진. 그는 세 배의 품삯을 약속한 철산문의 탐사대에 합류한다. 하지만 무경 깊은 곳에서 봉함이 풀리자 여섯 석상이 움직이고, 믿었던 고수들은 짐꾼들을 남긴 채 철문을 잠근다.

다친 동료 도겸과 함께 버려진 서진에게 남은 것은 작은 단도와, 남들이 보지 않던 발끝과 손목을 관찰하는 버릇뿐. 거대한 돌검이 다시 내려오는 순간, 서진은 그 짧은 틈을 향해 몸을 낮춘다.

〈나 혼자 무공을 진화시킨다〉 1화 — 버려진 짐꾼
강호의 가장 낮은 자리에서 시작하는 오리지널 무협 성장 이야기.

#무협웹툰 #무빙툰 #성장물'''
 layers=[{'id':'ep01-kicker','text':'버림받은 순간','fontSize':19,'fontFamily':'Noto Sans KR','color':'#FFFFFF','strokeColor':'#08151B','strokeWidth':1.5,'x':22,'y':31},
         {'id':'ep01-headline','text':'틈이\n보였다','fontSize':37,'fontFamily':'Black Han Sans','color':'#F6F0C8','strokeColor':'#071820','strokeWidth':2,'x':22,'y':55},
         {'id':'ep01-badge','text':'버려진 짐꾼 · 1화','fontSize':12,'fontFamily':'Noto Sans KR','color':'#82DFE5','strokeColor':'#071820','strokeWidth':1,'x':22,'y':83}]
 m={'titles':[title,'버려진 짐꾼에게만 보인 석상의 빈틈 | 나 혼자 무공을 진화시킨다 1화','고수들이 문을 잠갔다. 짐꾼은 석상의 손목을 봤다 | 무협웹툰 1화'],
 'selected_title':title,'description':description,'tags':['무협웹툰','무빙툰','오리지널무협','성장물','강호','짐꾼','무공','나혼자무공을진화시킨다'],'hashtags':['#무협웹툰','#무빙툰','#성장물']}
 write(OUT/'publish-metadata.json',m)
 design={'contract':'editable-background-v1','width':1280,'height':720,'editor_width':480,'text_layers':layers,'render_status':'awaiting_user_save','thumbnail_url':None}
 write(OUT/'thumbnail-design.json',design)
 write(OUT/'packaging-review.json',{'title':title,'vidiq_title_score':89,'credits_used':5,'score_context':'long-form, no channel-specific analytics; directional model score, not predicted CTR',
 'thumbnail_review':'actual generated pixels inspected; original Seojin identity, no successful attack shown, empty left area reserved for editable text',
 'hook_alternatives':['버림받은 순간, 틈이 보였다','고수들은 도망쳤다','저 틈이다!!'],'youtube_publication':False})
def upload_all():
 store=ScriptStore()
 conf,_=store.request('GET','global_settings',params={'select':'key,value','key':'in.(sys_api_gcs_bucket_name,sys_api_gcs_project_id,sys_api_gcs_client_email,sys_api_gcs_private_key)'})
 names={'sys_api_gcs_bucket_name':'GCS_BUCKET_NAME','sys_api_gcs_project_id':'GCS_PROJECT_ID','sys_api_gcs_client_email':'GCS_CLIENT_EMAIL','sys_api_gcs_private_key':'GCS_PRIVATE_KEY'}
 for r in conf:
  if r.get('value'):os.environ[names[r['key']]]=str(r['value'])
 creds,bucket=_gcs_credentials()
 files=sorted((P/'images').glob('*.png'))+sorted((P/'character-sheets').glob('*-v1.png'))+[OUT/'thumbnail-bg-v1.png',P/'direction/ae-scene-package.json',P/'direction/build_ae_preview.jsx',P/'direction/sound-and-music-direction.json']
 saved=read(OUT/'asset-upload-receipts.json') if (OUT/'asset-upload-receipts.json').exists() else {}
 def upload(p):
  rel=p.relative_to(P).as_posix();data=p.read_bytes();sha=hashlib.sha256(data).hexdigest();md5=base64.b64encode(hashlib.md5(data).digest()).decode()
  obj=f'codex-productions/{P.parent.name}/{P.name}/{p.stem}-{sha}{p.suffix}'
  old=saved.get(rel)
  if old and old['sha256']==sha:
   meta=requests.get(f'https://storage.googleapis.com/storage/v1/b/{quote(bucket,safe="")}/o/{quote(obj,safe="")}',headers={'Authorization':f'Bearer {creds.token}'},timeout=40)
   if meta.ok and meta.json().get('md5Hash')==md5:return rel,old
  mime='image/png' if p.suffix=='.png' else 'application/json' if p.suffix=='.json' else 'text/javascript'
  b,o,url=_upload_gcs_file(p,obj,mime)
  res=requests.get(f'https://storage.googleapis.com/storage/v1/b/{quote(b,safe="")}/o/{quote(o,safe="")}',params={'alt':'media'},headers={'Authorization':f'Bearer {creds.token}'},timeout=90)
  res.raise_for_status();assert hashlib.sha256(res.content).hexdigest()==sha,'uploaded bytes mismatch'
  return rel,{'gcs_bucket':b,'gcs_path':o,'media_url':url,'sha256':sha,'bytes':len(data),'verified_download_sha256':True}
 with ThreadPoolExecutor(max_workers=4) as pool:
  future=[pool.submit(upload,p) for p in files]
  for i,f in enumerate(as_completed(future),1):
   rel,receipt=f.result();saved[rel]=receipt;write(OUT/'asset-upload-receipts.json',saved)
   print(f'asset {i}/{len(files)} verified: {rel}',flush=True)
 assert all(p.relative_to(P).as_posix() in saved for p in files)
if __name__=='__main__':
 metadata()
 if '--upload' in sys.argv:upload_all()
