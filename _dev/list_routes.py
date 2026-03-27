
try:
    with open("main.py", "r", encoding="utf-8") as f:
        for line in f:
            if "@app.get" in line and "full" in line:
                print(line.strip())
            if "@app.get" in line and "projects" in line:
                print(line.strip())
except Exception as e:
    print(e)
