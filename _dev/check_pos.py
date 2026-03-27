import sys
import os
sys.path.append(os.path.dirname(__file__))
import database as db

try:
    y = db.get_project_setting(120, 'subtitle_pos_y')
    print(f"y: '{y}'")
except Exception as e:
    print(f"Error: {e}")
