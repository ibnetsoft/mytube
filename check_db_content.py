
import sqlite3
import json
from pathlib import Path
import sys

# Ensure UTF-8 output
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def check_presets_content():
    try:
        db_path = Path(__file__).parent / "data" / "wingsai.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT name, settings_json FROM shorts_template_presets")
        rows = cursor.fetchall()
        print(f"--- PRESETS CONTENT CHECK ({len(rows)} items) ---")
        for row in rows:
            name = row['name']
            js = row['settings_json']
            try:
                data = json.loads(js)
                # Show first layer font and text as sample
                layers = data.get('layerStyles', [])
                sample = layers[0] if layers else {}
                print(f"Preset: [{name}]")
                print(f"  - Layers Count: {len(layers)}")
                print(f"  - Sample Font: {sample.get('font_family')}")
                print(f"  - Sample Size: {sample.get('font_size')}")
                print(f"  - Sample Color: {sample.get('color')}")
            except:
                print(f"  - [ERROR] Invalid JSON for {name}")
            
        conn.close()
    except Exception as e:
        print(f"DB ERROR: {e}")

if __name__ == "__main__":
    check_presets_content()
