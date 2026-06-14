import os
import re

search_dir = r"C:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator"
pattern = re.compile(r"def .*render", re.IGNORECASE)

for root, dirs, files in os.walk(search_dir):
    if "venv" in root or ".git" in root:
        continue
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line_num, line in enumerate(f, 1):
                        if pattern.search(line):
                            print(f"{path}:{line_num}: {line.strip()}")
            except Exception:
                pass
