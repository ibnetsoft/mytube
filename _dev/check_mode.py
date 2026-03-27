import sqlite3

conn = sqlite3.connect('data/wingsai.db')
cursor = conn.cursor()

# Check global_settings table
cursor.execute('SELECT key, value FROM global_settings WHERE key = ?', ('app_mode',))
row = cursor.fetchone()
print(f'Current app_mode in global_settings: {row[1] if row else "NOT SET"}')

# Check recent projects
cursor.execute('''
    SELECT p.id, p.name, ps.app_mode 
    FROM projects p 
    LEFT JOIN project_settings ps ON p.id = ps.project_id 
    ORDER BY p.id DESC 
    LIMIT 5
''')
rows = cursor.fetchall()
print('\n최근 프로젝트 5개:')
for r in rows:
    print(f'ID: {r[0]}, Name: {r[1]}, Mode: {r[2]}')

conn.close()
