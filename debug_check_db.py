import database as db
import os
import json

# DB Path setup for script
db.DB_PATH = db.Path(os.getcwd()) / "data" / "wingsai.db"

def check_latest_project_settings():
    print("Checking Latest Project Settings...")
    
    # Get latest project
    projects = db.get_all_projects()
    if not projects:
        print("No projects found.")
        return

    # Sort by ID desc
    latest_project = sorted(projects, key=lambda x: x['id'], reverse=True)[0]
    pid = latest_project['id']
    print(f"Latest Project ID: {pid}, Name: {latest_project['name']}")
    
    # Get Settings
    settings = db.get_project_settings(pid)
    
    print("\n[Project Settings]")
    if settings:
        bg_url = settings.get('background_video_url')
        print(f"background_video_url: {repr(bg_url)}")
        
        # Check other keys to ensure we are looking at the right dict
        print(f"video_path: {settings.get('video_path')}")
    else:
        print("Settings is None/Empty")

if __name__ == "__main__":
    check_latest_project_settings()
