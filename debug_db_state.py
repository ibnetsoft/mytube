import database as db
import os

db.init_db()

# Get latest project
projects = db.get_recent_projects(1)
if not projects:
    print("No projects found.")
    exit()

project = projects[0]
# Need to find ID - get_recent_projects returns dict with name/topic but maybe not ID if row factory used differently? 
# Let's check get_all_projects to be sure or use name to find ID.
# Actually get_recent_projects returns dict(row). Let's see what keys it has.
all_projects = db.get_all_projects()
if not all_projects:
    print("No projects.")
    exit()

# Assuming the last one is the target
target_project = all_projects[0] # Updated_at DESC usually means first one is recent
pid = target_project['id']

print(f"Checking Project ID: {pid} ({target_project['name']})")

# Check TTS
tts = db.get_tts(pid)
print(f"TTS Data: {tts}")
if tts:
    print(f"Audio Path exists: {os.path.exists(tts['audio_path'])}")

# Check Script
script = db.get_script(pid)
print(f"Script Table: {script}")

# Check Settings
settings = db.get_project_settings(pid)
print(f"Settings Script: {settings.get('script') if settings else 'None'}")
