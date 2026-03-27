
import os
import sys
from datetime import datetime

# Setup paths to import services
sys.path.append(os.getcwd())

from services.video_service import video_service
from moviepy.editor import AudioFileClip

def test_render():
    project_id = 5
    print(f"[{datetime.now()}] Starting isolated render test for Project {project_id}")
    
    # Paths based on previous listing
    base_dir = r"c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기"
    output_dir = os.path.join(base_dir, "output", "고스톱_20251227")
    
    images = [
        os.path.join(output_dir, "p5_s1_1766823644.png"),
        os.path.join(output_dir, "p5_s2_1766823655.png"),
        os.path.join(output_dir, "p5_s3_1766823665.png"),
        os.path.join(output_dir, "p5_s4_1766823675.png"),
        os.path.join(output_dir, "p5_s5_1766823685.png"),
        os.path.join(output_dir, "p5_s6_1766823696.png"),
        os.path.join(output_dir, "p5_s7_1766823706.png"),
        os.path.join(output_dir, "p5_s8_1766823718.png"),
    ]
    
    audio_path = os.path.join(output_dir, "tts_20251227_173617.mp3")
    
    # Validation
    for img in images:
        if not os.path.exists(img):
            print(f"Missing image: {img}")
            return
            
    if not os.path.exists(audio_path):
        print(f"Missing audio: {audio_path}")
        return
        
    print("All assets found.")
    
    # Calculate duration
    try:
        audio_clip = AudioFileClip(audio_path)
        audio_duration = audio_clip.duration
        audio_clip.close()
        print(f"Audio Duration: {audio_duration}s")
    except Exception as e:
        print(f"Error reading audio: {e}")
        return

    duration_per_image = audio_duration / len(images)
    print(f"Duration per image: {duration_per_image}s")
    
    output_filename = os.path.join(output_dir, "test_render_isolated.mp4")
    
    try:
        print("Calling video_service.create_slideshow...")
        video_path = video_service.create_slideshow(
            images=images,
            audio_path=audio_path,
            output_filename=output_filename,
            duration_per_image=duration_per_image,
            title_text="Test Render Project 5"
        )
        print(f"Render success: {video_path}")
    except Exception as e:
        print("Render Exception:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_render()
