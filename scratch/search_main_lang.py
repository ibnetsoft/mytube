import re

main_path = r"C:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator\main.py"

with open(main_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Let's find anything related to language/translation
lines = content.split('\n')
for line_num, line in enumerate(lines, 1):
    if any(k in line for k in ['language', 'locale', 't(', 'get_lang', 'i18n']):
        print(f"{line_num}: {line.strip()}")
