with open('templates/pages/settings.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = False
skip_content = False
for line in lines:
    if 'id="tab-withdrawal"' in line:
        skip = True
        continue
    if skip and '</button>' in line:
        skip = False
        continue
    if skip:
        continue

    if '<div id="tab-content-withdrawal"' in line:
        skip_content = True
        continue
    if skip_content and '<!-- Referral Tab -->' in line:
        skip_content = False
        new_lines.append(line)
        continue
    if skip_content:
        continue
    
    new_lines.append(line)

with open('templates/pages/settings.html', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
