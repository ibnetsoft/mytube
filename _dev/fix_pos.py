import sqlite3

try:
    conn = sqlite3.connect('projects.db')
    cur = conn.cursor()
    cur.execute("DELETE FROM project_settings WHERE key='subtitle_pos_y' OR key='subtitle_pos_x'")
    conn.commit()
    print("Positions fixed in projects.db")
except Exception as e:
    print(f"Error: {e}")
