import sys
import os

# Adjust path to find services/i18n.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.i18n import PLATFORM_TRANSLATIONS

ko_keys = set(PLATFORM_TRANSLATIONS['ko'].keys())
vi_keys = set(PLATFORM_TRANSLATIONS['vi'].keys())

missing_in_vi = sorted(list(ko_keys - vi_keys))
print(f"Total keys in KO: {len(ko_keys)}")
print(f"Total keys in VI: {len(vi_keys)}")
print(f"Keys missing in VI ({len(missing_in_vi)}):")
for k in missing_in_vi:
    val_ko = PLATFORM_TRANSLATIONS['ko'][k]
    print(f"  {k!r}: {val_ko!r}")

# Check if there are keys in VI that have Korean text (which might mean copy-pasted untranslated values)
import re
korean_regex = re.compile('[ㄱ-ㅎㅏ-ㅣ가-힣]')
vietnamese_with_korean = []
for k, v in PLATFORM_TRANSLATIONS['vi'].items():
    if korean_regex.search(str(v)):
        vietnamese_with_korean.append((k, PLATFORM_TRANSLATIONS['ko'].get(k), v))

print(f"\nKeys in VI containing Korean characters ({len(vietnamese_with_korean)}):")
for k, ko_val, vi_val in vietnamese_with_korean:
    print(f"  {k!r}: KO={ko_val!r} | VI={vi_val!r}")
