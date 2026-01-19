
import re

def find_route():
    with open("main.py", "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    print("--- Scanning for 'subtitle_gen.html' ---")
    for i, line in enumerate(lines):
        if "subtitle_gen.html" in line:
            print(f"Line {i+1}: {line.strip()}")
            # Print context (previous 5 lines to see @app.get)
            start = max(0, i-10)
            for j in range(start, i):
                print(f"  {j+1}: {lines[j].strip()}")
            print("-" * 20)

if __name__ == "__main__":
    find_route()
