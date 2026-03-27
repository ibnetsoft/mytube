
import os

filepath = r"c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\main.py"
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "scenes/animate" in line or "wan-video" in line or "animate" in line:
        print(f"Line {i+1}: {line.strip()}")
