import os

p = r'C:\Users\kimse\AppData\Roaming\Code\User\History'
for root, _, files in os.walk(p):
    for f in files:
        path = os.path.join(root, f)
        try:
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
                if 'webtoon_studio.html' in content or 'window.switchWebtoonTab' in content or 'function approveAndGenerate()' in content:
                    print('FOUND:', path)
        except Exception:
            pass
