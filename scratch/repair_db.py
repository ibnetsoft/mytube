import os
import sys

# 한글 경로 처리
path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\database.py'

try:
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 에러가 발생한 3081라인 이후를 깔끔하게 제거하고 새로 작성
    new_content = lines[:3081]
    
    extra_code = """
def get_project_settings_by_youtube_id(youtube_video_id: str):
    \"\"\"유튜브 비디오 ID로 프로젝트 설정을 조회\"\"\"
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM project_settings WHERE youtube_video_id = ?", (youtube_video_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"[DB Error] get_project_settings_by_youtube_id: {e}")
        return None
    finally:
        conn.close()

def get_channel(channel_id: int):
    \"\"\"ID로 채널 정보를 조회\"\"\"
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM channels WHERE id = ?", (channel_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"[DB Error] get_channel: {e}")
        return None
    finally:
        conn.close()
"""
    
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(new_content)
        f.write(extra_code)
    
    print("Successfully repaired database.py")
except Exception as e:
    print(f"Error: {e}")
