"""Purpose-specific bounds and reversible, evidence-triggered direction repair."""
import copy,json,math
from pathlib import Path
CONFIG=json.loads((Path(__file__).resolve().parents[1]/'auth-web/lib/scenePurposePolicy.json').read_text(encoding='utf-8'))
CONTRACT=CONFIG['contract']
TASK="""Apply scene-purpose direction limits from purpose_direction_limits. Classify scene_role as dialogue, reaction, clue_reveal, location, tension, transition, resolution, narration, hold or action. Confirmed character dialogue takes priority over dramatic camera/effects. Preserve source movement on uploaded video; never damp baked action. In dialogue/reaction favor a stable face and quiet background; location may use a slower wider depth reveal; clue_reveal must guide attention to the actual clue without covering it; action alone may use impacts, only on an explicit finalized-voice event. Resolution/hold must settle. Evaluate previous/next scene purposes, intensity, gaze/screen direction and lighting: no sudden escalation without story evidence, repeated conspicuous effects or three identical camera moves. Effects are optional. Use cut transitions in this fixed-clock pipeline; no overlapping crossfades or retiming. Fix unsafe direction parameters when validation_feedback is provided; never change the script, dialogue attribution, source artwork or audio clock."""

def policy(scene,role):
    role='dialogue' if scene.get('has_character_dialogue') else role
    if role not in CONFIG['roles']:role='narration'
    return dict(copy.deepcopy(CONFIG['roles'][role]),contract=CONTRACT,role=role,max_repair_attempts=2)

def active(scene):
    return (scene.get('purpose_policy') or (scene.get('creative_reference') or {}).get('purpose_policy') or {}).get('contract')==CONTRACT

def validate_design(policy,keys,effects):
    if not keys:return
    for field,limit in [('x','max_move_ratio'),('y','max_move_ratio'),('scale','max_scale_delta'),('rotation','max_rotation_degrees')]:
        if max(k[field] for k in keys)-min(k[field] for k in keys)>policy[limit]+1e-7:raise ValueError('Scene purpose '+policy['role']+' exceeds '+limit)
    if len(effects)>policy['max_effects']:raise ValueError('Too many effects for scene purpose '+policy['role'])
    for effect in effects:
        if effect['type'] not in policy['allowed_effects'] or effect.get('intensity',0)>policy['intensity']+1e-7:raise ValueError('Effect is excessive or unsuitable for scene purpose '+policy['role'])

def validate_script(scene,direction):
    if scene.get('direction_policy_version')!=CONTRACT:return
    p=policy(scene,direction['scene_role']);direction['scene_role']=p['role'];direction['purpose_policy']=p
    limits=direction['effect_limits']
    for field in ('max_move_ratio','max_scale_delta','max_rotation_degrees','speed','intensity'):
        if limits[field]>p[field]+1e-7:raise ValueError('Declared '+field+' exceeds '+p['role']+' purpose limit')
    design=direction.get('execution_design') or {}
    if design and (design.get('transition') or {}).get('kind')!='cut':raise ValueError('Purpose-directed fixed-clock scenes require cut transitions')
    validate_design(p,(design.get('camera') or {}).get('keys',[]),design.get('effects',[])+direction.get('depth_effects',[])+(direction.get('submitted_video_postwork') or {}).get('effects',[]))

def validate_native(scene,plan):
    p=scene.get('purpose_policy') or (scene.get('creative_reference') or {}).get('purpose_policy')
    if not p or p.get('contract')!=CONTRACT:return
    validate_design(p,plan['camera'],plan.get('effects',[]))
    if len(plan.get('effects',[]))+len(plan.get('lights',[]))>p['max_effects']:raise ValueError('Too many lighting/effect layers for scene purpose')
    if any(k['opacity']>p['intensity']*100+1e-7 for light in plan.get('lights',[]) for k in light['keys']):raise ValueError('Lighting is excessive for scene purpose')
    from ae_scene_animation import resolved_layers
    for layer in resolved_layers(plan):validate_design(p,layer['motion'],[])

