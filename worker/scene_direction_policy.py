"""Explicit future-topic direction; old saved contracts are never upgraded in place."""
from __future__ import annotations
import copy
import math

CONTRACT = 'scene_direction_plan/v2'
DIRECTING_TASK = '''For NEW topics return topic_direction:{genre,visual_language,reason,continuity_rules},
where visual_language is cinematic, illustrated_drama, or comic_action. Derive this
from this topic's story, audience and era, not a universal preset. Also return
execution_design for EACH scene: {camera:{kind,reason,reversal_reason,keys},
cue:{quote,phase},effects:[{type,reason,intensity,center,radius,color,event}],
transition:{kind,reason},graphics:{speech_bubbles,speedlines,reason}}.
camera.kind is hold, push, pull or pan. keys are 2..6 normalized poses
{t,x,y,scale,rotation,opacity}, endpoints t=0,1; x/y .44..56, scale1..1.08,
rotation -1..1, opacity100. Use one motivated screen direction and an intentional
settle/hold; never oscillate to fill time. Reversal requires a specific visible
story action in reversal_reason. Sample gentle acceleration/deceleration in key
spacing; preserve monotonic travel without overshoot. Leave room for voice-bound
start/end hold keys. Enable graphics only when execution_capabilities permits them.
All separated layers respond to ONE camera;
do not animate unrelated alternate layers in opposite directions. Without depth
assets choose a flat camera move or hold, never synthesize fake depth.
cue.quote is an exact unique phrase from this scene's narration; phase is before,
during, or after. Its key timing is provisional until matched to the finalized
recording's subtitle intervals. No invented speech, word timestamps or audition.
Holds need no quote. Distinguish narration from spoken dialogue. speech_bubbles
and speedlines default false; a bubble needs visible identified speaker and safe
negative space, and speedlines require comic_action plus a brief physical action,
never mere emotional words. Specify a reason for every graphic. Choose holds and
quiet reactions in the sequence; do not repeat the same camera move three scenes
in a row. Do not mandate an effect count. Coordinates remain provisional until
actual source imagery is inspected. Unsupported art/motion => needs_repair.
Choose zero to two restrained finishing effects only when visible source detail and
story beat justify them. Allowed types: atmospheric_haze,warm_dust_motes,focus_glow,
light_sweep,impact_flash,subtle_vignette,impact_shake,shock_ring. Each effect has
intensity .05.. .35, normalized center/radius/color and a concrete visible reason.
An event effect has event:{quote,phase,at,duration_seconds}: quote must be an exact
unique phrase, phase before/during/after, at start/middle/end, duration .12.. .8s;
it will be placed against finalized subtitle timing. Ambient effects may omit event.
impact_shake needs camera overscan. Never use a decorative effect to fill time.
transition is cut or crossfade, chosen from adjacent-shot flow; a crossfade uses
.12.. .6 seconds, blends into the next shot at final assembly, and does not retime audio.
Every qa_assertions list must check bubble/body/tail integration when used,
camera direction/settle, readable faces, actual voice cue and adjacent-shot flow.'''

DIRECTED_EFFECTS = {'atmospheric_haze','warm_dust_motes','focus_glow','light_sweep',
                    'impact_flash','subtle_vignette','impact_shake','shock_ring'}


def is_directed(direction):
    return isinstance(direction, dict) and direction.get('contract') == CONTRACT


def validate_keys(keys, reversal_reason=''):
    if not isinstance(keys, list) or not 2 <= len(keys) <= 8:
        raise ValueError('Directed camera needs 2..8 keys')
    previous = -1
    for key in keys:
        if not isinstance(key, dict):
            raise ValueError('Directed camera key must be an object')
        for field, bounds in {'t': (0, 1), 'x': (.44, .56), 'y': (.44, .56),
                              'scale': (1, 1.08), 'rotation': (-1, 1), 'opacity': (100, 100)}.items():
            value = key.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not bounds[0] <= value <= bounds[1]:
                raise ValueError('Invalid directed camera ' + field)
        if key['t'] <= previous:
            raise ValueError('Directed camera times must increase')
        previous = key['t']
    if keys[0]['t'] != 0 or keys[-1]['t'] != 1:
        raise ValueError('Directed camera must cover 0..1')
    for field in ('x', 'y', 'scale', 'rotation'):
        signs = {1 if b[field] > a[field] else -1 for a, b in zip(keys, keys[1:]) if abs(b[field] - a[field]) > 1e-7}
        if len(signs) > 1 and not str(reversal_reason).strip():
            raise ValueError('Unmotivated camera reversal: ' + field)
    # Conservative 16:9 / 9:16 cover bound; no path may expose a canvas edge.
    for key in keys:
        angle=math.radians(key['rotation'])
        cover=abs(math.cos(angle))+abs(math.sin(angle))*16/9
        if key['scale']+1e-7 < cover+2*max(abs(key['x']-.5),abs(key['y']-.5)):
            raise ValueError('Directed camera exposes an image edge; prepare sufficient overscan')
    return copy.deepcopy(keys)


