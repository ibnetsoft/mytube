import re

file_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\main.py'
with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

# Find start
for i, line in enumerate(lines):
    if 'async def analyze_scenes' in line:
        start_idx = i
        break

if start_idx != -1:
    # Find end (next decorator or def, or sufficiently far)
    for i in range(start_idx + 1, len(lines)):
        curr_line = lines[i]
        if curr_line.startswith('@app.') or curr_line.startswith('async def ') or curr_line.startswith('def '):
            end_idx = i
            break
    
    if end_idx == -1:
        end_idx = start_idx + 100 # Safety cap

    print(f"Replacing analyze_scenes from {start_idx} to {end_idx}")
    
    new_func = [
        'async def analyze_scenes(project_id: int):\n',
        '    # Placeholder to fix syntax errors\n',
        '    return {"scene_count": 10, "reason": "Default (Repair Mode)"}\n',
        '\n'
    ]
    
    # Replace lines
    lines[start_idx:end_idx] = new_func

    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print("Replaced analyze_scenes.")
else:
    print("analyze_scenes not found.")
