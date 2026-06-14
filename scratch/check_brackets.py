with open(r"C:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator\auth-web\components\DashboardContent.tsx", "r", encoding="utf-8") as f:
    code = f.read()

stack = []
pairs = {')': '(', '}': '{', ']': '['}
lines = code.split('\n')

for i, line in enumerate(lines, 1):
    for j, char in enumerate(line, 1):
        if char in '({[':
            stack.append((char, i, j))
        elif char in ')}]':
            if not stack:
                print(f"Extra closing char '{char}' at line {i}, col {j}")
            else:
                top, ti, tj = stack.pop()
                if pairs[char] != top:
                    print(f"Mismatched char: opened '{top}' at line {ti}, col {tj} but closed with '{char}' at line {i}, col {j}")

print(f"Stack size at end: {len(stack)}")
for item in stack[:10]:
    print(f"Unclosed '{item[0]}' opened at line {item[1]}, col {item[2]}")
