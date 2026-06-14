"""
멀티보이스 생성 시 특정 세그먼트가 누락되는 버그 진단 스크립트
"""
import asyncio
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()

from services.tts_service import tts_service

# 실제 문제 텍스트 (스크린샷에서 추출)
TEST_TEXT = """진우: (헛웃음 치며) 타격감이 완전 제로야. 세상 평온해 보이는데?
수아: (어리둥둥하며) 발길 하이에나가 히클한 거 봤어?
진우: (기막하다) 호칭
태현: (긴장하며) 지금 엄청난 상황이 벌어지기 직전입니다.
민석: (돌봄 죽이며) 네, 호랑이와 하이에나가 정면으로 마주쳤습니다.
태현: (급급하게) 야생의 최강자 호환입니다.
민석: (진지하게) 그리고 아프리카"""

# 음성 매핑 (스크린샷 기준)
VOICE_MAP = {
    "민석": "CwhRBWXzGAHq8TQ4Fs17",  # Roger
    "수아": "EXAVITQu4vr4xnSDxMaL",  # Sarah
    "진우": "FGY2WhTYpPnrIDTdsKH5",  # Laura
    "태현": "IKne3meq5aSn9XLyUdCD",  # Charlie
}

DEFAULT_VOICE = "CwhRBWXzGAHq8TQ4Fs17"

async def main():
    print("=== 멀티보이스 세그먼트 파싱 테스트 ===\n")
    
    # 1. 파싱 로직 재현
    segments = []
    lines = TEST_TEXT.split('\n')
    
    pattern = re.compile(
        r'^\s*(?:'
        r'[\*\_\[\(]*([^\s:\[\(\*\_]+)[\*\_\]\)]*[ \t]*(\([^)]*\))?[ \t]*[:：][ \t]*(.*)'
        r'|'
        r'([^\s:\[\(\*\_]+)[ \t]*[\)）\]][ \t]*(.*)'
        r')$'
    )
    
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
    
    print(f"파싱된 세그먼트 수: {len(segments)}")
    for i, seg in enumerate(segments):
        voice_id = VOICE_MAP.get(seg['speaker'], DEFAULT_VOICE)
        print(f"  [{i}] Speaker: '{seg['speaker']}' → Voice: {voice_id}")
        print(f"      Text: '{seg['text']}'")
    
    print("\n=== 각 세그먼트 순차 생성 테스트 ===\n")
    
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
    os.makedirs(output_dir, exist_ok=True)
    
    el_voice_settings = {
        "stability": 0.5,
        "similarity_boost": 0.75,
        "style": 0.45,
        "speed": 1.0
    }
    
    results = []
    for i, seg in enumerate(segments):
        voice_id = VOICE_MAP.get(seg['speaker'], DEFAULT_VOICE)
        seg_filename = f"test_debug_seg_{i:03d}.mp3"
        seg_path = os.path.join(output_dir, seg_filename)
        
        print(f"[{i}] 생성 중: '{seg['speaker']}' → '{seg['text'][:40]}...' (Voice: {voice_id})")
        
        try:
            result = await tts_service.generate_elevenlabs(
                seg['text'], voice_id, seg_path, voice_settings=el_voice_settings
            )
            if result and result.get('audio_path'):
                actual_path = result['audio_path']
                file_exists = os.path.exists(actual_path)
                file_size = os.path.getsize(actual_path) if file_exists else 0
                print(f"  ✅ 성공: {actual_path}")
                print(f"     파일 존재: {file_exists}, 크기: {file_size} bytes, 길이: {result.get('duration', 0):.2f}s")
                results.append(actual_path)
            else:
                print(f"  ❌ 실패: result={result}")
                results.append(None)
        except Exception as e:
            print(f"  ❌ 예외: {e}")
            results.append(None)
        
        await asyncio.sleep(1.0)  # Rate limit 방지
    
    print(f"\n=== 결과 요약 ===")
    print(f"총 {len(segments)}개 세그먼트 중 {sum(1 for r in results if r)}개 성공")
    for i, (seg, res) in enumerate(zip(segments, results)):
        status = "✅" if res else "❌"
        print(f"  {status} [{i}] {seg['speaker']}: {seg['text'][:30]}...")

if __name__ == "__main__":
    asyncio.run(main())
