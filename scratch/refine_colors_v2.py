import os
import re

target_dir = r"c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\templates\pages"
color_hex = "#000106"

def clean_content(content):
    # Support both old #06101e and new #000106 to be safe
    old_color = "#06101e"
    
    # Replace the old color with the new one
    content = content.replace(old_color, color_hex)
    
    # Remove any duplicates that might occur
    content = re.sub(rf'bg-\[{color_hex}\]\s+bg-\[{color_hex}\]', f'bg-[{color_hex}]', content)
    
    # Handle the specific case in settings.html top bar
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
            print(f"Refined to #000106: {filename}")
