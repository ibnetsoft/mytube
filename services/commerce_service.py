"""
커머스 쇼츠 비즈니스 로직 서비스
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from services.topview_service import topview_service
import database as db


logger = logging.getLogger(__name__)


class CommerceService:
    """커머스 쇼츠 관련 비즈니스 로직"""
    
    def __init__(self):
        self.logger = logger
    
    # ============ 스타일 프리셋 ============
    
    def get_style_presets(self) -> list:
        """스타일 프리셋 목록 반환"""
        return [
            {
                "key": "fashion",
                "name": "패션/의류",
                "description": "트렌디하고 세련된 스타일",
                "model_default": "female_20s",
                "background_default": "studio_clean"
            },
            {
                "key": "electronics",
                "name": "전자제품",
                "description": "기술적이고 현대적인 느낌",
                "model_default": "male_30s",
                "background_default": "studio_tech"
            },
            {
                "key": "food",
                "name": "식품/음료",
                "description": "따뜻하고 친근한 분위기",
                "model_default": "female_30s",
                "background_default": "kitchen"
            },
            {
                "key": "lifestyle",
                "name": "생활용품",
                "description": "실용적이고 편안한 스타일",
                "model_default": "neutral",
                "background_default": "home"
            }
        ]
    
    # ============ 제품 분석 ============
    
    async def analyze_product(self, product_url: str) -> Dict[str, Any]:
        """
        제품 URL 분석 (현재는 더미 데이터)
        추후 크롤링 또는 API 연동 가능
        """
        self.logger.info(f"Analyzing product: {product_url}")
        
        # TODO: 실제 크롤링 또는 API 호출
        # 현재는 더미 데이터 반환
        return {
            "product_name": "샘플 제품",
            "product_price": "29,900원",
            "product_description": "고품질 제품입니다. 지금 특별 할인 중!",
            "product_images": [
                "https://via.placeholder.com/400x400?text=Product+1",
                "https://via.placeholder.com/400x400?text=Product+2",
                "https://via.placeholder.com/400x400?text=Product+3"
            ]
        }
    
    # ============ 영상 생성 ============
    
    async def create_video(self, video_data: dict) -> Dict[str, Any]:
        """
        커머스 영상 생성 요청
        1. DB에 레코드 생성
        2. TopView API 호출
        3. task_id 저장
        """
        try:
            # 1. DB에 레코드 생성 (pending 상태)
            video_id = db.create_commerce_video({
                **video_data,
                'status': 'pending'
            })
            
            # 2. TopView API 호출
            result = await topview_service.create_video_by_url(video_data['product_url'])
            
            if result and result.get('id'):
                # task_id 저장
                task_id = result.get('id')
                db.update_commerce_video(video_id, {
                    'topview_task_id': task_id,
                    'status': 'processing'
                })
                
                return {
                    "status": "success",
                    "video_id": video_id,
                    "task_id": task_id,
                    "message": "영상 생성이 시작되었습니다. 약 2분 소요됩니다."
                }
            else:
                # API 호출 실패
                db.update_commerce_video(video_id, {
                    'status': 'failed',
                    'error_message': 'TopView API 호출 실패'
                })
                
                return {
                    "status": "error",
                    "video_id": video_id,
                    "message": "TopView API 호출에 실패했습니다."
                }
                
        except Exception as e:
            self.logger.error(f"Video creation error: {e}")
            raise
    
    # ============ 상태 폴링 ============
    
    async def poll_video_status(self, video_id: int, task_id: str, max_attempts: int = 60):
        """
        백그라운드에서 TopView 영상 생성 상태를 주기적으로 확인
        10초마다 확인, 최대 10분
        """
        attempt = 0
        
        while attempt < max_attempts:
            try:
                await asyncio.sleep(10)  # 10초 대기
                
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
                    
                    self.logger.info(f"Video {video_id} completed: {video_url}")
                    break
                    
                elif status == 'failed':
                    # 영상 생성 실패
                    error_msg = status_result.get('error', 'Unknown error')
                    db.update_commerce_video(video_id, {
                        'status': 'failed',
                        'error_message': error_msg
                    })
                    
                    self.logger.error(f"Video {video_id} failed: {error_msg}")
                    break
                    
                elif status == 'processing':
                    # 아직 처리 중
                    self.logger.info(f"Video {video_id} still processing... ({attempt}/{max_attempts})")
                    attempt += 1
                    
            except Exception as e:
                self.logger.error(f"Polling error for video {video_id}: {e}")
                attempt += 1
        
        # 타임아웃
        if attempt >= max_attempts:
            db.update_commerce_video(video_id, {
                'status': 'failed',
                'error_message': 'Timeout: 영상 생성 시간 초과'
            })
            self.logger.error(f"Video {video_id} timed out")
    
    # ============ 영상 관리 ============
    
    def get_all_videos(self, limit: int = 50) -> list:
        """모든 커머스 영상 조회"""
        return db.get_all_commerce_videos(limit)
    
    def get_video(self, video_id: int) -> Optional[dict]:
        """특정 영상 조회"""
        return db.get_commerce_video(video_id)
    
    def delete_video(self, video_id: int):
        """영상 삭제"""
        db.delete_commerce_video(video_id)


# 싱글톤 인스턴스
commerce_service = CommerceService()
