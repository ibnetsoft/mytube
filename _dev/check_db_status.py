import database as db
import json

projects = db.get_all_projects()
projects.sort(key=lambda x: x['id'], reverse=True)
for p in projects[:10]:
    pid = p['id']
    settings = db.get_project_settings(pid) or {}
    print(f"Project ID: {pid}, Name: {p.get('name')}, Status: {p.get('status')}")
    print(f"  All Video: {settings.get('all_video')}, Video Engine: {settings.get('video_engine')}")
    print(f"  App Mode: {settings.get('app_mode')}, Mode: {settings.get('mode')}")
    scripts = db.get_script(pid)
    print(f"  Has Script: {bool(scripts)}")
