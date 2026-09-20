"""Language and unified setting choices shared by the local topic and script workflows."""
from __future__ import annotations
from typing import Any


LANGUAGE_NAMES = {'ko': 'Korean', 'en': 'English', 'ja': 'Japanese', 'es': 'Spanish'}
LANGUAGE_KOREAN_NAMES = {'ko': '한국어', 'en': '영어', 'ja': '일본어', 'es': '스페인어'}

DEFAULT_COUNTRY_BY_LANGUAGE = {
    'ko': '한국',
    'en': '미국',
    'ja': '일본',
    'es': '스페인',
}

COUNTRY_NAMES_EN = {
    '한국': 'South Korea',
    '미국': 'United States',
    '일본': 'Japan',
    '스페인': 'Spain',
    '영국': 'United Kingdom',
    '멕시코': 'Mexico',
    '캐나다': 'Canada',
    '호주': 'Australia',
    '프랑스': 'France',
    '독일': 'Germany',
    '이탈리아': 'Italy',
    '중국': 'China',
    '대만': 'Taiwan',
}

DEFAULT_ERA_REGION = '현대 지방 소도시'
DEFAULT_IMAGE_STYLE = '실사'

IMAGE_STYLE_MAP_EN = {
    '실사': 'realistic',
    'realistic': 'realistic',
    '시네마틱': 'cinematic',
    'cinematic': 'cinematic',
    '애니메이션': 'anime illustration',
    '일러스트': 'editorial illustration',
    '웹툰': 'korean webtoon style',
}


def output_language(payload: dict[str, Any] | None) -> str:
    payload = payload or {}
    lang = str(payload.get('language') or {'12': 'en', '13': 'ja'}.get(str(payload.get('category_id')), 'ko')).lower()
    return lang if lang in LANGUAGE_NAMES else 'ko'


def resolve_setting(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    lang = output_language(payload)
    lang_name_ko = LANGUAGE_KOREAN_NAMES.get(lang, lang)
    lang_name_en = LANGUAGE_NAMES.get(lang, lang)

    user_country = str(payload.get('setting_country') or payload.get('country') or '').strip()
    if user_country:
        country = user_country
        country_source = 'user_override'
    else:
        country = DEFAULT_COUNTRY_BY_LANGUAGE.get(lang, '한국')
        country_source = 'language_default'

    country_en = COUNTRY_NAMES_EN.get(country, country)
    era_region = str(payload.get('era_region') or payload.get('era') or DEFAULT_ERA_REGION).strip() or DEFAULT_ERA_REGION
    image_style = str(payload.get('image_style') or DEFAULT_IMAGE_STYLE).strip() or DEFAULT_IMAGE_STYLE
    image_style_en = IMAGE_STYLE_MAP_EN.get(image_style.lower(), image_style)

    summary_label = f"{lang_name_ko} · {country} {era_region} · {image_style}"

    return {
        'language': lang,
        'language_name_ko': lang_name_ko,
        'language_name_en': lang_name_en,
        'setting_country': country,
        'setting_country_en': country_en,
        'country_source': country_source,
        'era_region': era_region,
        'image_style': image_style,
        'image_style_en': image_style_en,
        'summary_label': summary_label,
    }


def language_directive(language: str) -> str:
    name = LANGUAGE_NAMES.get(language, language)
    return (
        f'OUTPUT LANGUAGE: {name} ({language}). Write the title, narration and character dialogue in idiomatic {name}. '
        'This explicit language takes precedence over language examples in category/style presets, the source language, '
        'and the language of the input title or user notes. Translate the input title naturally when needed. '
        'Keep JSON field names and source IDs unchanged; preserve verbatim evidence quotes in their original language. '
        'Use natural spoken grammar, punctuation and forms of address. Review and repair must preserve this language; '
        'reject a draft in another language, including English when Spanish was requested.'
    )


def setting_directive(setting: dict[str, Any], mode: str = 'story') -> str:
    country_ko = setting.get('setting_country', '한국')
    country_en = setting.get('setting_country_en', 'South Korea')
    era_region = setting.get('era_region', DEFAULT_ERA_REGION)
    lang_name_en = setting.get('language_name_en', 'Korean')
    lang_code = setting.get('language', 'ko')

    if mode == 'grounded':
        return (
            f"[Grounded Source Setting Policy]\n"
            f"- Output spoken/written language is {lang_name_en} ({lang_code}).\n"
            "- CRITICAL FIDELITY RULE: Preserve the original real-world historical/geographical setting, real people, "
            "and factual events exactly as provided in the sources. Do not change the source setting country, era, "
            f"or real identities to {country_ko} or {country_en}. Only adapt the narrative explanation language to {lang_name_en}."
        )

    return (
        f"[Unified Story Setting & Cultural Continuity Contract]\n"
        f"- Target Setting Country: {country_en} ({country_ko})\n"
        f"- Era and Specific Region: {era_region}\n"
        f"- Spoken and Written Language: {lang_name_en} ({lang_code})\n"
        f"- Story World Building: Character names, familial terms, everyday routines, architecture, streetscapes, "
        f"interior layouts, vehicles, living environment, and props must naturally reflect {country_en} ({era_region}).\n"
        f"- Anti-Stereotype Rule: Do NOT homogenize or caricature characters based solely on nationality or ethnicity; "
        "maintain distinct individual personalities, realistic occupations, and modern everyday depth. "
        "Avoid forced cultural clichés (for example, in a modern Japanese setting, do not force traditional kimonos "
        "or shrines into ordinary contemporary scenes unless explicitly part of the story premise).\n"
        "- Downstream Visual Continuity: Scene images, character reference portraits, and thumbnail will strictly share "
        f"this exact {country_en} ({era_region}) setting."
    )


def visual_setting_prompt(setting: dict[str, Any]) -> str:
    image_style = setting.get('image_style_en') or 'realistic'
    country_en = setting.get('setting_country_en') or 'South Korea'
    era_region = setting.get('era_region') or DEFAULT_ERA_REGION
    return (
        f"{image_style} visual continuity; consistent recurring characters, authentic {country_en} setting ({era_region}) "
        "with period- and location-accurate architecture, interior spaces, streetscape, vehicles, wardrobe, lighting, and props; "
        "realistic everyday texture without uniform caricature or exaggerated cultural clichés"
    )


def narration_scale(language: str) -> float:
    # Approximate character-budget ratios, not measured TTS durations.
    # Latin-script narration needs more characters than Korean at a similar pace.
    return {'en': 2.5, 'es': 2.6, 'ja': 1.2}.get(language, 1.0)
