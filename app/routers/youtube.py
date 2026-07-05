"""
YouTube API Router
"""
import os
import shutil
import time
from typing import List, Optional, Dict, Any
import httpx
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks

from config import config
import database as db
from app.models.media import SearchRequest
from services.drive_bundle_service import drive_bundle_service

router = APIRouter(prefix="/api", tags=["YouTube"])


# ===========================================
# Helper Functions
# ===========================================

def _resolve_local_output_asset_path(asset_url_or_path: Optional[str]) -> Optional[str]:
    if not asset_url_or_path:
        return None
    if os.path.isabs(asset_url_or_path) and os.path.exists(asset_url_or_path):
        return asset_url_or_path
    if asset_url_or_path.startswith("/output/"):
        rel = asset_url_or_path.replace("/output/", "", 1).replace("/", os.sep)
        path = os.path.join(config.OUTPUT_DIR, rel)
        return path if os.path.exists(path) else None
    if asset_url_or_path.startswith("/static/"):
        rel = asset_url_or_path.replace("/static/", "", 1).replace("/", os.sep)
        path = os.path.join(config.STATIC_DIR, rel)
        return path if os.path.exists(path) else None
    if os.path.exists(asset_url_or_path):
        return asset_url_or_path
    return None


def _resolve_youtube_token_path(settings: Dict[str, Any], requested_channel_id: Optional[int] = None) -> Optional[str]:
    token_path = None
    preferred_handle = (settings.get("preferred_youtube_channel_handle") or "").strip()
    try:
        target_chan_id = requested_channel_id or settings.get("youtube_channel_id")
        if not target_chan_id:
            if preferred_handle:
                preferred_channel = db.get_channel_by_handle(preferred_handle)
                if preferred_channel and preferred_channel.get("id"):
                    target_chan_id = preferred_channel["id"]
        if target_chan_id:
            channel = db.get_channel(target_chan_id)
            if channel and channel.get("credentials_path"):
                cand_path = channel["credentials_path"]
                if not os.path.isabs(cand_path):
                    cand_path = os.path.join(config.BASE_DIR, cand_path)
                if os.path.exists(cand_path):
                    token_path = cand_path
                else:
                    rec_filename = f"token_{target_chan_id}.pickle"
                    rec_path = os.path.join(config.BASE_DIR, "tokens", rec_filename)
                    if os.path.exists(rec_path):
                        token_path = rec_path
                        print(f"[YouTube] Recovered token path from tokens directory: {token_path}")

        if not token_path and not preferred_handle:
            channels = db.get_all_channels()
            for ch in channels or []:
                c_path = ch.get("credentials_path")
                if not c_path:
                    continue
                if not os.path.isabs(c_path):
                    c_path = os.path.join(config.BASE_DIR, c_path)
                if os.path.exists(c_path):
                    token_path = c_path
                    break
    except Exception as e:
        print(f"[YouTube] Channel resolution error: {e}")
        token_path = None
    return token_path


def _resolve_project_thumbnail_path(project_id: int, settings: Dict[str, Any]) -> Optional[str]:
    thumb_candidate = settings.get("thumbnail_path") or settings.get("thumbnail_url")
    return _resolve_local_output_asset_path(thumb_candidate)


# ===========================================
# API: YouTube
# ===========================================

@router.post("/youtube/search")
async def youtube_search(req: SearchRequest):
    """YouTube 검색"""
    params = {
        "part": "snippet",
        "q": req.query,
        "type": "video",
        "maxResults": req.max_results,
        "order": req.order,
        "key": config.YOUTUBE_API_KEY
    }

    if req.published_after:
        params["publishedAfter"] = req.published_after

    if req.video_duration:
        params["videoDuration"] = req.video_duration
        
    if req.relevance_language:
        params["relevanceLanguage"] = req.relevance_language

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{config.YOUTUBE_BASE_URL}/search",
            params=params
        )
        data = response.json()
        
        # [NEW] Error Handling for API Credentials
        if response.status_code != 200:
            error_data = data.get("error", {})
            message = error_data.get("message", "YouTube API Error")
            print(f"[YouTube Search] Failed: {response.status_code} - {message}")
            if "API key not valid" in message or "API_KEY_INVALID" in str(error_data):
                return {"error": "API_KEY_INVALID", "message": "유효하지 않은 YouTube API 키입니다. 설정에서 확인해주세요."}
            return {"error": "API_ERROR", "message": message}

        return data


