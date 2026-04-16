
import sys
import re

target_file = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\services\i18n.py'

encodings = ['utf-8', 'cp949', 'euc-kr']
content = None
chosen_enc = None

for enc in encodings:
    try:
        with open(target_file, 'r', encoding=enc) as f:
            content = f.read()
            chosen_enc = enc
            break
    except Exception:
        continue

if not content:
    print("Failed to read file")
    sys.exit(1)

lines = content.splitlines()
new_lines = []

# Regex to detect nav_thumbnail lines
# Example: 'nav_thumbnail': '썸네일 생성',
pattern = re.compile(r"(\s+)'nav_thumbnail':\s+['\"](.*?)['\"],")

for line in lines:
    match = pattern.search(line)
    if match:
        indent = match.group(1)
        value = match.group(2)
        
        # 1. Fix corrupted/incorrect thumbnail label
        if value == "템플릿":
            line = line.replace("템플릿", "썸네일 생성")
            print(f"Fixed '템플릿' -> '썸네일 생성' at line item")
        
        new_lines.append(line)
        
        # 2. Add nav_shorts_template if not already there in the next line (simple check)
        # We'll just add it anyway if the next line doesn't start with it.
        # To avoid duplicates in this run, we check if we already have it.
        pass # We'll handle insertion in a second pass or smarter way
    else:
        new_lines.append(line)

# Final step: Ensure nav_thumbnail is followed by nav_shorts_template if missing
final_lines = []
for i in range(len(new_lines)):
    line = new_lines[i]
    final_lines.append(line)
    
    match = pattern.search(line)
    if match:
        # Check if next line is already nav_shorts_template
        exists = False
        if i + 1 < len(new_lines) and "nav_shorts_template" in new_lines[i + 1]:
            exists = True
        
        if not exists:
            indent = match.group(1)
            thumb_val = match.group(2)
            
            # Determine template label based on language
            # Simple check: if thumb_val has Korean, use '템플릿', else 'Template'
            is_korean = any('\uac00' <= char <= '\ud7a3' for char in thumb_val)
            template_val = "템플릿" if is_korean else "Template"
            
            template_line = f"{indent}'nav_shorts_template': '{template_val}',"
            final_lines.append(template_line)
            print(f"Added {template_line}")

with open(target_file, 'w', encoding=chosen_enc) as f:
    f.write("\n".join(final_lines))

print("Cleanup and synchronization complete.")
