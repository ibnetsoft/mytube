
import database as db

try:
    # Force set to shorts
    db.update_project_setting(1, 'app_mode', 'shorts')
    print("Forced app_mode to 'shorts'")
    
    s = db.get_project_settings(1)
    print(f"New Mode: {s.get('app_mode')}")
except Exception as e:
    print(f"Error: {e}")
