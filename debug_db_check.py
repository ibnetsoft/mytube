
import database as db
import os
from config import config

# Initialize DB (if needed, but importing should likely be enough if it connects on import/call)

def check_latest_project():
    try:
        projects = db.get_projects_with_status()
        if not projects:
            print("No projects found.")
            return

        # Sort by ID desc (assuming recent is last)
        latest = sorted(projects, key=lambda x: x['id'], reverse=True)[0]
        pid = latest['id']
        print(f"Latest Project: ID {pid}, Name: {latest['name']}, Status: {latest['status']}")
        
        # Check assets
        images = db.get_image_prompts(pid)
        print(f"  - Images: {len(images)} found.")
        for i, img in enumerate(images[:3]):
             print(f"    [{i}] {img.get('image_url')}")
             
        tts = db.get_tts(pid)
        if tts:
             print(f"  - TTS: Found. Path: {tts.get('audio_path')}")
             if os.path.exists(tts.get('audio_path')):
                 print(f"    (File exists, size: {os.path.getsize(tts.get('audio_path'))} bytes)")
             else:
                 print(f"    (File MISSING)")
        else:
             print("  - TTS: Not found.")
             
        script = db.get_script(pid)
        if script:
            print(f"  - Script: Found ({len(script.get('full_script', ''))} chars)")
        else:
            print("  - Script: Not found.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_latest_project()
