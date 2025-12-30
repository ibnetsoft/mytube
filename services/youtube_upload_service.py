
import os
import pickle
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

class YouTubeUploadService:
    def __init__(self):
        from config import config
        self.client_secret_file = os.path.join(config.BASE_DIR, "client_secret.json")
        self.token_file = os.path.join(config.BASE_DIR, "token.pickle")
        self.scopes = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"]
        self.api_service_name = "youtube"
        self.api_version = "v3"

    def get_authenticated_service(self):
        """인증된 YouTube API 서비스 객체 반환"""
        credentials = None
        
        # 저장된 토큰이 있는지 확인
        if os.path.exists(self.token_file):
            with open(self.token_file, "rb") as token:
                credentials = pickle.load(token)

        # 토큰이 없거나 유효하지 않으면 새로 인증
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                if not os.path.exists(self.client_secret_file):
                    raise FileNotFoundError("client_secret.json 파일이 없습니다. OAuth 설정을 먼저 해주세요.")
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.client_secret_file, self.scopes
                )
                credentials = flow.run_local_server(port=0)

            # 토큰 저장
            with open(self.token_file, "wb") as token:
                pickle.dump(credentials, token)

        return build(self.api_service_name, self.api_version, credentials=credentials)

    def upload_video(
        self,
        file_path: str,
        title: str,
        description: str,
        tags: list = [],
        category_id: str = "22",  # 22: People & Blogs
        privacy_status: str = "private", # public, unlisted, private
        publish_at: str = None # ISO 8601 format (e.g., 2023-12-25T10:00:00Z)
    ) -> dict:
        """비디오 업로드 (예약 발행 지원)"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

        youtube = self.get_authenticated_service()

        status_body = {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False
        }
        
        # 예약 발행 설정 (반드시 private이어야 함)
        if publish_at:
            status_body["privacyStatus"] = "private"
            status_body["publishAt"] = publish_at

        body = {
            "snippet": {
                "title": title[:100], # 제목 길이 제한
                "description": description[:5000], # 설명 길이 제한
                "tags": tags,
                "categoryId": category_id
            },
            "status": status_body
        }

        # 미디어 업로드 설정 (재시도 기능 포함)
        media = MediaFileUpload(
            file_path,
            chunksize=-1, 
            resumable=True
        )

        request = youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media
        )

        response = None
        
        # 업로드 실행
        print(f"업로드 시작: {title}")
        response = request.execute()
        print(f"업로드 완료: https://youtu.be/{response['id']}")
        
        return response

    def set_thumbnail(self, video_id: str, thumbnail_path: str):
        """비디오 썸네일 설정"""
        if not os.path.exists(thumbnail_path):
            print(f"썸네일 파일을 찾을 수 없습니다: {thumbnail_path}")
            return None

        youtube = self.get_authenticated_service()
        
        request = youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path)
        )
        response = request.execute()
        print(f"썸네일 설정 완료: {video_id}")
        return response

    def update_video_privacy(self, video_id: str, privacy_status: str = "public"):
        """비디오 공개 범위 수정 (private -> public 등)"""
        youtube = self.get_authenticated_service()

        body = {
            "id": video_id,
            "status": {
                "privacyStatus": privacy_status
            }
        }

        request = youtube.videos().update(
            part="status",
            body=body
        )
        response = request.execute()
        print(f"공개 범위 수정 완료 ({privacy_status}): {video_id}")
        return response

# 싱글톤 인스턴스
youtube_upload_service = YouTubeUploadService()
