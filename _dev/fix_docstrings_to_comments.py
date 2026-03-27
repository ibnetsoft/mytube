import re

file_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\main.py'
with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    # Check if line looks like a simple docstring """...""" or "..."
    # And is indented (likely inside function)
    strip_line = line.strip()
    if strip_line.startswith('"""') and strip_line.endswith('"""') and len(strip_line) > 6:
        # Convert to comment
        # Calculate indent
        indent = line[:line.find('"""')]
        content = strip_line[3:-3]
        new_lines.append(f'{indent}# {content}\n')
    elif strip_line.startswith("'''") and strip_line.endswith("'''") and len(strip_line) > 6:
        indent = line[:line.find("'''")]
        content = strip_line[3:-3]
        new_lines.append(f'{indent}# {content}\n')
    else:
        new_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("Converted docstrings to comments.")
