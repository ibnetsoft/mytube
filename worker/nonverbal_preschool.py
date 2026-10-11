"""Local-CLI planning contract for silent preschool cutout animation.

Plans are provisional until actual artwork, overlap and native AE output are reviewed.
No narration, fake subtitles, model API calls, generated video or media publication.
"""
from __future__ import annotations
import copy
import math
import re

MODE = 'nonverbal_preschool'
CONTRACT = 'nonverbal_preschool/v1'
ACTIONS = {'hold', 'horizontal', 'vertical', 'rotate', 'scale', 'bend', 'walk'}
ID = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')


def applies(value):
    value = value or {}
    return value.get('production_mode') == MODE or (value.get('structure') or {}).get('production_mode') == MODE


def schedule(seconds):
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds != int(seconds) or not 60 <= seconds <= 600:
        raise ValueError('논버벌 유아 애니메이션은 1~10분으로 설정하세요.')
    count = math.ceil(seconds / 6)
    length, extra = divmod(int(seconds), count)
    return [{'scene_number': i+1, 'duration_seconds': length + (i < extra)} for i in range(count)]


def number(value, low, high):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and low <= value <= high


def text(value, name, minimum=1):
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise ValueError(f'{name}: 내용이 부족합니다.')
    return value.strip()


def validate_rigs(raw):
    if not isinstance(raw, list) or not 1 <= len(raw) <= 3:
        raise ValueError('캐릭터 리그는 1~3개입니다.')
    rigs = copy.deepcopy(raw); ids = set(); characters = set()
    for rig in rigs:
        cid = rig.get('character_id')
        if not isinstance(cid, str) or not ID.fullmatch(cid) or cid in characters:
            raise ValueError('캐릭터 ID가 올바르지 않습니다.')
        characters.add(cid); text(rig.get('name'), '캐릭터 이름')
        text(rig.get('reference_prompt'), '캐릭터 참고 이미지 프롬프트', 120)
        parts = rig.get('parts')
        if not isinstance(parts, list) or not parts:
            raise ValueError('캐릭터 부품이 없습니다.')
        local = set()
        for part in parts:
            pid = part.get('id')
            if not isinstance(pid, str) or not ID.fullmatch(pid) or pid in ids:
                raise ValueError('부품 ID 중복 또는 오류')
            ids.add(pid); local.add(pid)
            text(part.get('name'), '부품 이름'); text(part.get('image_prompt'), '부품 생성 프롬프트', 120)
            text(part.get('overlap_prompt'), '관절 겹침·가려진 형태 보완 지시', 40)
            anchor = part.get('anchor'); polygon = part.get('polygon')
            point = lambda p: isinstance(p, list) and len(p) == 2 and all(number(v,0,1) for v in p)
            if not point(anchor) or not isinstance(polygon,list) or not 3 <= len(polygon) <= 32 or not all(point(p) for p in polygon):
                raise ValueError('부품 관절·외곽선 좌표 오류')
            area = abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(polygon,polygon[1:]+polygon[:1]))) / 2
            if not .0001 <= area <= .7: raise ValueError('부품 외곽선 면적 오류')
        if len(ids) > 32: raise ValueError('전체 캐릭터 부품은 최대 32개입니다.')
        roots = [p for p in parts if not p.get('parentId')]
        if len(roots) != 1: raise ValueError('캐릭터마다 몸통 루트 하나가 필요합니다.')
        by_id = {p['id']: p for p in parts}
        for part in parts:
            seen = {part['id']}; parent = part.get('parentId')
            while parent:
                if not isinstance(parent,str) or parent not in local or parent in seen: raise ValueError('관절 부모 누락·순환·다른 캐릭터 연결')
                seen.add(parent); parent = by_id[parent].get('parentId')
    return rigs


