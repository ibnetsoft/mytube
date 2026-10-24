import copy
import hashlib
import json
from PIL import Image
import pytest
from worker.horizontal_webtoon import validate_plan,write_jsx,prepare

def plan():
    return {'version':1,'evidence':['Two panels separated by a visible gutter; speech balloons remain inside source crops'],
            'shots':[{'start':0,'end':1,'panels':[
                {'crop':[0,0,1,.5],'frame':[0,0,.5,1],'reveal':0,'zoom_from':1,'zoom_to':1.05},
                {'crop':[0,.5,1,.5],'frame':[.5,0,.5,1],'reveal':.3,'zoom_from':1,'zoom_to':1}]}]}

def test_native_script_preserves_crops_and_voice_clock(tmp_path):
    image=Image.new('RGB',(100,200),'red');image.paste('blue',(0,100,100,200));source=tmp_path/'original.png';image.save(source)
    jsx,project,native=write_jsx(source,plan(),tmp_path,5,24)
    assert Image.open(tmp_path/'panel-0-0.png').getpixel((50,50))==(255,0,0)
    assert Image.open(tmp_path/'panel-0-1.png').getpixel((50,50))==(0,0,255)
    data=json.loads(jsx.read_text().split(';\n',1)[0][6:])
    assert data['duration']==5 and data['panels'][1]['reveal']==.3
    assert data['status']==str((tmp_path/'webtoon.status.txt').resolve())
    assert "reportStatus('success|'" in jsx.read_text()
    assert "reportStatus('error|'" in jsx.read_text()
    assert 'Math.max(p.zoom_from,p.zoom_to)' in jsx.read_text()  # Contain even at maximum zoom.
    assert project.suffix=='.aep' and native.suffix=='.avi'
    receipt=json.loads((tmp_path/'webtoon-execution.json').read_text())
    assert receipt['source_sha256']==hashlib.sha256(source.read_bytes()).hexdigest()

@pytest.mark.parametrize('change',[
    lambda p:p['shots'][0].update(start=.1),lambda p:p['shots'][0].update(end=.8),
    lambda p:p['shots'][0]['panels'][0].update(crop=[0,0,2,1]),
    lambda p:p['shots'][0]['panels'][1].update(frame=[0,0,1,1]),
    lambda p:p['shots'][0]['panels'][0].update(reveal=.2),
    lambda p:p['shots'][0]['panels'][0].update(zoom_to=True),
])
def test_invalid_plan_stops_before_native_execution(change):
    p=plan();change(p)
    with pytest.raises(ValueError):validate_plan(p,5)

def test_uncertain_source_never_gets_ready_receipt(tmp_path):
    source=tmp_path/'original.png';Image.new('RGB',(100,200),'white').save(source)
    class Runner:
        def _stage(self,*args):return {'status':'needs_repair','reason':'Panel edge hidden'}
    with pytest.raises(ValueError,match='Panel edge hidden'):prepare({'duration':5,'subtitles':[]},source,tmp_path,Runner())
    assert not (tmp_path/'direction.json').exists()

def layered_source(directory):
    from PIL import ImageDraw
    from psd_tools import PSDImage
    from psd_tools.api.layers import PixelLayer
    psd=PSDImage.new('RGBA',(320,180))
    background=Image.new('RGBA',psd.size,'#334455')
    person=Image.new('RGBA',psd.size)
    draw=ImageDraw.Draw(person);draw.ellipse((130,30,180,80),fill='#ddbb99');draw.rectangle((120,80,190,160),fill='#00aaaa')
    for name,image in [('background',background),('character',person)]:PixelLayer.frompil(image,psd,name)
    path=directory/'layered.psd';psd.save(path);return path

def character_plan():
    return {'version':1,'evidence':['Independent character on a complete background'],
        'layer_motion':[{'layer':1,'anchor':[.5,.85],'from':{'offset':[0,0],'rotation':0},'to':{'offset':[.025,0],'rotation':3}}],
        'shots':[{'start':0,'end':1,'panels':[{'crop':[0,0,1,1],'frame':[0,0,1,1],'reveal':0,'zoom_from':1,'zoom_to':1}]}]}

def test_real_character_layers_remain_separate_in_native_project(tmp_path):
    source=layered_source(tmp_path)
    jsx,_,_=write_jsx(source,character_plan(),tmp_path,3,24)
    data=json.loads(jsx.read_text().split(';\n',1)[0][6:])
    assert len(data['layers'])==2 and data['layers'][0]['opaque'] and not data['layers'][1]['opaque']
    assert data['layer_motion'][0]['layer']==1 and data['video'] is None
    assert json.loads((tmp_path/'webtoon-execution.json').read_text())['motion_mode']=='separated_character'

def test_script_planning_receives_real_layers_and_publishes_motion_capability(tmp_path):
    source=layered_source(tmp_path)
    class Runner:
        def _stage(self,job,stage,context,task):
            assert context['source_kind']=='layered_psd'
            assert [layer['name'] for layer in context['layers']]==['background','character']
            assert 'never cyclic' in task
            return character_plan()
    prepare({'duration':3,'subtitles':[]},source,tmp_path,Runner())
    assert json.loads((tmp_path/'direction.json').read_text())['webtoon']['motion_capability']=='separated_character'

def test_flat_image_cannot_be_mislabeled_character_motion(tmp_path):
    source=tmp_path/'flat.png';Image.new('RGB',(320,180),'white').save(source)
    with pytest.raises(ValueError,match='인물 레이어'):write_jsx(source,character_plan(),tmp_path,3,24)

@pytest.mark.parametrize('bad',[0,True,-1,999])
def test_invalid_character_target_is_rejected(tmp_path,bad):
    source=layered_source(tmp_path);p=character_plan();p['layer_motion'][0]['layer']=bad
    with pytest.raises(ValueError):write_jsx(source,p,tmp_path,3,24)

def test_video_clock_is_continuous_and_short_video_stops(tmp_path):
    import subprocess
    from worker.ae_media_utils import ffmpeg
    source=tmp_path/'source.mp4'
    subprocess.run([ffmpeg(),'-v','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=24:duration=2','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True)
    p=character_plan();p.pop('layer_motion')
    jsx,_,_=write_jsx(source,p,tmp_path,1.5,24)
    data=json.loads(jsx.read_text().split(';\n',1)[0][6:])
    assert data['video']==str(source.resolve())
    assert 'original.startTime=0;original.stretch=100' in jsx.read_text()
    with pytest.raises(ValueError,match='2.000초 / 필요한 구간 3.000초'):write_jsx(source,p,tmp_path,3,24)
