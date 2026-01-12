import sqlite3
import json

def check_settings():
    import os
    db_path = os.path.join('data', 'wingsai.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get the most recent project and its settings
    query = """
    SELECT p.id, p.name, ps.subtitle_color, ps.subtitle_style_enum, ps.subtitle_font, ps.subtitle_stroke_color, ps.subtitle_stroke_width
    FROM projects p
    LEFT JOIN project_settings ps ON p.id = ps.project_id
    ORDER BY p.id DESC LIMIT 1
    """
    cursor.execute(query)
    row = cursor.fetchone()
    
    if row:
        pid, name, color, style, font, stroke, stroke_width = row
        print(f"Project ID: {pid}")
        print(f"Name: {name}")
        print(f"Subtitle Color: {color}")
        print(f"Subtitle Style Enum: {style}")
        print(f"Subtitle Font: {font}")
        print(f"Stroke Color: {stroke}")
        print(f"Stroke Width: {stroke_width}")
    else:
        print("No projects found.")
        
    conn.close()

if __name__ == "__main__":
    check_settings()
