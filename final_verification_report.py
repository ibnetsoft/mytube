
import sys
import os
import json

# Add current dir to path
sys.path.append(os.getcwd())

from services.video_service import video_service

def verify_final_output():
    # Use the REAL script text from log
    script_text = """어? 잠깐! 지금 뭐하세요? 설마 아직도 신맞고 안 하고?! 딱 60초만 투자하면… 이야기가 달라집니다! 

 자, 묻겠습니다. 당신은 마지막으로 신맞고를 쳤을 때가 언제였나요? 기억도 안 난다고요? 바로 그거예요! 잊고 지냈던 그 짜릿함, 단순하지만 헤어나올 수 없는 그 마성의 게임성을 다시 느껴볼 시간입니다! 왜냐고요? """
    
    # Mock AI words from the Real log
    # AI Words (First 20): [' 어?', ' 잠깐.', ' 지금', ' 뭐하세요?', ' 설마', ' 아직도', ' 신막구', ' 안', ' 하고', ' 딱', ' 60초만', ' 투자하면', ' 이야기가', ' 달라집니다.', ' 자,', ' 묶겠습니다.', ' 당신은', ' 마지막으로', ' 신막구를', ' 쳤을']
    class WordObj:
        def __init__(self, w, s, e):
            self.word = w
            self.start = s
            self.end = e
            
    ai_words = [
        WordObj("어?", 0.0, 0.5), WordObj("잠깐.", 0.6, 1.0), WordObj("지금", 1.1, 1.5), 
        WordObj("뭐하세요?", 1.6, 2.0), WordObj("설마", 2.1, 2.5), WordObj("아직도", 2.6, 3.0),
        WordObj("신막구", 3.1, 3.5), WordObj("안", 4.0, 4.3), WordObj("하고", 4.4, 5.0),
        WordObj("딱", 5.1, 5.5), WordObj("60초만", 5.6, 6.2), WordObj("투자하면", 6.3, 7.0),
        WordObj("이야기가", 7.1, 7.8), WordObj("달라집니다.", 7.9, 8.5), WordObj("자,", 9.0, 9.5),
        WordObj("묶겠습니다.", 9.6, 10.2), WordObj("당신은", 10.3, 11.0), WordObj("마지막으로", 11.1, 12.0),
        WordObj("신막구를", 12.1, 13.0), WordObj("쳤을", 13.1, 13.8)
    ]

    print("--- Running AI Sync Logic ---")
    # We bypass actual transcribe and call our logic
    aligned_words = video_service._align_script_with_timestamps(script_text, ai_words)
    
    # Now build subtitles manually to see what's in there
    # (Or just use the logic in generate_aligned_subtitles)
    
    print("\nMatched Word Examples:")
    for i in range(min(10, len(aligned_words))):
        print(f"[{i}] {aligned_words[i]['word']} ({aligned_words[i]['start']:.2f} - {aligned_words[i]['end']:.2f})")

    # Check for "신맞고"
    target = "신맞고"
    found = False
    for aw in aligned_words:
        if target in aw['word']:
            print(f"\nSUCCESS: Found '{target}' in aligned words: {aw}")
            found = True
            break
    
    if not found:
        print(f"\nFAILURE: Could not find '{target}' in aligned words.")

if __name__ == "__main__":
    verify_final_output()
