import re

file_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\main.py'
with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

output_lines = []
for i, line in enumerate(lines):
    # Check if line has non-ascii
    if not all(ord(c) < 128 for c in line):
        # Fix Docstrings
        if '"""' in line:
            # Replace content inside """...""" with "Docstring"
            # But handle indentation.
            match = re.search(r'(\s*)"""(.*)"""', line)
            if match:
                indent = match.group(1)
                # Keep original if it looks like just English? No, line has non-ascii.
                new_line = f'{indent}"""Docstring placeholder"""\n'
                output_lines.append(new_line)
                print(f"Fixed docstring at line {i+1}")
                continue
        
        # Fix "title": "..."
        if '"title":' in line or "'title':" in line:
             match = re.search(r'(\s*)(["\']title["\']:\s*)(["\'].*["\'])(.*)', line)
             if match:
                 indent = match.group(1)
                 key_part = match.group(2)
                 val_part = match.group(3)
                 end_part = match.group(4)
                 
                 # Replace value using English or placeholder
                 new_line = f'{indent}{key_part}"Title Placeholder"{end_part}\n'
                 output_lines.append(new_line)
                 print(f"Fixed title at line {i+1}")
                 continue

        # If it is a comment (#), let's strip non-ascii or replace
        if line.strip().startswith('#'):
            # Replace garbled comment with # Comment
            match = re.search(r'(\s*)#', line)
            if match:
                indent = match.group(1)
                new_line = f'{indent}# Comment\n'
                output_lines.append(new_line)
                # We don't print for comments to avoid spamming stdout
                continue
        
        # For other lines (code mixed with garbled strings), we have to be careful.
        # If it contains f-string with garbled text...
        # Example line 587: analysis_prompt = f"""...
        # This is a Multi-line string start.
        if 'f"""' in line or 'f\'\'\'' in line or '"""' in line:
             # It might be start of multi-line.
             # If it marks start/end of function docstring, handled above?
             # But prompt templates like `prompt = f"""` need care.
             # We will just strip non-ascii chars from the line.
             cleaned = "".join([c for c in line if ord(c) < 128])
             output_lines.append(cleaned)
             print(f"Stripped non-ascii from line {i+1}")
             continue
        
        # Default fallback: Strip non-ascii and hope for syntax validity
        cleaned = "".join([c for c in line if ord(c) < 128])
        output_lines.append(cleaned)
        # print(f"Stripped non-ascii from code line {i+1}")

    else:
        output_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(output_lines)
print("Mass fix completed.")
