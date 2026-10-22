import copy
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'worker'))
import ec_supplemental_assets as ec


def setup(tmp_path, values=None):
    source=tmp_path/'original.png';Image.new('RGBA',(512,512),(20,40,80,255)).save(source)
    voice=tmp_path/'final.wav';voice.write_bytes(b'fixed final recording')
    scene=dict(number=1,start=0,end=8,source_kind='image')
    snapshot=dict(renderer={'engine':'effectcraft'},project={'id':'p'},audio={'id':'voice'},motion={'fps':24},
        subtitles=[dict(scene_number=1,text='Door opens',start=2,end=4)])
    plan=dict(scene={'keys':[dict(t=t,x=.5,y=.5,scale=1,rotation=0,opacity=100) for t in (0,1)],'effects':[]},supplemental_assets=values or [overlay()])
    return snapshot,scene,plan,source,voice


def overlay():return dict(id='lamp',kind='overlay',role='prop',reason='Existing lamp needs a separate warm glow',prompt='Only the aligned lamp glow, no face',quote='Door opens',dx=0,dy=0)
def cutout():return dict(id='person',kind='source_cutout',role='character',reason='Separate the existing subject for a small move',prompt='Exact original subject alpha',quote='Door opens',dx=.01,dy=0)
def background():return dict(id='scenery',kind='background_fill',role='background',reason='Fill scenery hidden under the extracted subject',prompt='Only hidden scenery')


class Generator:
    def __init__(self,hook=None):self.calls=[];self.hook=hook
    def generate(self,**args):
        self.calls.append(args);target=Path(args['work_dir'])/'generated.png';target.parent.mkdir(parents=True,exist_ok=True)
        image=Image.new('RGBA',(512,512),(0,0,0,0))
        if args['role']=='background':image=Image.new('RGBA',(512,512),(40,120,30,255))
        else:image.paste((255,0,0,255),(160,160,352,352))
        image.save(target)
        if self.hook:self.hook()
        return target


class Runner:
    def __init__(self,answers=(True,)):self.calls=[];self.answers=list(answers)
    def _stage(self,identity,name,context,task):
        self.calls.append(context)
        assert all(Path(p).is_file() for p in context['_local_image_paths'])
        passed=self.answers[min(len(self.calls)-1,len(self.answers)-1)]
        return dict(passed=passed,critical_issues=[] if passed else ['Wrong palette at the lamp edge'],checks=[dict(id=k,passed=passed,evidence='Fixture: compared source pixels, alpha contour and fixed recorded interval') for k in ec.CHECKS])


def prepare(tmp_path,values=None,runner=None,generator=None):
    s,scene,plan,source,voice=setup(tmp_path,values)
    runner=runner or Runner();generator=generator or Generator()
    package=ec.prepare(s,scene,plan,source,source,voice,runner,tmp_path/'supplements',generator=generator)
    return package,(s,scene,plan,source,voice),runner,generator


def test_reuses_reviewed_pixels_without_generating_or_reviewing_again(tmp_path):
    package,f,runner,generator=prepare(tmp_path)
    s,scene,plan,source,voice=f;original=ec.sha(source);sound=ec.sha(voice)
    again=ec.prepare(s,scene,plan,source,source,voice,runner,tmp_path/'supplements',generator=generator)
    assert again==package and len(generator.calls)==len(runner.calls)==1
    assert ec.sha(source)==original and ec.sha(voice)==sound
    assert package['files'][0]['motion']['start']==.25 and package['files'][0]['motion']['end']==.5


def test_failed_visual_review_repairs_once_and_preserves_both_attempts(tmp_path):
    package,_,runner,generator=prepare(tmp_path,runner=Runner((False,True)))
    assert len(runner.calls)==len(generator.calls)==2
    assert 'Wrong palette' in generator.calls[-1]['prompt']
    assert list((tmp_path/'supplements').rglob('rejected.json'))
    assert ec.verify_package(package)


def test_two_failures_do_not_regenerate_forever_on_recovery(tmp_path):
    s,scene,plan,source,voice=setup(tmp_path);runner=Runner((False,));generator=Generator()
    for _ in range(2):
        with pytest.raises(ec.SupplementReviewRequired,match='failed twice'):
            ec.prepare(s,scene,plan,source,source,voice,runner,tmp_path/'supplements',generator=generator)
    assert len(generator.calls)==len(runner.calls)==2


