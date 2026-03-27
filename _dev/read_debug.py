import os
with open('prompt_debug.txt', 'rb') as f:
    content = f.read()
    try:
        print(content.decode('utf-16'))
    except:
        print(content.decode('utf-8', errors='ignore'))
