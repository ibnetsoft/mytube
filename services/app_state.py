"""
앱 전역 공유 상태 모듈
main.py에서 초기화하고 routers에서 참조합니다.
'import main' 순환 참조 / __main__ 인스턴스 불일치 문제를 해결합니다.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

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
    """언어를 즉시 전환. 성공하면 True 반환."""
    global _translator, _templates
    if _translator is None:
        return False
    try:
        _translator.set_lang(lang)
        if _templates is not None:
            _templates.env.globals['current_lang'] = lang
        return True
    except Exception as e:
        print(f"[AppState] switch_language error: {e}")
        return False