def test_cutout_keeps_original_rgb_and_restoration_only_changes_occluded_pixels(tmp_path):
    package,f,_,_=prepare(tmp_path,[background(),cutout()])
    source=Image.open(f[3]).convert('RGBA')
    person=Image.open(next(x['path'] for x in package['files'] if x['kind']=='source_cutout'))
    plate=Image.open(next(x['path'] for x in package['files'] if x['kind']=='background_fill'))
    assert person.getpixel((200,200))==source.getpixel((200,200))
    assert person.getpixel((0,0))[3]==0
    assert plate.getpixel((0,0))==source.getpixel((0,0))
    assert plate.getpixel((200,200))!=source.getpixel((200,200))


@pytest.mark.parametrize('what',['source','voice','timing'])
def test_mutating_frozen_inputs_stops_before_approval(tmp_path,what):
    s,scene,plan,source,voice=setup(tmp_path);runner=Runner()
    def mutate():
        if what=='source':Image.new('RGBA',(512,512),'white').save(source)
        elif what=='voice':voice.write_bytes(b'changed')
        else:s['subtitles'][0]['start']=3
    with pytest.raises(ec.SupplementReviewRequired,match='changed during'):
        ec.prepare(s,scene,plan,source,source,voice,runner,tmp_path/'supplements',generator=Generator(mutate))
    assert not runner.calls


def test_safety_refusal_is_never_rephrased_or_retried(tmp_path):
    s,scene,plan,source,voice=setup(tmp_path)
    class Refusal(Generator):
        def generate(self,**args):self.calls.append(args);raise RuntimeError('native image generation safety refusal; review required')
    generator=Refusal()
    with pytest.raises(RuntimeError,match='safety refusal'):
        ec.prepare(s,scene,plan,source,source,voice,Runner(),tmp_path/'supplements',generator=generator)
    assert len(generator.calls)==1


def test_pixel_motion_and_timing_tampering_invalidates_review(tmp_path):
    package,_,_,_=prepare(tmp_path)
    changed=copy.deepcopy(package);changed['files'][0]['motion']['dx']=.01
    with pytest.raises(ec.SupplementReviewRequired,match='motion or canvas'):ec.verify_package(changed)
    changed=copy.deepcopy(package);changed['timing_sha256']='different'
    with pytest.raises(ec.SupplementReviewRequired,match='timing binding'):ec.verify_package(changed)
    Path(package['files'][0]['path']).write_bytes(b'changed image')
    with pytest.raises(ec.SupplementReviewRequired,match='pixels changed'):ec.verify_package(package)


def test_attach_keeps_saved_camera_and_binds_opacity_to_recorded_phrase(tmp_path):
    package,f,_,_=prepare(tmp_path)
    source=f[3];directory=tmp_path/'render';directory.mkdir()
    base=dict(plan=dict(width=512,height=512,camera=f[2]['scene']['keys']),layers=[dict(id='original',role='background')],files={'original':str(source)})
    result=ec.attach(base,package,source,directory)
    assert result['plan']['camera']==base['plan']['camera'] and len(base['layers'])==1
    assert result['files']['original']==str(source)
    keys=result['layers'][-1]['motion']
    assert all(k['opacity']==0 for k in keys if k['t']<=.25 or k['t']>=.5)
    assert any(k['opacity']==100 for k in keys if .25<k['t']<.5)
    assert all(0<=k['t']<=1 for k in keys)


def test_bad_requests_never_generate_replacement_frames_or_retime_voice(tmp_path):
    s,scene,_,_,_=setup(tmp_path)
    for rows in ([overlay()]*5,[cutout()],[background()],[dict(overlay(),role='character')],[dict(overlay(),quote='invented')],[dict(overlay(),dx=.1)]):
        with pytest.raises(ec.SupplementReviewRequired):ec.requests(s,scene,rows)
    with pytest.raises(ec.SupplementReviewRequired):ec.requests(s,{**scene,'source_kind':'video'},[background(),cutout()])
    s['renderer']['engine']='ae'
    with pytest.raises(ec.SupplementReviewRequired):ec.requests(s,scene,[overlay()])


