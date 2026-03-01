from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Body
from typing import List, Optional
import os
import shutil
from services.source_service import source_service
import database as db
from config import config

router = APIRouter(prefix="/api/projects", tags=["Sources"])

@router.get("/{project_id}/sources")
async def get_sources(project_id: int):
    """프로젝트의 모든 소스 목록 조회"""
    try:
        sources = db.get_project_sources(project_id)
        return {"status": "ok", "sources": sources}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/{project_id}/sources/url")
async def add_url_source(project_id: int, url: str = Body(..., embed=True)):
    """URL에서 정보를 추출하여 소스로 추가"""
    try:
        data = await source_service.extract_text_from_url(url)
        source_id = db.add_project_source(
            project_id=project_id,
            source_type="url",
            title=data["title"],
            content=data["content"],
            url=url
        )
        return {"status": "ok", "source_id": source_id, "title": data["title"]}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/{project_id}/sources/file")
async def add_file_source(project_id: int, file: UploadFile = File(...)):
    """TXT 파일을 업로드하여 소스로 추가"""
    try:
        # 임시 저장
        temp_dir = os.path.join(config.OUTPUT_DIR, str(project_id), "temp_sources")
        os.makedirs(temp_dir, exist_ok=True)
        file_path = os.path.join(temp_dir, file.filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 텍스트 추출
        data = source_service.extract_text_from_file(file_path)
        
        # DB 저장
        source_id = db.add_project_source(
            project_id=project_id,
            source_type="txt",
            title=data["title"],
            content=data["content"]
        )
        
        # 임시 파일 삭제
        os.remove(file_path)
        
        return {"status": "ok", "source_id": source_id, "title": data["title"]}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.delete("/{project_id}/sources/{source_id}")
async def delete_source(project_id: int, source_id: int):
    """소스를 삭제"""
    try:
        db.delete_project_source(source_id)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/all-sources-summary")
async def get_all_sources_summary():
    """자료를 가지고 있는 모든 프로젝트 목록 조회"""
    try:
        # DB에서 직접 쿼리 (database.py에 함수 추가 대신 여기서 간단히 처리)
        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.id, p.name, COUNT(s.id) as source_count
            FROM projects p
            JOIN project_sources s ON p.id = s.project_id
            GROUP BY p.id
            HAVING source_count > 0
            ORDER BY p.updated_at DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        return {"status": "ok", "projects": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/{project_id}/sources/clone/{from_project_id}")
async def clone_sources(project_id: int, from_project_id: int):
    """다른 프로젝트의 모든 소스를 현재 프로젝트로 복제"""
    try:
        sources = db.get_project_sources(from_project_id)
        for s in sources:
            db.add_project_source(
                project_id=project_id,
                source_type=s['type'],
                title=s['title'],
                content=s['content'],
                url=s.get('url')
            )
        return {"status": "ok", "cloned_count": len(sources)}
    except Exception as e:
        raise HTTPException(500, str(e))
