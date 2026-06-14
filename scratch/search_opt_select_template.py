with open(r"C:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator\services\i18n.py", 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    if "opt_select_template" in line:
        print(f"{i}: {line.strip()}")
