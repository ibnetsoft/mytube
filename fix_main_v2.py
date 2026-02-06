import os

file_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\main.py'
with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

updates = {
    450: '    """Video Upload Page"""\n',
    454: '        "title": "Video Upload",\n',
    460: '    """Subtitle Generation Page"""\n',
    473: '        "title": "Subtitle Edit",\n',
    480: '    """Title/Desc Gen Page"""\n',
    484: '        "title": "Title/Desc Gen"\n',
    489: '    """Thumbnail Gen Page"""\n',
    493: '        "title": "Thumbnail Gen"\n',
    498: '    """Shorts Gen Page"""\n',
    502: '        "title": "Shorts Gen"\n',
    507: '    """Settings Page"""\n',
    511: '        "title": "Settings"\n',
    527: '    """Keyword based title recommendation"""\n',
    536: '    """Save Script"""\n',
    543: '    """Get Script"""\n',
    548: '    """Get Project Full Data"""\n',
    554: '    """Analyze script and determine scene count"""\n',
    586: '        analysis_prompt = f"""Analyze the following script and determine the appropriate number of scenes for image generation.\n',
    588: 'Script:\n',
    591: 'Guidelines:\n',
    592: '- Determine a natural scene count considering the flow.\n',
    593: '- Avoid too few (1-2) or too many (50+).\n',
    594: '- Typically 5-20 is appropriate.\n',
    595: '- Consider script length and topic changes.\n',
    597: 'Output Format (JSON only):\n',
    598: '{{"scene_count": number, "reason": "reason"}}"""\n'
}

for idx, content in updates.items():
    if idx < len(lines):
        lines[idx] = content

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Fixed more lines in main.py')