def validate_topic(value):
    if (not isinstance(value, dict) or value.get('visual_language') not in {'cinematic', 'illustrated_drama', 'comic_action'}
            or any(not isinstance(value.get(k), str) or not value[k].strip() for k in ('genre', 'reason'))
            or not isinstance(value.get('continuity_rules'), list) or not value['continuity_rules']
            or any(not isinstance(v, str) or not v.strip() for v in value['continuity_rules'])):
        raise ValueError('A topic-specific visual language and continuity rules are required')
    return copy.deepcopy(value)


def validate_execution(value, topic, scene):
    if not isinstance(value, dict):
        raise ValueError('Every new scene needs explicit execution_design')
    camera, cue, graphics = (value.get(k) for k in ('camera', 'cue', 'graphics'))
    if not isinstance(camera, dict) or camera.get('kind') not in {'hold', 'push', 'pull', 'pan'} or not str(camera.get('reason') or '').strip():
        raise ValueError('Camera needs a shot purpose')
    keys = validate_keys(camera.get('keys'), camera.get('reversal_reason', ''))
    if len(keys)>6: raise ValueError('Preproduction camera allows six keys plus final voice-bound holds')
    if camera['kind'] == 'hold' and any(any(k[f] != keys[0][f] for f in ('x', 'y', 'scale', 'rotation')) for k in keys):
        raise ValueError('Hold cannot contain camera movement')
    if camera['kind'] == 'push' and keys[-1]['scale'] <= keys[0]['scale']:
        raise ValueError('Push must approach the focus')
    if camera['kind'] == 'pull' and keys[-1]['scale'] >= keys[0]['scale']:
        raise ValueError('Pull must move away from the focus')
    if not isinstance(cue, dict) or cue.get('phase') not in {'before', 'during', 'after'}:
        raise ValueError('An exact narration cue and phase are required')
    narration = str(scene.get('scene_text') or scene.get('narration') or '')
    quote = str(cue.get('quote') or '')
    if camera['kind'] != 'hold' and (not quote.strip() or narration.count(quote) != 1):
        raise ValueError('Moving shots need a unique exact narration quote')
    if not isinstance(graphics, dict) or any(type(graphics.get(k)) is not bool for k in ('speech_bubbles', 'speedlines')):
        raise ValueError('Explicit graphic treatment is required')
    if any(graphics[k] for k in ('speech_bubbles','speedlines')) and (not quote.strip() or narration.count(quote)!=1):
        raise ValueError('Graphics need a unique exact recorded-dialogue/action cue')
    if any(graphics[k] for k in ('speech_bubbles', 'speedlines')) and not str(graphics.get('reason') or '').strip():
        raise ValueError('Graphic treatment needs a story reason')
    if graphics['speedlines'] and topic['visual_language'] != 'comic_action':
        raise ValueError('Speedlines are not allowed in this topic visual language')
    effects=value.get('effects',[])
    if not isinstance(effects,list) or len(effects)>2:
        raise ValueError('A scene may select at most two finishing effects')
    cleaned=[];seen=set();duration=float(scene.get('duration_seconds') or scene.get('target_duration') or 0)
    for effect in effects:
        if not isinstance(effect,dict) or effect.get('type') not in DIRECTED_EFFECTS or effect['type'] in seen:
            raise ValueError('Unsupported or repeated directed finishing effect')
        seen.add(effect['type'])
        intensity=effect.get('intensity')
        if isinstance(intensity,bool) or not isinstance(intensity,(int,float)) or not math.isfinite(intensity) or not .05<=intensity<=.35:
            raise ValueError('Directed finishing effects must stay restrained (.05.. .35)')
        center=effect.get('center');color=effect.get('color');radius=effect.get('radius')
        if not isinstance(center,list) or len(center)!=2 or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and 0<=v<=1 for v in center):
            raise ValueError('Effect center must be grounded in normalized source coordinates')
        if not isinstance(color,list) or len(color)!=3 or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and 0<=v<=1 for v in color):
            raise ValueError('Effect color must use normalized RGB')
        if isinstance(radius,bool) or not isinstance(radius,(int,float)) or not math.isfinite(radius) or not .02<=radius<=1:
            raise ValueError('Effect radius must be normalized')
        reason=str(effect.get('reason') or '').strip()
        if not reason:raise ValueError('Each finishing effect needs a source-grounded reason')
        event=effect.get('event')
        if event is not None:
            if not isinstance(event,dict) or event.get('phase') not in {'before','during','after'} or event.get('at') not in {'start','middle','end'}:
                raise ValueError('Effect event needs a precise recorded voice cue')
            event_quote=str(event.get('quote') or '')
            seconds=event.get('duration_seconds')
            if not event_quote.strip() or narration.count(event_quote)!=1:
                raise ValueError('Effect event quote must uniquely match this scene narration')
            if isinstance(seconds,bool) or not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or not .12<=seconds<=min(.8,max(.12,duration)):
                raise ValueError('Effect event duration must be .12.. .8 seconds')
        elif effect['type'] in {'impact_flash','impact_shake','shock_ring'}:
            raise ValueError('Impact effects need a finalized-voice event cue')
        if effect['type']=='impact_shake' and min(k['scale'] for k in keys)<1.03:
            raise ValueError('Impact shake needs at least 3% camera overscan')
        cleaned.append(copy.deepcopy(effect))
    transition=value.get('transition')
    if not isinstance(transition,dict) or transition.get('kind') not in {'cut','crossfade'} or not str(transition.get('reason') or '').strip():
        raise ValueError('Scene transition needs an edit reason')
    transition_seconds=transition.get('duration_seconds',.22 if transition['kind']=='crossfade' else 0)
    if transition['kind']=='cut' and transition_seconds!=0 or transition['kind']=='crossfade' and (
            isinstance(transition_seconds,bool) or not isinstance(transition_seconds,(int,float)) or
            not math.isfinite(transition_seconds) or not .12<=transition_seconds<=.6):
        raise ValueError('Crossfade duration must be .12.. .6 seconds; cuts use zero')
    transition=copy.deepcopy(transition);transition['duration_seconds']=transition_seconds
    return {**copy.deepcopy(value), 'camera': {**copy.deepcopy(camera), 'keys': keys},
            'effects': cleaned, 'transition': copy.deepcopy(transition),
            'source_review': 'pending_actual_image', 'timing_review': 'pending_final_recording'}


