
import database as db

try:
    s = db.get_project_settings(1)
    print(f"Project 1 Settings: ID={s.get('id')}")
    print(f"APP_MODE: {s.get('app_mode')}")
    print(f"Sub Font: {s.get('subtitle_font')}")
except Exception as e:
    print(f"Error: {e}")
