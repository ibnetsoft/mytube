import re

with open("services/i18n.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add nav_referral translations for each language
# We'll just insert them near 'nav_wallet' or 'nav_logs'
# For ko
content = re.sub(r"('nav_logs':\s*'.+?',)", r"\1\n        'nav_referral': '추천인',", content)
# For en
content = re.sub(r"('nav_logs':\s*'.+?',)", r"\1\n        'nav_referral': 'Referral',", content)
# For vi (assuming 'nav_logs' exists, or 'nav_settings')
# It's safer to just inject at the beginning of each dict
content = re.sub(r"('ko':\s*{)", r"\1\n        'nav_referral': '추천인',", content)
content = re.sub(r"('en':\s*{)", r"\1\n        'nav_referral': 'Referral',", content)
content = re.sub(r"('vi':\s*{)", r"\1\n        'nav_referral': 'Giới thiệu',", content)
content = re.sub(r"('th':\s*{)", r"\1\n        'nav_referral': 'ผู้แนะนำ',", content)

with open("services/i18n.py", "w", encoding="utf-8") as f:
    f.write(content)

with open("templates/base.html", "r", encoding="utf-8") as f:
    base = f.read()

# 1. Update the nav link
base = base.replace(
    '''<span class="font-bold">추천인 (Referral)</span>''',
    '''<span class="font-bold" data-i18n-key="nav_referral">{{ t('nav_referral') }}</span>'''
)

# 2. Add 'nav_referral' to the loop
base = base.replace(
    """['nav_repository','nav_plan','nav_music_plan','nav_script','nav_title_desc','nav_intro','nav_image','nav_cover_image','nav_image_crop','nav_audio','nav_track_generation','nav_thumbnail','nav_shorts_template','nav_tts','nav_subtitle','nav_render','nav_upload','nav_reserve','nav_shorts','nav_commerce_shorts','nav_autopilot','nav_settings','nav_logs','nav_wallet']""",
    """['nav_repository','nav_plan','nav_music_plan','nav_script','nav_title_desc','nav_intro','nav_image','nav_cover_image','nav_image_crop','nav_audio','nav_track_generation','nav_thumbnail','nav_shorts_template','nav_tts','nav_subtitle','nav_render','nav_upload','nav_reserve','nav_shorts','nav_commerce_shorts','nav_autopilot','nav_settings','nav_logs','nav_wallet','nav_referral']"""
)

# 3. Add window.location.reload()
reload_code = """
                    window.currentLang = lang;
                    updateLangButtonStates(lang);
                    refreshLangDependentUI(lang);
                    Utils.showToast(i18n.lang_change_success || 'Language changed', 'success');
                    
                    // Reload to immediately apply the language change to Jinja-rendered templates
                    setTimeout(() => window.location.reload(), 300);
"""
base = base.replace(
    """
                    window.currentLang = lang;
                    updateLangButtonStates(lang);
                    refreshLangDependentUI(lang);
                    Utils.showToast(i18n.lang_change_success || 'Language changed', 'success');""",
    reload_code
)

with open("templates/base.html", "w", encoding="utf-8") as f:
    f.write(base)

print("done")
