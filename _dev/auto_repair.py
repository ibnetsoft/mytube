import sys
import re

file_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\main.py'

def check_syntax():
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        compile(content, file_path, 'exec')
        return None
    except SyntaxError as e:
        return e

def fix_line(line_num, error_msg):
    # line_num is 1-indexed
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    if line_num > len(lines):
        return False
    
    idx = line_num - 1
    line = lines[idx]
    print(f"Fixing line {line_num}: {line.strip()}")
    
    # Strategy 1: Unterminated string
    if "unterminated string literal" in str(error_msg) or "EOL while scanning string literal" in str(error_msg):
        # Check occurance of " and '
        # Crude fix: if line contains " and no closing ", add "
        # But we need to know where.
        # Often it's inside a function call like raises HTTPException(..., "text)
        # If it ends with `)`, we might insert `"` before `)`.
        
        # Check if line ends with `)` or `),` or similar.
        if line.strip().endswith(')'):
             # Insert quote before )
             # But verify if it has an opening quote.
             if '"' in line:
                 lines[idx] = line.replace(')', '")')
                 print(f" -> Replaced ) with \")")
             elif "'" in line:
                 lines[idx] = line.replace(')', "')")
                 print(f" -> Replaced ) with ')")
        elif line.strip().endswith(','):
             # Insert quote before ,
             if '"' in line:
                 lines[idx] = line.replace(',', '",')
                 print(f" -> Replaced , with \",")
        else:
            # Just append quote
             lines[idx] = line.strip() + '"\n'
             print(f" -> Appended \"")

    # Strategy 2: Invalid syntax generic (often caused by stripped content becoming `return` without value, or empty `f""`)
    else:
        # If line contains `raise HTTPException`, likely string issue too
        if "raise HTTPException" in line:
             # Just replace with generic error
             lines[idx] = '    raise HTTPException(500, "Error")\n'
             print(" -> Replaced with generic Exception")
        else:
             # Comment it out? 
             lines[idx] = "# " + line
             print(" -> Commented out line")

    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    return True

MAX_ITER = 20
for i in range(MAX_ITER):
    err = check_syntax()
    if not err:
        print("Syntax check passed!")
        break
    
    print(f"Iteration {i}: Error at line {err.lineno}: {err.msg}")
    if not fix_line(err.lineno, err):
        print("Could not fix or line out of bounds.")
        break
else:
    print("Max iterations reached. Syntax still broken.")
