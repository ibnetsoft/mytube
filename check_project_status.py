
import database as db
import json

project_id = 70
project = db.get_project(project_id)
settings = db.get_project_settings(project_id)
print(f"Project Name: {project['name']}")
print(f"Project Status: {project['status']}")
print(f"Updated At: {project['updated_at']}")
print(f"Settings Status: {settings.get('status', 'N/A')}")
print(f"Video Path: {settings.get('video_path', 'N/A')}")
