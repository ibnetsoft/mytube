import re
import sys

# Ensure UTF-8 output
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Regex from main.py
pattern = re.compile(
    r'^\s*(?:'
    r'[\*\_\[\(]*([^\s:\[\(\*\_]+)[\*\_\]\)]*[ \t]*(\([^)]*\))?[ \t]*[:：][ \t]*(.*)'
    r'|'
    r'([^\s:\[\(\*\_]+)[ \t]*[\)）\]][ \t]*(.*)'
    r')$'
)

text = """진우: (헛웃음 치며) 타격감이 완전 제로야. 세상 평온해 보이는데?
수아: (어리둥절하며) 방금 하이에나 하품한 거 봤어?
진우: (기막혀하며) 호랑
태현: (긴장하며) 지금 엄청난 상황이 벌어지기 직전입니다.
민석: (숨을 죽이며) 네, 호랑이와 하이에나가 정면으로 마주쳤습니다.
태현: (급하게) 야생의 최강자 호랑이입니다.
민석: (진지하게) 그리고 아프리카"""

segments = []
lines = text.split('\n')
current_chunk = []
current_speaker = None

for line in lines:
    match = pattern.match(line.strip())
    if match:
        if current_chunk:
            segments.append({
                "speaker": current_speaker,
                "text": "\n".join(current_chunk)
            })
        
        if match.group(1) is not None:
            current_speaker = match.group(1).strip()
            emotion = match.group(2) or ""
            content = match.group(3).strip()
        else:
            current_speaker = match.group(4).strip()
            emotion = ""
            content = match.group(5).strip()

        current_speaker = re.sub(r'[\*\_\#\[\]\(\)]', '', current_speaker).strip()
        
        if emotion:
            content = f"{emotion} {content}"
        current_chunk = [content]
    else:
        current_chunk.append(line.strip())

if current_chunk:
    segments.append({
        "speaker": current_speaker,
        "text": "\n".join(current_chunk)
    })

print(f"Parsed segments length: {len(segments)}")
for i, s in enumerate(segments):
    print(f"Segment {i}: Speaker='{s['speaker']}', Text='{s['text']}'")
