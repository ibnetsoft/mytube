"""
커머스 쇼츠 비즈니스 로직 서비스
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from services.topview_service import topview_service
from services.akool_service import akool_service
from services.tts_service import tts_service
from config import config
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
            # 1. DB에 레코드 생성 (pending 상태)
            video_id = db.create_commerce_video({
                **video_data,
                'status': 'pending',
                'engine': engine
            })
            
            if engine == 'akool':
                return await self._create_akool_video(video_id, video_data)

            # 2. TopView API 호출 시도
            try:
                result = await topview_service.create_video_by_url(video_data['product_url'])
            except:
                result = None

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

    async def _create_akool_video(self, video_id: int, video_data: dict) -> Dict[str, Any]:
        """Akool Talking Avatar 영상 생성 흐름"""
        try:
            # 1. Script
            script = video_data.get('message', '')
            if not script:
                script = f"안녕하세요! {video_data.get('product_name', '이 제품')}을 소개합니다. 정말 좋은 제품이니 꼭 확인해보세요!"

            # 2. TTS Generation (Local File)
            # Default voice?
            voice_name = "ko-KR-Standard-A" # Simple default or use config
            # Use tts_service to generate generic audio
            import os
            import uuid
            
            # Use existing tts_service function if available?
            # tts_service.generate_audio(text, output_path)
            temp_audio_filename = f"akool_tts_{video_id}_{uuid.uuid4()}.mp3"
            temp_audio_path = os.path.join(config.OUTPUT_DIR, temp_audio_filename)
            
            # We use Google TTS via tts_service or simple default?
            # tts_service has generate_audio(text, path, ...)
            await tts_service.generate_audio(script, temp_audio_path)
            
            # 3. Upload Audio to Public URL (Akool Requirement)
            audio_url = await akool_service._upload_temp_file(temp_audio_path)
            if not audio_url:
                raise Exception("Failed to upload audio for Akool")

            # 4. Avatar Image
            # Use Product Image (First one) or Default Avatar
            # Akool is 'Talking Photo' -> Face is required.
            # Using product image usually fails if no face.
            # So we use a DEFAULT AVATAR logic.
            # Or check if user selected 'model_type'? 
            # Simplified: Use a specific default avatar URL for now.
            avatar_url = "https://img.freepik.com/free-photo/young-woman-with-round-glasses-yellow-sweater_273609-7091.jpg"
            
            # 5. Call Akool API
            task_id = await akool_service.create_talking_photo(avatar_url, audio_url)
            
            # 6. Update DB
            db.update_commerce_video(video_id, {
                'topview_task_id': task_id, # Reusing column or add 'akool_task_id'? Reuse for simplicity as 'task_id'
                'status': 'processing',
                'engine': 'akool'
            })
            
            return {
                "status": "success",
                "video_id": video_id,
                "task_id": task_id,
                "engine": "akool",
                "message": "Akool Avatar 영상 생성이 시작되었습니다."
            }
            
        except Exception as e:
            self.logger.error(f"Akool creation error: {e}")
            db.update_commerce_video(video_id, {
                'status': 'failed',
                'error_message': f"Akool Error: {str(e)}"
            })
            return {
                "status": "error",
                "video_id": video_id,
                "message": f"Akool 생성 실패: {str(e)}"
            }
    
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
                
                status = status_result.get('status')
                # Akool Status Mapping: 1(Queued), 2(Processing), 3(Success), 4(Failed)
                # But existing code checks string 'completed'.
                # We need to normalize status if possible, or handle engine specific logic.
                
                # Retrieve Engine info if not passed
                video = self.get_video(video_id)
                engine = video.get('engine', 'topview') if video else 'topview'
                
                if engine == 'akool':
                    # Akool Polling
                    try:
                        akool_status, akool_url = await akool_service.get_job_status(task_id)
                        # akool_service returns ('success'/'processing'/'failed', url)
                        if akool_status == 'success':
                            db.update_commerce_video(video_id, {
                                'status': 'completed',
                                'video_url': akool_url,
                                'thumbnail_url': akool_url # Akool doesn't give separate thumb usually, use video or avatar
                            })
                            self.logger.info(f"Akool Video {video_id} completed")
                            break
                        elif akool_status == 'failed':
                            db.update_commerce_video(video_id, {'status': 'failed', 'error_message': 'Akool Processing Failed'})
                            break
                        else:
                            # processing
                            attempt += 1
                            continue
                            
                    except Exception as e:
                        self.logger.error(f"Akool Polling Error: {e}")
                        attempt += 1
                        continue

                else:
                    # TopView Logic
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
