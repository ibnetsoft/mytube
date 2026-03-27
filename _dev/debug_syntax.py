
import os

path = "main.py"
with open(path, "rb") as f:
    data = f.read()

# Search for the problematic string
target = "개의 API 키가 저장되었습니다".encode('utf-8')
idx = data.find(target)
if idx != -1:
    print(f"Found target at {idx}")
    # Print the context around it
    print(data[idx-50:idx+100].decode('utf-8', errors='replace'))
else:
    # Try searching for a portion of it
    target = "저장되었습니다".encode('utf-8')
    idx = data.find(target)
    if idx != -1:
        print(f"Found partial target at {idx}")
        print(data[idx-100:idx+100].decode('utf-8', errors='replace'))
    else:
        print("Target not found")
