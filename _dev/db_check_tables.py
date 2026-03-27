import sqlite3
db_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\data\wingsai.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
print(", ".join(tables))
conn.close()
