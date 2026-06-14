import sys
import os
import asyncio

# Add project path to python imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import database as db

async def test_flow():
    print("--- 테스트 시작 ---")
    
    # 1. DB 연결 테스트
    try:
        conn = db.get_db()
        print("✅ DB 연결 성공")
        conn.close()
    except Exception as e:
        print(f"❌ DB 연결 실패: {e}")
        return

    # 2. 임의의 프로젝트 조회 또는 임시 테스트 프로젝트 확보
    projects = db.get_recent_projects(limit=1)
    if not projects:
        print("⚠️ 테스트용 프로젝트가 없습니다. 검증을 위해 프로젝트를 먼저 생성해 주세요.")
        return
        
    project = projects[0]
    pid = project['id']
    print(f"✅ 테스트 대상 프로젝트: ID={pid}, Name={project['name']}")

    # 3. 번역 및 저장 테스트 (Gemini 호출 없이 API 컴파일/라우팅 로직 검토)
    try:
        from main import TranslateScriptRequest, translate_project_script
        print("✅ main.py 라우트 및 모델 가져오기 성공")
    except Exception as e:
        print(f"❌ main.py 가져오기 실패: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    # CP949 인코딩 문제 방지를 위해 stdout 재설정
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(test_flow())
