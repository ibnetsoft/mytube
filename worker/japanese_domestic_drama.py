"""Opt-in Japanese fictional domestic drama; never factual crime reconstruction."""
import json
from pathlib import Path
PROFILE=json.loads((Path(__file__).resolve().parents[1]/'auth-web/lib/japaneseDomesticDramaStyle.json').read_text(encoding='utf-8'))

def applies(payload):
    return (payload.get('assigned_script_style') or payload.get('script_style'))==PROFILE['key']

def prepare_request(request):
    if not applies(request):return request
    minutes=request.get('duration_minutes',15)
    minutes=minutes if isinstance(minutes,int) and not isinstance(minutes,bool) and 13<=minutes<=15 else 15
    return {**request,'language':'ja','setting_country':'일본','category':PROFILE['category'],
        'duration_minutes':minutes,'duration_seconds':minutes*60,'target_duration_seconds':minutes*60,
        'image_style':PROFILE['image_style'],'production_mode':'standard','required_video_scene_count':0,'generate_bgm_prompt':True,
        'era_region':'현대 일본 · 도쿄 근교 주거지역',
        'notes':str(request.get('notes') or '')+'\n\n'+PROFILE['narration_directive']+'\nRequired opening: '+PROFILE['fiction_disclaimer']}

def schedule(seconds):
    seconds=int(seconds)
    if not 780<=seconds<=900:raise ValueError('일본사건 드라마는 13~15분입니다.')
    base,extra=divmod(seconds,PROFILE['scene_count'])
    return [{'scene_number':i+1,'scene_order':i+1,'duration_seconds':base+(i<extra)} for i in range(PROFILE['scene_count'])]

def apply_visual_base(prompt):
    prompt=str(prompt or '')
    return prompt if PROFILE['prompt'] in prompt else prompt+'\n'+PROFILE['prompt']

def enforce_package(package,payload):
    if not applies(payload):return package
    disclaimer=PROFILE['fiction_disclaimer']
    if not str(package.get('script') or '').strip().startswith(disclaimer):
        raise ValueError('일본사건 대본 첫머리에 픽션 고지가 필요합니다. 첫 씬 시간 예산 안에서 다시 작성하세요.')
    sections=package.get('sections') or []
    if sections and not str(sections[0].get('text') or '').strip().startswith(disclaimer):
        raise ValueError('첫 씬의 실제 발화에도 픽션 고지가 필요합니다.')
    def visit(value):
        if isinstance(value,dict):
            for k,v in value.items():
                if isinstance(v,str) and (k in ('image_prompt','reference_prompt','panel_prompt','shared_style','thumbnail_image_prompt') or k.endswith('_image_prompt')):value[k]=apply_visual_base(v)
                else:visit(v)
        elif isinstance(value,list):
            for v in value:visit(v)
    visit(package)
    meta=package.setdefault('publish_metadata',{})
    desc=str(meta.get('description') or '').strip()
    if not desc.startswith(disclaimer):meta['description']=disclaimer+'\n\n'+desc
    structure=package.setdefault('structure',{})
    scenes=structure.get('scenes') or []
    if len(scenes)!=PROFILE['scene_count']:raise ValueError('일본사건 드라마는 36개 정지 장면이 필요합니다.')
    for scene in scenes:
        scene.update(video_prompt_required=False,visual_type='image',video_generation_mode='image')
        scene.pop('video_prompt',None)
    structure.update(script_style=PROFILE['key'],required_video_scene_count=0,video_scenes=0,
        fiction_disclaimer=disclaimer,visual_format='illustrated_domestic_drama',
        music_direction='Instrumental: restrained tense piano, warmer strings at the earned reversal, quiet hopeful ending. No vocals.',
        caption_direction='Editable finalized Japanese lower subtitles or optional balloons; no baked text in generated images.')
    package.update(script_style=PROFILE['key'],image_style=PROFILE['image_style'],required_video_scene_count=0,video_scenes=0)
    return package
