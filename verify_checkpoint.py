
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

import database as db
from services.autopilot_service import autopilot_service

async def test_checkpoint_resume():
    print("Testing AutoPilot Checkpoint System...")
    
    # 1. Create a dummy project
    project_id = db.create_project(name="Test Resume Project", topic="resumption")
    
    # 2. Simulate "analyzed" state with some data
    db.save_analysis(project_id, {"id": "test_vid"}, {"summary": "test analysis"})
    db.update_project(project_id, status="analyzed")
    
    # 3. Simulate "scripted" state
    script = "This is a test script for resumption. It should be long enough."
    db.save_script(project_id, script, len(script), 10)
    db.update_project(project_id, status="scripted")
    
    # 4. Mock Asset Generation partial progress
    # We'll mock gemini_service and tts_service to see what gets called
    from services.gemini_service import gemini_service
    from services.tts_service import tts_service
    
    # Pre-populate 1 image prompt with a "existing" URL
    dummy_prompts = [{"scene": "Scene 1", "prompt_ko": "테스트 1", "prompt_en": "Test 1"}]
    db.save_image_prompts(project_id, dummy_prompts)
    db.update_image_prompt_url(project_id, 1, "/output/existing_image.png")
    
    # Create a dummy file to simulate existence
    os.makedirs("output", exist_ok=True)
    with open("output/existing_image.png", "w") as f:
        f.write("dummy image data")

    original_gen_image = gemini_service.generate_image
    original_gen_tts = tts_service.generate_google_cloud
    
    image_gen_count = 0
    async def mock_gen_image(prompt, **kwargs):
        nonlocal image_gen_count
        image_gen_count += 1
        print(f"MOCK: Generating image for {prompt}")
        return [b"fake_image_data"]

    tts_gen_count = 0
    async def mock_gen_tts(text, **kwargs):
        nonlocal tts_gen_count
        tts_gen_count += 1
        print(f"MOCK: Generating TTS for {text[:20]}...")
        fpath = os.path.join("output", kwargs.get("filename", "test.mp3"))
        with open(fpath, "wb") as f:
            f.write(b"fake_audio_data")
        return fpath

    gemini_service.generate_image = mock_gen_image
    tts_service.generate_google_cloud = mock_gen_tts
    
    # Mock video service to avoid actual rendering
    from services.video_service import video_service
    video_service.create_slideshow = lambda **kwargs: "mock_video.mp4"
    video_service.generate_aligned_subtitles = lambda *args: []

    print(f"Created project {project_id} with status 'scripted' and 1 existing image.")
    
    # Run workflow
    await autopilot_service.run_workflow(keyword="resumption", project_id=project_id)
    
    # Check if we skipped the existing image
    # Note: If we had only 1 prompt and it was skipped, image_gen_count should be 0.
    # Actually, the refactored code generates 50 prompts if none exist. 
    # Here we provided 1 manually.
    print(f"Verification Results:")
    print(f"- Image generation called {image_gen_count} times (should be 0 for Scene 1)")
    
    # Clean up dummy file
    if os.path.exists("output/existing_image.png"):
        os.remove("output/existing_image.png")

if __name__ == "__main__":
    asyncio.run(test_checkpoint_resume())