def test_no_missing_layers_does_not_contact_a_generator(tmp_path):
    s,scene,plan,source,voice=setup(tmp_path);plan.pop('supplemental_assets')
    assert ec.prepare(s,scene,plan,source,source,voice,None,tmp_path/'unused') is None
    assert not (tmp_path/'unused').exists()


def test_publication_is_idempotent_and_does_not_replace_the_scene_image(tmp_path):
    from motion_automation_worker import publish_supplemental
    package,_,_,_=prepare(tmp_path)
    class Api:
        def __init__(self):self.uploads=[];self.rows=[]
        def _upload_gcs_file(self,path,key,mime):self.uploads.append(key);return 'bucket',key,'url'
        def _request(self,*args,**kwargs):self.rows.append(kwargs['json'])
    api=Api();job=dict(id='job',project_id='p')
    first=publish_supplemental(package,job,1,api,'https://db.test',{},lambda:None)
    second=publish_supplemental(package,job,1,api,'https://db.test',{},lambda:None)
    assert first['asset_id']==second['asset_id']
    assert all(row['asset_type']=='other' and row['metadata']['kind']=='ec_supplemental_assets' for row in api.rows)
    assert api.rows[0]['metadata']['review']['passed'] is True


def test_remote_reviewed_assets_resume_without_regeneration_when_local_cache_is_gone(tmp_path):
    from motion_automation_worker import publish_supplemental,recover_supplemental
    from types import SimpleNamespace
    import shutil
    package,f,_,_=prepare(tmp_path)
    s,scene,plan,source,voice=f
    class Api:
        GcsRef=staticmethod(lambda bucket,path:SimpleNamespace(bucket=bucket,path=path))
        def __init__(self):self.storage={};self.metadata=None
        def _upload_gcs_file(self,path,key,mime):self.storage[key]=Path(path);return 'bucket',key,'url'
        def _download_gcs_file(self,ref,target):shutil.copyfile(self.storage[ref.path],target)
        def _request(self,method,url,headers,**kwargs):
            if method=='POST':self.metadata=kwargs['json']['metadata'];return None
            return SimpleNamespace(json=lambda:[{'metadata':self.metadata}])
    class NeverGenerate:
        def generate(self,**_):raise AssertionError('Reviewed cloud assets must be reused')
    api=Api();job=dict(id='job',project_id='p')
    summary=publish_supplemental(package,job,1,api,'https://db.test',{},lambda:None)
    restored=ec.prepare(s,scene,plan,source,source,voice,None,tmp_path/'recovered',generator=NeverGenerate(),
        recover=lambda identity,directory:recover_supplemental(identity,directory,job,{'supplemental_assets':[summary]},api,'https://db.test',{},lambda:None))
    assert restored['fingerprint']==package['fingerprint']
    assert restored['review']==package['review']
    assert Path(restored['receipt_path']).is_file()


def test_ec_direction_can_request_assets_and_resume_without_changing_source_or_timing(tmp_path):
    from motion_automation_worker import validate_direction
    s,scene,plan,source,voice=setup(tmp_path)
    s['motion'].update(version=1,enabled=True,aspect='16:9',automation={'mode':'ae_only','max_ai_clips':1,'max_ai_seconds':5})
    plan['scene'].update(source='image',fit='contain',direction='Preserve the lamp and original subject',transition='cut')
    response=dict(status='needs_assets',scene=plan['scene'],ai=None,supplemental_assets=[overlay()],
        evidence=['Original lamp is on the right side'],continuity={k:'Original registration is preserved' for k in ('entry','exit','screen_direction','lighting')})
    result=validate_direction(response,scene,s,[])
    assert result['supplemental_assets'][0]['start']==.25
    assert result['scene']['source']=='image'
    package=ec.prepare(s,scene,result,source,source,voice,Runner(),tmp_path/'supplements',generator=Generator())
    receipt=package['receipt_path']
    cached=dict(supplemental_receipt=receipt,supplemental_receipt_sha256=ec.sha(receipt),supplemental_fingerprint=package['fingerprint'])
    assert ec.output_cache_is_current(cached)
    Path(package['files'][0]['path']).write_bytes(b'tampered')
    assert not ec.output_cache_is_current(cached)


