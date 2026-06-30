"""
숏폼 영상 생성 비즈니스 로직 서비스
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from services.topview_service import topview_service
import database as db


logger = logging.getLogger(__name__)


class ShortsService:
    """숏폼 영상 관련 비즈니스 로직"""

    def __init__(self):
        self.logger = logger

    def _convert_length_to_type(self, length_seconds: int) -> int:
        """영상 길이(초)를 TopView API 타입으로 변환"""
        # TopView API의 videoLengthType (0: 15초, 1: 30초, 2: 45초, 3: 60초)
        if length_seconds <= 15:
            return 0
        elif length_seconds <= 30:
            return 1
        elif length_seconds <= 45:
            return 2
        else:
            return 3

    def save_video_settings(self, settings: dict) -> bool:
        """숏폼 영상 설정 저장"""
        try:
            project_id = settings.get('project_id')

            if project_id:
                # 프로젝트별 설정 저장
                existing_settings = db.get_shorts_video_settings(project_id)
                if existing_settings:
                    # 기존 설정 업데이트
                    return db.update_shorts_video_settings(project_id, settings)
                else:
                    # 새 설정 생성
                    return db.create_shorts_video_settings(project_id, settings)
            else:
                # 전역 설정 저장 (localStorage 활용)
                return True

        except Exception as e:
            self.logger.error(f"Failed to save video settings: {e}")
            return False

    def get_video_settings(self, project_id: int = None) -> dict:
        """숏폼 영상 설정 조회"""
        try:
            if project_id:
                return db.get_shorts_video_settings(project_id)
            else:
                # 기본 설정 반환
                return {
                    'avatar_id': None,
                    'voice_id': None,
                    'background_style': 'studio',
                    'video_length': 30
                }

        except Exception as e:
            self.logger.error(f"Failed to get video settings: {e}")
            return {}

    async def create_video(self, video_data: dict) -> Dict[str, Any]:
        """
        숏폼 영상 생성 요청
        1. DB에 레코드 생성
        2. TopView API 호출 시도
        """
        try:
            # 쇼츠 데이터 추출
            short_data = video_data.get('short_data', {})
            short_title = short_data.get('title', '숏폼')
            short_hook = short_data.get('hook', '')
            short_script = short_data.get('script', '')

            # TopView용 제목과 설명 생성
            product_name = f"{short_title} - {short_hook[:30]}" if short_hook else short_title
            product_desc = short_script[:500] if short_script else "숏폼 영상"

            # 사용자가 선택한 AI 모델 설정
            avatar_id = video_data.get('avatar_id')
            voice_id = video_data.get('voice_id')
            background_style = video_data.get('background_style', 'studio')
            video_length = video_data.get('video_length', 30)

            # DB에 레코드 생성 (AI 모델 설정 포함)
            video_id = db.create_shorts_video({
                'short_index': video_data.get('short_index', 0),
                'short_title': short_title,
                'hook': short_hook,
                'script': short_script,
                'video_style': video_data.get('video_style', 'vlog'),
                'avatar_style': video_data.get('avatar_style', 'default'),
                'avatar_id': avatar_id,
                'voice_id': voice_id,
                'background_style': background_style,
                'video_length': video_length,
                'project_id': video_data.get('project_id'),
                'status': 'pending'
            })

            # TopView API 호출 시도
            try:
                # 기본값 설정 (사용자 선택이 없으면)
                default_avatar = avatar_id or "AIAvatar1780521406560067586"
                default_voice = voice_id or "TtsVoice1780829871032872962"

                # 영상 길이 타입 변환 (초 -> 타입)
                video_length_type = self._convert_length_to_type(video_length)

                result = await topview_service.submit_marketing_task(
                    product_url='',  # 숏폼은 제품 URL 없음
                    product_name=product_name,
                    product_desc=product_desc,
                    voice_id=default_voice,
                    avatar_id=default_avatar,
                    language="ko"
                )
            except Exception as e:
                self.logger.error(f"TopView Submit Error: {e}")
                result = None

            if result and result.get('taskId'):
                # task_id 저장
                task_id = result.get('taskId')
                db.update_shorts_video(video_id, {
                    'topview_task_id': task_id,
                    'status': 'processing'
                })

                # 백그라운드 폴링 시작
                asyncio.create_task(self.poll_video_status(video_id, task_id))

                return {
                    "status": "success",
                    "video_id": video_id,
                    "task_id": task_id,
                    "message": "TopView AI 숏폼 영상 생성이 시작되었습니다."
                }
            else:
                # API 호출 실패
                db.update_shorts_video(video_id, {
                    'status': 'failed',
                    'error_message': 'TopView API 호출 실패'
                })

                return {
                    "status": "error",
                    "video_id": video_id,
                    "message": "TopView API 호출에 실패했습니다."
                }
        except Exception as e:
            self.logger.error(f"Shorts video creation error: {e}")
            raise

    async def poll_video_status(self, video_id: int, task_id: str, max_attempts: int = 60):
        """
        백그라운드에서 TopView 영상 생성 상태를 주기적으로 확인
        10초마다 확인, 최대 10분
        """
        attempt = 0

        while attempt < max_attempts:
            try:
                await asyncio.sleep(10)  # 10초 대기

                # 영상 정보 조회
                video = self.get_video(video_id)
                if not video:
                    self.logger.error(f"Video {video_id} not found in DB")
                    break

                # TopView 상태 확인
                status_result = await topview_service.query_task_status(task_id)
                if not status_result:
                    attempt += 1
                    continue

                # 상태 처리
                status = status_result.get('status')

                if status == 2 or str(status).lower() in ['success', 'completed']:
                    # 최종 영상 URL 확인
                    final_video_url = status_result.get('videoUrl') or status_result.get('video_url')

                    if final_video_url:
                        # 영상 생성 완료
                        thumbnail_url = status_result.get('coverUrl') or status_result.get('thumbnail_url')
                        db.update_shorts_video(video_id, {
                            'status': 'completed',
                            'video_url': final_video_url,
                            'thumbnail_url': thumbnail_url
                        })
                        self.logger.info(f"Shorts video {video_id} completed: {final_video_url}")
                        break
                    else:
                        # 초안 성공 - 스크립트 업데이트 및 내보내기
                        export_triggered = video.get('meta_data', {}).get('export_triggered') if video.get('meta_data') else False

                        if not export_triggered:
                            # 커스텀 스크립트 업데이트
                            custom_script = video.get('script')
                            if custom_script:
                                self.logger.info(f"Updating script for shorts video {video_id}")
                                await topview_service.update_task_script(task_id, "", custom_script)

                            # 내보내기 요청
                            self.logger.info(f"Requesting export for shorts video {video_id}")
                            export_success = await topview_service.export_task(task_id)

                            if export_success:
                                # 메타 데이터 플래그 업데이트
                                meta_data = video.get('meta_data', {}) if video.get('meta_data') else {}
                                meta_data['export_triggered'] = True
                                db.update_shorts_video(video_id, {'meta_data': meta_data})
                                self.logger.info(f"Export triggered successfully for video {video_id}")
                            else:
                                db.update_shorts_video(video_id, {
                                    'status': 'failed',
                                    'error_message': 'Export Request Failed'
                                })
                                break

                        attempt += 1

                elif status == 3 or str(status).lower() in ['failed', 'error']:
                    # 영상 생성 실패
                    error_msg = status_result.get('errorMsg') or status_result.get('error', 'Unknown error')
                    db.update_shorts_video(video_id, {
                        'status': 'failed',
                        'error_message': error_msg
                    })
                    self.logger.error(f"Shorts video {video_id} failed: {error_msg}")
                    break
                else:
                    # 아직 처리 중
                    self.logger.info(f"Shorts video {video_id} still processing (Status: {status})... ({attempt}/{max_attempts})")
                    attempt += 1

            except Exception as e:
                self.logger.error(f"Polling error for video {video_id}: {e}")
                attempt += 1

        # 타임아웃
        if attempt >= max_attempts:
            db.update_shorts_video(video_id, {
                'status': 'failed',
                'error_message': 'Timeout: 영상 생성 시간 초과'
            })
            self.logger.error(f"Shorts video {video_id} timed out")

    def get_all_videos(self, limit: int = 50) -> list:
        """모든 숏폼 영상 조회"""
        return db.get_all_shorts_videos(limit)

    def get_project_videos(self, project_id: int, limit: int = 50) -> list:
        """프로젝트별 숏폼 영상 조회"""
        return db.get_project_shorts_videos(project_id, limit)

    def get_video(self, video_id: int) -> Optional[dict]:
        """특정 영상 조회"""
        return db.get_shorts_video(video_id)

    def delete_video(self, video_id: int):
        """영상 삭제"""
        db.delete_shorts_video(video_id)


# 싱글톤 인스턴스
shorts_service = ShortsService()