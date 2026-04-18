"""
커머스 쇼츠 비즈니스 로직 서비스
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from services.topview_service import topview_service
from services.tts_service import tts_service
from config import config
import database as db
import os


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
        제품 URL 분석 (실제 크롤링)
        - OpenGraph 메타데이터 기반 정보 추출
        - 이미지 태그 분석
        """
        self.logger.info(f"Analyzing product: {product_url}")
        
        try:
            import httpx
            from bs4 import BeautifulSoup
            import re
            from urllib.parse import urljoin
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            # 1. Fetch Page
            async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=10.0) as client:
                response = await client.get(product_url, headers=headers)
                response.raise_for_status()
                html = response.text
                
            soup = BeautifulSoup(html, "html.parser")
            
            # Helper: Get Meta
            def get_meta(property_name):
                tag = soup.find("meta", property=property_name) or soup.find("meta", attrs={"name": property_name})
                return tag["content"] if tag else None
            
            # 2. Extract Basic Info
            title = get_meta("og:title")
            if not title:
                title = soup.title.string if soup.title else "제품명 없음"
            
            desc = get_meta("og:description") or get_meta("description") or ""
            
            # 3. Extract Price (Try Microdata, OG, or Regex)
            price = "가격 정보 없음"
            og_price = get_meta("product:price:amount")
            if og_price:
                currency = get_meta("product:price:currency") or "원"
                price = f"{og_price} {currency}"
            else:
                # Text Regex Search (Find 'N,NNN원' pattern)
                price_pattern = re.compile(r'([0-9,]+)\s*원')
                # Check visible text
                text_content = soup.get_text()
                match = price_pattern.search(text_content)
                if match:
                    price = match.group(0)
            
            # 4. Extract Images
            images = []
            
            # (1) OG Image is best quality usually
            og_img = get_meta("og:image")
            if og_img: 
                images.append(urljoin(product_url, og_img))
            
            # (2) Find main product images
            for img in soup.find_all("img"):
                # Prioritize lazy loading attributes
                src = img.get("data-src") or img.get("data-original") or img.get("src")
                if not src: continue
                
                full_url = urljoin(product_url, src)
                
                # Filter bad keywords
                lower_src = full_url.lower()
                if any(x in lower_src for x in ['logo', 'icon', 'button', 'banner', 'pixel', 'blank']):
                    continue
                
                if full_url not in images:
                    images.append(full_url)
            
            # Limit images
            final_images = images[:8] # Return up to 8, frontend limits display
            
            if not final_images:
                final_images = ["https://via.placeholder.com/400x400?text=No+Image+Found"]

            self.logger.info(f"Analysis success: {title} ({len(final_images)} images)")
            
            return {
                "product_name": title.strip()[:100],
                "product_price": price,
                "product_description": desc.strip()[:200],
                "product_images": final_images
            }
            
        except Exception as e:
            self.logger.error(f"Crawling failed for {product_url}: {e}")
            # Instead of failing hard, return partial/dummy if possible, but user wants REAL check.
            # Throw descriptive error
            raise ValueError(f"사이트 접속 또는 분석에 실패했습니다: {str(e)}")
    
    # ============ 영상 생성 ============
    
    async def create_video(self, video_data: dict) -> Dict[str, Any]:
        """
        커머스 영상 생성 요청
        1. DB에 레코드 생성
        2. TopView API 호출 시도 (또는 Akool)
        """
        engine = video_data.get('engine', 'topview').lower()
        
        try:
            video_id = db.create_commerce_video({
                **video_data,
                'status': 'pending',
                'engine': engine
            })

            # 2. TopView API 호출 시도
            try:
                result = await topview_service.submit_marketing_task(
                    product_url=video_data.get('product_url', ''),
                    product_name=video_data.get('product_name', '상품'),
                    product_desc=video_data.get('product_description', '상품 설명'),
                    language="ko"
                )
            except Exception as e:
                self.logger.error(f"TopView Submit Error: {e}")
                result = None

            if result and result.get('taskId'):
                # task_id 저장
                task_id = result.get('taskId')
                db.update_commerce_video(video_id, {
                    'topview_task_id': task_id,
                    'status': 'processing'
                })
                
                # [NEW] Start background polling
                asyncio.create_task(self.poll_video_status(video_id, task_id))

                return {
                    "status": "success",
                    "video_id": video_id,
                    "task_id": task_id,
                    "engine": "topview",
                    "message": "TopView AI 영상 생성이 시작되었습니다."
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
                
                # Retrieve Engine info if not passed
                video = self.get_video(video_id)
                if not video:
                    self.logger.error(f"Video {video_id} not found in DB")
                    break
                    
                engine = video.get('engine', 'topview')
                
                # TopView Logic (Avatar Marketing Video)
                status_result = await topview_service.query_task_status(task_id)
                if not status_result:
                    attempt += 1
                    continue
                        
                    # TopView M2V uses status: 0(wait), 1(ing), 2(success), 3(fail) usually
                    # Check strings as well just in case
                    status = status_result.get('status')
                    
                    if status == 2 or str(status).lower() in ['success', 'completed']:
                        # 이 상태가 Draft(초안) 성공인지, Export(최종) 성공인지 확인
                        # 최종 영상 URL이 있으면 Export 완료
                        final_video_url = status_result.get('videoUrl') or status_result.get('video_url')
                        
                        if final_video_url:
                            # 1. 최종 영상 생성 완료
                            thumbnail_url = status_result.get('coverUrl') or status_result.get('thumbnail_url')
                            db.update_commerce_video(video_id, {
                                'status': 'completed',
                                'video_url': final_video_url,
                                'thumbnail_url': thumbnail_url
                            })
                            self.logger.info(f"Video {video_id} fully completed: {final_video_url}")
                            break
                        else:
                            # 2. 초안 성공 (Script & Preview Ready)
                            # Export Triggered 플래그 확인 (방어 코드)
                            export_triggered = video.get('meta_data', {}).get('export_triggered') if video.get('meta_data') else False
                            
                            if not export_triggered:
                                # (선택) 커스텀 스크립트 업데이트
                                custom_message = video.get('message')
                                if custom_message:
                                    self.logger.info(f"TopView updating script with custom message for video {video_id}")
                                    await topview_service.update_task_script(task_id, "", custom_message)
                                
                                # Export 요청
                                self.logger.info(f"TopView requesting export for video {video_id}")
                                export_success = await topview_service.export_task(task_id)
                                
                                if export_success:
                                    # 메타 데이터 플래그 업데이트 (무한루프 방지)
                                    meta_data = video.get('meta_data', {}) if video.get('meta_data') else {}
                                    meta_data['export_triggered'] = True
                                    db.update_commerce_video(video_id, {'meta_data': meta_data})
                                    self.logger.info(f"TopView Export triggered successfully. Waiting for final render...")
                                else:
                                    db.update_commerce_video(video_id, {
                                        'status': 'failed',
                                        'error_message': 'TopView Export Request Failed'
                                    })
                                    break
                            
                            attempt += 1
                        
                    elif status == 3 or str(status).lower() in ['failed', 'error']:
                        # 영상 생성 실패
                        error_msg = status_result.get('errorMsg') or status_result.get('error', 'Unknown error')
                        db.update_commerce_video(video_id, {
                            'status': 'failed',
                            'error_message': error_msg
                        })
                        self.logger.error(f"Video {video_id} failed: {error_msg}")
                        break
                        
                    else:
                        # 0, 1 -> 아직 처리 중
                        self.logger.info(f"Video {video_id} still processing (Status: {status})... ({attempt}/{max_attempts})")
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
