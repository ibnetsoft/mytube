import os
import re

target_dir = r"c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\templates\pages"
color_hex = "#06101e"

def clean_content(content):
    # 1. Replace multiple occurrences of the same background color
    content = re.sub(rf'bg-\[{color_hex}\]\s+bg-\[{color_hex}\]', f'bg-[{color_hex}]', content)
    
    # 2. Re-standardize all possible backgrounds to the target color in dark/default contexts
    # These are classes often used as container backgrounds
    patterns = [
        r'bg-gray-950', r'dark:bg-gray-950',
        r'bg-gray-900', r'dark:bg-gray-900',
        r'bg-gray-800', r'dark:bg-gray-800',
        r'bg-white', r'dark:bg-white',
        r'bg-gray-50', r'bg-gray-100',
    ]
    
    for p in patterns:
        content = re.sub(rf'\b{p}\b', f'bg-[{color_hex}]', content)
    
    # 3. Handle semi-transparent ones to be based on the new color
    content = re.sub(r'bg-gray-900/([0-9]+)', rf'bg-[{color_hex}]/\1', content)
    content = re.sub(r'bg-gray-800/([0-9]+)', rf'bg-[{color_hex}]/\1', content)
    content = re.sub(r'bg-black/([0-9]+)', rf'bg-[{color_hex}]/\1', content)
    
    # 4. Final duplicate cleanup again just in case
    content = re.sub(rf'bg-\[{color_hex}\]\s+bg-\[{color_hex}\]', f'bg-[{color_hex}]', content)
    
    return content

for filename in os.listdir(target_dir):
    if filename.endswith(".html"):
        filepath = os.path.join(target_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        new_content = clean_content(content)
        
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Refined: {filename}")