def require_execution_match(direction, keys, effects=(), transition=None, *, allow_effect_refinement=False):
    if not is_directed(direction):
        return
    design = direction['execution_design']
    validate_keys(keys, design['camera'].get('reversal_reason', ''))
    if design['camera']['kind'] == 'hold' and any(any(k[f] != keys[0][f] for f in ('x', 'y', 'scale', 'rotation')) for k in keys):
        raise ValueError('Hold cannot acquire implicit motion')
    if not design['graphics']['speedlines'] and any(e.get('type') == 'speedline_burst' for e in effects):
        raise ValueError('Speedlines were not directed')
    if not allow_effect_refinement:
        expected={e['type'] for e in design.get('effects',[])}
        actual={e.get('type') for e in effects}
        if expected!=actual:
            raise ValueError('Rendered finishing effects do not match the topic direction')
        if transition is not None and transition!=design.get('transition',{'kind':'cut'}).get('kind'):
            raise ValueError('Rendered scene transition does not match the topic direction')


def bind_prepared_camera(prepared, scene, execution):
    """Runtime copy only: preserve reviewed layer/art package and use frozen voice-bound camera."""
    if not is_directed(scene.get('creative_reference')):
        return prepared
    if not is_directed(prepared['plan'].get('direction_policy')):
        raise ValueError('New scene direction needs an actual-image reviewed PSD plan')
    require_execution_match(scene['creative_reference'], execution['keys'], execution.get('effects', []))
    result = {**prepared, 'plan': copy.deepcopy(prepared['plan'])}
    result['plan']['camera'] = [{k: row[k] for k in ('t', 'x', 'y', 'scale', 'rotation')} for row in execution['keys']]
    result['plan']['effects'] = copy.deepcopy(execution.get('effects', []))
    transition=execution.get('transition', 'cut')
    result['plan']['transition']={'in':'cut','out':'cut','fraction':0}
    from ae_scene_animation import validate_plan
    result['plan'] = validate_plan(result['plan'])
    return result


