import copy,sys
sys.path[:0]=['worker']
import ae_highlight_worker as a
P='6b46f709-b4bf-4ccd-ac12-9c8c3981e249';J='8a5880c3-ce87-41e6-8478-6fadb38b6540'
b,h=a._supabase();u=b+'/rest/v1/std_project_assets'
job=a._request('GET',u,h,params={'select':'*','id':'eq.'+J}).json()[0]
m=copy.deepcopy(job['metadata'])
for r in m['results']:
 if r['number']==34:
  for k in ('reason','fallback','skip_reason','diagnostic_error','asset_id','render_sha256','output_review'):r.pop(k,None)
  r['status']='direction_approved'
m.update(state='direction_approved',phase='render',auto_pending=True,error='',current_scene=None,worker_token=None,lease_expires_at=None)
a._request('PATCH',u,{**h,'Prefer':'return=representation'},params={'id':'eq.'+J},json={'metadata':m,'updated_at':a._now()}).raise_for_status()
print('scene 34 reset for render')
