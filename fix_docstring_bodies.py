file_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\main.py'
with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

new_lines = []
inside_broken_docstring = False

for line in lines:
    stripped = line.strip()
    
    # Check for my previous marker `# """` or `# '''`
    # Note: Indentation might precede #.
    # regex for `^\s*#\s*"""`
    is_doc_marker = False
    if '"""' in line and line.strip().startswith('#'):
        is_doc_marker = True
    elif "'''" in line and line.strip().startswith('#'):
        is_doc_marker = True
        
    if is_doc_marker:
        # Toggle?
        # But wait, original code might have used same-line docstrings `"""Doc"""` which I commented out.
        # If it was one-liner: `# """Doc"""`. This is fine.
        # If it was multi-line: `# """` (start) ... `# """` (end).
        # We need to distinguish.
        
        # Heuristic: If marker line ends with `"""` (ignoring comments/spaces) and has content in between?
        # My previous script:
        # indent = ...; content = line[...].strip()
        # new_lines.append(f'{indent}# {content}\n')
        
        # If content was just `"""` (start of multi-line), then `content` is `"""`.
        
        # Let's see if the line ends with `"""` appearing TWICE or just ONCE?
        # `"""` appears once -> Toggle.
        # `"""..."""` appears twice -> One-liner.
        
        quote_count = line.count('"""')
        if quote_count == 1:
            inside_broken_docstring = not inside_broken_docstring
            new_lines.append(line)
        else:
            # Assumed one-liner or already handled
            new_lines.append(line)
    else:
        if inside_broken_docstring:
            # This is the body. Comment it out.
            new_lines.append(f'# {line}')
        else:
            # Normal code (or garbage needing fix, but let's hope syntax checker catches it)
            new_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("Commented out docstring bodies.")