def recording_fingerprint(payload, number):
    rows=[r for r in (payload or {}).get('subtitles', []) if int(r.get('scene_number') or 0)==number]
    audio=(payload or {}).get('subtitle_source_audio_id')
    if not audio or not rows: return None
    from ae_scene_animation import canonical_plan_sha256
    normalized=[{'text':str(r.get('text') or ''),
                 'start':float(r.get('start_num',r.get('start_time',r.get('start')))),
                 'end':float(r.get('end_num',r.get('end_time',r.get('end'))))} for r in rows]
    return canonical_plan_sha256({'audio':audio,'rows':normalized})


def execution_capabilities(payload):
    settings=(payload or {}).get('render_settings') or {}
    motion=settings.get('motion') or (payload or {}).get('motion') or {}
    engine=motion.get('production_method') or 'ae'
    return {'engine':engine,'reviewed_speech_bubbles':engine=='ae',
            'reviewed_speedlines':engine=='ae','flat_camera':True,
            'unsupported_required_graphics':'needs_repair_never_silent_omission'}


def bind_recorded_direction(direction, payload, number):
    """Use recorded subtitle intervals; do not invent phoneme/word alignment."""
    fingerprint=recording_fingerprint(payload,number)
    if not is_directed(direction) or not fingerprint: return direction, None
    rows=[r for r in payload['subtitles'] if int(r.get('scene_number') or 0)==number]
    def seconds(row, field):
        return float(row.get(field+'_num',row.get(field+'_time',row.get(field))))
    start=min(seconds(r,'start') for r in rows); end=max(seconds(r,'end') for r in rows)
    if not math.isfinite(start+end) or end<=start: raise ValueError('Final recording interval is invalid')
    result=copy.deepcopy(direction); design=result['execution_design']; camera=design['camera']
    source=camera.get('unbound_keys') or camera['keys']; a,b=0.,1.; first,last=0.,1.
    if camera['kind']!='hold' or any(design['graphics'][k] for k in ('speech_bubbles','speedlines')):
        quote=str(design['cue'].get('quote') or ''); text=''.join(str(r.get('text') or '') for r in rows)
        if not quote.strip() or text.count(quote)!=1: raise ValueError('Exact direction cue changed in finalized recording')
        at=text.index(quote); offset=0; selected=[]
        for row in rows:
            left=offset;offset+=len(str(row.get('text') or ''))
            if left<at+len(quote) and offset>at:selected.append(row)
        first=(seconds(selected[0],'start')-start)/(end-start); last=(seconds(selected[-1],'end')-start)/(end-start)
        phase=design['cue']['phase']
        if phase=='before':b=first
        elif phase=='during':a,b=first,last
        elif phase=='after':a=last
        if (b-a)*(end-start)<3/24: raise ValueError('Recording cue leaves no usable camera movement window')
    keys=[{**k,'t':a+k['t']*(b-a)} for k in source]
    if a>0:keys.insert(0,{**keys[0],'t':0})
    if b<1:keys.append({**keys[-1],'t':1})
    validate_keys(keys,camera.get('reversal_reason',''))
    camera.update(keys=keys,unbound_keys=copy.deepcopy(source))
    binding={'fingerprint':fingerprint,'audio_asset_id':payload['subtitle_source_audio_id'],
             'start':start,'end':end,'cue_start_seconds':first*(end-start),'cue_end_seconds':last*(end-start),
             'method':'recorded_subtitle_interval_not_word_alignment'}
    design['timing_review']=binding
    return result,binding


def bind_recorded_bubbles(spec, payload, number, binding):
    result=copy.deepcopy(spec)
    if not result.get('enabled'):return result
    rows=[r for r in payload['subtitles'] if int(r.get('scene_number') or 0)==number]
    text=''.join(str(r.get('text') or '') for r in rows)
    def seconds(row,field):return float(row.get(field+'_num',row.get(field+'_time',row.get(field))))
    for bubble in result.get('bubbles',[]):
        quote=str(bubble.get('text') or '')
        if not quote.strip() or text.count(quote)!=1:raise ValueError('Speech bubble text must match exact unique recorded dialogue')
        at=text.index(quote);offset=0;selected=[]
        for row in rows:
            left=offset;offset+=len(str(row.get('text') or ''))
            if left<at+len(quote) and offset>at:selected.append(row)
        bubble['start_seconds']=seconds(selected[0],'start')-binding['start']
        bubble['end_seconds']=seconds(selected[-1],'end')-binding['start']
    return result
