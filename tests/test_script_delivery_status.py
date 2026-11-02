from unittest.mock import Mock,patch
from worker.script_delivery_status import reconcile,active

def test_live_recovery_preserves_failure_and_patches_only_job_status(tmp_path):
 store=Mock();store.request.return_value=([{'id':'a'*32,'status':'failed','updated_at':4,'job_record':{'status':'failed','error':'original failure'}}],1)
 with patch('worker.script_delivery_status.active',return_value={'stage':'02f_batch_021_040_director'}):reconcile(store,tmp_path,'a'*32)
 args=store.request.call_args;assert args.args[0]=='PATCH';body=args.kwargs['body'];assert body['status']=='running';assert body['job_record']['delivery_source_status']=='failed';assert body['job_record']['previous_error']=='original failure';assert body['job_record']['error']=='';assert '21~40' in body['job_record']['stage'];assert 'candidate' not in body;assert args.kwargs['params']['status']=='eq.failed'

def test_dead_recovery_never_looks_running(tmp_path):
 store=Mock();store.request.return_value=([{'status':'running','updated_at':4,'job_record':{'status':'running','delivery_active':True}}],1)
 with patch('worker.script_delivery_status.active',return_value=None):reconcile(store,tmp_path,'a'*32)
 assert store.request.call_args.kwargs['body']['status']=='interrupted'

def test_completed_or_canceled_jobs_are_preserved(tmp_path):
 for status in ('completed','canceled'):
  store=Mock();store.request.return_value=([{'status':status,'job_record':{},'updated_at':4}],1)
  with patch('worker.script_delivery_status.active',return_value={'stage':'stale'}):reconcile(store,tmp_path,'a'*32)
  assert store.request.call_count==1

def test_status_file_alone_is_not_proof_of_live_process(tmp_path):
 import json
 d=tmp_path/('a'*32)/'delivery';d.mkdir(parents=True);(d/'status.json').write_text(json.dumps({'source_job_id':'a'*32,'stage':'running'}));(d/'supervisor.lock').write_bytes(b'0')
 assert active(tmp_path,'a'*32) is None
