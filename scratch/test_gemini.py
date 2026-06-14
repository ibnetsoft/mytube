import os
import asyncio
from dotenv import load_dotenv
from services.gemini_service import gemini_service

load_dotenv()

async def main():
    print("Gemini API Key:", os.getenv("GEMINI_API_KEY"))
    try:
        res = await gemini_service.generate_text("Hello, how are you?")
        print("Success response:", res)
    except Exception as e:
        print("Failed to call Gemini:", e)
        import traceback
        traceback.print_exc()

asyncio.run(main())
