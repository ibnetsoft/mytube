file_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\main.py'
with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

# Replace first 5 lines with clean header
lines[0] = '"""\n'
lines[1] = 'PICADIRI STUDIO - FastAPI Main Server\n'
lines[2] = 'AI Automated Video Creation Platform\n'
lines[3] = '"""\n'
lines[4] = '# Header restored\n'

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print("Restored header.")
