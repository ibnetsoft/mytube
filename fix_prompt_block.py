import re

file_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\main.py'
with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

updates = {
    586: '        analysis_prompt = f"""Analyze the following script and determine the appropriate number of scenes for image generation.\n',
    587: '\n',
    588: 'Script:\n',
    589: f'{{script}}\n',
    590: '\n',
    591: 'Guidelines:\n',
    592: '- Determine a natural scene count considering the flow.\n',
    593: '- Avoid too few (1-2) or too many (50+).\n',
    594: '- Typically 5-20 is appropriate.\n',
    595: '- Consider script length and topic changes.\n',
    596: '\n',
    597: 'Output Format (JSON only):\n',
    598: '{{"scene_count": number, "reason": "reason"}}"""\n'
}

# Apply updates. Note that I need to be careful with indexing if previous edits shifted lines.
# But since I'm editing in-place with replacing, line count should be same if I map 1-to-1.
# My previous `fix_docstrings` didn't change line count.

# Wait, `updates` keys are 0-based index?
# In Step 1460, I used 586 as key for `lines[idx]`.
# I should double check if 586 is indeed the line starting with `analysis_prompt`.
# Use a search to find the line index.

for i, line in enumerate(lines):
    if 'analysis_prompt = f"' in line or 'analysis_prompt = f""' in line:
        print(f"Found analysis_prompt at {i}")
        # Only if it looks like the one we want
        if 'Analyze' in line or 'scene_count' in line or 'script' in line or len(line.strip()) < 80:
             # Apply the block update starting from i
             lines[i] = '        analysis_prompt = f"""Analyze the following script and determine the appropriate number of scenes for image generation.\n'
             lines[i+1] = '\n'
             lines[i+2] = 'Script:\n'
             lines[i+3] = f'{{script}}\n'
             lines[i+4] = '\n'
             lines[i+5] = 'Guidelines:\n'
             lines[i+6] = '- Determine a natural scene count considering the flow.\n'
             lines[i+7] = '- Avoid too few (1-2) or too many (50+).\n'
             lines[i+8] = '- Typically 5-20 is appropriate.\n'
             lines[i+9] = '- Consider script length and topic changes.\n'
             lines[i+10] = '\n'
             lines[i+11] = 'Output Format (JSON only):\n'
             lines[i+12] = '{{"scene_count": number, "reason": "reason"}}"""\n'
             print("Replaced analysis_prompt block")
             break

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print("Rewrote prompt block.")
