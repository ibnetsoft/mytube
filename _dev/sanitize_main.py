import re

file_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\main.py'

with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    # 1. Strip BOM if present on first line (already handled by utf-8-sig usually, but let's be safe)
    # 2. Convert NBSP (\xa0) to space
    clean_line = line.replace('\xa0', ' ')
    
    # 3. Check for other invisible chars in indentation
    # Regex to find leading whitespace
    match = re.match(r'^([ \t]*)(.*)', clean_line, re.DOTALL)
    if match:
        indent = match.group(1)
        content = match.group(2)
        
        # If 'indent' contains anything other than space or tab, replace it?
        # But regex [ \t]* matches only space/tab.
        # If there are other chars, they are part of 'content'.
        
        # If 'content' starts with something invalid but looks like invisible, it might be issue.
        # But 'invalid syntax' on `"""String"""` suggests the `"""` is seen as invalid or not starting a string.
        
        pass

    new_lines.append(clean_line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Sanitized main.py")
