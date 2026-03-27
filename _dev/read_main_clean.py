
import os

path = "main.py"
encodings = ["utf-8", "cp949", "euc-kr", "latin-1"]
content = None
chosen_enc = None

for enc in encodings:
    try:
        with open(path, "r", encoding=enc) as f:
            lines = f.readlines()
        content = lines
        chosen_enc = enc
        print(f"Read success with {enc}")
        break
    except:
        continue

if content:
    # Print lines 1050 to 1150
    start = 1050
    end = 1150
    for i in range(max(0, start-1), min(len(content), end)):
        print(f"{i+1}: {content[i].strip()}")
else:
    print("FAILED TO READ")