def test_submitted_ec_job_generates_reviews_publishes_and_reaches_renderer(tmp_path,monkeypatch):
    import motion_automation_worker as worker
    import ae_highlight_worker as ae
    import worker_config
    import codex_content_runner
    import effectcraft_render
    import shutil
    s,scene,plan,source,voice=setup(tmp_path)
    s['scenes']=[scene];s['motion'].update(aspect='16:9',automation={'mode':'ae_only'})
    plan['scene'].update(source='image',fit='contain',direction='Keep original composition',transition='cut')
    scene['prepared_direction']=copy.deepcopy(plan['scene'])
    scene['source']={'id':'original','file_name':'original.png','metadata':{'gcs_bucket':'bucket','gcs_path':'source.png'}}
    s['audio'].update(file_name='final.wav',metadata={'gcs_bucket':'bucket','gcs_path':'voice.wav'})
    meta=dict(kind='effectcraft_automation',enabled=True,state='queued',fingerprint='f'*64,input={})
    job=dict(id='job',project_id='p',updated_at='old',metadata=meta,workflow_project={'id':'p','submitted_at':'now','status':'review_requested'})
    class Response:
        def __init__(self,value):self.value=value
        def json(self):return self.value
    published=[];patches=[];rendered=[]
    def request(method,url,headers,**kwargs):
        if url.endswith('patch_std_motion_job'):
            changes=kwargs['json']['p_patch'];patches.append(changes);meta.update(changes);return Response(dict(meta))
        if url.endswith('/std_projects'):return Response([job['workflow_project']])
        if method=='GET':return Response([job])
        if method=='PATCH':meta.update(kwargs['json']['metadata']);return Response([{'metadata':dict(meta)}])
        if method=='POST' and url.endswith('/std_project_assets'):published.append(kwargs['json']);return Response([])
        raise AssertionError((method,url))
    def download(ref,target):shutil.copyfile(source if ref.path=='source.png' else voice,target)
    class Director(Runner):
        def _stage(self,identity,name,context,task):
            if name=='motion_auto_direction':
                assert 'EC post-submission supplemental capability' in task
                return dict(status='needs_assets',scene=copy.deepcopy(plan['scene']),ai=None,supplemental_assets=[overlay()],
                    evidence=['Original has a lamp'],continuity={k:'Same original lighting' for k in ('entry','exit','screen_direction','lighting')})
            return super()._stage(identity,name,context,task)
    def render(snapshot,submitted,direction,*args):
        rendered.append(ec.verify_package(direction['_supplemental_package']))
        raise RuntimeError('TEST_STOP_AFTER_RENDER_ENTRY')
    monkeypatch.setattr(worker_config,'PROJECT_ROOT',tmp_path)
    monkeypatch.setattr(worker,'unseal',lambda envelope:s)
    monkeypatch.setattr(worker,'voice_evidence',lambda voice,scene,work: ({'audio_sha256':ec.sha(voice)},source))
    monkeypatch.setattr(worker,'render_base',render)
    monkeypatch.setattr(effectcraft_render,'binary',lambda:Path('installed-test-engine'))
    monkeypatch.setattr(codex_content_runner,'CodexStagedContentRunner',Director)
    import manga_layer_generation
    monkeypatch.setattr(manga_layer_generation,'NativeCodexLayerGenerator',Generator)
    monkeypatch.setattr(ae,'_supabase',lambda:('https://db.test',{}))
    monkeypatch.setattr(ae,'_request',request)
    monkeypatch.setattr(ae,'_download_gcs_file',download)
    monkeypatch.setattr(ae,'_upload_gcs_file',lambda path,key,mime:('bucket',key,'url'))
    assert worker.process_one('effectcraft') is True
    assert len(rendered)==1 and len(published)==1
    assert published[0]['asset_type']=='other' and published[0]['metadata']['review']['passed'] is True
    assert any(p.get('phase')=='supplement_generation' for p in patches)
    assert any(p.get('phase')=='supplement_review' for p in patches)
    assert meta['supplemental_assets'][0]['reviewed'] is True
    assert meta['error']=='TEST_STOP_AFTER_RENDER_ENTRY'
