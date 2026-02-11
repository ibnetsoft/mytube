from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os
import datetime
import pandas as pd
from config import config

router = APIRouter(prefix="/repository", tags=["Repository"])
templates = Jinja2Templates(directory="templates")

@router.get("", response_class=HTMLResponse)
async def repository_page(request: Request):
    """저장소 메인 페이지"""
    return templates.TemplateResponse("pages/repository.html", {
        "request": request, 
        "title": "분석 저장소", 
        "page": "repository"
    })

@router.get("/api/folders")
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

@router.get("/api/{folder_name}/content")
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
