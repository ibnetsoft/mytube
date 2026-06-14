import sys
sys.stdout.reconfigure(encoding='utf-8')

from services.i18n import PLATFORM_TRANSLATIONS

for lang, dict_data in PLATFORM_TRANSLATIONS.items():
    if "opt_select_template" in dict_data:
        print(f"'{lang}': {repr(dict_data['opt_select_template'])}")
