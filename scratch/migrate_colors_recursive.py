import os
import re

# Update target_dir to parent to catch base.html etc
target_dir = r"c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\templates"
replacements = {
    "#000106": "#1c2027",
    "#13161b": "#1c2027",
    "#1c2128": "#1c2027",
    "bg-black": "bg-[#1c2027]",
    "dark:bg-black": "dark:bg-[#1c2027]",
    "border-gray-800": "border-white/5",
    "border-gray-900": "border-white/5"
}

# Walk recursively
for root, dirs, files in os.walk(target_dir):
    for filename in files:
        if filename.endswith(".html"):
            filepath = os.path.join(root, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            new_content = content
            for old, new in replacements.items():
                new_content = new_content.replace(old, new)
            
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Updated: {filepath}")
