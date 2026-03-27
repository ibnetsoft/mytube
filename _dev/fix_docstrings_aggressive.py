import re

file_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\main.py'
with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    sline = line.strip()
    if '"""' in sline:
        # Check if it is a docstring line
        # If it starts with """ (ignoring indentation)
        if sline.startswith('"""'):
            # It is likely a docstring start/end or one-liner.
            # Convert to comment
            indent = line[:line.find('"""')]
            content = line[line.find('"""'):].strip()
            # Just comment the whole line
            new_lines.append(f'{indent}# {content}\n')
            print(f"Commented out line {i+1}")
        else:
            # Maybe `x = """` or `f"""`
            # If it has non-ascii, we probably want to kill it too if it's garbled prompt.
            if not all(ord(c) < 128 for c in line):
                 new_lines.append(f'# {line.strip()}\n')
                 print(f"Commented out non-ascii line with quotes {i+1}")
            else:
                 new_lines.append(line)
    else:
        new_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("Aggressive docstring fixing done.")
