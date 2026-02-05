import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "wingsai.db"
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

# Check style_presets table with all columns
cursor.execute('SELECT style_key, prompt_value FROM style_presets')
rows = cursor.fetchall()
print(f'style_presets - Total rows: {len(rows)}\n')

for row in rows:
    style_key, prompt_value = row
    # Show first 100 chars of prompt
    prompt_preview = prompt_value[:100] if prompt_value else "[NULL]"
    print(f"Style: {style_key}")
    print(f"Prompt: {prompt_preview}...")
    print("-" * 80)

conn.close()
