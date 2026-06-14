import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r"C:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator\templates\pages\subtitle_gen.html", 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    if "shorts-template" in line or "presets" in line or "template" in line:
        if any(k in line for k in ['fetch', 'API', 'select', 'load']):
            print(f"{i}: {line.strip()}")
