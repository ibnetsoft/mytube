
import difflib
import re

def align_test(script_text, ai_text_list):
    script_tokens = script_text.split()
    # Normalize
    def normalize(s):
        return re.sub(r'[^\w]', '', s).lower()

    script_norm = [normalize(s) for s in script_tokens]
    ai_norm = [normalize(s) for s in ai_text_list]
    
    print(f"Script: {script_norm}")
    print(f"AI:     {ai_norm}")

    matcher = difflib.SequenceMatcher(None, script_norm, ai_norm)
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        print(f"{tag:7} script[{i1}:{i2}] ({script_tokens[i1:i2]}) -> ai[{j1}:{j2}] ({ai_text_list[j1:j2]})")

script = "설마 아직도 신맞고 안 하고"
ai_wrong = ["설마", "아직도", "신막구", "안", "하고"]

print("--- Test 1 ---")
align_test(script, ai_wrong)

script2 = "설마 아직도 신맞고 안 하고?! 딱 60초만 투자하면"
ai_wrong2 = ["설마", "아직도", "신막구", "안", "하고", "딱", "60초만", "투자하면"]
print("\n--- Test 2 ---")
align_test(script2, ai_wrong2)
