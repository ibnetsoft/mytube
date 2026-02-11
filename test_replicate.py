import asyncio
import os
from services.replicate_service import replicate_service
from config import config

async def test_replicate():
    print("--- TESTING REPLICATE VIDEO GEN ---")
    if not replicate_service.api_key:
        print("❌ Replicate API Token is missing!")
        return

    # Use the test image we generated earlier
    image_path = "test_imagen.png"
    if not os.path.exists(image_path):
        print("❌ test_imagen.png not found. Run test_imagen.py first.")
        return

    try:
        print("🎬 Starting video generation...")
        video_data = await replicate_service.generate_video_from_image(
            image_path, 
            prompt="Cinematic motion, high quality",
            duration=5.0,
            method="standard"
        )
        if video_data:
            print(f"✅ Success! Generated {len(video_data)} bytes.")
            with open("test_video.mp4", "wb") as f:
                f.write(video_data)
            print("Saved to test_video.mp4")
        else:
            print("❌ No video data returned.")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_replicate())
