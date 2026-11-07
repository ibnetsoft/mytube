"""Evict reproducible per-attempt state downloads, never source objects or rendered clips.

The native project and a receipt naming its original immutable GCS inputs remain.
The normal prepare step restores these files if that scene ever needs rendering again.
"""
import argparse,base64,hashlib,json,sys
from pathlib import Path
from urllib.parse import quote
import requests
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
import worker_config
from worker.script_worker_store import ScriptStore
import ae_highlight_worker as ae
from motion_automation_worker import unseal
JOBS={'91c265fe-12cf-4788-ba1d-e3eae9a3b2fe','13f6e0a5-ab9f-4750-aa3e-0d5b895694dc','9df7ce21-e660-4553-8577-778fc02b02f9'}

def release(path,asset,metadata):
 data=path.read_bytes()
 if hashlib.sha256(data).hexdigest()!=asset['sha256']:raise ValueError('Local state differs from frozen source')
 if int(metadata['size'])!=len(data) or metadata['md5Hash']!=base64.b64encode(hashlib.md5(data).digest()).decode():raise ValueError('GCS source does not match cached bytes')
 receipt={'path':str(path),'sha256':asset['sha256'],'gcs_bucket':asset['gcs_bucket'],'gcs_path':asset['gcs_path'],'generation':metadata['generation'],'bytes':len(data),'kind':'reproducible_download_cache','released':False}
 record=path.with_suffix('.download-cache.json');record.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
 path.unlink();receipt['released']=True;record.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
 return receipt

def main():
 p=argparse.ArgumentParser();p.add_argument('job',choices=sorted(JOBS));p.add_argument('--release',action='store_true');args=p.parse_args()
 rows,_=ScriptStore().request('GET','std_project_assets',params={'id':'eq.'+args.job,'select':'results:metadata->results,input:metadata->input','limit':1})
 row=rows[0];snapshot=unseal(row['input']);done={r['number']:r for r in row.get('results') or []};creds,_=ae._gcs_credentials();released=[]
 directory=worker_config.PROJECT_ROOT/'output/codex-local-console/motion-automation'/args.job
 for scene in snapshot['scenes']:
  if scene['number'] not in done:continue
  result=done[scene['number']];movie=Path(result['path'])
  if not movie.is_file() or ae._sha256_file(movie)!=result['sha256']:raise ValueError('Completed native scene is not preserved')
  attempt=directory/('scene-'+str(scene['number']))
  for asset in scene.get('wuxia_timeline',{}).get('states',[]):
   for path in attempt.glob('attempt-*/wuxia/'+asset['sha256']+'.png'):
    if not args.release:released.append({'candidate':str(path),'bytes':path.stat().st_size});continue
    url='https://storage.googleapis.com/storage/v1/b/'+quote(asset['gcs_bucket'],safe='')+'/o/'+quote(asset['gcs_path'],safe='')
    response=requests.get(url,headers={'Authorization':'Bearer '+creds.token},params={'fields':'size,md5Hash,generation'},timeout=(10,30));response.raise_for_status()
    released.append(release(path,asset,response.json()))
 print(json.dumps({'job':args.job,'released':args.release,'files':len(released),'bytes':sum(r['bytes']for r in released),'receipts':released}))
if __name__=='__main__':main()
