
import database as db

try:
    s = db.get_project_settings(15)
    print(f"Project 15 Settings:")
    print(f"Subtitle Path: {s.get('subtitle_path')}")
    print(f"Audio Path: {s.get('audio_path')}")
    print(f"Timeline Images: {s.get('timeline_images_path')}")
except Exception as e:
    print(f"Error: {e}")
