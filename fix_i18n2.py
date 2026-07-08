import re

with open('services/i18n.py', 'r', encoding='utf-8') as f:
    content = f.read()

# First, remove all duplicate occurrences of nav_referral
content = re.sub(r'\s*\'nav_referral\': \'.*?\',\n', '', content)

def insert_nav_referral(content, lang_key, translation):
    idx = content.find(f"'{lang_key}': {{")
    if idx != -1:
        logs_idx = content.find("'nav_logs':", idx)
        if logs_idx != -1:
            end_line_idx = content.find('\n', logs_idx)
            content = content[:end_line_idx+1] + f"        'nav_referral': '{translation}',\n" + content[end_line_idx+1:]
    return content

content = insert_nav_referral(content, 'ko', '추천인')
content = insert_nav_referral(content, 'en', 'Referral')
content = insert_nav_referral(content, 'vi', 'Giới thiệu')
content = insert_nav_referral(content, 'th', 'ผู้แนะนำ')

with open('services/i18n.py', 'w', encoding='utf-8') as f:
    f.write(content)
