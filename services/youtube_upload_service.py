
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

    def get_authenticated_service(self, token_path: str = None):
        """인증된 YouTube API 서비스 객체 반환 (채널별 토큰 지원)"""
        credentials = None
        
        # 1. 사용할 토큰 파일 결정
        # token_path가 없으면 기본 'token.pickle' 사용
        target_token_file = token_path if token_path else self.token_file
        
        # 2. 토큰 로드
        if os.path.exists(target_token_file):
            with open(target_token_file, "rb") as token:
                credentials = pickle.load(token)

        # 3. 토큰 유효성 검사 및 갱신/신규 발급
        if not credentials or not credentials.valid:
            needs_login = True
            if credentials and credentials.expired and credentials.refresh_token:
                try:
                    from google.auth.exceptions import RefreshError
                    credentials.refresh(Request())
                    needs_login = False
                except RefreshError:
                    print("Refresh token is invalid (invalid_grant). Re-authenticating...")
                    needs_login = True
            
            if needs_login:
                if not os.path.exists(self.client_secret_file):
                    raise FileNotFoundError("client_secret.json 파일이 없습니다. OAuth 설정을 먼저 해주세요.")
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.client_secret_file, self.scopes
                )
                # 로컬 서버를 통해 인증 프로세스 진행
                credentials = flow.run_local_server(port=0)

            # 4. 갱신/발급된 토큰 저장
            # 폴더가 없으면 생성 (tokens/ 등)
            os.makedirs(os.path.dirname(target_token_file) if os.path.dirname(target_token_file) else ".", exist_ok=True)
            
            with open(target_token_file, "wb") as token:
                pickle.dump(credentials, token)

        return build(self.api_service_name, self.api_version, credentials=credentials)

    def upload_video(
        self,
        file_path: str,
        title: str,
        description: str,
        tags: list = [],
        category_id: str = "22",
        privacy_status: str = "private",
        publish_at: str = None,
        token_path: str = None # [NEW] 인증 토큰 경로
    ) -> dict:
        """비디오 업로드 (채널 지정 가능)"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

        # 지정된 토큰(채널)으로 인증
        youtube = self.get_authenticated_service(token_path)

        status_body = {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False
        }
        
        if publish_at:
            status_body["privacyStatus"] = "private"
            status_body["publishAt"] = publish_at

        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags,
                "categoryId": category_id
            },
            "status": status_body
        }

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

        print(f"업로드 시작: {title}")
        response = request.execute()
        print(f"업로드 완료: https://youtu.be/{response['id']}")
        
        return response

    def set_thumbnail(self, video_id: str, thumbnail_path: str, token_path: str = None):
        """비디오 썸네일 설정 (채널 지정 가능)"""
        if not os.path.exists(thumbnail_path):
            print(f"썸네일 파일을 찾을 수 없습니다: {thumbnail_path}")
            return None

        youtube = self.get_authenticated_service(token_path)
        
        request = youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path)
        )
        response = request.execute()
        print(f"썸네일 설정 완료: {video_id}")
        return response

    def update_video_privacy(self, video_id: str, privacy_status: str = "public", token_path: str = None):
        """비디오 공개 범위 수정"""
        youtube = self.get_authenticated_service(token_path)

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
