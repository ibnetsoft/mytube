import sqlite3

conn = sqlite3.connect('data/wingsai.db')
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print('Tables:', tables)
print()

cur.execute('SELECT id, name, topic, status, created_at, updated_at FROM projects ORDER BY id')
rows = cur.fetchall()
for r in rows:
    print(r)

print()
print('--- project_settings (app_mode) ---')
try:
    cur.execute('SELECT project_id, app_mode, creation_mode FROM project_settings ORDER BY project_id')
    for r in cur.fetchall():
        print(r)
except Exception as e:
    print('Error:', e)

conn.close()
