import sys
sys.stdout.reconfigure(encoding='utf-8')
import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Let's search for patch/post routes related to projects/{project_id}
for m in re.finditer(r'@app\.(patch|post|put)\("/api/projects/.*?"\)', content):
    start = m.start()
    end = content.find('def ', start)
    func_end = content.find(':', end)
    print(content[start:func_end+1])
    # print next 25 lines
    lines = content[func_end:func_end+1000].split('\n')[:25]
    print('\n'.join(lines))
    print('='*50)
