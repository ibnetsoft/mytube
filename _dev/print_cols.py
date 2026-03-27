import sqlite3

def get_table_info(table_name):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name});")
    cols = cursor.fetchall()
    print(f"--- {table_name} Columns ---")
    for col in cols:
        print(col[1])
    conn.close()

if __name__ == "__main__":
    get_table_info('project_settings')
    get_table_info('projects')
    get_table_info('image_prompts')
