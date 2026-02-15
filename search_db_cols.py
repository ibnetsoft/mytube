import os

with open('database.py', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if 'webtoon_scenes_json' in line or 'voice_mapping_json' in line:
            print(f"{i+1}: {line.strip()}")
