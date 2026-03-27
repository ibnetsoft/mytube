
import os

path = "main.py"
with open(path, "rb") as f:
    data = f.read()

target = b"class ApiKeySave(BaseModel):"
idx = data.find(target)
if idx != -1:
    print(f"Found class at {idx}")
    print(data[idx:idx+1000].decode('utf-8', errors='replace'))
else:
    print("Not found")
