import unittest
from worker.script_manual_workflow import digest
from worker.script_web_incremental import image_prompt_updates

class IncrementalMappingTests(unittest.TestCase):
    def test_source_bound_draft_and_approved_cut(self):
        scene={'scene_id':'s1','visual_action':'A'}
        workflow={'stages':[{'status':'approved','output':{'scenes':[scene]}}, {'status':'pending'}],
                  'scene_image_prompts':{'s1':{'status':'review','source_hash':digest(scene),'image_prompt':'draft'}}}
        self.assertEqual(image_prompt_updates(workflow)[0]['image_prompt'],'draft')
        workflow['scene_image_prompts']['s1']['source_hash']='old'
        self.assertEqual(image_prompt_updates(workflow),[])
        workflow['stages'][1]={'status':'approved','output':{'cuts':[{'scene_id':'s1','cut_id':'c1','image_prompt':'final'}]}}
        self.assertEqual(image_prompt_updates(workflow)[0]['cut_id'],'c1')
        workflow['stages'][1]['output']['cuts'].append({'scene_id':'s1','cut_id':'c2','image_prompt':'other'})
        with self.assertRaises(ValueError): image_prompt_updates(workflow)

if __name__ == '__main__': unittest.main()

class ConflictTests(unittest.TestCase):
    def test_user_edit_is_preserved_and_scene_mapping_is_exact(self):
        from worker.script_web_incremental import plan_prompt_patch
        scenes=[{'id':'a','metadata':{'scene_id':'s1'},'image_prompt':'worker-old'}]
        updates=[{'scene_id':'s1','image_prompt':'worker-new'}]
        self.assertEqual(plan_prompt_patch(scenes,updates,{'s1':'worker-old'})[0]['expected_image_prompt'],'worker-old')
        scenes[0]['image_prompt']='user edit'
        with self.assertRaises(ValueError): plan_prompt_patch(scenes,updates,{'s1':'worker-old'})
        with self.assertRaises(ValueError): plan_prompt_patch([],updates,{})

def test_delivery_route_checks_source_and_reads_back():
    import copy
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from threading import RLock
    from worker.script_web_incremental import register
    scene={'scene_id':'s1','visual_action':'A'}
    candidate={'script':'text','manual_workflow':{'stages':[{'status':'approved','output':{'scenes':[scene]}}, {'status':'pending'}]}}
    class Store:
        def get(self, identity): return {'candidate':copy.deepcopy(candidate),'job':{'storage_revision':3}}
        def request(self, method, table, **kwargs):
            if table.startswith('rpc/'):
                assert kwargs['body']['p_revision']==3
                return {'project_id':'p','topic_id':1,'prompt_count':0,'scene_count':1},None
            return [{'id':'p','topic_queue_id':1,'progress_payload':{'script_worker_delivery':{'job_revision':3}}}],None
    class Jobs:
        lock=RLock(); worker_id='local'; inflight=set(); store=Store()
        def load(self, identity): return {'job':{'worker_id':'local','status':'awaiting_approval','sync_status':'synced'},'candidate':candidate}
        def update(self, identity, **values): self.saved=values
    jobs=Jobs(); app=FastAPI(); register(app,jobs); client=TestClient(app)
    result=client.post('/api/jobs/job/web-delivery',json={'expected_hash':digest(candidate)})
    assert result.status_code==200 and jobs.saved['registered_project_id']=='p'
    assert client.post('/api/jobs/job/web-delivery',json={'expected_hash':'0'*64}).status_code==409
