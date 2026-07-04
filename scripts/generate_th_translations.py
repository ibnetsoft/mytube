#!/usr/bin/env python3
"""
AIR-0131 TH Translation Generator (DRY-RUN ONLY)
Generates Thai translations for EN keys missing from TH section.
Does NOT write to i18n.py — outputs Python dict lines for manual review.

Usage:
    python scripts/generate_th_translations.py          # dry-run, print to stdout
    python scripts/generate_th_translations.py --write  # NOT IMPLEMENTED - manual review required
"""
import re
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

REPO_ROOT = __file__.replace('\\', '/').rsplit('/scripts/', 1)[0]
I18N_PATH = REPO_ROOT + '/services/i18n.py'


def parse_section(content, lang):
    m = re.search(f"'{lang}'\\s*:\\s*{{", content)
    if not m:
        return {}
    start = m.end()
    # Find next top-level section
    next_m = re.search(r"^\s{4}'[a-z]{2}'\s*:\s*\{", content[start:], re.MULTILINE)
    end = start + next_m.start() if next_m else len(content)
    section = content[start:end]
    keys = {}
    for km in re.finditer(r"^\s{8}'([^']+)'\s*:", section, re.MULTILINE):
        keys[km.group(1)] = True
    return keys


def main():
    content = open(I18N_PATH, encoding='utf-8').read()

    m_en = re.search(r"'en'\s*:\s*\{", content)
    m_vi = re.search(r"'vi'\s*:\s*\{", content)
    m_th = re.search(r"'th'\s*:\s*\{", content)

    en_section = content[m_en.end():m_vi.start()]
    th_section = content[m_th.end():]

    en_keys = {}
    for km in re.finditer(r"^\s+'([^']+)'\s*:\s*(.+?)(?=,\s*$)", en_section, re.MULTILINE):
        en_keys[km.group(1)] = km.group(2).strip()

    th_keys = set()
    for km in re.finditer(r"^\s+'([^']+)'\s*:", th_section, re.MULTILINE):
        th_keys.add(km.group(1))

    missing = sorted(k for k in en_keys if k not in th_keys)
    print(f"# EN keys missing from TH: {len(missing)}")
    print(f"# DRY-RUN: review translations below, then add to services/i18n.py TH section manually")
    print()

    # Group by prefix
    groups = {}
    for k in missing:
        prefix = k.split('_')[0]
        groups.setdefault(prefix, []).append(k)

    for prefix, keys in sorted(groups.items()):
        print(f"        # --- {prefix}_* ({len(keys)} keys) ---")
        for k in keys:
            en_val = en_keys.get(k, "''")
            # Placeholder: use EN value until proper TH translation is provided
            print(f"        '{k}': {en_val},  # TODO: translate to Thai")
        print()


if __name__ == '__main__':
    main()
