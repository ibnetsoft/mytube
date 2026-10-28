import sys,json,copy
from pathlib import Path
sys.path[:0]=['worker']
import ae_highlight_worker as ae
P='6b46f709-b4bf-4ccd-ac12-9c8c3981e249';J='8a5880c3-ce87-41e6-8478-6fadb38b6540'
qpath=Path(r'output/codex-local-console/6ae46b7afca84070b36e9e13d7de0a6e/web-package/ae-mouth-final-qa/qa-receipt.json')
qa=json.loads(qpath.read_text(encoding='utf-8')); byn={x['scene']:x for x in qa['scenes']}
b,h=ae._supabase();u=b+'/rest/v1/std_project_assets';now=ae._now()
job=ae._request('GET',u,h,params={'select':'*','id':'eq.'+J}).json()[0];m=copy.deepcopy(job['metadata'])
for r in m['results']:
 n=r['number'];assert r['status']=='review_pending' and n in byn
 asset=ae._request('GET',u,h,params={'select':'*','id':'eq.'+r['asset_id']}).json()[0]
 receipt={'version':1,'method':'codex_full_decode_visual_audio_gcs_review','reviewed_by':'codex','reviewed_at':now,**byn[n]}
 updated={**asset['metadata'],'ae_reviewed':True,'ae_reviewed_by':'codex','ae_reviewed_at':now,'automatic_review':receipt}
 saved=ae._request('PATCH',u,{**h,'Prefer':'return=representation'},params={'id':'eq.'+asset['id'],'updated_at':'eq.'+asset['updated_at']},json={'metadata':updated,'updated_at':now}).json();assert saved,n
 r['status']='approved';r['output_review']=receipt
m.update(state='reviewed',phase='complete',auto_pending=False,error='',reviewed_by='codex',reviewed_at=now,review_receipt_path=str(qpath.resolve()),worker_token=None,current_scene=None)
saved=ae._request('PATCH',u,{**h,'Prefer':'return=representation'},params={'id':'eq.'+J,'updated_at':'eq.'+job['updated_at']},json={'metadata':m,'updated_at':now}).json();assert saved
print('approved',[(r['number'],r['status']) for r in m['results']])
