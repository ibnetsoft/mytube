"""Restore episode03 rewrite snapshot without overwriting work or registering topics."""
import argparse,json,os,sys
from pathlib import Path
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[3];SOURCE=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from scripts.restore_wuxia_handoff import digest,save_new_or_same

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--target',type=Path);parser.add_argument('--assets',action='store_true');parser.add_argument('--readback',action='store_true');args=parser.parse_args()
 target=(args.target or ROOT/'output/wuxia-series-rewrite/episode-03').resolve();manifest=json.loads((SOURCE/'snapshot-manifest.json').read_text(encoding='utf-8'))
 for row in manifest:
  f=(SOURCE/row['file']).resolve();destination=(target/row['file']).resolve()
  if not f.is_relative_to(SOURCE)or not destination.is_relative_to(target):raise RuntimeError('Invalid snapshot path')
  data=f.read_bytes()
  if digest(data)!=row['sha256']:raise RuntimeError('Snapshot hash mismatch: '+row['file'])
  if row['file']=='image-generation-jobs.json':
   jobs=json.loads(data)
   for job in jobs:job['reference_paths']=[str(target/'character-sheets'/Path(x.replace('\\','/')).name)for x in job.get('reference_paths',[])]
   data=json.dumps(jobs,ensure_ascii=False,indent=2).encode()
  save_new_or_same(destination,data)
 for name in ['NotoSansKR-Bold.ttf','DoHyeon-Regular.ttf','BlackHanSans-Regular.ttf']:
  f=ROOT/'auth-web/public/fonts'/name
  if f.exists():save_new_or_same(target/'fonts'/name,f.read_bytes())
 if args.assets or args.readback:
  from dotenv import load_dotenv
  load_dotenv(ROOT/'worker/connection.env')
  from worker.script_worker_store import ScriptStore
  store=ScriptStore()
 if args.assets:
  import requests
  from worker.cowork_scene_assets import _gcs_credentials
  keys={'sys_api_gcs_bucket_name':'GCS_BUCKET_NAME','sys_api_gcs_project_id':'GCS_PROJECT_ID','sys_api_gcs_client_email':'GCS_CLIENT_EMAIL','sys_api_gcs_private_key':'GCS_PRIVATE_KEY'}
  rows,_=store.request('GET','global_settings',params={'select':'key,value','key':'in.('+','.join(keys)+')'})
  for row in rows:
   if row.get('value'):os.environ[keys[row['key']]]=str(row['value'])
  credentials,_=_gcs_credentials();receipts=json.loads((target/'packaging/asset-upload-receipts.json').read_text(encoding='utf-8'))
  for rel,asset in receipts.items():
   f=(target/rel).resolve()
   if not f.is_relative_to(target):raise RuntimeError('Invalid asset path')
   if f.is_file()and digest(f.read_bytes())==asset['sha256']:continue
   # Planned jobs are portable text; their original remote bytes retain old absolute paths.
   if rel=='image-generation-jobs.json':continue
   url='https://storage.googleapis.com/storage/v1/b/'+quote(asset['gcs_bucket'],safe='')+'/o/'+quote(asset['gcs_path'],safe='')
   response=requests.get(url,params={'alt':'media'},headers={'Authorization':'Bearer '+credentials.token},timeout=90);response.raise_for_status()
   if digest(response.content)!=asset['sha256']:raise RuntimeError('Remote hash mismatch: '+rel)
   save_new_or_same(f,response.content)
  print('Remote assets checked:',len(receipts))
 if args.readback:
  receipt=json.loads((target/'packaging/registration-receipt.json').read_text(encoding='utf-8'));expected=json.loads((target/'packaging/web-topic.json').read_text(encoding='utf-8'))
  if receipt['topic_id']!=3432:raise RuntimeError('Unexpected topic identity')
  rows,_=store.request('GET','topics_queue',params={'select':'id,pregenerated_script,pregenerated_structure,publish_metadata,progress_payload','id':'eq.3432','limit':1})
  if len(rows)!=1:raise RuntimeError('Registered topic unavailable')
  for key in ['pregenerated_script','pregenerated_structure','publish_metadata','progress_payload']:
   if rows[0][key]!=expected[key]:raise RuntimeError('Registered topic changed: '+key)
  save_new_or_same(target/'packaging/restore-readback-verification.json',json.dumps({'topic_id':3432,'database_readback':'exact_match','script_sha256':digest(rows[0]['pregenerated_script'].encode())},indent=2).encode())
  print('Readback exact match:3432')
 print('Restored',len(manifest),'text files; no topic created or modified:',target)
if __name__=='__main__':main()
