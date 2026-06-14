import sqlite3
import os
import sys

# Set stdout encoding
sys.stdout.reconfigure(encoding='utf-8')

db_path = 'data/wingsai.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get project 190 details
cursor.execute("SELECT id, name FROM projects WHERE id = 190")
project = cursor.fetchone()
print("Project:", project)

# Get script
cursor.execute("SELECT full_script FROM scripts WHERE project_id = 190")
script = cursor.fetchone()
script_text = script[0] if script else ""
print("Script length:", len(script_text))

# Get tts audio
cursor.execute("SELECT audio_path FROM tts_audio WHERE project_id = 190")
audio = cursor.fetchone()
audio_path = audio[0] if audio else ""
print("Audio path:", audio_path)

conn.close()

# Let's run generate_aligned_subtitles
if os.path.exists(audio_path):
    # Add project root to sys.path
    sys.path.append(os.path.abspath('.'))
    from services.video_service import video_service
    
    print("Testing generate_aligned_subtitles...")
    subs = video_service.generate_aligned_subtitles(audio_path, script_text)
    print(f"Generated {len(subs)} subtitles.")
    for i, s in enumerate(subs[:5]):
        print(f"{i}: [{s['start']:.2f} -> {s['end']:.2f}] {repr(s['text'])}")
else:
    print("Audio path does not exist:", audio_path)
