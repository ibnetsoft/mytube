import copy
import sys
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from worker import codex_local_console as console
from worker import local_production_settings as production

def test_script_settings_validation_and_roundtrip(monkeypatch):
    saved=[]
    def db(method,table,**kwargs):
        assert table=='global_settings'
        if method=='POST':
            import json
            record=copy.deepcopy(kwargs['body']);record['value']=json.dumps(record['value'])
            saved[:]=[record]
        return copy.deepcopy(saved),None
    monkeypatch.setattr(console.store,'request',db)
    client=TestClient(console.app,base_url=console.ORIGIN,headers={'X-Codex-Local':console.TOKEN})
    assert client.get('/api/script-settings').json()['settings']['setting_country']=='한국'
    body={'language':'ja','setting_country':'일본','duration_minutes':22,'production_mode':'moving_comic','generate_bgm_prompt':True}
    assert client.post('/api/script-settings',json=body).status_code==200
    assert client.get('/api/script-settings').json()['settings']['duration_minutes']==22
    before=copy.deepcopy(saved)
    assert client.post('/api/script-settings',json={'duration_minutes':999}).status_code==400
    assert client.post('/api/script-settings',json={'api_key':'forbidden'}).status_code==400
    assert client.post('/api/script-settings',headers={'Origin':'https://evil.invalid'},json=body).status_code==403
    assert saved==before

def test_new_jobs_inherit_defaults_but_preserve_explicit_fields(monkeypatch):
    captured=[]
    monkeypatch.setattr(console,'load_script_settings',lambda:{'language':'ja','duration_minutes':22,'production_mode':'moving_comic','generate_bgm_prompt':True})
    monkeypatch.setattr(console.jobs,'start',lambda request,*args:captured.append(request) or {'id':'fixture'})
    client=TestClient(console.app,base_url=console.ORIGIN,headers={'X-Codex-Local':console.TOKEN})
    assert client.post('/api/jobs',json={'mode':'new','title':'test','category':'test','language':'ko','generate_bgm_prompt':False}).status_code==200
    assert captured[0].language=='ko' and captured[0].generate_bgm_prompt is False
    assert captured[0].duration_minutes==22 and captured[0].production_mode=='moving_comic'

def test_loopback_rejects_missing_token_without_invoking_backend(monkeypatch):
    class Handler:
        path='/api/local/projects';command='GET';headers={}
        def send_error(self,status,*args):self.status=status
    handler=Handler()
    monkeypatch.setattr(production,'invoke',lambda *args:(_ for _ in ()).throw(AssertionError('must not execute')))
    assert production.handle(handler) is True and handler.status==401

def test_native_model_sessions_are_not_returned_to_the_browser(monkeypatch):
    class Result:
        stdout='AIR_RESULT:{"status":200,"session_token":"fixture-private-session","data":{"connected":true}}'
    monkeypatch.setattr(production.subprocess,'run',lambda *args,**kwargs:Result())
    result=production.invoke('/api/local/account-login',method='POST',body={'password':'fixture'},project_id='fixture')
    assert 'session_token' not in result
    assert production._sessions['fixture']=='fixture-private-session'
    production._sessions.pop('fixture')

def test_native_http_boundary_and_local_storage_upload(monkeypatch,tmp_path):
    import http.client
    import socket
    from worker import local_media_supervisor as media
    monkeypatch.setattr(media,'HOME',tmp_path)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    origin=f'http://127.0.0.1:{port}'
    monkeypatch.setattr(production,'invoke',lambda *args:{'status':200,'data':{'storage_upload_url':'https://storage.googleapis.com/fixture?signature=test'}})
    captured=[]
    class Uploaded:
        ok=True
    def upload(url,**kwargs):
        captured.append((url,kwargs['data'].read(),kwargs['headers']))
        return Uploaded()
    monkeypatch.setattr('requests.put',upload)
    server=media.serve_status(port)
    client=http.client.HTTPConnection('127.0.0.1',port,timeout=10)
    try:
        client.request('GET','/');response=client.getresponse();html=response.read().decode()
        assert response.status==200 and '__LOCAL_TOKEN__' not in html and production.TOKEN in html
        assert 'worker-studio' not in html
        client.request('GET','/api/local/projects');response=client.getresponse();response.read();assert response.status==401
        body={'file_size':4,'mime_type':'image/png'}
        import json
        encoded=json.dumps(body).encode()
        headers={'Content-Type':'application/json','X-Codex-Local':production.TOKEN,'Origin':origin}
        client.request('POST','/api/std/projects/fixture/assets/init',body=encoded,headers={**headers,'Origin':'https://evil.invalid'})
        response=client.getresponse();response.read();assert response.status==403
        client.request('POST','/api/std/projects/fixture/assets/init',body=encoded,headers=headers)
        response=client.getresponse();data=json.loads(response.read());assert response.status==200
        assert data['storage_upload_url'].startswith('/api/local/uploads/')
        client.request('PUT',data['storage_upload_url'],body=b'file',headers={'Origin':origin,'Content-Type':'image/png'})
        response=client.getresponse();response.read();assert response.status==200
        assert captured[0][1]==b'file'
    finally:
        client.close();server.shutdown();server.server_close()


def test_all_scene_parallax_normalizes_request_without_requiring_uploaded_clips():
    request=console.StartRequest(mode='new',parallax_mode='all_scenes',required_video_scene_count=18,image_layer_mode='hybrid',image_layer_scene_start=19,image_layer_scene_end=35)
    assert request.required_video_scene_count==0
    assert request.image_layer_mode=='full_psd'
    assert request.image_layer_scene_start is None and request.image_layer_scene_end is None
    assert 'parallax_mode' in console.SCRIPT_SETTING_FIELDS
