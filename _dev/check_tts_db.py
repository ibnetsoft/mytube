import database as db
import os

def check_tts():
    db.init_db()
    conn = db.get_db()
    cursor = conn.cursor()
    
    print("--- Checking Projects ---")
    projects = db.get_all_projects()
    if not projects:
        print("No projects found.")
        return

    latest_project = projects[0]
    pid = latest_project['id']
    print(f"Latest Project ID: {pid}, Name: {latest_project['name']}")
    
    print("\n--- Checking TTS Data ---")
    tts = db.get_tts(pid)
    if tts:
        print(f"TTS Data Found: {tts}")
        print(f"Audio Path: {tts.get('audio_path')}")
        
        # Verify Path existence
        if tts.get('audio_path'):
            exists = os.path.exists(tts['audio_path'])
            print(f"File Exists on Disk: {exists}")
    else:
        print("No TTS data found for this project.")

    print("\n--- Checking Image Prompts ---")
    prompts = db.get_image_prompts(pid)
    print(f"Image Prompts Count: {len(prompts)}")
    if prompts:
        print(f"Sample Prompt 1 Image URL: {prompts[0].get('image_url')}")

if __name__ == "__main__":
    check_tts()
