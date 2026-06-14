import re
import subprocess
import os

html_path = r"C:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator\templates\pages\thumbnail.html"

with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the main script block
scripts = re.findall(r'<script>(.*?)</script>', content, re.DOTALL)

for i, script in enumerate(scripts):
    temp_dir = r"C:\Users\kimse\.gemini\antigravity\scratch"
    os.makedirs(temp_dir, exist_ok=True)
    temp_file_path = os.path.join(temp_dir, f"temp_script_{i}.js")
    
    # We replace Jinja double curly brackets:
    # 1. If it's inside quotes: e.g. "{{ t(...) }}" or '{{ t(...) }}' -> replace standard expression with simple string
    # Let's replace any "{{ ... }}" or '{{ ... }}' (including quotes) with a simple string literal like 'jinja_expr'
    processed_script = re.sub(r'["\']\{\{.*?\}\}["\']', "'jinja_expr'", script)
    # Also replace any other loose {{ ... }} with a numeric literal or string
    processed_script = re.sub(r'\{\{.*?\}\}', '123', processed_script)
    # Replace {% ... %} with a comment or pass it
    processed_script = re.sub(r'\{%.*?%\}', '/* jinja_stmt */', processed_script)
    
    with open(temp_file_path, 'w', encoding='utf-8') as tf:
        tf.write(processed_script)
        
    print(f"Checking script block {i}...")
    try:
        res = subprocess.run(['node', '-c', temp_file_path], capture_output=True, text=True, check=True)
        print(f"Script block {i} is syntactically valid!")
    except subprocess.CalledProcessError as e:
        print(f"Error in script block {i}:")
        print(e.stderr)
        lines = processed_script.split('\n')
        match = re.search(r'temp_script_\d+\.js:(\d+)', e.stderr)
        if match:
            err_line = int(match.group(1))
            print(f"Error around line {err_line} in temp script:")
            start = max(0, err_line - 10)
            end = min(len(lines), err_line + 10)
            for l_num in range(start, end):
                prefix = "=> " if l_num + 1 == err_line else "   "
                print(f"{prefix}{l_num + 1}: {lines[l_num]}")
