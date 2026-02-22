import sqlite3
import json

def go():
    conn = sqlite3.connect('data/wingsai.db')
    c = conn.cursor()
    c.row_factory = sqlite3.Row
    for r in c.execute('SELECT project_id, scene_number, video_url, image_url FROM image_prompts ORDER BY id DESC LIMIT 5').fetchall():
        print(dict(r))

    print("\nProject 78 settings:")
    for r in c.execute("SELECT project_settings FROM projects WHERE id=78").fetchall():
        settings = json.loads(r['project_settings'])
        print("S1 motion:", settings.get('scene_1_motion'), "wan:", settings.get('scene_1_wan_image'))
        print("S2 motion:", settings.get('scene_2_motion'), "wan:", settings.get('scene_2_wan_image'))

if __name__ == '__main__':
    go()
