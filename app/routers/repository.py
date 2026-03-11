from fastapi import APIRouter, HTTPException, Request, Body
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os
import datetime
import pandas as pd
from config import config
from services.auth_service import auth_service
from services import app_state as _app_state
import database as db

router = APIRouter(prefix="", tags=["Repository"])
templates = Jinja2Templates(directory="templates")

# app_state 공유 translator 사용 (자체 인스턴스 제거)
templates.env.globals['membership'] = auth_service.get_membership()
templates.env.globals['is_independent'] = auth_service.is_independent()

@router.get("/repository", response_class=HTMLResponse)
async def repository_page(request: Request):
    """저장소 메인 페이지"""
    templates.env.globals['t'] = _app_state.get_translator().t if _app_state.get_translator() else (lambda k: k)
    templates.env.globals['current_lang'] = _app_state.get_translator().lang if _app_state.get_translator() else 'ko'
    return templates.TemplateResponse("pages/repository.html", {
        "request": request, 
        "title": "분석 저장소", 
        "page": "repository"
    })

@router.get("/api/repository/folders")
async def list_repository_folders():
    """output/analysis 폴더 내의 하위 폴더 목록 반환"""
    try:
        base_path = os.path.join(config.OUTPUT_DIR, "analysis")
        if not os.path.exists(base_path):
            return {"folders": []}
        
        folders = []
        for d in os.listdir(base_path):
            full_path = os.path.join(base_path, d)
            if os.path.isdir(full_path):
                ctime = os.path.getctime(full_path)
                date_str = datetime.datetime.fromtimestamp(ctime).strftime('%Y-%m-%d %H:%M')
                folders.append({"name": d, "date": date_str, "timestamp": ctime})
                
        folders.sort(key=lambda x: x['timestamp'], reverse=True)
        return {"folders": folders}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/api/repository/{folder_name}/content")
async def get_repository_content(folder_name: str):
    """폴더 내의 첫 번째 엑셀/CSV 파일 내용을 파싱하여 반환"""
    folder_path = os.path.join(config.OUTPUT_DIR, "analysis", folder_name)
    if not os.path.exists(folder_path):
        return {"error": "폴더를 찾을 수 없습니다."}
    
    files = os.listdir(folder_path)
    target_file = None
    for f in files:
        if f.endswith(".xlsx") or f.endswith(".csv"):
            target_file = os.path.join(folder_path, f)
            break
            
    if not target_file:
        return {"error": "분석 파일이 없습니다.", "data": []}
        
    try:
        data = []
        if target_file.endswith(".xlsx"):
            try:
                df = pd.read_excel(target_file)
                data = df.to_dict(orient='records')
            except Exception as e:
                print(f"Excel error: {e}")
                return {"error": f"Excel 파싱 오류: {str(e)}"}
        else:
            try:
                df = pd.read_csv(target_file)
                data = df.to_dict(orient='records')
            except Exception as e:
                print(f"CSV error: {e}")
                return {"error": f"CSV 파싱 오류: {str(e)}"}
                
        return {"status": "success", "data": data, "file": os.path.basename(target_file)}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/api/repository/create-plan")
async def create_plan_from_repo(req: dict = Body(...)):
    """저장소 데이터 기반 프로젝트 생성 및 대본 기획 시작"""
    try:
        title = req.get("title")
        synopsis = req.get("synopsis")
        success_factor = req.get("success_factor")
        
        if not title or not synopsis:
            raise HTTPException(400, "제목과 시놉시스가 필요합니다.")
            
        # 1. 새 프로젝트 생성
        project_id = db.create_project(
            name=title,
            topic=synopsis,
            app_mode="longform" # 기본값
        )
        
        # 2. 프로젝트 설정에 성공 요인 저장 (참고용)
        if success_factor:
            db.update_project_setting(project_id, "success_factor", success_factor)
            
        # 3. 대본 구조 생성 (Gemini 호출 생략하고 빈 데이터로 시작하거나, 필요시 Gemini 연동 가능)
        # 여기서는 일단 프로젝트 생성만 하고 리다이렉트 유도
        
        return {"status": "ok", "project_id": project_id}
    except Exception as e:
        print(f"Error creating plan from repo: {e}")
        raise HTTPException(500, str(e))
