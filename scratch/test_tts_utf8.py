import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure we use UTF-8 output even on Windows command line
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Add workspace directory to path
sys.path.append(os.path.abspath("."))

from services.tts_service import tts_service

async def test():
    load_dotenv(override=True)
    
    text = "(떨리는 목소리로) 평생을 바둥거리며 애를 써도 따뜻한 칭찬 한 번 들어본 적이 없었습니다."
    voice_id = "5n5gqmaQi9Ewevrz7bOS" # Sian custom voice ID
    
    print("\n=== GENERATING WITH MULTILINGUAL_V2 & STABILITY = 0.2 ===")
    res_low = await tts_service.generate_elevenlabs(
        text=text,
        voice_id=voice_id,
        filename="test_v2_stability_0_2.mp3",
        voice_settings={"stability": 0.20, "similarity_boost": 0.75, "style": 0.55}
    )
    print("Stability 0.2 duration:", res_low.get("duration"))
    
    print("\n=== GENERATING WITH MULTILINGUAL_V2 & STABILITY = 0.8 ===")
    res_high = await tts_service.generate_elevenlabs(
        text=text,
        voice_id=voice_id,
        filename="test_v2_stability_0_8.mp3",
        voice_settings={"stability": 0.80, "similarity_boost": 0.75, "style": 0.55}
    )
    print("Stability 0.8 duration:", res_high.get("duration"))

if __name__ == "__main__":
    asyncio.run(test())
