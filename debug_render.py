
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.video_service import video_service
from config import config

# Hardcoded paths based on previous file listing
project_dir = os.path.join(config.OUTPUT_DIR, "삼국지_20251219")
images = [
    os.path.join(project_dir, "p2_s1_1766123830.png"),
    os.path.join(project_dir, "p2_s2_1766123898.png"),
    os.path.join(project_dir, "p2_s3_1766123910.png"),
    os.path.join(project_dir, "p2_s4_1766123919.png"),
    os.path.join(project_dir, "p2_s5_1766123929.png")
]
audio_path = os.path.join(project_dir, "tts_20251219_145910.wav")

output_filename = os.path.join(project_dir, "debug_output.mp4")

print("Starting manually triggered render...")
print(f"Images: {len(images)}")
print(f"Audio: {audio_path}")
print(f"Output: {output_filename}")

try:
    final_path = video_service.create_slideshow(
        images=images,
        audio_path=audio_path,
        output_filename=output_filename,
        duration_per_image=5.0
    )
    print(f"Success! Video created at: {final_path}")
except Exception as e:
    print(f"Render failed: {e}")
    import traceback
    traceback.print_exc()
