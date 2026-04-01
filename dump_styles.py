import sqlite3
import os

def dump_style(key):
    db_path = 'data/wingsai.db'
    if not os.path.exists(db_path): return
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    p = conn.execute("SELECT prompt_value FROM style_presets WHERE style_key = ?", (key,)).fetchone()
    if p:
        print(f"PROMPT: {dict(p)['prompt_value']}")
    else:
        print("Style Key Not Found")
    conn.close()

if __name__ == "__main__":
    dump_style("역사/동양철/다큐")
