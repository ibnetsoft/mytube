import sqlite3
import os

db_path = os.path.join("data", "wingsai.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE image_prompts ADD COLUMN flow_prompt TEXT")
    print("Added flow_prompt column.")
except Exception as e:
    print(f"flow_prompt column may already exist: {e}")

try:
    cursor.execute("ALTER TABLE image_prompts ADD COLUMN scene_type TEXT")
    print("Added scene_type column.")
except Exception as e:
    print(f"scene_type column may already exist: {e}")

conn.commit()
conn.close()
