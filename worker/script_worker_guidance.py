"""Load the versioned local operating guidance into new script requests."""
from pathlib import Path

GUIDE_PATH = Path(__file__).resolve().parents[1] / 'docs' / 'SCRIPT_WORKER_PRODUCTION_GUIDE.md'
JAPANESE_GUIDE_PATH = GUIDE_PATH.with_name('JAPANESE_CATEGORY_SCRIPT_GUIDE.md')
WUXIA_DELIVERY_PATH = GUIDE_PATH.with_name('WUXIA_SERIES_DELIVERY.md')
WEB_DELIVERY_PATH = GUIDE_PATH.with_name('SCRIPT_WORKER_WEB_DELIVERY.md')


def load_production_guidance():
    text = GUIDE_PATH.read_text(encoding='utf-8').strip()
    if not text:
        raise ValueError('대본워커 제작 기준 문서가 비어 있습니다.')
    web_delivery = WEB_DELIVERY_PATH.read_text(encoding='utf-8').strip()
    if not web_delivery:
        raise ValueError('유저웹 등록 작업 지침이 비어 있습니다.')
    japanese_guide = JAPANESE_GUIDE_PATH.read_text(encoding='utf-8').strip()
    if not japanese_guide:
        raise ValueError('일본어 카테고리 제작 기준 문서가 비어 있습니다.')
    delivery = WUXIA_DELIVERY_PATH.read_text(encoding='utf-8').strip()
    if not delivery:
        raise ValueError('무협 연작 납품 지침이 비어 있습니다.')
    wuxia = GUIDE_PATH.with_name('wuxia-webtoon-production-defaults.md').read_text(encoding='utf-8').strip()
    if not wuxia:
        raise ValueError('무협 웹툰 제작 기본 지침이 비어 있습니다.')
    props = (GUIDE_PATH.parent / 'wuxia-props' / 'PROP_BIBLE.md').read_text(encoding='utf-8').strip()
    if not props:
        raise ValueError('무협 고정 소품 기준 문서가 비어 있습니다.')
    plan = GUIDE_PATH.with_name('WUXIA_SERIES_PLAN_03_50.md').read_text(encoding='utf-8').strip()
    if not plan:
        raise ValueError('무협 전체 회차 계획 문서가 비어 있습니다.')
    motion = GUIDE_PATH.with_name('WUXIA_TRANSITIONS.md').read_text(encoding='utf-8').strip()
    if not motion:
        raise ValueError('무협 자동 모션·실제 AE 검수 지침이 비어 있습니다.')
    from worker.wuxia_generation_gate import instruction
    execution_rules = instruction()
    return f'{text}\n\n{web_delivery}\n\n{japanese_guide}\n\n{delivery}\n\n{wuxia}\n\n{props}\n\n{plan}' + '\n\n' + motion + '\n\n' + execution_rules
