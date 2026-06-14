import asyncio
import os
import sys
from dotenv import load_dotenv

# Add workspace directory to path
sys.path.append(os.path.abspath("."))

from services.tts_service import tts_service

async def test():
    # Load env
    load_dotenv(override=True)
    print("API Key:", os.getenv("ELEVENLABS_API_KEY")[:10] + "...")
    
    text = "시어머니 (슬프게): 아아...모르겠다. 안되고 있는듯.. 이제는 한숨도 안쉬는데.. 다시 체크해봐"
    voice_id = "5n5gqmaQi9Ewevrz7bOS" # Sian custom voice ID
    
    # Let's test with stability=0.35
    print("\n--- TEST 1: stability=0.35 ---")
    res1 = await tts_service.generate_elevenlabs(
        text=text,
        voice_id=voice_id,
        filename="test_stability_0_35.mp3",
        voice_settings={"stability": 0.35, "similarity_boost": 0.75, "style": 0.45}
    )
    print("Result:", res1)
    
    # Let's test with stability=0.0
    print("\n--- TEST 2: stability=0.0 ---")
    res2 = await tts_service.generate_elevenlabs(
        text=text,
        voice_id=voice_id,
        filename="test_stability_0_0.mp3",
        voice_settings={"stability": 0.0, "similarity_boost": 0.75, "style": 0.45}
    )
    print("Result:", res2)

if __name__ == "__main__":
    asyncio.run(test())
