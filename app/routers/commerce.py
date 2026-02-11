"""
커머스 쇼츠 API 라우터
TopView API를 사용한 제품 프로모션 영상 생성
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json
import asyncio
from datetime import datetime
import os
import uuid
from pathlib import Path

# TopView 서비스 import
from services.topview_service import topview_service
import database as db

router = APIRouter(prefix="/api/commerce", tags=["Commerce"])

# 업로드 디렉토리 설정
UPLOAD_DIR = Path("uploads/commerce")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ============ 요청/응답 모델 ============

class ProductAnalysisRequest(BaseModel):
    product_url: str

class CommerceVideoRequest(BaseModel):
    product_url: str
    product_name: Optional[str] = None
    product_price: Optional[str] = None
    product_description: Optional[str] = None
    product_images: Optional[List[str]] = []
    style_preset: str = "electronics"
    model_type: Optional[str] = None
    background_type: Optional[str] = None
    music_type: Optional[str] = None
    message: Optional[str] = None
    cta: str = "buy_now"

# ============ API 엔드포인트 ============

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

@router.post("/analyze-product")
async def analyze_product(request: ProductAnalysisRequest):
    """
    제품 URL 분석
    - 제품명, 가격, 설명, 이미지 추출
    """
    try:
        # TODO: 웹 크롤링 또는 API로 제품 정보 추출
        # 임시로 더미 데이터 반환
        return {
            "product_name": "샘플 제품",
            "product_price": "99,000원",
            "product_description": "고품질 제품입니다.",
            "product_images": [
                "/static/img/sample1.jpg",
                "/static/img/sample2.jpg",
                "/static/img/sample3.jpg"
            ],
            "category": "electronics"
        }
    except Exception as e:
        raise HTTPException(500, f"제품 분석 실패: {str(e)}")

@router.post("/create-video")
async def create_commerce_video(request: CommerceVideoRequest, background_tasks: BackgroundTasks):
    """
    커머스 쇼츠 영상 생성 요청
    TopView API를 사용하여 실제 영상 생성
    """
    try:
        # 1. DB에 레코드 생성 (pending 상태)
        video_data = {
            'product_url': request.product_url,
            'product_name': request.product_name,
            'product_price': request.product_price,
            'product_description': request.product_description,
            'product_images': request.product_images,
            'style_preset': request.style_preset,
            'model_type': request.model_type,
            'background_type': request.background_type,
            'music_type': request.music_type,
            'message': request.message,
            'cta': request.cta,
            'status': 'pending'
        }
        
        video_id = db.create_commerce_video(video_data)
        
        # 2. TopView API 호출 (비동기)
        result = await topview_service.create_video_by_url(request.product_url)
        
        if result and result.get('id'):
            # TopView task ID 저장
            task_id = result.get('id')
            db.update_commerce_video(video_id, {
                'topview_task_id': task_id,
                'status': 'processing'
            })
            
            # 3. 백그라운드에서 상태 폴링 시작
            background_tasks.add_task(poll_video_status, video_id, task_id)
            
            return {
                "status": "success",
                "video_id": video_id,
                "task_id": task_id,
                "message": "영상 생성이 시작되었습니다. 약 2분 소요됩니다."
            }
        else:
            # TopView API 호출 실패
            db.update_commerce_video(video_id, {
                'status': 'failed',
                'error_message': 'TopView API 호출 실패'
            })
            raise HTTPException(500, "TopView API 호출에 실패했습니다. API 키를 확인해주세요.")
            
    except Exception as e:
        print(f"[Commerce] Video creation error: {e}")
        raise HTTPException(500, f"영상 생성 실패: {str(e)}")

async def poll_video_status(video_id: int, task_id: str, max_attempts: int = 60):
    """
    백그라운드에서 TopView 영상 생성 상태를 주기적으로 확인
    """
    attempt = 0
    while attempt < max_attempts:
        try:
            await asyncio.sleep(10)  # 10초마다 확인
            
            status_result = await topview_service.get_task_status(task_id)
            
            if not status_result:
                attempt += 1
                continue
            
            status = status_result.get('status')
            
            if status == 'completed':
                # 영상 생성 완료
                video_url = status_result.get('video_url')
                thumbnail_url = status_result.get('thumbnail_url')
                
                db.update_commerce_video(video_id, {
                    'status': 'completed',
                    'video_url': video_url,
                    'thumbnail_url': thumbnail_url
                })
                print(f"[Commerce] Video {video_id} completed: {video_url}")
                break
                
            elif status == 'failed':
                # 영상 생성 실패
                error_msg = status_result.get('error', 'Unknown error')
                db.update_commerce_video(video_id, {
                    'status': 'failed',
                    'error_message': error_msg
                })
                print(f"[Commerce] Video {video_id} failed: {error_msg}")
                break
                
            elif status == 'processing':
                # 아직 처리 중
                print(f"[Commerce] Video {video_id} still processing... ({attempt}/{max_attempts})")
                attempt += 1
                
        except Exception as e:
            print(f"[Commerce] Polling error for video {video_id}: {e}")
            attempt += 1
    
    # 타임아웃
    if attempt >= max_attempts:
        db.update_commerce_video(video_id, {
            'status': 'failed',
            'error_message': 'Timeout: 영상 생성 시간 초과'
        })

@router.get("/videos")
async def get_commerce_videos(limit: int = 50):
    """
    생성된 커머스 비디오 목록 조회
    """
    try:
        videos = db.get_all_commerce_videos(limit)
        return {
            "videos": videos,
            "total": len(videos)
        }
    except Exception as e:
        raise HTTPException(500, f"목록 조회 실패: {str(e)}")

@router.get("/videos/{video_id}")
async def get_commerce_video(video_id: int):
    """
    특정 커머스 비디오 조회
    """
    try:
        video = db.get_commerce_video(video_id)
        if not video:
            raise HTTPException(404, "영상을 찾을 수 없습니다")
        return video
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"비디오 조회 실패: {str(e)}")

@router.delete("/videos/{video_id}")
async def delete_commerce_video(video_id: int):
    """
    커머스 비디오 삭제
    """
    try:
        db.delete_commerce_video(video_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, f"삭제 실패: {str(e)}")

@router.get("/style-presets")
async def get_style_presets():
    """
    스타일 프리셋 목록
    """
    return {
        "presets": [
            {
                "key": "fashion",
                "name": "패션/뷰티",
                "description": "패션 및 뷰티 제품에 최적화",
                "model_default": "female_20s",
                "background_default": "studio_clean"
            },
            {
                "key": "electronics",
                "name": "전자제품",
                "description": "기술 제품에 맞는 깔끔한 스타일",
                "model_default": "male_30s",
                "background_default": "studio_tech"
            },
            {
                "key": "food",
                "name": "식품/음료",
                "description": "식욕을 자극하는 따뜻한 톤",
                "model_default": "female_30s",
                "background_default": "kitchen"
            },
            {
                "key": "lifestyle",
                "name": "생활용품",
                "description": "일상적인 분위기",
                "model_default": "neutral",
                "background_default": "home"
            }
        ]
    }