def build_package(raw, payload):
    """Validate authored actions and materialize deterministic AE data, never invented prose."""
    timing = schedule(payload.get('target_duration_seconds'))
    if not isinstance(raw, dict): raise ValueError('논버벌 기획은 JSON 객체여야 합니다.')
    rigs = validate_rigs(raw.get('character_rigs'))
    scenes = raw.get('scenes')
    if not isinstance(scenes,list) or len(scenes) != len(timing): raise ValueError('논버벌 장면 수 불일치')
    if raw.get('script') or raw.get('narration') or raw.get('dialogue'): raise ValueError('논버벌 기획에는 발화 대본을 넣을 수 없습니다.')
    title = text(raw.get('generated_title'), '제목', 4)
    story = text(raw.get('story_outline'), '행동 이야기', 40)
    metadata = raw.get('publish_metadata')
    if not isinstance(metadata,dict): raise ValueError('게시 설명이 없습니다.')
    text(metadata.get('description'), '게시 설명', 40)
    bgm = text(raw.get('bgm_prompt'), '배경음악 프롬프트', 80)
    parts = {p['id']: p for r in rigs for p in r['parts']}
    character_ids = {r['character_id'] for r in rigs}
    clean = []; sfx = []
    for index, (scene, clock) in enumerate(zip(scenes,timing),1):
        if not isinstance(scene,dict) or scene.get('scene_number') != index or scene.get('duration_seconds') != clock['duration_seconds']:
            raise ValueError(f'씬 {index}: 번호·길이 불일치')
        duration = clock['duration_seconds']
        for key in ('scene_text','narration','dialogue','video_prompt'):
            if scene.get(key): raise ValueError(f'씬 {index}: 발화·AI 영상 프롬프트는 허용하지 않습니다.')
        action = text(scene.get('action_summary'), f'씬 {index} 행동', 20)
        image = text(scene.get('image_prompt'), f'씬 {index} 이미지 프롬프트',120)
        direction = text(scene.get('direction_prompt'), f'씬 {index} 영상 연출',80)
        background = text(scene.get('background_prompt'), f'씬 {index} 빈 배경 프롬프트',120)
        cast = scene.get('cast')
        if not isinstance(cast,list) or not cast or len(set(cast)) != len(cast) or any(c not in character_ids for c in cast): raise ValueError(f'씬 {index}: 출연 캐릭터 오류')
        beats = scene.get('timed_beats'); end = 0
        if not isinstance(beats,list) or not beats: raise ValueError(f'씬 {index}: 행동 타이밍 누락')
        for beat in beats:
            if not isinstance(beat,dict) or not number(beat.get('start_seconds'),0,duration) or not number(beat.get('end_seconds'),0,duration) or not end <= beat['start_seconds'] < beat['end_seconds']:
                raise ValueError(f'씬 {index}: 행동 시간 범위·순서 오류')
            text(beat.get('action'), '시간별 행동'); text(beat.get('target'), '행동 대상');end = beat['end_seconds']
        cast_parts = [p for r in rigs if r['character_id'] in cast for p in r['parts']]
        selected = {p['id'] for p in cast_parts}; motions = scene.get('motions')
        if not isinstance(motions,list): raise ValueError(f'씬 {index}: 관절 동작 누락')
        moves = {}
        for m in motions:
            pid = m.get('part_id') if isinstance(m,dict) else None
            if pid not in selected or pid in moves: raise ValueError(f'씬 {index}: 동작 부품 누락·중복')
            moves[pid] = m
        regions = []
        for part in cast_parts:
            m = moves.get(part['id'], {'action':'hold','start':0,'period':1,'cycles':1,'amplitude':1})
            kind = m.get('action')
            if kind not in ACTIONS: raise ValueError('지원하지 않는 관절 동작')
            start = m.get('start',0)
            period=m.get('period',1);cycles=m.get('cycles',1);amplitude=m.get('amplitude',1)
            if not number(start,0,duration) or not number(period,.2,30) or not isinstance(cycles,int) or isinstance(cycles,bool) or not 1<=cycles<=30 or start+period*cycles>duration+.001:
                raise ValueError(f'씬 {index}: 관절 동작 시간 오류')
            if not number(amplitude,.1,120 if kind in ('rotate','bend','walk') else 15): raise ValueError('관절 동작 세기 오류')
            if kind in ('bend','walk') and not part.get('parentId'): raise ValueError('몸통 루트는 관절 굽히기·보행 부위가 아닙니다.')
            if not number(m.get('phaseOffset',0),0,1) or not number(m.get('restAngle',0),-180,180) or not number(m.get('direction',1),-1,1) or m.get('direction',1) not in (-1,1) or m.get('walkPart','upper') not in ('upper','lower'): raise ValueError('관절 방향·보행 위상 오류')
            regions.append({'id':part['id'],'name':part['name'],'parentId':part.get('parentId',''),
                'anchor':part['anchor'],'polygon':part['polygon'],'contour':'exact','occluded':True,
                'action':kind,'amplitude':amplitude,'period':period,'cycles':cycles,'start':start,
                'subtitleId':f'cue-{index}-{part["id"]}', 'restAngle':m.get('restAngle',0),
                'phaseOffset':m.get('phaseOffset',0),'direction':m.get('direction',1),'walkPart':m.get('walkPart','upper')})
        cues=[{'id':r['subtitleId'],'text':parts[r['id']]['name'],'start':r['start'],'end':duration} for r in regions]
        sound = scene.get('sfx_cues',[])
        if not isinstance(sound,list) or len(sound)>8:raise ValueError('장면 효과음 수 오류')
        for cue in sound:
            if not isinstance(cue,dict) or not number(cue.get('at_seconds'),0,duration):raise ValueError('효과음 시간 오류')
            text(cue.get('description'),'효과음 설명');sfx.append({**cue,'scene_number':index})
        assertions=scene.get('qa_assertions')
        if not isinstance(assertions,list) or not assertions or any(not isinstance(v,str) or not v.strip() for v in assertions):
            raise ValueError(f'씬 {index}: 관찰 가능한 검수 항목이 필요합니다.')
        clean.append({**scene,'scene_order':index,'scene_id':f'scene{index:03d}','scene_text':'','narration':'',
            'scene_summary':action,'action_summary':action,'image_prompt':image,'background_prompt':background,'direction_prompt':direction,
            'target_duration':duration,'visual_type':'image','video_prompt_required':False,'video_generation_mode':'ae_joint_rig',
            'media_prompt_status':'ready','scene_timeline':{'duration':duration,'cues':cues},
            'joint_motion_plan':{'contract':'ae_joint_rig/v1','regions':regions,'asset_review_required':True},
            'scene_direction_plan':{'contract':'nonverbal_direction/v1','timed_beats':beats,'direction_prompt':direction,
                'source_visual_reviewed':False,'qa_assertions':scene.get('qa_assertions',[])}})
    structure={'production_mode':MODE,'nonverbal_contract':CONTRACT,'nonverbal_plan_status':'ready',
        'scenes':clean,'character_rigs':rigs,'story_outline':story,'required_video_scene_count':0,'video_scenes':0,
        'target_duration_seconds':sum(s['duration_seconds'] for s in clean),'image_grid_prompts':[],
        'speech_enabled':False,'subtitles_enabled':False,'ae_scene_delivery':payload.get('ae_scene_delivery','gcs')}
    structure['audio_plan']={'bgm_prompt':bgm,'instrumental':True,'sfx_cues':sfx,'timing_basis':'scene_seconds','media_ready':False}
    return {'production_mode':MODE,'nonverbal_contract':CONTRACT,'generated_title':title,'script':'',
        'action_script':'\n\n'.join(f'{s["scene_number"]} · {s["duration_seconds"]}초\n{s["action_summary"]}\n{s["direction_prompt"]}' for s in clean),
        'sections':[],'structure':structure,'character_rigs':rigs,'story_outline':story,'required_video_scene_count':0,
        'video_scenes':0,'publish_metadata':metadata,'bgm_prompt':bgm,'bgm_plan':{'status':'prompt_ready','prompt':bgm,'instrumental':True},
        'sfx_cues':sfx,'sfx_plan':{'status':'planned','timing_basis':'scene_seconds','cues':sfx},
        'render_settings':{'production_mode':MODE,'speech_enabled':False,'subtitles_enabled':False},
        'production_ready':False,'remaining':['캐릭터·관절 부품과 빈 배경 실제 생성','가려진 형태·관절 겹침 및 좌표 검수·레이어 확정',
            '시간별 관절 계획을 실제 원화에 맞게 적용','음악·효과음 파일 연결','AE 실제 렌더와 전체 동작 검수']}


