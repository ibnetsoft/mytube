with open(r"C:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator\main.py", 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    if "templates" in line:
        print(f"{i}: {line.strip()}")
