import asyncio
import os
import sys
from services.gemini_service import gemini_service
from config import config

async def test_imagen():
    print("--- TESTING IMAGEN GENERATION ---")
    prompt = "A futuristic city at night, neon lights, 8k, highly detailed"
    try:
        images = await gemini_service.generate_image(prompt)
        if images:
            print(f"✅ Success! Generated {len(images)} images.")
            save_path = "test_imagen.png"
            with open(save_path, "wb") as f:
                f.write(images[0])
            print(f"Saved to {save_path}")
        else:
            print("❌ No images returned (Empty list)")
    except Exception as e:
        print(f"❌ Error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(test_imagen())
