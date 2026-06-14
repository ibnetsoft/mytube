import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r"C:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator\templates\pages\template.html", 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    if "window.i18n" in line:
        print(f"{i}: {line.strip()}")
