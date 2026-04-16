
import sys

target_file = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\services\i18n.py'

with open(target_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
count = 0
for line in lines:
    if "숏폼 템플릿" in line:
        new_line = line.replace("숏폼 템플릿", "템플릿")
        new_lines.append(new_line)
        count += 1
    else:
        new_lines.append(line)

with open(target_file, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print(f"Renamed {count} instances of 숏폼 템플릿 to 템플릿")
