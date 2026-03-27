
import asyncio
import os
from dotenv import load_dotenv
from services.tts_service import tts_service

async def main():
    load_dotenv()
    print("Testing get_elevenlabs_voices...")
    try:
        voices = await tts_service.get_elevenlabs_voices()
        print(f"Voices found: {len(voices)}")
        if voices:
            print(f"First voice: {voices[0]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
