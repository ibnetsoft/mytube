"""Prepare and register the explicitly requested reviewed script; never render or upload."""
import copy, json, sys, time, traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
import worker_config
from worker.script_worker_store import ScriptStore
from worker.script_topic_delivery import write, complete_candidate, publish_topic, chunked_direction
from worker.codex_sfx import plan_package_sfx
from codex_content_runner import (CodexStagedContentRunner, _plan_ae_effects_for_scenes,
    _plan_ae_motion_for_scenes, resolve_directing_profile, execution_capabilities, DIRECTING_TASK,
    SCENE_VISUAL_DIRECTOR_PERSONA, validate_directorial_plans)
from purpose_direction import CONFIG as PURPOSE_CONFIG, TASK as PURPOSE_TASK
from worker.effect_scene_scope import validate_directions

ID='d57947df4af3479b85185c7ca0610a60'
ROOT_JOB=ROOT/'output/codex-local-console'/ID
OUT=ROOT_JOB/'verified-delivery'
OUT.mkdir(parents=True,exist_ok=True)
store=ScriptStore()
runner=CodexStagedContentRunner()

def status(stage, state='running', **extra):
    write(OUT/'status.json',{'status':state,'stage':stage,'updated_at':time.time(),**extra})
    print(stage,flush=True)

