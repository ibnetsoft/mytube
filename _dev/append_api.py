
path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\main.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

target = 'if __name__ == "__main__":'
api_code = '''
# ===========================================
# API: Repository to Script Plan
# ===========================================

class RepositoryPlanRequest(BaseModel):
    title: str
    synopsis: str
    success_factor: str

@app.post("/api/repository/create-plan")
async def create_plan_from_repository(req: RepositoryPlanRequest):
    """
    저장소(Repository)의 분석 결과를 바탕으로
    1. 새 프로젝트 생성
    2. 대본 기획(Structure) 자동 생성
    """
    # 1. Create Project
    try:
        project_id = db.create_project(req.title, req.synopsis)
        print(f"Created Project for Plan: {req.title} ({project_id})")
    except Exception as e:
        raise HTTPException(500, f"프로젝트 생성 실패: {str(e)}")

    # 2. Prepare Mock Analysis Data for Gemini
    # Repository data provides minimal context, so we adapt it.
    analysis_simulation = {
        "topic": req.synopsis, # Use synopsis as the core topic
        "user_notes": f"Original Motivation (Success Factor): {req.success_factor}\\nTarget Title: {req.title}",
        "duration": 600, # Default ~10 min
        "script_style": "story" # Default style
    }

    # 3. Generate Structure
    from services.gemini_service import gemini_service
    try:
        structure = await gemini_service.generate_script_structure(analysis_simulation)
        
        if "error" in structure:
            print(f"Structure Gen Warning: {structure['error']}")
        else:
            db.save_script_structure(project_id, structure)
            db.update_project(project_id, status="planned")
            
    except Exception as e:
        print(f"Structure Gen Error: {e}")
    
    return {"status": "ok", "project_id": project_id}

'''

if target in content:
    new_content = content.replace(target, api_code + '\n' + target)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Successfully appended API.")
else:
    print("Target not found.")
