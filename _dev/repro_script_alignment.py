
import difflib
import re
import unicodedata

def align_logic_repro():
    script_text = """ ** [서론 (5초)] **
(신맞고 BGM, 귓가에 익숙한 멜로디가 울려 퍼지며)

어? 잠깐! 지금 뭐하세요? 설마 아직도 신맞고 안 하고?! 딱 60초만 투자하면… 이야기가 달라집니다! 

 ** [본론 1 (20초): 신맞고, 왜 다시 해야 할까?] **
자, 묻겠습니다. 당신은 마지막으로 신맞고를 쳤을 때가 언제였나요? 기억도 안 난다고요? 바로 그거예요! 잊고 지냈던 그 짜릿함, 단순하지만 헤어나올 수 없는 그 마성의 게임성을 다시 느껴볼 시간입니다! 왜냐고요? 
"""
    
    # Simulate AI output (with errors and missing words)
    # "신막구" error, missing "쳤을 때가"
    ai_words_simulated = [
        {"word": "어", "start": 0.0, "end": 0.5},
        {"word": "잠깐", "start": 0.6, "end": 1.0},
        {"word": "지금", "start": 1.1, "end": 1.5},
        {"word": "뭐하세요", "start": 1.6, "end": 2.0},
        {"word": "설마", "start": 2.5, "end": 2.8},
        {"word": "아직도", "start": 2.9, "end": 3.2},
        {"word": "신막구", "start": 3.3, "end": 3.8}, # Error
        {"word": "안", "start": 3.9, "end": 4.1},
        {"word": "하고", "start": 4.2, "end": 4.5}, 
        {"word": "딱", "start": 5.0, "end": 5.3}, 
        {"word": "60초만", "start": 5.4, "end": 6.0},
        {"word": "투자하면", "start": 6.1, "end": 6.8},
        {"word": "이야기가", "start": 7.0, "end": 7.5},
        {"word": "달라집니다", "start": 7.6, "end": 8.0},
        
        # Next sentence
        {"word": "자", "start": 9.0, "end": 9.2},
        {"word": "묻겠습니다", "start": 9.3, "end": 9.8},
        {"word": "당신은", "start": 9.9, "end": 10.3},
        {"word": "마지막으로", "start": 10.4, "end": 10.9},
        {"word": "신막구를", "start": 11.0, "end": 11.5}, # Error
        # Missing "쳤을" "때가"
        {"word": "언제였나요", "start": 12.0, "end": 12.8}
    ]
    
    class WordObj:
        def __init__(self, w, s, e):
            self.word = w
            self.start = s
            self.end = e
            
    ai_words = [WordObj(x['word'], x['start'], x['end']) for x in ai_words_simulated]

    print("--- 1. Script Cleaning ---")
    clean_script = re.sub(r'\([^)]*\)|\[[^\]]*\]|\*\*.*?\*\*', '', script_text)
    script_tokens = clean_script.split()
    print(f"Clean Script Tokens (First 20): {script_tokens[:20]}")
    
    print("\n--- 2. Jamo Normalization ---")
    def normalize_jamo(s):
        s = re.sub(r'[^\w]', '', s).lower()
        return unicodedata.normalize('NFD', s)

    script_norm = [normalize_jamo(s) for s in script_tokens]
    ai_norm = [normalize_jamo(w.word) for w in ai_words]
    
    print(f"Script Norm example: {script_norm[5:10]}") # 신맞고 around here
    print(f"AI Norm example: {ai_norm[6]}") # 신막구

    print("\n--- 3. Matching ---")
    matcher = difflib.SequenceMatcher(None, script_norm, ai_norm)
    aligned_pre = []
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        print(f"{tag:7} script[{i1}:{i2}] {script_tokens[i1:i2]} -> ai[{j1}:{j2}] {[w.word for w in ai_words[j1:j2]]}")
        
        if tag == 'equal':
            for k in range(i2 - i1):
                aligned_pre.append({"word": script_tokens[i1+k], "type": "equal"})
        elif tag == 'replace':
             for k in range(i2 - i1):
                aligned_pre.append({"word": script_tokens[i1+k], "type": "replace"})
        elif tag == 'delete':
             for k in range(i2 - i1):
                aligned_pre.append({"word": script_tokens[i1+k], "type": "delete"})
                
    print(f"\nTotal Aligned Words: {len(aligned_pre)}")

if __name__ == "__main__":
    align_logic_repro()
