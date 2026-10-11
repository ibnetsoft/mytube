"""Opt-in Japanese fictional domestic drama; never factual crime reconstruction."""
import json
from pathlib import Path
PROFILE=json.loads((Path(__file__).resolve().parents[1]/'auth-web/lib/japaneseDomesticDramaStyle.json').read_text(encoding='utf-8'))

def applies(payload):
    return (payload.get('assigned_script_style') or payload.get('script_style'))==PROFILE['key']

def prepare_request(request):
    if not applies(request):return request
    seconds=request.get('source_duration_seconds') or request.get('duration_seconds') or request.get('target_duration_seconds') or request.get('duration_minutes',15)*60
    if request.get('youtube_url') and not request.get('source_duration_verified'):
        raise ValueError('원본 YouTube 영상 길이 확인이 필요합니다.')
    if not isinstance(seconds,(int,float)) or isinstance(seconds,bool) or seconds!=int(seconds) or not 60<=seconds<=3600:
        raise ValueError('일본사건 영상 길이는 1~60분 범위에서 정확한 초 단위로 설정하세요.')
    return {**request,'language':'ja','setting_country':'일본','category':PROFILE['category'],
        'duration_minutes':(int(seconds)+59)//60,'duration_seconds':int(seconds),'target_duration_seconds':int(seconds),
        'image_style':PROFILE['image_style'],'production_mode':'standard','required_video_scene_count':18,'generate_bgm_prompt':True,
        'era_region':'현대 일본 · 원본 사건에 대응하는 현지 지역',
        'notes':str(request.get('notes') or '')+'\n\n'+PROFILE['narration_directive']+'\nRequired opening: '+PROFILE['fiction_disclaimer']}

def schedule(seconds):
    from services.scene_pacing import pacing_schedule
    return pacing_schedule(seconds)

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
    if not scenes:raise ValueError('일본사건 장면 계획이 없습니다.')
    clip_count=min(18,len(scenes))
    for i,scene in enumerate(scenes,1):
        if i<=clip_count:
            if not payload.get('script_only') and structure.get('media_prompt_status')=='ready' and not scene.get('video_prompt'):
                raise ValueError(f'일본사건 {i}씬 영상 연출 프롬프트가 필요합니다.')
            scene.update(video_prompt_required=True,visual_type='video',video_generation_mode='user_upload')
        else:
            scene.update(video_prompt_required=False,visual_type='image',video_generation_mode='image')
            scene.pop('video_prompt',None)
    structure.update(script_style=PROFILE['key'],required_video_scene_count=clip_count,video_scenes=clip_count,
        source_reference=payload.get('source_reference') or structure.get('source_reference') or {},source_localization_map=payload.get('source_localization_map') or structure.get('source_localization_map') or [],
        fiction_disclaimer=disclaimer,visual_format='anime_event_adaptation',
        music_direction='Instrumental: restrained tense piano, warmer strings at the earned reversal, quiet hopeful ending. No vocals.',
        caption_direction='Editable finalized Japanese lower subtitles or optional balloons; no baked text in generated images.')
    package.update(script_style=PROFILE['key'],image_style=PROFILE['image_style'],required_video_scene_count=clip_count,video_scenes=clip_count)
    return package
