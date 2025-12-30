
with open('c:/Users/kimse/Downloads/유튜브소재발굴기/backend/main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    for i, line in enumerate(lines):
        if '@app.post("/api/image/generate")' in line:
            print(f"Line {i+1}: {line.strip()}")
            # Print next few lines to identify function signature
            for j in range(1, 5):
                if i+j < len(lines):
                    print(f"  {lines[i+j].strip()}")
