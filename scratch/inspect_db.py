import sqlite3
import os

db = 'data/wingsai.db'
if os.path.exists(db):
    try:
        conn = sqlite3.connect(db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall()]
        print(f'{db}: {tables}')
        
        # print recent projects
        cursor.execute("SELECT id, name, created_at FROM projects ORDER BY id DESC LIMIT 5")
        for p in cursor.fetchall():
            print("Project:", p)
            
        # check metadata
        if 'metadata' in tables:
            cursor.execute("SELECT * FROM metadata WHERE project_id IN (191, 190)")
            print("Metadata:", cursor.fetchall())
            
        # check tts_audio
        if 'tts_audio' in tables:
            cursor.execute("SELECT * FROM tts_audio WHERE project_id IN (191, 190)")
            print("TTS Audio:", cursor.fetchall())
            
        conn.close()
    except Exception as e:
        print(f'Error {db}: {e}')
