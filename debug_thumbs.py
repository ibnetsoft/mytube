import database as db
import os
from config import config

print("--- RECENT PROJECTS THUMBNAIL STATUS ---")
projects = db.get_recent_projects(20)
for p in projects:
    pid = p['id']
    name = p['name']
    settings = db.get_project_settings(pid) or {}
    thumb = settings.get('thumbnail_url', 'MISSING')
    status = p.get('status', 'unknown')
    print(f"[{pid}] {name} | Status: {status} | Thumb: {thumb}")
