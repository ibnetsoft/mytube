import os
import re

target_dir = r"c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\templates\pages"
color = "#06101e"

replacements = {
    'dark:bg-gray-900': f'bg-[{color}]',
    'dark:bg-gray-800': f'bg-[{color}]',
    'dark:bg-gray-700': f'bg-[{color}]/50',
    'dark:bg-gray-950': f'bg-[{color}]',
    'bg-gray-50': f'bg-[{color}]',
    'bg-white': f'bg-[{color}]',
}

for filename in os.listdir(target_dir):
    if filename.endswith(".html"):
        filepath = os.path.join(target_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        new_content = content
        for old, new in replacements.items():
            new_content = new_content.replace(old, new)
        
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Updated: {filename}")
