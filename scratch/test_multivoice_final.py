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

from app.models.media import TTSRequest
import main

async def test():
    load_dotenv(override=True)
    
    # Test 1: Test with '이름) 대사' format (specifically '하게)') and standard colon formats
    # Also test with dict values in voice_map to ensure backend is robust
    voice_map = {
        "하게": {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella"},
        "진우": "21m00Tcm4TlvDq8ikWAM",
        "수아": "AZnzlk1XvdvUeBnXmlld"
    }
    
    text = (
        "하게) 헐. 뭐야 저게. 지금 둘러 있는 거 맞아?\n"
        "진우: (헛웃음 치며) 타격감이 완전 제로야. 세상 평온해 보이는데?\n"
        "수아: (어리둥절하며) 방금 하이에나 하품한 거 봤어?"
    )
    
    # We will test generating a very short text to save EleventhLabs credits
    short_text = (
        "하게) 헐. 뭐야 저게.\n"
        "진우: 평온해 보이는데?\n"
        "수아: 하품한 거 봤어?"
    )
    
    req = TTSRequest(
        text=short_text,
        voice_id="21m00Tcm4TlvDq8ikWAM",
        provider="elevenlabs",
        multi_voice=True,
        voice_map=voice_map, # Contains dict value for '하게' and string for others
        stability=0.35,
        style=0.45
    )
    
    print("\n=== RUNNING FINAL BACKEND MULTI-VOICE GENERATION TEST ===")
    try:
        res = await main.tts_generate(req)
        print("Generation complete!")
        print("Response:", res)
    except Exception as e:
        print("Error during generation:", e)

if __name__ == "__main__":
    asyncio.run(test())
