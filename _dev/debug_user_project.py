import database as db
import os
import json

db.DB_PATH = db.Path(os.getcwd()) / "data" / "wingsai.db"

def check_user_project():
    print("Searching for project '동산'...")
    all_projects = db.get_all_projects()
    target = None
    for p in all_projects:
        if "동산" in p['name']:
            target = p
            break
    
    if target:
        print(f"Found Project: ID={target['id']}, Name={target['name']}")
        settings = db.get_project_settings(target['id'])
        print(f"Background Video URL: {settings.get('background_video_url')}")
    else:
        print("Project '동산' not found.")

if __name__ == "__main__":
    check_user_project()
