from database import get_db

def check_table():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(image_prompts)")
    cols = [info[1] for info in cursor.fetchall()]
    print("Columns:", cols)
    
    cursor.execute("SELECT * FROM image_prompts WHERE project_id=1")
    rows = cursor.fetchall()
    print("Num rows:", len(rows))
    if rows:
        print("First row:", dict(rows[0]))
    conn.close()

if __name__ == '__main__':
    check_table()
