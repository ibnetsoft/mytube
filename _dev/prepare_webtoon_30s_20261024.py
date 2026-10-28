import sys,os
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root),str(root/'worker')]
from dotenv import load_dotenv
load_dotenv(root/'.env');load_dotenv(root/'auth-web/.env.local')
import ae_highlight_worker as ae
import worker_config
from ae_mouth_runtime import instance_lock
from worker.motion_preview_worker import process_one
original=ae._request
project='d837454e-77c6-4c65-9a8b-c6a73cbb00e8'
def scoped(method,url,*args,**kwargs):
 if method=='GET' and url.endswith('/rest/v1/std_project_assets'):
  kwargs['params']={**kwargs.get('params',{}),'project_id':'eq.'+project}
 return original(method,url,*args,**kwargs)
ae._request=scoped
with instance_lock(worker_config.STATE_DIR/'motion_preview_worker.lock'):
 for _ in range(2):print('prepared:',process_one('preparation'),flush=True)
