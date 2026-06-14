import os
import requests
import threading
import database as db
from config import config
from services.google_drive_service import google_drive_service
from services.auth_service import auth_service

def upload_and_sync_video(project_id: int, local_video_path: str):
    """최종 렌더링 완료 비디오를 구글 드라이브에 업로드하고 공유 링크를 Supabase DB에 기록하여 어드민 웹과 동기화"""
    try:
        project = db.get_project(project_id)
        if not project:
            print(f"[Sync] Project {project_id} not found")
            return
            
        email = project.get("employee_email") or auth_service.get_user_email()
        if not email:
            print("[Sync] No email associated with project/session")
            return
            
        print(f"[Sync] Starting Google Drive upload for project {project_id} ({local_video_path})...")
        
        # 1. Google Drive 업로드
        drive_url = google_drive_service.upload_video_to_drive(local_video_path)
        if not drive_url:
            print("[Sync] Google Drive upload failed")
            return
            
        print(f"[Sync] Google Drive upload success. URL: {drive_url}")
        
        # 2. Supabase profiles에서 이메일 매칭 UUID 조회
        supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not supabase_url or not supabase_key:
            print("[Sync] Supabase credentials missing")
            return
            
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json"
        }
        
        profile_url = f"{supabase_url.rstrip('/')}/rest/v1/profiles?email=eq.{email}&select=id"
        # Suppress insecure request warnings
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        r = requests.get(profile_url, headers=headers, timeout=10, verify=False)
        if r.status_code != 200 or not r.json():
            print(f"[Sync] Failed to find profile UUID for email {email}")
            return
            
        user_id = r.json()[0]["id"]
        
        # 3. Supabase publishing_requests 테이블에 기록 추가 (어드민 연동)
        publish_url = f"{supabase_url.rstrip('/')}/rest/v1/publishing_requests"
        payload = {
            "user_id": user_id,
            "video_url": drive_url,
            "metadata": {
                "project_id": project_id,
                "project_name": project.get("name"),
                "topic": project.get("topic")
            },
            "status": "pending"
        }
        
        r_publish = requests.post(publish_url, headers=headers, json=payload, timeout=10, verify=False)
        if r_publish.status_code in [200, 201]:
            print(f"[Sync] Successfully published video link to Supabase for admin review!")
            db.update_project_setting(project_id, "is_uploaded", 1)
        else:
            print(f"[Sync] Failed to insert publishing request: {r_publish.text}")
            
    except Exception as e:
        print(f"[Sync Error] Failed to upload/sync: {e}")

def start_upload_and_sync_background(project_id: int, local_video_path: str):
    """백그라운드 스레드에서 업로드 및 동기화 작업 시작"""
    threading.Thread(
        target=upload_and_sync_video,
        args=(project_id, local_video_path),
        daemon=True
    ).start()
