import sqlite3

dbs = ['app.db', 'database.db', 'longform.db', 'longform_studio.db', 'mytube.db', 'projects.db', 'vcoin_maker.db', 'vlog.db', 'wings.db']

for db in dbs:
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        print(f'=== {db} tables: {tables}')
        if 'projects' in tables:
            try:
                cur.execute('SELECT id, name, app_mode FROM projects LIMIT 10')
            except:
                cur.execute('SELECT id, name FROM projects LIMIT 10')
            rows = cur.fetchall()
            print(f'  projects: {rows}')
        conn.close()
    except Exception as e:
        print(f'  ERROR {db}: {e}')
