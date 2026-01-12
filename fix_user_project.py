import database as db
import os
from services.pexels_service import pexels_service

# Setup
db.DB_PATH = db.Path(os.getcwd()) / "data" / "wingsai.db"

def force_loop_mode(project_id=10, query="mountain nature"):
    print(f"Forcing Loop Mode for Project {project_id}...")
    
    # 1. Search for a fallback video
    print(f"Searching Pexels for '{query}'...")
    result = pexels_service.search_videos(query, per_page=1)
    
    video_url = None
    if result.get("status") == "ok" and result.get("videos"):
        video_url = result["videos"][0]["url"]
        print(f"Found Video URL: {video_url}")
    else:
        # Fallback hardcoded if API fails
        video_url = "https://videos.pexels.com/video-files/854671/854671-hd_1920_1080_25fps.mp4"
        print(f"Using Fallback URL: {video_url}")

    # 2. Force Update DB
    db.update_project_setting(project_id, "background_video_url", video_url)
    print(f"✅ Forced background_video_url update for Project {project_id}")
    
    # Check result
    settings = db.get_project_settings(project_id)
    print(f"Current DB Value: {settings.get('background_video_url')}")

if __name__ == "__main__":
    force_loop_mode()
