"""
숏폼 영상 생성 API 라우터
TopView API를 사용한 숏폼 영상 생성
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from typing import Optional
import logging

from app.models.shorts import ShortsVideoRequest, ShortsVideoSettings
from services.shorts_service import shorts_service


router = APIRouter(prefix="/api/shorts", tags=["Shorts"])
logger = logging.getLogger(__name__)


@router.post("/generate-video")
async def generate_shorts_video(request: ShortsVideoRequest, background_tasks: BackgroundTasks):
    """
    숏폼 영상 생성 요청
    TopView API를 사용하여 숏폼 영상 생성
    """
    try:
        result = await shorts_service.create_video(request.model_dump())

        if result['status'] == 'success':
            # 백그라운드에서 상태 폴링 시작
            background_tasks.add_task(
                shorts_service.poll_video_status,
                result['video_id'],
                result['task_id']
            )

        return result

    except Exception as e:
        logger.error(f"Shorts video creation error: {e}")
        raise HTTPException(500, f"영상 생성 실패: {str(e)}")


@router.get("/video-status/{video_id}")
async def get_video_status(video_id: int):
    """숏폼 영상 생성 상태 조회"""
    try:
        video = shorts_service.get_video(video_id)

        if not video:
            raise HTTPException(404, "영상을 찾을 수 없습니다")

        return {
            "status": "success",
            "video": video
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Video status check error: {e}")
        raise HTTPException(500, f"상태 조회 실패: {str(e)}")


@router.get("/videos")
async def get_all_videos():
    """모든 숏폼 영상 목록 조회"""
    try:
        videos = shorts_service.get_all_videos()

        return {
            "status": "success",
            "videos": videos
        }

    except Exception as e:
        logger.error(f"Videos list error: {e}")
        raise HTTPException(500, f"영상 목록 조회 실패: {str(e)}")


@router.get("/videos/{project_id}")
async def get_project_videos(project_id: int):
    """프로젝트별 숏폼 영상 목록 조회"""
    try:
        videos = shorts_service.get_project_videos(project_id)

        return {
            "status": "success",
            "videos": videos
        }

    except Exception as e:
        logger.error(f"Project videos list error: {e}")
        raise HTTPException(500, f"프로젝트 영상 목록 조회 실패: {str(e)}")


@router.delete("/videos/{video_id}")
async def delete_video(video_id: int):
    """숏폼 영상 삭제"""
    try:
        shorts_service.delete_video(video_id)

        return {
            "status": "success",
            "message": "영상이 삭제되었습니다"
        }

    except Exception as e:
        logger.error(f"Video delete error: {e}")
        raise HTTPException(500, f"영상 삭제 실패: {str(e)}")


@router.post("/video-settings")
async def save_video_settings(request: ShortsVideoSettings):
    """숏폼 영상 AI 모델 설정 저장"""
    try:
        success = shorts_service.save_video_settings(request.model_dump())

        if success:
            return {
                "status": "success",
                "message": "설정이 저장되었습니다"
            }
        else:
            raise HTTPException(500, "설정 저장 실패")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Video settings save error: {e}")
        raise HTTPException(500, f"설정 저장 실패: {str(e)}")


@router.get("/video-settings")
async def get_video_settings(project_id: Optional[int] = Query(None)):
    """숏폼 영상 AI 모델 설정 조회"""
    try:
        settings = shorts_service.get_video_settings(project_id)

        return {
            "status": "success",
            "settings": settings
        }

    except Exception as e:
        logger.error(f"Video settings get error: {e}")
        raise HTTPException(500, f"설정 조회 실패: {str(e)}")