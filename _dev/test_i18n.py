import sys
sys.path.append(r"c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기")
from services.i18n import PLATFORM_TRANSLATIONS

def get_translation(key, lang='ko'):
    return PLATFORM_TRANSLATIONS.get(lang, {}).get(key, key)

print(f"style_nursery_rhyme: {get_translation('style_nursery_rhyme')}")
print(f"style_character_webtoon: {get_translation('style_character_webtoon')}")
