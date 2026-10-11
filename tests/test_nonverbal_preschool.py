import copy
import json
import pytest
from worker.nonverbal_preschool import build_package, validate_package, validate_review, schedule, generate


def fixture():
    parts = [{'id':pid,'name':pid,'parentId':parent,'anchor':[.5,.5],
        'polygon':[[.4,.4],[.6,.4],[.6,.6],[.4,.6]],'image_prompt':'complete transparent reusable part '*6,
        'overlap_prompt':'Complete hidden rounded ends with painted overlap and no seam.'} for pid,parent in [('body',''),('leg','body'),('calf','leg')]]
    return {'generated_title':'공을 찾는 친구','story_outline':'작은 친구가 굴러간 공을 찾고 다시 바구니에 담는 행동으로 원인과 결과를 보여준다.',
        'publish_metadata':{'description':'말 없이 행동과 표정으로 공을 찾는 과정을 보여주는 어린이용 애니메이션입니다.'},
        'bgm_prompt':'Gentle instrumental playful marimba, no voice, no lyrics, soft percussion and small pauses. '*2,
        'character_rigs':[{'character_id':'friend','name':'친구','reference_prompt':'Original rounded friendly 2D toddler character with simple colors and reusable articulated limbs. '*2,'parts':parts}],
        'scenes':[{'scene_number':i+1,'duration_seconds':6,'cast':['friend'],
            'action_summary':'친구가 공을 바라보고 천천히 걸어가 공을 양손으로 집는다.',
            'image_prompt':'Clear original rounded character standing near a bright ball, simple readable silhouettes and fixed rest pose. '*2,
            'background_prompt':'Empty soft pastel playground, no characters, a basket and clear uncluttered floor, fixed camera and light. '*2,
            'direction_prompt':'At zero seconds look at the ball, walk slowly toward it, then pause and reach down to grasp it. '*2,
            'timed_beats':[{'start_seconds':0,'end_seconds':6,'target':'friend','action':'Walk to ball then hold'}],
            'motions':[{'part_id':'leg','action':'walk','start':0,'period':2,'cycles':2,'amplitude':20},
                       {'part_id':'calf','action':'walk','start':0,'period':2,'cycles':2,'amplitude':30,'walkPart':'lower','phaseOffset':.5}],
            'qa_assertions':['Feet contact the floor without gaps at the knee.']} for i in range(10)]}


def reviewed():
    return {'verdict':'pass','critical_issues':[], 'checks':[{'name':name,'passed':True,'evidence':'Observed in the supplied scene plan.'} for name in ['visual_story','child_suitability','timing','no_speech','reusable_parts','joint_motion']]}


def test_reusable_joint_contract_without_narration():
    p=build_package(fixture(),{'target_duration_seconds':60})
    p['script_quality_report']=reviewed();validate_package(p)
    assert p['script']=='' and p['production_ready'] is False
    scene=p['structure']['scenes'][0]
    assert scene['scene_text']=='' and scene['video_generation_mode']=='ae_joint_rig'
    assert scene['joint_motion_plan']['regions'][2]['parentId']=='leg'
    assert scene['joint_motion_plan']['regions'][2]['phaseOffset']==.5
    assert scene['joint_motion_plan']['regions'][0]['action']=='hold'
    assert all(r['occluded'] for r in scene['joint_motion_plan']['regions'])


@pytest.mark.parametrize('mutation', ['speech','cycle','timing','phase','unknown_part','overlap'])
def test_rejects_broken_animation_contract(mutation):
    raw=fixture()
    if mutation=='speech': raw['scenes'][0]['narration']='hello'
    elif mutation=='cycle': raw['character_rigs'][0]['parts'][0]['parentId']='calf'
    elif mutation=='timing': raw['scenes'][0]['motions'][0]['cycles']=10
    elif mutation=='phase': raw['scenes'][0]['motions'][0]['phaseOffset']=2
    elif mutation=='unknown_part': raw['scenes'][0]['motions'][0]['part_id']='missing'
    else: raw['character_rigs'][0]['parts'][0]['overlap_prompt']=''
    with pytest.raises(ValueError): build_package(raw,{'target_duration_seconds':60})


def test_schedule_and_independent_review():
    assert sum(s['duration_seconds'] for s in schedule(61))==61
    with pytest.raises(ValueError):schedule(601)
    report=reviewed();report['checks'][0]['passed']=False
    with pytest.raises(ValueError):validate_review(report)


def test_local_stages_never_generate_narration():
    class Runner:
        stages=[]
        def _stage(self, job, name, payload, prompt):
            self.stages.append(name)
            return reviewed() if name.endswith('review') else fixture()
    runner=Runner();p=generate(runner,'test',{'production_mode':'nonverbal_preschool','target_duration_seconds':60,'language':'ko','setting_country':'한국','era_region':'현대'})
    assert len(runner.stages)==2 and p['script']==''
    validate_package(p)


def test_stale_or_modified_derived_plan_is_rejected():
    p=build_package(fixture(),{'target_duration_seconds':60});p['script_quality_report']=reviewed()
    p['structure']['scenes'][0]['joint_motion_plan']['regions'][1]['parentId']='missing'
    with pytest.raises(ValueError):validate_package(p)


def test_console_and_web_requests_select_nonverbal_contract():
    from worker.codex_local_console import StartRequest
    from worker.web_topic_submissions import generation_request
    r=StartRequest(mode='new',production_mode='nonverbal_preschool',duration_minutes=3,title='공 찾기')
    assert r.required_video_scene_count==0 and r.script_style=='nonverbal_preschool'
    with pytest.raises(ValueError):StartRequest(mode='new',production_mode='nonverbal_preschool',duration_minutes=11)
    request=generation_request({'id':'test','request_data':{'title':'공 찾기','story':'공을 찾는다', 'category':'이야기', 'duration_minutes':3,'language':'ko','setting_country':'한국','era_region':'현대','image_style':'anime','production_mode':'nonverbal_preschool','script_style':'nonverbal_preschool'}})
    assert request['required_video_scene_count']==0
