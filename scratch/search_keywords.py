import os

search_dir = r"C:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator\auth-web"
keywords = ["AdminDashboardContent"]

for root, dirs, files in os.walk(search_dir):
    if "node_modules" in root or ".next" in root:
        continue
    for file in files:
        if file.endswith((".tsx", ".ts", ".js", ".jsx")):
            filepath = os.path.join(root, file)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                for idx, line in enumerate(lines):
                    for kw in keywords:
                        if kw.lower() in line.lower():
                            rel_path = os.path.relpath(filepath, search_dir)
                            print(f"{rel_path} Line {idx+1}: {line.strip()}")
                            break
            except Exception as e:
                pass
