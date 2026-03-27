
import asyncio
import os
from services.gemini_service import GeminiService

async def test_service():
    service = GeminiService()
    print(f"Service initialized. API Key present: {bool(service.api_key)}")
    
    prompt = "A cute 3D robot waving hello"
    print(f"Generating image with prompt: {prompt}")
    
    try:
        images = await service.generate_image(prompt, num_images=1)
        if images:
            print("SUCCESS! Image generated.")
            print(f"Image size: {len(images[0])} bytes")
        else:
            print("FAILED. No images returned.")
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_service())
