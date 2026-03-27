import database as db
import os

# DB Path setup for script
db.DB_PATH = db.Path(os.getcwd()) / "data" / "wingsai.db"

def test_loop_mode_persistence():
    print("Testing Loop Mode Persistence...")
    
    # 1. Create Project
    pid = db.create_project("Loop Mode Test")
    print(f"Project Created: {pid}")
    
    # 2. Update Settings (Simulate selecting a background video)
    bg_url = "https://images.pexels.com/videos/12345/free-video.mp4"
    db.update_project_setting(pid, "background_video_url", bg_url)
    print(f"Updated setting: background_video_url = {bg_url}")
    
    # 3. Fetch Full Data
    data = db.get_project_full_data(pid)
    settings = data.get('settings', {})
    
    # 4. Verify
    saved_url = settings.get('background_video_url')
    print(f"Saved URL in DB: {saved_url}")
    
    if saved_url == bg_url:
        print("✅ SUCCESS: Background Video URL is persisted and retrieved.")
    else:
        print("❌ FAIL: Background Video URL is NOT found.")

if __name__ == "__main__":
    test_loop_mode_persistence()
