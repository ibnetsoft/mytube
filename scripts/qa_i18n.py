#!/usr/bin/env python3
"""
AIR-0131 QA Script: i18n audit
- Finds EN keys missing from VI/TH/KO sections
- Detects current_lang conditionals in templates
- Reports summary
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
I18N_PATH = REPO / "services" / "i18n.py"
TEMPLATES_DIR = REPO / "templates"


def extract_section_keys(text, section_start_pattern):
    """Extract all keys from a PLATFORM_TRANSLATIONS language section."""
    # Find section start
    m = re.search(section_start_pattern, text)
    if not m:
        return {}
    start = m.start()

    # Find next section start (same pattern for next lang) or end of dict
    remaining = text[start + len(m.group()):]
    keys = {}
    for km in re.finditer(r"^\s+'([^']+)'\s*:", remaining, re.MULTILINE):
        keys[km.group(1)] = True
    return keys


def parse_i18n_sections(path):
    """Parse i18n.py by actually importing it (accurate Python dict semantics)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("i18n_module", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    pt = mod.PLATFORM_TRANSLATIONS
    sections = {lang: dict(keys) for lang, keys in pt.items()}
    return sections


def find_current_lang_in_templates(templates_dir):
    results = {}
    for tmpl in sorted(templates_dir.rglob("*.html")):
        count = 0
        lines = []
        for i, line in enumerate(tmpl.read_text(encoding="utf-8").splitlines(), 1):
            if "current_lang ==" in line or "current_lang in [" in line:
                count += 1
                lines.append(i)
        if count:
            rel = tmpl.relative_to(templates_dir)
            results[str(rel)] = lines
    return results


def main():
    print("=" * 60)
    print("AIR-0131 i18n QA Report")
    print("=" * 60)

    sections = parse_i18n_sections(I18N_PATH)
    en_keys = set(sections.get("en", {}).keys())
    vi_keys = set(sections.get("vi", {}).keys())
    th_keys = set(sections.get("th", {}).keys())
    ko_keys = set(sections.get("ko", {}).keys())

    print(f"\nKey counts: KO={len(ko_keys)}  EN={len(en_keys)}  VI={len(vi_keys)}  TH={len(th_keys)}")

    # EN keys missing from VI (exclude 'vi' which is a section-marker false positive)
    vi_missing = sorted((en_keys - vi_keys) - {'vi'})
    print(f"\nEN keys missing from VI: {len(vi_missing)}")
    for k in vi_missing:
        print(f"  {k}")

    # EN keys missing from TH
    th_missing = sorted(en_keys - th_keys)
    print(f"\nEN keys missing from TH: {len(th_missing)}")
    for k in th_missing[:20]:
        print(f"  {k}")
    if len(th_missing) > 20:
        print(f"  ... and {len(th_missing)-20} more")

    # current_lang conditionals in templates
    print("\n" + "=" * 60)
    print("current_lang conditionals in templates:")
    cl_results = find_current_lang_in_templates(TEMPLATES_DIR)
    total_cl = sum(len(v) for v in cl_results.values())
    if cl_results:
        for tmpl, lines in cl_results.items():
            print(f"  {tmpl}: lines {lines}")
        print(f"  Total: {total_cl} occurrences in {len(cl_results)} files")
    else:
        print("  None found (all clean)")

    print("\n" + "=" * 60)
    return vi_missing


if __name__ == "__main__":
    main()
