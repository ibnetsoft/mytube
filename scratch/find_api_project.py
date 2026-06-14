import sys
sys.stdout.reconfigure(encoding='utf-8')
import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Let's search for '/api/projects' occurrences in main.py
for m in re.finditer(r'/api/projects', content):
    start = max(0, m.start() - 50)
    end = min(len(content), m.end() + 200)
    print(f"Match: {content[start:end]}")
    print('='*50)