@router.post("/projects/{project_id}/youtube/auto-upload")
async def auto_upload_youtube(project_id: int):
    """유튜브 원클릭 자동 업로드 (영상 + 메타데이터 + 썸네일)"""
    from services.youtube_upload_service import youtube_upload_service
    from services.auth_service import auth_service

    if not auth_service.is_independent():
        raise HTTPException(
            status_code=403,
            detail="Standard worker accounts must register rendered videos in web-admin publishing instead of uploading to YouTube locally.",
        )

    # 1. 데이터 조회
    project = db.get_project(project_id)
    settings = db.get_project_settings(project_id)
    meta = db.get_metadata(project_id)

    if not project or not settings:
        raise HTTPException(404, "프로젝트 정보를 찾을 수 없습니다.")

    # 2. 파일 경로 및 메타데이터 준비
    video_web_path = settings.get('video_path')
    if not video_web_path:
        raise HTTPException(400, "렌더링된 영상 파일 정보가 없습니다.")

    # 웹 경로 (/output/folder/file.mp4) -> 절대 경로 변환
    video_rel_path = video_web_path.replace('/output/', '', 1)
    video_path = os.path.join(config.OUTPUT_DIR, video_rel_path)

    if not os.path.exists(video_path):
        print(f"DEBUG: Video file not found at {video_path}")
        raise HTTPException(400, f"영상 파일을 찾을 수 없습니다: {os.path.basename(video_path)}")

    # 메타데이터 (저장된 게 없으면 기본값 사용)
    title = project['name']
    description = ""
    tags = []

    if meta:
        titles = meta.get('titles', [])
        if titles:
            title = titles[0] # 첫 번째 추천 제목 사용
        description = meta.get('description', "")
        tags = meta.get('tags', [])

    # 3. 업로드 수행
    try:
        token_path = _resolve_youtube_token_path(settings)
        preferred_handle = (settings.get("preferred_youtube_channel_handle") or "").strip()
        if preferred_handle and not token_path:
            preferred_name = settings.get("preferred_youtube_channel_name") or preferred_handle
            raise HTTPException(status_code=400, detail=f"고정 업로드 채널이 아직 로컬에 연동되지 않았습니다: {preferred_name}")
        from services.qa_service import is_upload_blocked, resolve_upload_video_path, run_pre_upload_qa
        from services import learning_service
        learning_service.snapshot_project(project_id, "pre_upload", {"upload": {
            "title": title,
            "description_length": len(description or ""),
            "tag_count": len(tags or []),
            "privacy": "private",
            "source": "auto_upload",
        }})
        blocked, qa_result = is_upload_blocked(project_id)
        if blocked:
            learning_service.log_event(project_id, "qa_hold", "qa", {"qa_result": qa_result, "source": "auto_upload"}, source="qa")
            raise HTTPException(status_code=409, detail={
                "status": "qa_hold",
                "message": "QA 경고로 자동 업로드가 보류되었습니다. 프로젝트 화면에서 경고를 확인한 뒤 수동 업로드로 강제 진행할 수 있습니다.",
                "qa_result": qa_result,
            })

        video_path = resolve_upload_video_path(project_id, video_path)
        qa_result = await run_pre_upload_qa(project_id, video_path, {
            "title": title,
            "description": description,
            "tags": tags,
        })
        if qa_result.get("hold_upload"):
            learning_service.log_event(project_id, "qa_hold", "qa", {"qa_result": qa_result, "source": "pre_upload_qa"}, source="qa")
            raise HTTPException(status_code=409, detail={
                "status": "qa_hold",
                "message": "업로드 전 QA 검사 결과 자동 업로드가 보류되었습니다.",
                "qa_result": qa_result,
            })

        response = youtube_upload_service.upload_video(
            file_path=video_path,
            title=title,
            description=description,
            tags=tags,
            token_path=token_path,
            privacy_status="private" # 기본은 비공개 (사용자가 검토 후 공개 전환)
        )

        video_id = response.get('id')
        if not video_id:
            raise Exception("업로드 응답에 비디오 ID가 없습니다.")

        # 4. 썸네일 설정 (있는 경우)
        thumb_url = settings.get('thumbnail_url')
        if thumb_url:
            # 웹 경로 (/output/file.png) -> 절대 경로 변환
            thumb_rel_path = thumb_url.replace('/output/', '', 1)
            thumb_path = os.path.join(config.OUTPUT_DIR, thumb_rel_path)
            
            if os.path.exists(thumb_path):
                youtube_upload_service.set_thumbnail(video_id, thumb_path, token_path=token_path)

        # 5. 상태 업데이트 (비디오 ID 저장)
        db.update_project_setting(project_id, 'youtube_video_id', video_id)
        db.update_project_setting(project_id, 'is_uploaded', 1)
        db.update_project_setting(project_id, 'is_published', 0) # 아직 비공개 상태이므로 0
        learning_service.log_event(project_id, "upload_completed", "upload", {
            "youtube_video_id": video_id,
            "url": f"https://youtu.be/{video_id}",
            "title": title,
            "privacy": "private",
            "source": "auto_upload",
        }, source="system")
        learning_service.snapshot_project(project_id, "post_upload", {"upload": {
            "youtube_video_id": video_id,
            "url": f"https://youtu.be/{video_id}",
            "title": title,
            "privacy": "private",
            "source": "auto_upload",
        }})

        return {
            "status": "ok",
            "video_id": video_id,
            "url": f"https://youtu.be/{video_id}"
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            from services import learning_service as _learning_service
            _learning_service.log_event(project_id, "upload_failed", "upload", {"error": str(e), "source": "auto_upload"}, source="system")
        except Exception:
            pass
        print(f"Auto Upload Error: {e}")
        raise HTTPException(500, f"업로드 중 오류 발생: {str(e)}")


@router.post("/projects/{project_id}/youtube/public")
async def publicize_youtube_video(project_id: int):
    """유튜브 영상을 '공개(public)' 상태로 전환"""
    from services.youtube_upload_service import youtube_upload_service
    from services.auth_service import auth_service

    if not auth_service.is_independent():
        raise HTTPException(
            status_code=403,
            detail="Standard worker accounts cannot change YouTube visibility locally. Use web-admin publishing.",
        )
    
    settings = db.get_project_settings(project_id)
    if not settings or not settings.get('youtube_video_id'):
        raise HTTPException(400, "업로드된 영상의 ID를 찾을 수 없습니다. 먼저 업로드를 진행해 주세요.")
    
    video_id = settings['youtube_video_id']
    
    try:
        youtube_upload_service.update_video_privacy(video_id, "public")
        
        # 상태 업데이트
        db.update_project_setting(project_id, 'is_published', 1)
        
        return {"status": "ok", "message": "영상이 공개 상태로 전환되었습니다."}
    except Exception as e:
        print(f"Publicize Error: {e}")
        raise HTTPException(500, f"공개 전환 중 오류 발생: {str(e)}")


@router.get("/youtube/videos/{video_id}")
async def youtube_video_detail(video_id: str):
    """YouTube 영상 상세 정보"""
    params = {
        "part": "snippet,statistics,contentDetails",
        "id": video_id,
        "key": config.YOUTUBE_API_KEY
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{config.YOUTUBE_BASE_URL}/videos",
            params=params
        )
        data = response.json()
        if response.status_code != 200:
            error_data = data.get("error", {})
            message = error_data.get("message", "YouTube API Error")
            print(f"[YouTube Video] Failed: {response.status_code} - {message}")
            return {"error": "API_ERROR", "message": message}
        return data


@router.get("/youtube/comments/{video_id}")
async def youtube_comments(video_id: str, max_results: int = 100):
    """YouTube 댓글 조회"""
    params = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": max_results,
        "order": "relevance",
        "key": config.YOUTUBE_API_KEY
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{config.YOUTUBE_BASE_URL}/commentThreads",
            params=params
        )
        return response.json()


