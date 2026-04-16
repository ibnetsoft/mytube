
import sys

target_file = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\services\i18n.py'

with open(target_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if "'nav_settings': '세팅메뉴'" in line:
        # Keep indentation
        indent = line[:line.find("'nav_settings'")]
        new_lines.append(f"{indent}'nav_settings': '세팅',\n")
        new_lines.append(f"{indent}'nav_logs': '로그',\n")
    else:
        new_lines.append(line)

with open(target_file, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("Replacement successful")
