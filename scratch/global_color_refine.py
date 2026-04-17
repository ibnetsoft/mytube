import os
import re

target_dir = r"c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\templates"
color_hex = "#000106"
hover_hex = "#0a0f1d"

regex_patterns = [
    # 1. Backgrounds
    (r'\bbg-[a-z]+-50(/\d+)?\b', f'bg-[{color_hex}]'),
    (r'\bdark:bg-[a-z]+-900(/\d+)?\b', f'dark:bg-[{color_hex}]'),
    (r'\bbg-white\b', f'bg-[{color_hex}]'),
    
    # 2. Hovers
    (r'\bhover:bg-gray-700\b', f'hover:bg-[{hover_hex}]'),
    (r'\bdark:hover:bg-gray-700\b', f'dark:hover:bg-[{hover_hex}]'),
    (r'\bhover:bg-gray-200\b', f'hover:bg-[{hover_hex}]'),
    
    # 3. Select elements (Ensure bg-[#000106] is set)
    (r'<select([^>]*)class="([^"]*)"', r'<select\1class="\2 bg-[' + color_hex + r'] text-white"'),
    
    # 4. Hex
    (r'#06101e', color_hex),
    (r'#080c18', color_hex),
    (r'#111827', color_hex),
    
    # 5. Fixes
    (r'bg-\[' + re.escape(color_hex) + r'\]/50/50', f'bg-[{color_hex}]'),
    (r'bg-\[' + re.escape(color_hex) + r'\]/20', f'bg-[{color_hex}]'),
    # Clean up double bg-[color]
    (r'bg-\[' + re.escape(color_hex) + r'\]\s+bg-\[' + re.escape(color_hex) + r'\]', f'bg-[{color_hex}]'),
]

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = content
    for pattern, replacement in regex_patterns:
        new_content = re.sub(pattern, replacement, new_content)
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True
    return False

for root, dirs, files in os.walk(target_dir):
    for filename in files:
        if filename.endswith(".html"):
            filepath = os.path.join(root, filename)
            process_file(filepath)

print("Updated all selects and backgrounds.")
