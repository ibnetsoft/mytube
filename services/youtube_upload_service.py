
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
        self.scopes = [
            "https://www.googleapis.com/auth/youtube.upload", 
            "https://www.googleapis.com/auth/youtube",
            "https://www.googleapis.com/auth/drive.file"
        ]
        self.api_service_name = "youtube"
        self.api_version = "v3"

    def get_authenticated_service(self, token_path: str = None, interactive: bool = False, proxy: str = None):
        """인증된 YouTube API 서비스 객체 반환 (채널별 토큰 및 프록시 우회 지원)"""
        credentials = None
        
        # 1. 사용할 토큰 파일 결정
        # token_path가 없으면 기본 'token.pickle' 사용
        target_token_file = token_path if token_path else self.token_file
        
        # 2. 토큰 로드
        if os.path.exists(target_token_file):
            try:
                with open(target_token_file, "rb") as token:
                    credentials = pickle.load(token)
            except Exception as e:
                print(f"Failed to load existing token from {target_token_file}: {e}")
                credentials = None

        # 프록시 설정 적용 (http 클라이언트 래핑)
        http_client = None
        if proxy:
            import httplib2
            # proxy 형식 예: "http://username:password@ip:port" 또는 "http://ip:port"
            # httplib2는 proxy_info 객체를 받음
            try:
                print(f"[Proxy] Routing YouTube API requests through proxy: {proxy}")
                import urllib.parse
                parsed = urllib.parse.urlparse(proxy)
                proxy_type = httplib2.ProxyInfo.PROXY_TYPE_HTTP
                if parsed.scheme == 'socks5':
                    proxy_type = httplib2.ProxyInfo.PROXY_TYPE_SOCKS5
                elif parsed.scheme == 'socks4':
                    proxy_type = httplib2.ProxyInfo.PROXY_TYPE_SOCKS4
                
                proxy_info = httplib2.ProxyInfo(
                    proxy_type=proxy_type,
                    proxy_host=parsed.hostname,
                    proxy_port=parsed.port or (80 if parsed.scheme == 'http' else 443),
                    proxy_user=parsed.username,
                    proxy_pass=parsed.password
                )
                http_client = httplib2.Http(proxy_info=proxy_info, timeout=60)
            except Exception as proxy_err:
                print(f"[Proxy Error] Failed to parse proxy {proxy}: {proxy_err}")

        # 3. 토큰 유효성 검사 및 갱신/신규 발급
        is_authenticated = False
        if credentials and credentials.valid:
            is_authenticated = True
        elif credentials and credentials.expired and credentials.refresh_token:
            try:
                print(f"Refreshing expired token for {target_token_file}...")
                # 프록시를 적용해 갱신 요청을 전송
                from google.auth.transport.requests import Request
                import google.auth.transport.urllib3
                import urllib3
                
                request_runner = Request()
                if proxy:
                    proxy_manager = urllib3.ProxyManager(proxy)
                    request_runner = google.auth.transport.urllib3.Request(proxy_manager)
                    
                credentials.refresh(request_runner)
                # 갱신된 토큰 즉시 저장
                with open(target_token_file, "wb") as token:
                    pickle.dump(credentials, token)
                is_authenticated = True
            except Exception as e:
                print(f"Refresh token is invalid (expired or revoked): {e}")
                is_authenticated = False
        
        if not is_authenticated:
            if not interactive:
                # 비대화형 모드(백그라운드 작업 등)에서는 브라우저를 띄우지 않고 예러 발생
                chan_name = os.path.basename(target_token_file).replace("token_", "").replace(".pickle", "")
                raise Exception(f"YouTube 인증이 만료되었거나 연동되지 않았습니다. [설정 > 채널관리]에서 '{chan_name}' 로그인을 먼저 진행해주세요.")

            if not os.path.exists(self.client_secret_file):
                raise FileNotFoundError("client_secret.json 파일이 없습니다. OAuth 설정을 먼저 해주세요.")
            
            flow = InstalledAppFlow.from_client_secrets_file(
                self.client_secret_file, self.scopes
            )
            # 로컬 서버를 통해 인증 프로세스 진행
            credentials = flow.run_local_server(port=0)

            # 4. 갱신/발급된 토큰 저장
            os.makedirs(os.path.dirname(target_token_file) if os.path.dirname(target_token_file) else ".", exist_ok=True)
            with open(target_token_file, "wb") as token:
                pickle.dump(credentials, token)

        # build 시 http_client 주입하여 API 호출이 프록시를 거치도록 함
        if http_client:
            # credentials가 http를 래핑하도록 연결
            import google.auth.transport.requests
            authorized_http = google.auth.transport.requests.AuthorizedHttp(credentials, http=http_client)
            return build(self.api_service_name, self.api_version, http=authorized_http)
            
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
        token_path: str = None, # [NEW] 인증 토큰 경로
        proxy: str = None # [NEW] 프록시 정보
    ) -> dict:
        """비디오 업로드 (채널 지정 가능)"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

        # 지정된 토큰(채널) 및 프록시로 인증
        youtube = self.get_authenticated_service(token_path, proxy=proxy)

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

    def set_thumbnail(self, video_id: str, thumbnail_path: str, token_path: str = None, proxy: str = None):
        """비디오 썸네일 설정 (채널 지정 가능)"""
        if not os.path.exists(thumbnail_path):
            print(f"썸네일 파일을 찾을 수 없습니다: {thumbnail_path}")
            return None

        youtube = self.get_authenticated_service(token_path, proxy=proxy)
        
        request = youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path)
        )
        response = request.execute()
        print(f"썸네일 설정 완료: {video_id}")
        return response

    def update_video_privacy(self, video_id: str, privacy_status: str = "public", token_path: str = None, proxy: str = None):
        """비디오 공개 범위 수정"""
        youtube = self.get_authenticated_service(token_path, proxy=proxy)

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
