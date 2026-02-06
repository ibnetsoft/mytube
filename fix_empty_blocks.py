import re

file_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\main.py'
with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    new_lines.append(line)
    
    # Check if this line starts a block
    sline = line.strip()
    # Basic heuristic for block start
    if sline.endswith(':') and not sline.startswith('#'):
        # Check if block is empty
        # Get current indent
        indent_match = re.search(r'^([ \t]*)', line)
        current_indent = indent_match.group(1) if indent_match else ""
        
        # Look ahead
        is_empty = True
        j = i + 1
        while j < len(lines):
            next_line = lines[j]
            next_sline = next_line.strip()
            
            if not next_sline: # Empty line
                j += 1
                continue
            
            # Get next indent
            next_indent_match = re.search(r'^([ \t]*)', next_line)
            next_indent = next_indent_match.group(1) if next_indent_match else ""
            
            # If next line is deeper indent
            if len(next_indent) > len(current_indent):
                # Check if it is code or comment
                if next_sline.startswith('#'):
                     # It is a comment. Keep looking (might mean still empty code-wise)
                     j += 1
                     continue
                else:
                     # It is code! Block is not empty.
                     is_empty = False
                     break
            else:
                # We hit a line with same or less indent.
                # And we haven't found code yet.
                is_empty = True
                break
        else:
             # End of file
             pass
        
        if is_empty:
            # Insert pass
            pass_indent = current_indent + "    "
            new_lines.append(f'{pass_indent}pass # Auto-inserted\n')
            print(f"Inserted pass after line {i+1}")

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("Fixed empty blocks.")
