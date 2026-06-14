import os

keywords = ["괄호", "톤", "어투", "나레이션", "대본"]
search_dirs = [
    r"C:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator\services",
    r"C:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator"
]

for directory in search_dirs:
    for filename in os.listdir(directory):
        if filename.endswith(".py"):
            filepath = os.path.join(directory, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    for kw in keywords:
                        if kw in line:
                            print(f"{filename}:{i+1} ({kw}): {line.strip()[:100]}")
            except Exception as e:
                pass
