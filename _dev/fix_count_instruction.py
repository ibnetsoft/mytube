import re

file_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\main.py'
with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'count_instruction = "-' in line:
        if not all(ord(c) < 128 for c in line):
            print(f"Fixing count_instruction at {i+1}")
            # Get indent
            indent = line[:line.find('count_instruction')]
            lines[i] = f'{indent}count_instruction = "- Generate appropriate number of image prompts."\n'

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print("Fixed count_instruction.")
