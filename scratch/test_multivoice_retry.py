import asyncio
import os
import sys
import re
from dotenv import load_dotenv

# Ensure UTF-8 output
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass

# Add workspace directory to path
sys.path.append(os.path.abspath("."))

from services.tts_service import TTSService

async def test():
    load_dotenv(override=True)
    tts_service = TTSService()
    
    text = """진우: (헛웃음 치며) 타격감이 완전 제로야. 세상 평온해 보이는데?
수아: (어리둥절하며) 방금 하이에나 하품한 거 봤어?
진우: (기막혀하며) 호랑
태현: (긴장하며) 지금 엄청난 상황이 벌어지기 직전입니다.
민석: (숨을 죽이며) 네, 호랑이와 하이에나가 정면으로 마주쳤습니다.
태현: (급하게) 야생의 최강자 호랑이입니다.
민석: (진지하게) 그리고 아프리카"""

    voice_map = {
        "진우": "FGY2WhTYpPnrIDTdsKH5", # Laura
        "수아": "EXAVITQu4vr4xnSDxMaL", # Sarah
        "태현": "IKne3meq5aSn9XLyUdCD", # Charlie
        "민석": "CwhRBWXzGAHq8TQ4Fs17"  # Roger
    }
    default_voice = "bIHbv24MWmeRgasZH58o" # Will
    
    # 1. Parse segments
    segments = []
    lines = text.split('\n')
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
                segments.append({"speaker": current_speaker, "text": "\n".join(current_chunk)})
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
        segments.append({"speaker": current_speaker, "text": "\n".join(current_chunk)})
        
    print(f"Parsed {len(segments)} segments.")
    
    # 2. Concurrency Semaphore (set to 3, same as main.py)
    semaphore = asyncio.Semaphore(3)
    
    async def process_segment(idx, segment):
        async with semaphore:
            speaker = segment["speaker"]
            seg_text = segment["text"]
            target_voice = voice_map.get(speaker, default_voice)
            
            seg_filename = f"test_retry_seg_{idx:03d}.mp3"
            seg_path = os.path.join("output", seg_filename)
            
            print(f"--> Starting segment {idx} (Speaker: {speaker}, Text: '{seg_text[:20]}...')")
            try:
                result = await tts_service.generate_elevenlabs(
                    text=seg_text,
                    voice_id=target_voice,
                    filename=seg_filename,
                    voice_settings={"stability": 0.5, "similarity_boost": 0.75, "style": 0.45}
                )
                print(f"<-- Finished segment {idx} successfully. Path: {result.get('audio_path')}")
                return result.get('audio_path')
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"❌ Segment {idx} failed: {e}")
                return None

    tasks = [process_segment(i, s) for i, s in enumerate(segments)]
    results = await asyncio.gather(*tasks)
    
    print("\nGeneration Summary:")
    for i, res in enumerate(results):
        print(f"Segment {i}: {'SUCCESS' if res else 'FAILED'}")

if __name__ == "__main__":
    asyncio.run(test())
