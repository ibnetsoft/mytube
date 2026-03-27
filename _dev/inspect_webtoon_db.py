import sqlite3
import json
import os

def check_db():
    db_path = os.path.join('data', 'wingsai.db')
    if not os.path.exists(db_path):
        print(f"DB not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get the latest project
    cursor.execute("SELECT id, name, topic FROM projects ORDER BY id DESC LIMIT 5")
    projects = cursor.fetchall()
    
    print("--- LATEST PROJECTS ---")
    for p in projects:
        print(f"ID: {p['id']}, Name: {p['name']}, Topic: {p['topic']}")
    
    if not projects:
        return

    target_id = projects[0]['id']
    print(f"\n--- INSPECTING PROJECT ID: {target_id} ---")

    # Check Project Settings
    cursor.execute("SELECT voice_mapping_json, webtoon_scenes_json FROM project_settings WHERE project_id = ?", (target_id,))
    s = cursor.fetchone()
    
    if s:
        print("\n[Voice Mapping JSON]:")
        print(s['voice_mapping_json'])
        
        val = s['webtoon_scenes_json']
        if val:
            print(f"\n[Webtoon Scenes JSON (First 800 chars)]: ")
            print(val[:800])
            
            # Deep scan of the first scene in JSON
            try:
                scenes = json.loads(val)
                if scenes:
                    first = scenes[0]
                    print("\n[DEEP SCAN: FIRST SCENE]")
                    print(f"Scene #: {first.get('scene_number')}")
                    print(f"Voice Name: {first.get('voice_name')}")
                    print(f"Voice ID: {first.get('voice_id')}")
                    print(f"Voice Settings: {first.get('voice_settings')}")
                    print(f"Audio Direction: {first.get('audio_direction')}")
                    print(f"Analysis Object Keys: {list(first.get('analysis', {}).keys())}")
                    
                    analysis = first.get('analysis', {})
                    print(f"Voice Rec in Analysis: {analysis.get('voice_recommendation')}")
                    print(f"Voice Settings in Analysis: {analysis.get('voice_settings')}")
                    print(f"Audio Dir in Analysis: {analysis.get('audio_direction')}")
            except Exception as e:
                print(f"Failed to parse JSON: {e}")
        else:
            print("\n[webtoon_scenes_json is EMPTY]")
    else:
        print(f"\nNo settings found for project {target_id}")

    conn.close()

if __name__ == "__main__":
    check_db()
