import sys
sys.stdout.reconfigure(encoding='utf-8')
import re

with open('templates/base.html', 'r', encoding='utf-8') as f:
    content = f.read()

pattern = r"window\.dispatchEvent\(new CustomEvent\('projectStateRestored'"
for m in re.finditer(pattern, content):
    start = max(0, m.start() - 800)
    end = min(len(content), m.end() + 800)
    print(content[start:end])
    print('='*50)
