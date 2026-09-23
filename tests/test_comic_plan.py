import copy
import pytest
from worker.comic_plan import validate_plan, plan_comic

def plan(count=14):
    return {'scenes':[{'scene_number':i,'motion':'video' if i==14 else 'pan',
        'image_prompt':'Consistent character in a mountain temple with lettering whitespace.',
        'video_prompt':'A steady portrait with drifting hair and fog, no audio.'} for i in range(1,count+1)],
        'pages':[{'layout':'grid6','scene_numbers':list(range(1,7))},{'layout':'grid','scene_numbers':list(range(7,11))},
                 {'layout':'sequence','scene_numbers':list(range(11,15))}]}

def test_motion_after_hook_and_page_coverage():
    value=validate_plan(plan(),[{}]*14)
    assert value['render_settings']['page_layouts']=={'0':'grid6','1':'grid','2':'sequence'}
    assert value['render_settings']['panels']['14']['motion']=='video'
    bad=plan();bad['pages'][1]['scene_numbers'][0]=6
    with pytest.raises(ValueError):validate_plan(bad,[{}]*14)
    bad=plan();bad['scenes'][-1]['video_prompt']=''
    with pytest.raises(ValueError):validate_plan(bad,[{}]*14)

def test_comic_plan_saved_without_rewriting_final_dialogue():
    class Runner:
        def _stage(self,*args):return plan()
    package={'script':'Final dialogue stays unchanged','structure':{'scenes':[{'scene_text':f'scene {i}'} for i in range(14)]}}
    before=copy.deepcopy(package)
    plan_comic(Runner(),'test',package,lambda _:None)
    assert package['script']==before['script']
    assert package['structure']['scenes'][-1]['video_prompt_required']
    assert not package['structure']['scenes'][0]['video_prompt_required']
    assert package['render_settings']['comic']==package['structure']['comic_plan']['render_settings']

def test_worker_request_mode_is_opt_in():
    from worker.codex_local_console import StartRequest
    assert StartRequest(mode='new').production_mode=='standard'
    assert StartRequest(mode='new',production_mode='moving_comic').production_mode=='moving_comic'
    with pytest.raises(ValueError):StartRequest(mode='new',production_mode='wrong')

@pytest.mark.parametrize('invalid',[None,[],{'scenes':None},{'scenes':[None]}])
def test_malformed_ai_output_is_retriable(invalid):
    with pytest.raises(ValueError):validate_plan(invalid,[{}])