@router.get("/youtube/channel/{channel_id}")
async def youtube_channel(channel_id: str):
    """YouTube 채널 정보"""
    params = {
        "part": "snippet,statistics",
        "id": channel_id,
        "key": config.YOUTUBE_API_KEY
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{config.YOUTUBE_BASE_URL}/channels",
            params=params
        )
        return response.json()


@router.post("/youtube/upload-external/{project_id}")
async def upload_external_to_youtube(
    project_id: int, 
    request: Request
):
    """업로드된 외부 영상 게시 (Standard: Private, Independent: Selectable)"""
    try:
        data = await request.json()
        requested_privacy = data.get("privacy", "private")
        requested_publish_at = data.get("publish_at")
        requested_channel_id = data.get("channel_id")
    except Exception:
        requested_privacy = "private"
        requested_publish_at = None
        requested_channel_id = None

    # [NEW] Membership Check
    from services.auth_service import auth_service
    is_independent = auth_service.is_independent()

    if not is_independent:
        raise HTTPException(
            status_code=403,
            detail="Standard worker accounts must use web-admin publishing. Register the rendered video with /api/projects/{project_id}/admin-publish-request.",
        )
    
    # Force private if not independent
    final_privacy = "private"
    final_publish_at = None
    
    if is_independent:
        final_privacy = requested_privacy
        final_publish_at = requested_publish_at
        
        # YouTube requires 'private' for scheduled
        if final_publish_at:
            final_privacy = "private"
    else:
        # Standard user always private locally
        if requested_privacy == "public":
            print("[Security] Standard user attempted public upload. Forcing private.")
            final_privacy = "private"

    try:
        from services.project_publish_service import publish_project_to_youtube

        result = publish_project_to_youtube(
            project_id,
            requested_privacy=final_privacy,
            requested_publish_at=final_publish_at,
            requested_channel_id=requested_channel_id,
        )

        return {
            "status": "ok",
            "video_id": result.get("video_id"),
            "url": result.get("url"),
            "upload_source": result.get("upload_source"),
        }
    except Exception as shared_publish_error:
        print(f"[YouTube] Shared publish path failed, falling back to legacy handler: {shared_publish_error}")

    temp_dir_to_cleanup = None
    try:
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(404, "프로젝트를 찾을 수 없습니다.")

        settings = db.get_project_settings(project_id) or {}
        metadata = db.get_metadata(project_id) or {}

        video_path = _resolve_local_output_asset_path(settings.get("external_video_path"))
        upload_source = "external"

        if not video_path:
            video_path = _resolve_local_output_asset_path(settings.get("video_path"))
            if video_path:
                upload_source = "rendered_local"

        drive_assets = None
        if not video_path:
            drive_assets = drive_bundle_service.prepare_youtube_upload_assets(project_id)
            temp_dir_to_cleanup = drive_assets.get("temp_dir")
            video_path = drive_assets.get("video_path")
            upload_source = "drive_bundle"

        if not video_path or not os.path.exists(video_path):
            raise HTTPException(404, "업로드할 영상 파일을 찾을 수 없습니다.")

        from services.youtube_upload_service import youtube_upload_service

        if drive_assets:
            title = drive_assets.get("title") or project.get("name") or f"Project {project_id}"
            description = drive_assets.get("description") or ""
            tags = list(drive_assets.get("tags") or [])
            hashtags = list(drive_assets.get("hashtags") or [])
            thumbnail_path = drive_assets.get("thumbnail_path")
        else:
            title = (metadata.get("titles") or [project.get("name")])[0]
            description = metadata.get("description") or settings.get("description") or ""
            tags = list(metadata.get("tags") or [])
            hashtags = list(metadata.get("hashtags") or [])
            thumbnail_path = _resolve_project_thumbnail_path(project_id, settings)

        merged_tags = []
        for item in tags + hashtags:
            cleaned = str(item or "").strip()
            if cleaned and cleaned not in merged_tags:
                merged_tags.append(cleaned)

        token_path = _resolve_youtube_token_path(settings, requested_channel_id)
        preferred_handle = (settings.get("preferred_youtube_channel_handle") or "").strip()
        if preferred_handle and not token_path:
            preferred_name = settings.get("preferred_youtube_channel_name") or preferred_handle
            raise HTTPException(status_code=400, detail=f"고정 업로드 채널이 아직 로컬에 연동되지 않았습니다: {preferred_name}")
        result = youtube_upload_service.upload_video(
            file_path=video_path,
            title=title,
            description=description,
            tags=merged_tags[:15],
            category_id="22",
            privacy_status=final_privacy,
            publish_at=final_publish_at,
            token_path=token_path,
        )

        if not result or not result.get("id"):
            raise HTTPException(500, (result or {}).get("error", "YouTube 업로드 실패"))

        video_id = result.get("id")

        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                youtube_upload_service.set_thumbnail(
                    video_id=video_id,
                    thumbnail_path=thumbnail_path,
                    token_path=token_path,
                )
            except Exception as thumb_err:
                print(f"[YouTube] Thumbnail set skipped: {thumb_err}")

        db.update_project_setting(project_id, "youtube_video_id", video_id)
        db.update_project_setting(project_id, "is_published", 1)
        db.update_project_setting(project_id, "is_uploaded", 1)
        db.update_project_setting(project_id, "upload_source", upload_source)

        return {
            "status": "ok",
            "video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "upload_source": upload_source,
        }
    except Exception as e:
        print(f"YouTube upload error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": f"YouTube 업로드 실패: {str(e)}"}
    finally:
        if temp_dir_to_cleanup and os.path.isdir(temp_dir_to_cleanup):
            try:
                shutil.rmtree(temp_dir_to_cleanup, ignore_errors=True)
            except Exception:
                pass


