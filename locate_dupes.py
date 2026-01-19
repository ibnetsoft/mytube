
try:
    with open("main.py", "r", encoding="utf-8") as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if '/api/projects/{project_id}/full' in line:
                print(f"Let's look at line {i+1}: {line.strip()}")
                # Print next few lines to see function name
                for j in range(1, 5):
                     if i+j < len(lines):
                         print(f"  {lines[i+j].strip()}")
except Exception as e:
    print(e)
