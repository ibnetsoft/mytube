
import sys

target_file = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\database.py'

with open(target_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add table to init_db
table_sql = """
    # AI 생성 로그 테이블 [NEW]
    cursor.execute(\"\"\"
        CREATE TABLE IF NOT EXISTS ai_generation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            task_type TEXT,
            model_id TEXT,
            provider TEXT,
            status TEXT,
            prompt_summary TEXT,
            error_msg TEXT,
            elapsed_time REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    \"\"\")
"""

if 'ai_generation_logs' not in content:
    pos = content.find('conn.commit()', content.find('def init_db():'))
    if pos != -1:
        content = content[:pos] + table_sql + "\n    " + content[pos:]

# 2. Add helper function at the end
helper_func = """
def add_ai_log(project_id, task_type: str, model_id: str, provider: str, status: str, prompt_summary: str = "", error_msg: str = "", elapsed_time: float = 0.0):
    \"\"\"AI 생성 로그 추가\"\"\"
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(\"\"\"
            INSERT INTO ai_generation_logs (project_id, task_type, model_id, provider, status, prompt_summary, error_msg, elapsed_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        \"\"\", (project_id, task_type, model_id, provider, status, prompt_summary, error_msg, elapsed_time))
        conn.commit()
    except Exception as e:
        print(f"[DB] Failed to add AI log: {e}")
    finally:
        conn.close()
"""

if 'def add_ai_log' not in content:
    content += "\n" + helper_func

with open(target_file, 'w', encoding='utf-8') as f:
    f.write(content)
print("Database schema and helper added successfully")
