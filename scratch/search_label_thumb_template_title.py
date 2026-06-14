import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r"C:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator\services\i18n.py", 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    if "label_thumb_template_title" in line:
        print(f"{i}: {line.strip()}")
