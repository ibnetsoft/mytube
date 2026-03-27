import re

file_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\main.py'
with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

new_lines = []
skip = False
replaced = False

start_marker = '@app.post("/api/image/analyze-character")'
# Note: It might be commented out like `# @app.post...`
search_marker = 'analyze-character")'

for i, line in enumerate(lines):
    if search_marker in line and not replaced:
        # Found the start (commented or not)
        print(f"Found analyze_character at line {i+1}")
        
        # Insert dummy function
        new_lines.append('@app.post("/api/image/analyze-character")\n')
        new_lines.append('async def analyze_character(project_id: Optional[int] = Form(None)):\n')
        new_lines.append('    # Restored dummy function\n')
        new_lines.append('    return {"description": "Character analysis placeholder", "image_url": ""}\n')
        new_lines.append('\n')
        
        # Enable skip mode to eat up the old broken function
        skip = True
        replaced = True
    
    if skip:
        # Check if we hit the end of the function.
        # Heuristic: Next class or @app
        if (line.strip().startswith('class ') or line.strip().startswith('@app')) and search_marker not in line:
            skip = False
            new_lines.append(line)
        else:
            # Continue skipping (or commenting out just in case)
            pass
    else:
        new_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("Restored analyze_character.")
