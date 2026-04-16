
import sys

target_file = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\database.py'

with open(target_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Add get_ai_logs function
get_logs_func = """
def get_ai_logs(limit: int = 100) -> List[Dict[str, Any]]:
    \"\"\"AI 생성 로그 조회\"\"\"
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(\"\"\"
            SELECT id, project_id, task_type, model_id, provider, status, prompt_summary, error_msg, elapsed_time, created_at
            FROM ai_generation_logs
            ORDER BY created_at DESC
            LIMIT ?
        \"\"\", (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"[DB] Failed to get AI logs: {e}")
        return []
    finally:
        conn.close()

def clear_ai_logs():
    \"\"\"모든 AI 로그 삭제\"\"\"
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(\"DELETE FROM ai_generation_logs\")
        conn.commit()
    except Exception as e:
        print(f"[DB] Failed to clear AI logs: {e}")
    finally:
        conn.close()
"""

if 'def get_ai_logs' not in content:
    content += "\n" + get_logs_func

with open(target_file, 'w', encoding='utf-8') as f:
    f.write(content)
print("Log query functions added successfully")
