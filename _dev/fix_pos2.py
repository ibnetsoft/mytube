import sys
import os
sys.path.append(os.path.dirname(__file__))

import database as db

project_id = 120
try:
    db.update_project_setting(project_id, 'subtitle_pos_y', '')
    db.update_project_setting(project_id, 'subtitle_pos_x', '')
    print("Clearing positions using database.py")
except Exception as e:
    print(f"Error: {e}")
