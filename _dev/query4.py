import sqlite3
import json

def go():
    conn = sqlite3.connect('data/wingsai.db')
    c = conn.cursor()
    c.row_factory = sqlite3.Row

    print("\nProject 78 settings:")
    row = c.execute("SELECT webtoon_scenes_json FROM project_settings WHERE project_id=78").fetchone()
    if row and row['webtoon_scenes_json']:
        scenes = json.loads(row['webtoon_scenes_json'])
        for i, s in enumerate(scenes):
            print(f"Scene {i+1}: motion={s.get('effect_override')}, wan={s.get('original_image_path', '')[-20:] if s.get('original_image_path') else 'None'}")

if __name__ == '__main__':
    go()
