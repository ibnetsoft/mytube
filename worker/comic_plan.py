"""Validated, opt-in moving-comic direction for the dedicated script worker."""
from services.comic_layouts import LAYOUTS
DIRECTIVE = ('MOVING COMIC: write a visually staged story with natural direct character dialogue and concise narration. '
    'Keep spoken dialogue distinct from narration, indirect speech and thoughts. Preserve the requested story, language and scene budgets. '
    'Do not force dialogue into scenery-only shots. Plan character continuity and space for lettering. '
    'Use the selected image style, not an unconditional photorealistic style.')

def validate_plan(value, scenes):
    if not isinstance(value, dict):
        raise ValueError('무빙툰 연출 결과는 객체여야 합니다.')
    rows = value.get('scenes', [])
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError('무빙툰 씬 목록이 올바르지 않습니다.')
    if [r.get('scene_number') for r in rows] != list(range(1, len(scenes)+1)):
        raise ValueError('무빙툰 연출은 모든 씬을 순서대로 포함해야 합니다.')
    for row in rows:
        if row.get('motion') not in ('still', 'pan', 'video'):
            raise ValueError('잘못된 무빙툰 움직임입니다.')
        if not isinstance(row.get('image_prompt'),str) or len(row['image_prompt'].strip())<20:
            raise ValueError('씬 이미지 연출이 없습니다.')
        if row['motion']=='video' and not str(row.get('video_prompt','')).strip():
            raise ValueError('영상화 씬에 영상 프롬프트가 필요합니다.')
    pages=value.get('pages',[])
    if not isinstance(pages, list) or not all(isinstance(p, dict) and isinstance(p.get('scene_numbers'), list) for p in pages):
        raise ValueError('무빙툰 페이지 목록이 올바르지 않습니다.')
    if not pages or [n for p in pages for n in p.get('scene_numbers',[])] != list(range(1,len(scenes)+1)):
        raise ValueError('페이지에 씬이 중복되거나 누락됐습니다.')
    for p in pages:
        layout=p.get('layout')
        if layout not in LAYOUTS or not 1<=len(p['scene_numbers'])<=len(LAYOUTS[layout]):
            raise ValueError('페이지 레이아웃과 컷 수가 맞지 않습니다.')
        # Only the final page may be incomplete; grouping remains reproducible.
        if p is not pages[-1] and len(p['scene_numbers'])!=len(LAYOUTS[layout]):
            raise ValueError('중간 페이지의 컷을 모두 채워 주세요.')
        if layout=='breakout':
            raise ValueError('경계 돌파는 투명 전경이 준비된 뒤 편집기에서 지정해 주세요.')
    return {'version':1,'mode':'moving_comic','scenes':rows,'pages':pages,
        'render_settings':{'version':1,'mode':'moving_comic','layout':pages[0]['layout'],
            'page_layouts':{str(i):p['layout'] for i,p in enumerate(pages)},
            'turn_duration':1.2,'turn_sound':True,'font_size':25,'panels':{
                str(r['scene_number']):{'motion':r['motion'],'fit':'contain'} for r in rows}},
        'placement_status':'이미지 생성 후 얼굴·입 위치와 말풍선 위치 확정 필요'}

def plan_comic(runner, identity, package, notify):
    scenes=package['structure']['scenes']
    context={'scenes':scenes,'dialogue_annotations':package.get('dialogue_annotations') or package['structure'].get('dialogue_annotations'),
        'layouts':{k:len(v) for k,v in LAYOUTS.items() if k!='breakout'},'content_setting':package.get('content_setting')}
    task=('Do not rewrite the final script. Return {scenes:[{scene_number:1,motion:"still|pan|video",'
        'image_prompt:"English visual direction with consistent cast and lettering whitespace",'
        'video_prompt:"English image-to-video action, silent, no text",reason:"why this motion"}],'
        'pages:[{layout:"available layout key",scene_numbers:[1,2],reason:"dramatic purpose"}]}. '
        'Include all scenes exactly once in order. Choose motion by story importance, not first-12 rules. '
        'Use at least two appropriate page layouts when story length permits. No lip-sync claims. '
        'Video prompts must describe restrained character/environment action with stable identity. '
        'No invented spoken text. Fill each page to its layout capacity except the last.')
    notify('무빙툰 페이지·움직임 연출')
    for attempt in range(2):
        result=runner._stage('local-'+identity,'03_comic_plan',context,task)
        try:plan=validate_plan(result,scenes);break
        except (ValueError,TypeError,KeyError) as exc:
            if attempt:raise
            context['validation_feedback']=str(exc)
    package['production_mode']='moving_comic'
    package['comic_plan']=plan;package['structure']['comic_plan']=plan
    package['render_settings']={**package.get('render_settings',{}),'comic':plan['render_settings']}
    for scene,row in zip(scenes,plan['scenes']):
        scene.update(image_prompt=row['image_prompt'],video_prompt_required=row['motion']=='video',comic_motion=row['motion'])
        if row['motion']=='video':scene['video_prompt']=row['video_prompt']
        else:scene.pop('video_prompt',None)
    package.setdefault('remaining',[]).extend(['무빙툰 연출에 따른 이미지·선택 씬 영상 생성',plan['placement_status']])
    return package
