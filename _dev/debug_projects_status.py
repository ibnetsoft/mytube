import database as db
import os

db.DB_PATH = db.Path(os.getcwd()) / "data" / "wingsai.db"

def list_projects_video_settings():
    print("Listing all projects and their video settings...")
    projects = db.get_all_projects()
    
    found_any = False
    for p in projects:
        settings = db.get_project_settings(p['id'])
        bg_url = settings.get('background_video_url')
        video_path = settings.get('video_path')
        
        # Only print if relevant or recent
        print(f"ID: {p['id']}, Name: {p['name']}, BG_URL: {bg_url and bg_url[:50]}..., Video Path: {video_path}")
        
        if bg_url:
            found_any = True

    if not found_any:
        print("\n⚠️ No projects have background_video_url set (except potentially test ones).")

if __name__ == "__main__":
    list_projects_video_settings()
