"""Repair only the unclaimed topic 3386 direction; do not create media or publish."""
import copy, hashlib, json, sys, time, traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
import worker_config
from worker.script_worker_store import ScriptStore
from worker.script_topic_delivery import chunked_direction, write, web_readiness
from codex_content_runner import (CodexStagedContentRunner, resolve_directing_profile, execution_capabilities,
    SCENE_VISUAL_DIRECTOR_PERSONA, DIRECTING_TASK, validate_directorial_plans,
    _plan_ae_effects_for_scenes, _plan_ae_motion_for_scenes, _plan_image_generation_efficiency)
from purpose_direction import CONFIG, TASK as PURPOSE_TASK
from worker.effect_scene_scope import validate_directions

ID='d57947df4af3479b85185c7ca0610a60'; TOPIC='3386'
OUT=ROOT/'output/codex-local-console'/ID/'verified-delivery'
store=ScriptStore(); runner=CodexStagedContentRunner()
def status(stage,state='running',**extra):
    write(OUT/'direction-repair-status.json',{'stage':stage,'status':state,'updated_at':time.time(),**extra})
def topic():
    rows,_=store.request('GET','topics_queue',params={'select':'*','id':'eq.'+TOPIC})
    if len(rows)!=1:raise ValueError('토픽을 찾을 수 없습니다.')
    t=rows[0]
    if t.get('status')!='pending' or t.get('assigned_at') or t.get('assigned_employee_email'):
        raise ValueError('토픽의 소유 또는 취소 상태가 변경되어 자동 수정할 수 없습니다.')
    if (t.get('progress_payload') or {}).get('source_script_job_id')!=ID:raise ValueError('토픽 출처 불일치')
    return t
