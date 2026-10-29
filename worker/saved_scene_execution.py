"""Execute numbered saved topic directions against actual prepared assets."""
import copy,math
CONTRACT='saved_scene_execution/v1'
def validate_lights(lights):
    if not isinstance(lights,list) or len(lights)>2:raise ValueError('Invalid saved light count')
    for light in lights:
        if not isinstance(light.get('color'),list) or len(light['color'])!=3 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1 for v in light['color']):raise ValueError('Invalid saved light color')
        if not isinstance(light.get('center'),list) or len(light['center'])!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1 for v in light['center']):raise ValueError('Invalid saved light center')
        if not isinstance(light.get('radius'),(int,float)) or not .02<=light['radius']<=1:raise ValueError('Invalid saved light radius')
        keys=light.get('keys') or []
        if not 2<=len(keys)<=8 or keys[0].get('t')!=0 or keys[-1].get('t')!=1:raise ValueError('Invalid saved light timing')
        if any(not isinstance(k.get('t'),(int,float)) or not math.isfinite(k['t']) or not 0<=k['t']<=1 or not isinstance(k.get('opacity'),(int,float)) or not math.isfinite(k['opacity']) or not 0<=k['opacity']<=15 for k in keys):raise ValueError('Invalid saved light opacity')
        if any(b['t']<=a['t'] for a,b in zip(keys,keys[1:])):raise ValueError('Saved light times must increase')
    return copy.deepcopy(lights)
def bind_prepared(prepared,scene,execution):
    binding=scene.get('saved_direction_binding') or {}
    if binding.get('contract')!=CONTRACT:return prepared
    result={**prepared,'plan':copy.deepcopy(prepared['plan'])};plan=result['plan']
    plan['camera']=copy.deepcopy(execution['keys']);plan['effects']=copy.deepcopy(execution.get('effects',[]));plan['lights']=validate_lights(execution.get('lights',[]));plan['saved_direction_binding']=copy.deepcopy(binding)
    motion=execution.get('layer_motion')
    if motion:
        if motion.get('contract')!=CONTRACT:raise ValueError('Invalid saved layer binding')
        by_role={l.get('role'):l for l in plan['layers']}
        if not all(r in by_role for r in ('background','character','foreground')):raise ValueError('Actual background/character/foreground layers are required')
        a,b=motion['from'],motion['to'];delta=motion['move_x']
        if not 0<=a<b<=1 or not isinstance(delta,(int,float)) or not math.isfinite(delta) or abs(delta)>.025:raise ValueError('Unsafe saved layer movement')
        for role,ratio in [('background',0),('character',.5),('foreground',1)]:
            layer=by_role[role];base={'x':0,'y':0,'scale':1,'rotation':0,'opacity':100}
            keys=[{'t':0,**base},{'t':a,**base},{'t':b,**base,'x':delta*ratio},{'t':1,**base,'x':delta*ratio}]
            layer['motion']=[k for i,k in enumerate(keys) if i==0 or k['t']>keys[i-1]['t']]
    return result
