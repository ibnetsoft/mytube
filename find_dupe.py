
try:
    with open("main.py", "r", encoding="utf-8") as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if "/thumbnail/save" in line:
                print(f"Line {i+1}: {line.strip()}")
            if "thumb_" in line:
                 print(f"Line {i+1} (thumb_): {line.strip()}")
except Exception as e:
    print(e)
