import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure UTF-8 output
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Add workspace directory to path
sys.path.append(os.path.abspath("."))

from services.tts_service import TTSService

async def test():
    load_dotenv(override=True)
    service = TTSService()
    
    # Let's test generating both lines with the actual TTSService
    # Voice IDs from our Elevenlabs accounts:
    laura = "FGY2WhTYpPnrIDTdsKH5"
    roger = "CwhRBWXzGAHq8TQ4Fs17"
    
    text1 = "(헛웃음 치며) 타격감이 완전 제로야. 세상 평온해 보이는데?"
    text2 = "(진지하게) 그리고 아프리카"
    
    print("\n--- Generating Line 1 with TTSService ---")
    res1 = await service.generate_elevenlabs(
        text=text1,
        voice_id=laura,
        filename="test_actual_line1.mp3",
        voice_settings={"stability": 0.0, "similarity_boost": 0.75, "style": 1.0}
    )
    print("Line 1 result:", res1)
    
    print("\n--- Generating Line 2 with TTSService ---")
    res2 = await service.generate_elevenlabs(
        text=text2,
        voice_id=roger,
        filename="test_actual_line2.mp3",
        voice_settings={"stability": 0.0, "similarity_boost": 0.75, "style": 1.0}
    )
    print("Line 2 result:", res2)

if __name__ == "__main__":
    asyncio.run(test())
