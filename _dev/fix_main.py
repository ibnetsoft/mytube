
import os

path = "main.py"
# Try reading with different encodings
encodings = ["utf-8", "cp949", "euc-kr", "latin-1"]
content = None
for enc in encodings:
    try:
        with open(path, "r", encoding=enc) as f:
            content = f.read()
        print(f"Read success with {enc}")
        break
    except:
        continue

if content:
    marker = "app.include_router(repository_router.router)"
    new_line = "app.include_router(settings_router.router) # [RESTORED]\n"

    if "settings_router.router" not in content:
        content = content.replace(marker, new_line + marker)
        with open(path, "w", encoding=enc) as f:
            f.write(content)
        print("RESTORED settings_router")
    else:
        print("ALREADY EXISTS")
else:
    print("FAILED TO READ FILE")
