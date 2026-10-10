import json
from typing import Dict, Any
import database as db
from services.gemini_service import gemini_service
import asyncio

def _generate_optimized_prompt(target_type: str, category: str, feedbacks: list, current_prompt: str) -> str:
    """Gemini를 사용해 피드백을 기반으로 프롬프트를 최적화합니다."""
    # 간단한 프롬프트 엔지니어링
    system_prompt = f"당신은 {category} 카테고리의 {target_type} 프롬프트를 최적화하는 전문가입니다."
    
    feedback_text = ""
    for f in feedbacks:
        rating = "👍 좋아요" if f["rating"] >= 4 else "👎 별로예요"
        comment = f["comments"] or "코멘트 없음"
        feedback_text += f"- 평가: {rating}, 내용: {comment}\n"
        
    user_prompt = f"""
현재 사용 중인 프롬프트:
```
{current_prompt}
```

최근 작업 결과에 대한 사용자 피드백:
{feedback_text}

위 피드백을 반영하여 기존 프롬프트를 개선해주세요. 
규칙:
1. 기존 프롬프트의 좋은 점은 유지하되, 부정적 피드백(별로예요)의 원인을 해결할 수 있는 규칙을 추가하세요.
2. 프롬프트 본문만 바로 출력하세요. (마크다운이나 설명 금지)
"""
    try:
        # gemini_service.generate_text 사용 (동기 래퍼가 없으면 비동기 호출을 해야함)
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        response = loop.run_until_complete(gemini_service.generate_content(user_prompt))
        loop.close()
        return response.strip()
    except Exception as e:
        print(f"[AI Style] Optimization failed: {e}")
        return current_prompt

def run_optimization_and_deploy(target_type: str) -> dict:
    """
    버튼 클릭 시 실행:
    1. 카테고리별 피드백 수집
    2. AI를 통한 프롬프트 보완
    3. 즉시 배포 (DB 저장 및 관련 큐 업데이트)
    """
    categories_dict = {}
    
    # 1. 피드백이 있는 카테고리 찾기
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT category FROM project_feedback")
    categories = [row[0] for row in cursor.fetchall() if row[0]]
    conn.close()
    
    updated_categories = []
    
    for category in categories:
        feedbacks = db.get_project_feedbacks_by_category(category, limit=20)
        if not feedbacks:
            continue
            
        # 기존 프롬프트 가져오기 (없으면 기본값)
        current = db.get_latest_ai_style_prompt(category, target_type)
        current_prompt = current["prompt_content"] if current else "기본 스타일 프롬프트 (최적화 전)"
        
        # 2. AI 최적화 진행
        new_prompt = _generate_optimized_prompt(target_type, category, feedbacks, current_prompt)
        
        if new_prompt and new_prompt != current_prompt:
            # 3. 새 버전 저장 (승인 없이 자동 배포)
            db.save_ai_style_prompt(category, target_type, new_prompt)
            updated_categories.append(category)
            
            # TODO: 대기열(Queue)에 있는 프로젝트들의 설정값도 덮어쓰는 로직 (주제배정 페이지 연동용)
            _apply_style_to_pending_projects(category, target_type, new_prompt)
            
    return {"status": "success", "updated_categories": updated_categories}

def _apply_style_to_pending_projects(category: str, target_type: str, new_prompt: str):
    """아직 렌더링되지 않은 프로젝트(대기열)에 새 스타일을 덮어씌웁니다."""
    # 실제로 덮어씌울 필드 매핑
    field_mapping = {
        "image": "image_style_prompt",
        "script": "script_style"
    }
    field = field_mapping.get(target_type)
    if not field:
        return
        
    conn = db.get_db()
    cursor = conn.cursor()
    # 진행 중이거나 아직 렌더링 전인 프로젝트 찾기 (예: status in ('pending', 'planning', 'script_ready'))
    cursor.execute("""
        SELECT p.id 
        FROM projects p
        JOIN project_settings ps ON p.id = ps.project_id
        WHERE ps.preferred_youtube_channel_name = ? OR ps.preferred_youtube_channel_handle = ?
    """, (category, category))
    rows = cursor.fetchall()
    conn.close()
    
    for r in rows:
        db.update_project_setting(r[0], field, new_prompt)
