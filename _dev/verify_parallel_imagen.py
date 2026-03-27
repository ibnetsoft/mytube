
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from services.gemini_service import gemini_service
from config import config

async def test_parallel_images():
    print("Testing parallel image generation...")
    prompts = [
        {"scene_number": 1, "prompt_en": "A beautiful sunset over the ocean, cinematic"},
        {"scene_number": 2, "prompt_en": "A busy city street at night, photorealistic"},
        {"scene_number": 3, "prompt_en": "A futuristic space station, digital art"}
    ]
    
    async def process_prompt(p):
        print(f"Starting Scene {p['scene_number']}...")
        images = await gemini_service.generate_image(p['prompt_en'], aspect_ratio="16:9")
        if images:
            print(f"✅ Scene {p['scene_number']} success!")
            return True
        print(f"❌ Scene {p['scene_number']} failed.")
        return False

    tasks = [process_prompt(p) for p in prompts]
    results = await asyncio.gather(*tasks)
    print(f"Final results: {results}")

if __name__ == "__main__":
    asyncio.run(test_parallel_images())