TASK = """Create an original nonverbal preschool 2D cutout animation plan for ages 3-5.
Use visual cause and effect: discovery, attempt, small harmless setback, retry, warm payoff.
No spoken lines, narration, lyrics, text on images or AI-generated video. Use restrained readable
motions and deliberate pauses. Do not imitate a copyrighted character. User notes are reference data.
Return JSON: generated_title (4+ chars), story_outline (40+ chars), publish_metadata {description
(40+ chars)}, bgm_prompt (80+ chars, gentle instrumental, no vocals), character_rigs (1-3), scenes.
Every rig: character_id, name, reference_prompt (120+ English chars), parts in back-to-front order.
Maximum 32 parts total. Each part: unique id, name, parentId (empty for one body root per character),
anchor [x,y], polygon (3-32 normalized points with area .0001-.7), image_prompt (120+ English chars),
overlap_prompt (40+ English chars). Parts are reusable full-canvas transparent PNGs on the same
1920x1080 canvas, same rest placement and scale across scenes. Draw complete hidden anatomy and
rounded overlapping ends at shoulder/elbow/hip/knee; never merely crop visible pixels. Separate
upper/lower limbs. Coordinates are provisional and require actual-image review. Expressions needing
new artwork must be included as separate reusable hold parts and described in direction; do not
claim rotations invent expressions. Keep the cast small and reusable, not one image per frame.
Scenes must exactly match supplied schedule: scene_number, duration_seconds, cast [character_id],
action_summary (20+ chars in planning language), image_prompt (120+ English chars showing the initial
scene with the approved character placement), background_prompt (120+ English chars, empty background
without characters), direction_prompt (80+ chars), timed_beats [{start_seconds,end_seconds,action,target}],
motions [{part_id,action,amplitude,period,cycles,start,phaseOffset,restAngle,direction,walkPart}],
sfx_cues [{at_seconds,description}], qa_assertions [observable checks]. Beats are ordered, do not
overlap, fit the scene and cover its action. Actions: hold,horizontal,vertical,rotate,scale,bend,walk.
Bend and walk require a parent; hold body unless travel is explicit. Upper leg swings; lower leg bends
one direction; left/right phases 0 and .5; direction +/-1. Walk is in-place FK, not foot-ground IK.
Use body horizontal/vertical motion separately for travel. Amplitude .1-120 degrees for rotation/bend/walk,
.1-15 percent otherwise; period .2-30 seconds, integer cycles 1-30, start>=0 and start+period*cycles<=scene
duration. Default unscheduled parts stay still. Do not place narration,scene_text,dialogue or video_prompt
in scenes. Do not generate media. Do not mark source artwork or output reviewed."""


