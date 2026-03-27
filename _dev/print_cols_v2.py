import sqlite3

def get_table_info(db_path, table_name):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name});")
        cols = cursor.fetchall()
        print(f"--- {db_path} : {table_name} Columns ---")
        for col in cols:
            print(col[1])
        conn.close()
    except Exception as e:
        print(f"Error checking {db_path} {table_name}: {e}")

if __name__ == "__main__":
    db = 'data/wingsai.db'
    get_table_info(db, 'project_settings')
    get_table_info(db, 'projects')
    get_table_info(db, 'image_prompts')
    get_table_info(db, 'global_settings')
    get_table_info(db, 'scripts')
