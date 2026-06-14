import re

# New proposed pattern with OR to handle name) format without matching (emotion) lines
pattern = re.compile(
    r'^\s*(?:'
    r'[\*\_\[\(]*([^\s:\[\(\*\_]+)[\*\_\]\)]*[ \t]*(\([^)]*\))?[ \t]*[:：][ \t]*(.*)'
    r'|'
    r'([^\s:\[\(\*\_]+)[ \t]*[\)）\]][ \t]*(.*)'
    r')$'
)

lines = [
    "하게) 헐. 뭐야 저게. 지금 둘러 있는 거 맞아?",
    "진우: (헛웃음 치며) 타격감이 완전 제로야. 세상 평온해 보이는데?",
    "수아: (어리둥절하며) 방금 하이에나 하품한 거 봤어?",
    "진우: (기막혀하며) 호랑",
    "태현: (긴장하며) 지금 엄청난 상황이 벌어지기 직전입니다.",
    "민석: (숨을 죽이며) 네, 호랑이와 하이에나가 정면으로 마주쳤습니다.",
    "태현: (급하게) 야생의 최강자 호랑이입니다.",
    "민석: (진지하게) 그리고 아프리카",
    "(비가 내린다) 집으로 돌아갔다.",
    "(비가) 나는 집으로 갔다.",
    "**홍길동**: 안녕 하세요"
]

print("=== TESTING REGEX ===")
for l in lines:
    m = pattern.match(l)
    if m:
        if m.group(1): # First alternative (colon format)
            print(f"Match (Colon): '{l}' -> Speaker: '{m.group(1)}', Emotion: '{m.group(2)}', Content: '{m.group(3)}'")
        else: # Second alternative (parenthesis format)
            print(f"Match (Paren): '{l}' -> Speaker: '{m.group(4)}', Content: '{m.group(5)}'")
    else:
        print(f"No Match: '{l}'")
