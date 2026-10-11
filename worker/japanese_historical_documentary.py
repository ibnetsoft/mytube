"""Shared opt-in Japanese documentary contract; existing folktales stay separate."""
import json
from pathlib import Path

PROFILE = json.loads((Path(__file__).resolve().parents[1] / 'auth-web/lib/japaneseHistoricalDocumentaryStyle.json').read_text(encoding='utf-8'))

def applies(payload):
    return (payload.get('assigned_script_style') or payload.get('script_style')) == PROFILE['key']

def prepare_request(request):
    from worker.japanese_domestic_drama import applies as domestic, prepare_request as prepare_domestic
    if domestic(request): return prepare_domestic(request)
    if not applies(request):
        return request
    return {**request, 'language': 'ja', 'setting_country': '일본',
            'duration_minutes': 30, 'duration_seconds': 1800,
            'image_style': PROFILE['image_style'], 'production_mode': 'standard',
            'era_region': request.get('era_region') if request.get('era_region') not in (None, '', '현대 지방 소도시') else '주제 인물의 실제 생존 시대·지역',
            'notes': str(request.get('notes') or '') + '\n\n' + PROFILE['narration_directive']}

def apply_visual_base(prompt):
    prompt = str(prompt or '')
    return prompt if PROFILE['prompt'] in prompt else prompt + '\n' + PROFILE['prompt']


def enforce_package(package, payload):
    from worker.japanese_domestic_drama import applies as domestic, enforce_package as enforce_domestic
    if domestic(payload): return enforce_domestic(package, payload)
    if not applies(payload):
        return package
    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(child, str) and (key in ('image_prompt', 'reference_prompt', 'panel_prompt', 'shared_style', 'thumbnail_image_prompt') or key.endswith('_image_prompt')):
                    value[key] = apply_visual_base(child)
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(package)
    package.update(script_style=PROFILE['key'], image_style=PROFILE['image_style'])
    return package
