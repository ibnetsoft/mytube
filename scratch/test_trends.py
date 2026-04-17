
import asyncio
import os
import sys
from services.gemini_service import GeminiService
from services.auth_service import auth_service
from config import config

async def test_trends():
    print("Verifying license to load API keys...")
    # Manually trigger license verification to load keys into Config
    if not auth_service.verify_license():
        print("License verification failed. Using local .env if available.")
    
    # Debug: Check if key is loaded
    if not config.GEMINI_API_KEY:
        print("GEMINI_API_KEY is still empty!")
        # Try to load from .env manually for this test if needed
        from dotenv import load_dotenv
        load_dotenv()
        if os.getenv("GEMINI_API_KEY"):
            config.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
            print("Loaded key from .env")

    service = GeminiService()
    print(f"Testing generate_trending_keywords(ko, now, all) using key: {config.GEMINI_API_KEY[:5]}...")
    try:
        keywords = await service.generate_trending_keywords("ko", "now", "all")
        print(f"Result count: {len(keywords)}")
        if keywords:
            for i, k in enumerate(keywords[:5]):
                print(f"{i+1}. {k.get('keyword')} ({k.get('translation')}) - Vol: {k.get('volume')}")
        else:
            print("Empty result. Check gemini_service.py logic.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_trends())
