"""Load the versioned local operating guidance into new script requests."""
from pathlib import Path

GUIDE_PATH = Path(__file__).resolve().parents[1] / 'docs' / 'SCRIPT_WORKER_PRODUCTION_GUIDE.md'
JAPANESE_GUIDE_PATH = GUIDE_PATH.with_name('JAPANESE_CATEGORY_SCRIPT_GUIDE.md')


def load_production_guidance():
    text = GUIDE_PATH.read_text(encoding='utf-8').strip()
    if not text:
        raise ValueError('대본워커 제작 기준 문서가 비어 있습니다.')
    japanese_guide = JAPANESE_GUIDE_PATH.read_text(encoding='utf-8').strip()
    if not japanese_guide:
        raise ValueError('일본어 카테고리 제작 기준 문서가 비어 있습니다.')
    return f'{text}\n\n{japanese_guide}'
