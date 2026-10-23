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
