"""Shared release policy. Retained alternative engines never run by default."""
import json
from pathlib import Path

def alternatives_enabled():
    try:
        policy = Path(__file__).resolve().parents[1] / 'auth-web/lib/productionEnginePolicy.json'
        return json.loads(policy.read_text(encoding='utf-8')).get('alternative_engines_enabled') is True
    except (OSError, ValueError):
        return False

def require_engine(engine='ae', final_renderer='python'):
    if (engine in ('effectcraft', 'filmcraft', 'motion_studio') or final_renderer == 'filmcraft') and not alternatives_enabled():
        raise ValueError('대체 제작 엔진은 비활성화되어 있습니다. After Effects와 기본 FFmpeg 조립으로 다시 제출하세요. 기존 결과는 보존됩니다.')
