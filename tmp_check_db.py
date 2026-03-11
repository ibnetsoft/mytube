import sys
sys.path.insert(0, '.')
import sqlite3

DB_PATH = r'data\wingsai.db'
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# global_settings에서 API/Key 관련 항목만
cur.execute("SELECT key, SUBSTR(value,1,50) FROM global_settings WHERE key LIKE '%api%' OR key LIKE '%key%' OR key LIKE '%token%' OR key LIKE '%akool%' OR key LIKE '%replicate%' OR key LIKE '%elevenlabs%' ORDER BY key")
rows = cur.fetchall()
print("[API Key 관련 설정]")
for r in rows:
    print(f"  key={r[0]!r}  val_preview={r[1]!r}")

conn.close()
