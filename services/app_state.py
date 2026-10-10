"""
앱 전역 공유 상태 모듈
main.py에서 초기화하고 routers에서 참조합니다.
'import main' 순환 참조 / __main__ 인스턴스 불일치 문제를 해결합니다.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from app.modes import normalize_app_mode

if TYPE_CHECKING:
    from services.i18n import Translator

# 전역 translator 참조
_translator = None
_templates = None


def register_translator(translator):
    """main.py startup 시 translator 등록"""
    global _translator
    _translator = translator


def register_templates(templates):
    """main.py startup 시 templates 등록"""
    global _templates
    _templates = templates


def get_translator():
    return _translator


def get_templates():
    return _templates


def switch_language(lang: str) -> bool:
    """[Deprecated — AIR-0133] Per-request language is now handled via request.state.current_lang.
    Kept for backward compatibility; no longer mutates translator or env.globals.
    """
    return True

def switch_mode(mode: str) -> bool:
    """앱 모드를 즉시 전환. 성공하면 True 반환."""
    global _templates
    if _templates is None:
        return False
    try:
        mode = normalize_app_mode(mode)
        _templates.env.globals['app_mode'] = mode
        return True
    except Exception as e:
        print(f"[AppState] switch_mode error: {e}")
        return False
