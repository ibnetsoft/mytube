import sqlite3

conn = sqlite3.connect('data/wingsai.db', timeout=10)
cur = conn.cursor()

# 광마회귀(78), 성녀2(107) 확인
print("=== 변경 전 상태 ===")
cur.execute("SELECT ps.project_id, p.name, ps.app_mode, ps.creation_mode FROM project_settings ps LEFT JOIN projects p ON p.id = ps.project_id WHERE ps.project_id IN (78, 107)")
for r in cur.fetchall():
    print(r)

# project_settings의 app_mode를 'webtoon'으로 변경
cur.execute("UPDATE project_settings SET app_mode = 'webtoon' WHERE project_id IN (78, 107)")
conn.commit()
print(f"\n변경된 행: {cur.rowcount}")

print("\n=== 변경 후 상태 ===")
cur.execute("SELECT ps.project_id, p.name, ps.app_mode, ps.creation_mode FROM project_settings ps LEFT JOIN projects p ON p.id = ps.project_id WHERE ps.project_id IN (78, 107)")
for r in cur.fetchall():
    print(r)

conn.close()
print("\n완료!")
