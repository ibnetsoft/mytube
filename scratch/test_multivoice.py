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
from app.models.media import TTSRequest
import main

async def test():
    load_dotenv(override=True)
    
    # Let's mock a multi-voice request
    # Voice 1: Sian custom voice (5n5gqmaQi9Ewevrz7bOS)
    # Voice 2: ElevenLabs default voice (e.g. 4JJwo477JUAx3HV0T7n7 or 21m00Tcm4TlvDq8ikWAM)
    voice_map = {
        "시어머니": "5n5gqmaQi9Ewevrz7bOS",
        "며느리": "21m00Tcm4TlvDq8ikWAM"
    }
    
    text = (
        "시어머니 (슬프게): 평생을 애써도 칭찬 한 번 못 들었다.\n"
        "며느리 (차분하게): 어머니, 제가 항상 감사해하고 있어요."
    )
    
    req = TTSRequest(
        text=text,
        voice_id="21m00Tcm4TlvDq8ikWAM",
        provider="elevenlabs",
        multi_voice=True,
        voice_map=voice_map,
        stability=0.35,
        style=0.45
    )
    
    print("\n=== RUNNING BACKEND MULTI-VOICE GENERATION ===")
    res = await main.tts_generate(req)
    print("Generation complete!")
    print("Response:", res)

if __name__ == "__main__":
    asyncio.run(test())
