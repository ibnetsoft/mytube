import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r"C:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator\templates\pages\thumbnail.html", 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    if "opt_select_template" in line:
        print(f"{i}: {line.strip()}")
