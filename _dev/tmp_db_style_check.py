import sqlite3

DB_PATH = "data/wingsai.db"

def check_styles():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("--- Style Presets ---")
    rows = cursor.execute("SELECT * FROM style_presets").fetchall()
    for row in rows:
        print(f"Key: {row['style_key']}, Prompt: {row['prompt_value'][:50]}...")
    
    conn.close()

if __name__ == "__main__":
    check_styles()
