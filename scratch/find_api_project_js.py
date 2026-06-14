import sys
sys.stdout.reconfigure(encoding='utf-8')
import re

with open('static/js/api.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Let's search for API.project = or something
idx = content.find('project:')
if idx != -1:
    print(content[idx:idx+1500])
