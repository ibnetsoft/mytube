import sqlite3

def go():
    conn = sqlite3.connect('data/wingsai.db')
    c = conn.cursor()
    c.row_factory = sqlite3.Row

    print("\nProject 78 settings:")
    for r in c.execute("SELECT setting_key, setting_value FROM project_settings WHERE project_id=78").fetchall():
        if 'motion' in r['setting_key'] or 'wan' in r['setting_key']:
            print(r['setting_key'], r['setting_value'])

if __name__ == '__main__':
    go()
