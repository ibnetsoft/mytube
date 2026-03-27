file_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\main.py'
with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

output_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\audit_log_utf8.txt'
with open(output_path, 'w', encoding='utf-8') as f_out:
    for i, line in enumerate(lines):
        if not all(ord(c) < 128 for c in line):
            try:
                f_out.write(f"{i}: {line.strip()}\n")
            except:
                f_out.write(f"{i}: [Unprintable]\n")