def repair(scene,attempt,reason):
    if not active(scene) or type(attempt) is not int or not 1<=attempt<=2:raise ValueError('Unsupported purpose repair')
    if '_purpose_original' not in scene:scene['_purpose_original']=copy.deepcopy({k:scene.get(k) for k in ('creative_reference','prepared_direction','reviewed_depth_effects','postwork')})
    original=scene['_purpose_original'];factor=.5**attempt
    def calm(keys):
        first=keys[0]
        result=[{**k,**{f:first[f]+(k[f]-first[f])*factor for f in ('x','y','scale','rotation')}} for k in keys]
        for key in result:
            angle=math.radians(key['rotation'])
            cover=abs(math.cos(angle))+abs(math.sin(angle))*16/9+2*max(abs(key['x']-.5),abs(key['y']-.5))
            key['scale']=max(key['scale'],cover)
        return result
    for field in ('creative_reference','prepared_direction','reviewed_depth_effects','postwork'):scene[field]=copy.deepcopy(original[field])
    scene['reviewed_depth_effects']=scene.get('reviewed_depth_effects') or []
    creative=scene.get('creative_reference') or {};design=creative.get('execution_design')
    if design:
        design['camera']['keys']=calm(design['camera']['keys']);design['effects']=[]
        design['transition']={'kind':'cut','reason':'Evidence-based quieter continuity repair','duration_seconds':0}
    prepared=scene.get('prepared_direction') or {}
    if prepared.get('keys'):prepared['keys']=calm(prepared['keys'])
    prepared.update(effects=[],transition='cut')
    if scene.get('postwork'):scene['postwork']['transition']={'kind':'cut','duration_seconds':0,'reason':'Evidence-based quieter scene boundary repair'}
    for effect in (scene.get('postwork') or {}).get('requested_effects',[]):effect['intensity']=max(.05,effect['intensity']*factor)
    for effect in scene.get('reviewed_depth_effects') or []:effect['intensity']=max(.05,effect['intensity']*factor)
    scene['_purpose_repair']={'contract':CONTRACT,'attempt':attempt,'reason':str(reason)[:1600],'factor':factor}
    return copy.deepcopy(scene['_purpose_repair'])

def apply_native_repair(scene,prepared):
    receipt=scene.get('_purpose_repair')
    if not receipt:return prepared
    plan=copy.deepcopy(prepared['plan'])
    plan['effects']=copy.deepcopy(scene.get('reviewed_depth_effects') or [])
    for light in plan.get('lights',[]):
        for key in light['keys']:key['opacity']*=receipt['factor']
    return {**prepared,'plan':plan}


def direct_with_repair(stage,job_id,context,task,validate):
    current=copy.deepcopy(context)
    for attempt in range(3):
        name='02f_scene_visual_director' if attempt==0 else f'02f_scene_visual_director_repair_{attempt}'
        result=stage(job_id,name,copy.deepcopy(current),task)
        try:return validate(result)
        except ValueError as error:
            if attempt==2:raise ValueError('Scene direction rejected after two repairs: '+str(error)) from error
            current['validation_feedback']={'error':str(error),'previous_directions':result,'scope':'Repair direction only; preserve final script and dialogue.'}


def repairable_review(response,final=False):
    if response.get('repair_scope')!='direction_only':return False
    checks=response.get('checks')
    if not isinstance(checks,list) or not checks:return False
    if any(not isinstance(c,dict) or type(c.get('passed')) is not bool or not isinstance(c.get('id'),str) or not str(c.get('evidence') or '').strip() for c in checks):return False
    if len({c['id'] for c in checks})!=len(checks):return False
    failed={c['id'] for c in checks if c['passed'] is False}
    allowed={'purpose_fit','sequence_rhythm','framing','motion','lighting','continuity','depth_finishing','visual_quality'}
    if final:allowed={'purpose_fit','sequence_rhythm','depth_finishing','visual_quality','scene_boundary','postwork_continuity'}
    return bool(failed) and failed<=allowed


def restore_attempt(scene,plan):
    receipt=(plan or {}).get('purpose_repair')
    if not receipt:return None,False
    repair(scene,receipt['attempt'],receipt['reason'])
    return receipt,plan.get('purpose_repair_applied')!=receipt['attempt']