def prepare():
    bundle=store.get(ID)
    if bundle['job'].get('status')=='canceled':raise ValueError('사용자가 취소한 작업입니다.')
    candidate=copy.deepcopy(bundle['candidate'])
    request=copy.deepcopy(bundle['request'])
    scenes=candidate['structure']['scenes']
    if len(scenes)!=104 or sum(int(s.get('duration_seconds') or 0) for s in scenes)!=1951:
        raise ValueError('검토된 104씬·1951초 대본 버전이 아닙니다.')
    request.update(duration_minutes=33,duration_seconds=1951,required_video_scene_count=0,
        concentrated_scene_effects=True,image_layer_scene_start=19,image_layer_scene_end=50)
    payload={**request,'target_duration_seconds':1951}
    source_script=candidate['script']
    direction_path=OUT/'direction-package.json'
    if direction_path.exists():
        cached=json.loads(direction_path.read_text(encoding='utf-8'))
        if cached.get('script')==source_script: candidate=cached;scenes=candidate['structure']['scenes']
    if not direction_path.exists() or candidate['structure'].get('scene_visual_direction_status')!='planned':
        status('수정 대본 기준 104씬 장면 연출 재구성')
        profile=resolve_directing_profile(payload)
        visual_context={'language':'ja','purpose_direction_limits':PURPOSE_CONFIG,
            'execution_capabilities':execution_capabilities(payload),
            'direction_profile':{k:profile[k] for k in ('id','label','description','selection')},
            'script':source_script,'structure':candidate['structure'],
            'scenes':[{**s,'eligible_for_eye_blink':19<=i<=50} for i,s in enumerate(scenes,1)]}
        task=(SCENE_VISUAL_DIRECTOR_PERSONA+'\n'+profile['directive']+'\n'+DIRECTING_TASK+'\n'+PURPOSE_TASK+
            '\nUse the final scene_text as authoritative. Scenes 1–18 and 51 onward are a single still image '
            'with a fixed hold, no layers, effects, blinking or extra keyframes. Only scenes 19–50 may use '
            'story-motivated effects and layers. No slow or whole-scene zooms. No actual imagery has been '
            'inspected; all plans are provisional. Return topic_direction and scene_directions in exact order.')
        result=chunked_direction(runner._stage,'delivery-'+ID,'02f_scene_visual_director',visual_context,task)
        plans=validate_directorial_plans(scenes,result,direction_profile=profile['id'],require_execution=True)
        validate_directions({'start':19,'end':50},scenes,plans)
        for i,(scene,direction) in enumerate(zip(scenes,plans),1):
            if (i<19 or i>50) and (direction.get('execution_design') or {}).get('camera',{}).get('kind') != 'hold':
                raise ValueError(f'{i}씬은 고정 이미지 유지가 필요합니다.')
            scene['scene_direction_plan']=direction
            scene['ae_directorial_plan']=direction
            if i<19 or i>50:
                scene['ae_effect_plan']={'enabled':False,'reason':'outside_effect_scene_range'}
                scene['ae_motion_plan']={'enabled':False,'reason':'outside_effect_scene_range'}
            elif direction.get('requires_layered_assets'):
                scene['ae_effect_plan']={'enabled':True,'template':'directed_performance',
                    'template_source':'scene_visual_director','preset':'directed_scene_performance',
                    'duration_seconds':float(scene['duration_seconds']),'direction':direction['visual_strategy'],
                    'dramatic_intent':direction['dramatic_intent'],
                    'asset_requirements':{'required_layers':direction['required_layers'],'optional_layers':[]},
                    'beats':[{'at_seconds':b['start_seconds'],'end_seconds':b['end_seconds'],
                              'action':b['action'],'target':b['target']} for b in direction['timed_beats']],
                    'qa_assertions':direction['qa_assertions'],'continuity_rules':direction['continuity_rules'],
                    'required_keyframes':direction['additional_keyframes'],'directorial_plan':direction,
                    'scene_direction_plan':direction,'focus_target':direction['focus_target'],
                    'primary_effect':direction['primary_effect'],'secondary_effects':direction['secondary_effects'],
                    'effect_limits':direction['effect_limits'],'fallback':direction['fallback']}
        structure=candidate['structure']
        effects=_plan_ae_effects_for_scenes(scenes,payload)
        motion=_plan_ae_motion_for_scenes(scenes,payload)
        structure.update(scene_visual_direction_status='planned',scene_visual_direction_count=len(plans),
            scene_direction_plan_contract='scene_direction_plan/v2',
            scene_direction_plans=[{'scene_number':i,**p} for i,p in enumerate(plans,1)],
            effect_scene_range={'start':19,'end':50},ae_effect_plans=effects,ae_effect_scene_count=len(effects),
            ae_effect_plan_status='planned' if effects else 'not_required',
            ae_motion_plans=motion,ae_motion_scene_count=len(motion),
            ae_motion_plan_status='planned' if motion else 'not_required')
        write(direction_path,candidate)
    status('수정 대본 기준 효과음 재구성')
    previous=candidate.get('sfx_cues') or []
    protected=[c for c in previous if c.get('source')!='codex-sfx-v1' or c.get('user_override') or c.get('keep_ai')]
    plan=plan_package_sfx(runner,'delivery-'+ID,candidate,protected)
    if plan['status']!='ready':raise ValueError('효과음 재구성 실패: '+plan['status'])
    if any(c.get('needs_review') for c in plan.get('cues',[])):
        candidate['structure'].setdefault('quality_notes',[]).append({'stage':'sfx_reanchor','passed':False,
            'issues':['기존 사용자 효과음의 변경된 대본 위치 재검토 필요']})
    write(OUT/'sfx-package.json',candidate)
    status('유저웹 장면 프롬프트와 메타데이터 준비')
    package=complete_candidate(ID,candidate,request,runner,OUT,lambda stage:status(stage))
    status('유저웹 토픽 등록 및 저장 검증')
    receipt=publish_topic(ID,package,request,store,OUT)
    latest=store.get(ID)
    if latest['job'].get('status')=='canceled' or latest['candidate'].get('script')!=source_script:
        raise ValueError('등록 중 원본 대본이 변경 또는 취소됐습니다.')
    latest['candidate']=package
    latest['job'].update(published=True,topic_queue_id=receipt['topic_id'],status='completed',
        stage='유저웹 토픽 등록 및 연출·효과음 확인 완료',updated_at=time.time(),remaining=package.get('remaining',[]))
    store.save(latest)
    write(ROOT_JOB/'candidate.json',package);write(ROOT_JOB/'job.json',latest['job'])
    write(OUT/'quality-notes.json',{'script_quality_report':package.get('script_quality_report'),
        'quality_notes':package['structure'].get('quality_notes',[]),'actual_images_reviewed':False,
        'timing_note':'효과음과 장면 타이밍은 실제 음성·원본 이미지 확정 후 재검증 필요',
        'scene_count':len(scenes),'duration_seconds':1951,'sfx_cues':len(plan.get('cues',[]))})
    status('유저웹 토픽 등록 완료',state='completed',**receipt)

if __name__=='__main__':
    lock=(OUT/'supervisor.lock').open('a+b')
    lock.write(b'0');lock.flush();lock.seek(0)
    if sys.platform=='win32':
        import msvcrt
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    attempt=0
    while True:
        try:prepare();break
        except Exception as error:
            if '취소' in str(error):status('사용자 취소',state='canceled');break
            attempt+=1
            write(OUT/'last-error.json',{'message':str(error),'type':type(error).__name__,
                'traceback':traceback.format_exc(),'updated_at':time.time(),'retry':attempt})
            delay=min(300,20*2**min(attempt,4))
            status('오류 기록 · 저장된 단계에서 복구 대기',state='retry_wait',error=str(error),retry=attempt,retry_after=time.time()+delay)
            time.sleep(delay)
