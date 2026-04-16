
import sqlite3
import json
from pathlib import Path

def inject_test_presets():
    try:
        db_path = Path(__file__).parent / "data" / "wingsai.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Sample 1: Red Gungsuh
        style1 = {
            "layerStyles": [
                { "text": "RED", "font_family": "gungsuh", "font_size": 150, "color": "#FF0000", "stroke_color": "#000000", "stroke_width": 5, "position": "center", "x_offset": 0, "y_offset": 0, "bg_color": None }
            ],
            "shapeStyles": []
        }
        
        # Sample 2: Blue Malgun
        style2 = {
            "layerStyles": [
                { "text": "BLUE", "font_family": "malgun", "font_size": 120, "color": "#0000FF", "stroke_color": "#FFFFFF", "stroke_width": 3, "position": "center", "x_offset": 10, "y_offset": 50, "bg_color": "#000000" }
            ],
            "shapeStyles": []
        }
        
        cursor.execute("INSERT OR REPLACE INTO shorts_template_presets (name, settings_json, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", 
                       ("[TEST_RED_GUNSUH]", json.dumps(style1)))
        cursor.execute("INSERT OR REPLACE INTO shorts_template_presets (name, settings_json, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", 
                       ("[TEST_BLUE_MALGUN]", json.dumps(style2)))
        
        conn.commit()
        conn.close()
        print("Successfully injected [TEST_RED_GUNSUH] and [TEST_BLUE_MALGUN] into DB.")
    except Exception as e:
        print(f"Injection Failed: {e}")

if __name__ == "__main__":
    inject_test_presets()
