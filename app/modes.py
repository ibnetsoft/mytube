from enum import Enum
from typing import Optional


class AppMode(str, Enum):
    LONGFORM = "longform"
    LONGFORM_MUSIC = "longform_music"
    SHORTS = "shorts"
    COMMERCE = "commerce"
    WEBTOON = "webtoon"
    BLOG = "blog"


DEFAULT_APP_MODE = AppMode.LONGFORM.value
VALID_APP_MODES = {mode.value for mode in AppMode}
LANGUAGE_CODES = {"ko", "en", "ja", "vi", "es"}


def normalize_app_mode(value: Optional[str], default: str = DEFAULT_APP_MODE) -> str:
    mode = (value or default or DEFAULT_APP_MODE).strip()
    return mode if mode in VALID_APP_MODES else DEFAULT_APP_MODE


def is_shorts_mode(value: Optional[str]) -> bool:
    return normalize_app_mode(value) == AppMode.SHORTS.value


def is_longform_family(value: Optional[str]) -> bool:
    return normalize_app_mode(value) in {
        AppMode.LONGFORM.value,
        AppMode.LONGFORM_MUSIC.value,
    }


def is_longform_music_mode(value: Optional[str]) -> bool:
    return normalize_app_mode(value) == AppMode.LONGFORM_MUSIC.value


def recover_mode_language_mixup(app_mode: Optional[str], target_language: Optional[str]) -> tuple[str, Optional[str]]:
    """Recover old requests where language and app_mode were accidentally swapped."""
    mode = app_mode or DEFAULT_APP_MODE
    language = target_language

    if mode in LANGUAGE_CODES:
        if language in VALID_APP_MODES:
            return normalize_app_mode(language), mode
        return DEFAULT_APP_MODE, mode

    return normalize_app_mode(mode), language