@router.post("/projects/{project_id}/admin-publish-request")
async def request_admin_publish(project_id: int, background_tasks: BackgroundTasks):
    """Register a completed project for web-admin publishing without uploading to YouTube locally."""
    try:
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(404, "Project not found")

        settings = db.get_project_settings(project_id) or {}
        video_path = (
            _resolve_local_output_asset_path(settings.get("external_video_path"))
            or _resolve_local_output_asset_path(settings.get("video_path"))
        )

        try:
            bundle = drive_bundle_service.get_project_bundle(project_id)
        except Exception:
            bundle = {}

        if (bundle.get("video_file") or {}).get("id"):
            from services.project_publish_service import queue_project_for_admin_publish

            result = queue_project_for_admin_publish(
                project_id,
                requested_privacy=settings.get("upload_privacy") or "private",
                requested_publish_at=settings.get("upload_schedule_at"),
                requested_channel_id=settings.get("youtube_channel_id"),
            )
            return {
                "status": "ok",
                "mode": "queued",
                "message": "Registered in web-admin publishing queue.",
                **result,
            }

        if not video_path or not os.path.exists(video_path):
            raise HTTPException(404, "Uploadable rendered video file not found.")

        from services.sync_service import upload_and_sync_video

        db.update_project_setting(project_id, "admin_publish_ready", "0")
        db.update_project_setting(project_id, "admin_publish_status", "drive_sync_pending")
        background_tasks.add_task(upload_and_sync_video, project_id, video_path)
        return {
            "status": "ok",
            "mode": "sync_started",
            "message": "Drive sync started. Web-admin publishing queue will be updated after upload.",
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[AdminPublish] Request failed: {e}")
        return {"status": "error", "error": str(e)}
