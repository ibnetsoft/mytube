"""
커머스 쇼츠 API 라우터
TopView API를 사용한 제품 프로모션 영상 생성
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from typing import List, Optional
import os
import uuid
from pathlib import Path

from app.models.commerce import ProductAnalysisRequest, CommerceVideoRequest
from services.commerce_service import commerce_service


router = APIRouter(prefix="/api/commerce", tags=["Commerce"])

# 업로드 디렉토리 설정
UPLOAD_DIR = Path("uploads/commerce")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ============ 이미지 업로드 ============

@router.post("/upload-images")
async def upload_images(files: List[UploadFile] = File(...)):
    """
    제품 이미지 업로드
    - 최대 5장까지 업로드 가능
    - 지원 형식: jpg, jpeg, png, webp
    """
    try:
        if len(files) > 5:
            raise HTTPException(400, "최대 5장까지 업로드 가능합니다")
        
        uploaded_urls = []
        
        for file in files:
            # 파일 확장자 확인
            ext = file.filename.split('.')[-1].lower()
            if ext not in ['jpg', 'jpeg', 'png', 'webp']:
                raise HTTPException(400, f"지원하지 않는 파일 형식: {ext}")
            
            # 고유 파일명 생성
            unique_filename = f"{uuid.uuid4()}.{ext}"
            file_path = UPLOAD_DIR / unique_filename
            
            # 파일 저장
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)
            
            # 웹 접근 가능한 URL 생성
            web_url = f"/uploads/commerce/{unique_filename}"
            uploaded_urls.append(web_url)
        
        return {
            "status": "success",
            "images": uploaded_urls,
            "count": len(uploaded_urls)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Commerce] Upload error: {e}")
        raise HTTPException(500, f"업로드 실패: {str(e)}")


# ============ 트렌드 검색 ============

@router.get("/trends")
async def get_amazon_trends():
    """미국 아마존 트렌드 키워드 조회"""
    try:
        from services.gemini_service import GeminiService
        gemini = GeminiService()
        keywords = await gemini.generate_amazon_trends()
        return {"status": "success", "keywords": keywords}
    except Exception as e:
        print(f"[Commerce] Trend Gen Error: {e}")
        raise HTTPException(500, f"트렌드 조회 실패: {str(e)}")


# ============ 제품 분석 ============

@router.post("/analyze-product")
async def analyze_product(request: ProductAnalysisRequest):
    """
    제품 URL 분석
    - 제품명, 가격, 설명, 이미지 추출
    - 현재는 더미 데이터 반환
    """
    try:
        result = await commerce_service.analyze_product(request.product_url)
        
        return {
            "status": "success",
            **result
        }
        
    except Exception as e:
        print(f"[Commerce] Analysis error: {e}")
        raise HTTPException(500, f"제품 분석 실패: {str(e)}")


# ============ 카피라이팅 생성 ============

from pydantic import BaseModel
class CommerceCopyRequest(BaseModel):
    product_name: str
    product_price: Optional[str] = None
    product_description: Optional[str] = None

@router.post("/generate-copy")
async def generate_commerce_copy(req: CommerceCopyRequest):
    """
    제품 정보를 바탕으로 쇼츠 카피라이팅 3종 생성
    """
    try:
        from services.gemini_service import GeminiService
        gemini = GeminiService()
        
        info = {
            "product_name": req.product_name,
            "product_price": req.product_price,
            "product_description": req.product_description
        }
        
        result = await gemini.generate_commerce_copywriting(info)
        return {"status": "success", **result}
    except Exception as e:
        print(f"[Commerce] Copy Gen Error: {e}")
        raise HTTPException(500, f"카피라이팅 생성 실패: {str(e)}")



# ============ 스타일 프리셋 ============

@router.get("/style-presets")
async def get_style_presets():
    """스타일 프리셋 목록 조회"""
    try:
        presets = commerce_service.get_style_presets()
        
        return {
            "status": "success",
            "presets": presets
        }
        
    except Exception as e:
        print(f"[Commerce] Presets error: {e}")
        raise HTTPException(500, f"프리셋 조회 실패: {str(e)}")


# ============ 영상 생성 ============

@router.post("/create-video")
async def create_commerce_video(request: CommerceVideoRequest, background_tasks: BackgroundTasks):
    """
    커머스 쇼츠 영상 생성 요청
    TopView API를 사용하여 실제 영상 생성
    """
    try:
        # 영상 생성 요청
        result = await commerce_service.create_video(request.dict())
        
        if result['status'] == 'success':
            # 백그라운드에서 상태 폴링 시작
            background_tasks.add_task(
                commerce_service.poll_video_status,
                result['video_id'],
                result['task_id']
            )
        
        return result
        
    except Exception as e:
        print(f"[Commerce] Video creation error: {e}")
        raise HTTPException(500, f"영상 생성 실패: {str(e)}")


# ============ 영상 관리 ============

@router.get("/videos")
async def get_videos():
    """생성된 커머스 영상 목록 조회"""
    try:
        videos = commerce_service.get_all_videos()
        
        return {
            "status": "success",
            "videos": videos
        }
        
    except Exception as e:
        print(f"[Commerce] Videos list error: {e}")
        raise HTTPException(500, f"영상 목록 조회 실패: {str(e)}")


@router.get("/videos/{video_id}")
async def get_video(video_id: int):
    """특정 커머스 영상 조회"""
    try:
        video = commerce_service.get_video(video_id)
        
        if not video:
            raise HTTPException(404, "영상을 찾을 수 없습니다")
        
        return {
            "status": "success",
            "video": video
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Commerce] Video get error: {e}")
        raise HTTPException(500, f"영상 조회 실패: {str(e)}")


@router.delete("/videos/{video_id}")
async def delete_video(video_id: int):
    """커머스 영상 삭제"""
    try:
        commerce_service.delete_video(video_id)
        
        return {
            "status": "success",
            "message": "영상이 삭제되었습니다"
        }
        
    except Exception as e:
        print(f"[Commerce] Video delete error: {e}")
        raise HTTPException(500, f"영상 삭제 실패: {str(e)}")