try:
    t=topic(); bundle=store.get(ID)
    if bundle['job'].get('status')=='canceled' or t['pregenerated_script']!=bundle['candidate']['script']:
        raise ValueError('원본 대본 불일치 또는 취소됨')
    source=hashlib.sha256(t['pregenerated_script'].encode()).hexdigest()
    structure=copy.deepcopy(t['pregenerated_structure']);scenes=structure['scenes']
    if len(scenes)!=104:raise ValueError('씬 수 불일치')
    write(OUT/'before-direction-repair.json',t)
    request={**bundle['request'],'concentrated_scene_effects':True,'image_layer_scene_start':19,
             'image_layer_scene_end':50,'required_video_scene_count':0,'target_duration_seconds':1951}
    profile=resolve_directing_profile(request); selected=scenes[18:50]
    context={'language':'ja','purpose_direction_limits':CONFIG,'execution_capabilities':execution_capabilities(request),
        'direction_profile':{k:profile[k] for k in ('id','label','description','selection')},
        'script':t['pregenerated_script'],'structure':structure,
        'scenes':[{**s,'eligible_for_eye_blink':True} for s in selected]}
    task=(SCENE_VISUAL_DIRECTOR_PERSONA+'\n'+profile['directive']+'\n'+DIRECTING_TASK+'\n'+PURPOSE_TASK+
       '\nFor EVERY supplied scene 19–50, author at least one concrete, story-motivated visible effect '
       'or layer animation as the primary operation or execution_design effect. Holds may support an effect '
       'but must not be the only action. Use a fixed camera (camera.kind=hold) and no zoom. Select actual '
       'plausible source elements only, explain their link to narration, vary effects and avoid decorative '
       'invention. All coordinates and artwork verification are provisional. Do not claim images inspected. '
       'Return topic_direction and one scene_directions entry per supplied scene in order.')
    status('19~50씬 실제 효과 연출 재작성')
    result=chunked_direction(runner._stage,'repair-topic-'+ID,'02f_scene_visual_director',context,task)
    plans=validate_directorial_plans(selected,result,direction_profile=profile['id'],require_execution=True)
    for number,(scene,direction) in enumerate(zip(selected,plans),19):
        execution=direction.get('execution_design') or {}; camera=execution.get('camera') or {}
        operations=set(direction.get('ae_operations') or [])
        if camera.get('kind')!='hold':raise ValueError(f'{number}씬 고정 카메라 필요')
        if not execution.get('effects') and not (operations-{'hold','transition'}):
            raise ValueError(f'{number}씬에 실제 효과 방향이 없습니다')
        scene['scene_direction_plan']=direction;scene['ae_directorial_plan']=direction
        scene['ae_effect_plan']={'enabled':False,'reason':'authored_direction_uses_motion_plan'}
    # Outside the explicitly selected scope no synthetic ambient animation is allowed.
    for i,s in enumerate(scenes,1):
        if not 19<=i<=50:
            s['ae_effect_plan']={'enabled':False,'reason':'outside_effect_scene_range'}
            s['ae_motion_plan']={'enabled':False,'reason':'outside_effect_scene_range'}
    directions=[s['scene_direction_plan'] for s in scenes]
    validate_directions({'start':19,'end':50},scenes,directions)
    effects=_plan_ae_effects_for_scenes(scenes,request)
    motions=_plan_ae_motion_for_scenes(scenes,request)
    policy=_plan_image_generation_efficiency(scenes,request,effects)
    for i,s in enumerate(scenes,1):
        if i<19 or i>50:
            if (s.get('ae_effect_plan') or {}).get('enabled') or (s.get('ae_motion_plan') or {}).get('enabled'):
                raise ValueError(f'{i}씬에 범위 밖 동작이 남아 있습니다.')
        elif not (s.get('ae_effect_plan') or {}).get('enabled') and not (s.get('ae_motion_plan') or {}).get('enabled'):
            raise ValueError(f'{i}씬 효과 계획이 연결되지 않았습니다.')
    structure.update(scenes=scenes,scene_direction_plans=[{'scene_number':i,**d} for i,d in enumerate(directions,1)],
        scene_visual_direction_status='planned',scene_visual_direction_count=len(scenes),
        ae_effect_plans=effects,ae_effect_scene_count=len(effects),ae_motion_plans=motions,ae_motion_scene_count=len(motions),
        image_generation_policy=policy,psd_layer_prompts=policy.get('psd_layer_prompts',[]))
    # Inspect executable fields, not prose that may explicitly prohibit slow zooms.
    for i,s in enumerate(scenes,1):
        for key in ('ae_effect_plan','ae_motion_plan'):
            plan=s.get(key) or {}
            if plan.get('enabled') and any(term in str(plan.get('camera') or '').lower()
                    for term in ('slow depth push','slow_push_in','slow zoom','slow push-in')):
                raise ValueError(f'{i}씬 실행 카메라에 느린 줌이 남아 있습니다.')
        camera=((s.get('scene_direction_plan') or {}).get('execution_design') or {}).get('camera') or {}
        if camera.get('kind') not in ('hold',None):
            raise ValueError(f'{i}씬에 고정 카메라가 아닌 연출이 남아 있습니다.')
    status('조건부 토픽 저장 및 재조회')
    now=topic()
    if hashlib.sha256(now['pregenerated_script'].encode()).hexdigest()!=source:
        raise ValueError('원본 대본이 변경되어 저장하지 않았습니다.')
    progress=copy.deepcopy(now.get('progress_payload') or {})
    progress['direction_repair']={'scope':[19,50],'outside_scope':'fixed_image','review_status':'planned_actual_assets_pending'}
    rows,_=store.request('PATCH','topics_queue',params={'id':'eq.'+TOPIC,'status':'eq.pending',
        'assigned_at':'is.null','assigned_employee_email':'eq.','progress_payload->>source_script_job_id':'eq.'+ID},
        body={'pregenerated_structure':structure,'progress_payload':progress},prefer='return=representation')
    if len(rows)!=1:raise ValueError('조건부 저장 실패: 소유권 또는 상태를 다시 확인하세요.')
    saved=topic()
    if saved['pregenerated_structure']!=structure or saved['pregenerated_script']!=t['pregenerated_script']:
        raise ValueError('저장된 토픽의 실제 재조회가 일치하지 않습니다.')
    check=web_readiness(saved,OUT)
    if not check['ready']:raise ValueError('저장 후 유저웹 준비상태 확인 실패')
    write(OUT/'direction-repair-receipt.json',{'topic_id':3386,'effect_scenes':list(range(19,51)),
         'static_scenes':list(range(1,19))+list(range(51,105)),'ready':check,'images_reviewed':False,
         'voice_timing_verified':False})
    status('3386 연출 보정 및 재조회 완료','completed')
except Exception as exc:
    write(OUT/'direction-repair-error.json',{'message':str(exc),'traceback':traceback.format_exc(),'updated_at':time.time()})
    status('3386 연출 보정 중단','failed',error=str(exc))
