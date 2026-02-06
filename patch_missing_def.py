import os

file_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\main.py'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '"""외부 영상 파일 업로드"""' in line:
        if i > 0 and 'async def' not in lines[i-1]:
            print(f"Found orphan docstring at line {i+1}")
            # Insert headers
            lines.insert(i, 'async def upload_external_video(project_id: int, file: UploadFile = File(...)):\n')
            lines.insert(i, '@app.post("/api/video/upload-external/{project_id}")\n')
            # Indent the docstring line itself? The previous tool output showed it unindented.
            # But subsequent lines were indented.
            # If line is `"""...` (no indent), we should indent it to 4 spaces.
            if not line.startswith('    '):
                lines[i+2] = '    ' + lines[i+2]
            break

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print("Patched missing def.")
