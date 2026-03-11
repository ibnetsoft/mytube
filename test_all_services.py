import asyncio
import os
import sys
from dotenv import load_dotenv

# Add current dir to sys.path
sys.path.append(os.getcwd())

from services.replicate_service import replicate_service
from services.akool_service import akool_service
from services.gemini_service import gemini_service

load_dotenv()

async def test_replicate():
    print("--- Testing Replicate ---")
    try:
        res = await replicate_service.generate_image(prompt="a cute cat", aspect_ratio="1:1")
        if res:
            print(f"✅ Replicate Success: {len(res[0])} bytes")
        else:
            print("❌ Replicate Failed (returned None)")
    except Exception as e:
        print(f"❌ Replicate Exception: {e}")

async def test_gemini():
    print("\n--- Testing Gemini ---")
    try:
        res = await gemini_service.generate_image(prompt="a cute cat", aspect_ratio="1:1")
        if res:
            print(f"✅ Gemini Success: {len(res[0])} bytes")
        else:
            print("❌ Gemini Failed (returned None)")
    except Exception as e:
        print(f"❌ Gemini Exception: {e}")

async def test_akool():
    print("\n--- Testing AKOOL ---")
    try:
        res = await akool_service.generate_image(prompt="a cute cat", aspect_ratio="1:1")
        if res:
            print(f"✅ AKOOL Success: {len(res[0])} bytes")
        else:
            print("❌ AKOOL Failed (returned None)")
    except Exception as e:
        print(f"❌ AKOOL Exception: {e}")

async def main():
    await test_replicate()
    await test_gemini()
    await test_akool()

if __name__ == "__main__":
    asyncio.run(main())
