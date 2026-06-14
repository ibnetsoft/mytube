import re

filepath = 'services/i18n.py'

new_keys = {
    'ko': {
        'tooltip_sync_server': "서버와 동기화",
        'tooltip_logout': "로그아웃",
        'tooltip_token_balance': "보유 AI 토큰 잔액",
    },
    'en': {
        'tooltip_sync_server': "Sync with server",
        'tooltip_logout': "Logout",
        'tooltip_token_balance': "Available AI token balance",
    },
    'vi': {
        'tooltip_sync_server': "Đồng bộ hóa với máy chủ",
        'tooltip_logout': "Đăng xuất",
        'tooltip_token_balance': "Số dư Token AI hiện có",
    }
}

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Insert for 'ko'
ko_match = re.search(r"\'ko\'\s*:\s*\{", content)
if ko_match:
    idx = ko_match.end()
    ko_insert = ""
    for k, v in new_keys['ko'].items():
        ko_insert += f"\n        '{k}': '{v}',"
    content = content[:idx] + ko_insert + content[idx:]

# Insert for 'en'
en_match = re.search(r"\'en\'\s*:\s*\{", content)
if en_match:
    idx = en_match.end()
    en_insert = ""
    for k, v in new_keys['en'].items():
        en_insert += f"\n        '{k}': '{v}',"
    content = content[:idx] + en_insert + content[idx:]

# Insert for 'vi'
vi_match = re.search(r"\'vi\'\s*:\s*\{", content)
if vi_match:
    idx = vi_match.end()
    vi_insert = ""
    for k, v in new_keys['vi'].items():
        vi_insert += f"\n        '{k}': '{v}',"
    content = content[:idx] + vi_insert + content[idx:]

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("Tooltips successfully injected!")
