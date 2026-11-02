"""Keep episode 2 directions consistent with its indirect narration and camera brief."""
import copy

def normalize_scene(scene):
    scene=copy.deepcopy(scene)
    n=int(scene['scene_number']);duration=float(scene['duration_seconds'])
    original=scene.get('execution_design') or (scene.get('scene_direction_plan') or {}).get('execution_design') or {}
    design=copy.deepcopy(original)
    camera=copy.deepcopy(design.get('camera') or {})
    kind=camera.get('kind','hold')
    if kind not in ('push','pull','pan') or not camera.get('reason') or len(camera.get('keys') or [])<2:
        camera={'kind':'hold','reason':'Preserve the narrated situation and original composition.',
                'keys':[dict(t=0,x=.5,y=.5,scale=1,rotation=0,opacity=100),dict(t=1,x=.5,y=.5,scale=1,rotation=0,opacity=100)]}
    else:
        first={**camera['keys'][0],'t':0};last={**camera['keys'][-1],'t':1}
        a=min(.2,1.5/duration);b=min(.95,a+min(3,duration*.6)/duration)
        camera['keys']=[first,{**first,'t':a},{**last,'t':b},last]
        camera.update(movement_seconds=(b-a)*duration,holds_before_after=True)
    camera.update(speed_policy='no_slow_zoom/v1',timing_status='provisional_until_recorded_audio')
    design['camera']=camera
    design['graphics']={'speech_bubbles':False,'speedlines':False,'reason':'Photorealistic indirect narration.'}
    design['source_review']='planned_prompts_only_actual_scene_images_not_generated'
    design['timing_review']='pending_recorded_audio'
    if not 19<=n<=50:design['effects']=[]
    scene['execution_design']=copy.deepcopy(design)
    for key in ('scene_direction_plan','ae_directorial_plan','ae_effect_plan','ae_motion_plan'):
        if not isinstance(scene.get(key),dict):continue
        plan=scene[key]
        plan['execution_design']=copy.deepcopy(design)
        if 'camera' in plan:plan['camera']=camera['kind']
        if 'primary_effect' in plan:plan['primary_effect']=camera['kind'] if not 19<=n<=50 else plan['primary_effect']
        if not 19<=n<=50 and key=='ae_effect_plan':plan['enabled']=False
        if 'speech_bubble_plan' in plan:plan['speech_bubble_plan']={'contract':'speech_bubble_presets/v1','cues':[]}
        for nested in ('directorial_plan','scene_direction_plan'):
            if isinstance(plan.get(nested),dict):
                plan[nested]['execution_design']=copy.deepcopy(design)
                plan[nested]['speech_bubble_plan']={'contract':'speech_bubble_presets/v1','cues':[]}
    def remove_slow(value):
        if isinstance(value,dict):return {k:remove_slow(v) for k,v in value.items()}
        if isinstance(value,list):return [remove_slow(v) for v in value]
        return 'hold' if isinstance(value,str) and value in ('slow_push_in','slow_pull_back','slow_zoom_in','slow_zoom_out','slow_pan_left','slow_pan_right') else value
    return remove_slow(scene)