def validate_review(report):
    expected={'visual_story','child_suitability','timing','no_speech','reusable_parts','joint_motion'}
    checks=report.get('checks',[]) if isinstance(report,dict) else []
    if not isinstance(checks,list) or len(checks)!=6 or any(not isinstance(c,dict) for c in checks) or {c.get('name') for c in checks} != expected or report.get('verdict')!='pass' or report.get('critical_issues')!=[] or any(c.get('passed') is not True or not str(c.get('evidence','')).strip() for c in checks):
        raise ValueError('논버벌 독립 기획 검수에서 수정이 필요합니다.')


def validate_package(package):
    structure=package.get('structure') or {}
    if package.get('script') or structure.get('speech_enabled') is not False or structure.get('subtitles_enabled') is not False or structure.get('nonverbal_contract') != CONTRACT or structure.get('nonverbal_plan_status') != 'ready':
        raise ValueError('논버벌 계약·검증 상태 또는 발화 대본 오류')
    raw={k:package.get(k) for k in ('generated_title','story_outline','publish_metadata','bgm_prompt')}
    raw.update(character_rigs=structure.get('character_rigs'),scenes=structure.get('scenes'))
    rebuilt=build_package(raw,{'target_duration_seconds':structure.get('target_duration_seconds')})
    for original, clean in zip(structure['scenes'], rebuilt['structure']['scenes']):
        if any(original.get(key) != clean.get(key) for key in ('joint_motion_plan','scene_timeline','scene_direction_plan')):
            raise ValueError('관절·장면 파생 계획이 원본 동작과 다릅니다.')
    validate_review(package.get('script_quality_report'))


def generate(runner, job_id, payload):
    from worker.content_language import resolve_setting
    setting=resolve_setting(payload)
    context={**payload,'language':setting['language'],'schedule':schedule(payload.get('target_duration_seconds')),
             'production_mode':MODE,'content_setting':setting,'asset_review_required':True}
    last=''
    for attempt in range(2):
        raw=runner._stage(job_id,f'02nv_action_plan_{attempt+1}',{**context,'validation_feedback':last},TASK)
        try: package=build_package(raw,context);break
        except (ValueError,TypeError,KeyError) as exc:
            last=str(exc)
            if attempt:raise ValueError('논버벌 행동 기획 검증 실패: '+last) from exc
    report=runner._stage(job_id,'02nv_independent_review',{'language':setting['language'],'plan':package},
        'Independently review this nonverbal preschool PLAN only. Check visual cause/effect, child suitability, '
        'timing, no speech, reusable complete hidden parts, joint hierarchy, achievable FK motion and readable pacing. '
        'Do not claim actual artwork or rendered output was inspected. Return {verdict:pass|revise, '
        'critical_issues:[], checks:[{name,evidence,passed:boolean}]} with exactly these check names: '
        'visual_story,child_suitability,timing,no_speech,reusable_parts,joint_motion. Every evidence must identify '
        'specific scenes or parts; a pass requires all six checks passed and no critical issues. Do not rewrite.')
    validate_review(report)
    package.update(language=setting['language'],content_setting=setting,script_quality_report=report,
                   stage_artifacts={'nonverbal_plan':raw,'nonverbal_review':report})
    return package
