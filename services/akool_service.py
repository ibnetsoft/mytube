import httpx
import asyncio
import os
import time
from config import config

class AkoolService:
    def __init__(self):
        self.base_url = "https://openapi.akool.com/api/v1"
        self._token = None
        self._token_expiry = 0

    @property
    def client_id(self):
        return config.AKOOL_CLIENT_ID

    @property
    def client_secret(self):
        return config.AKOOL_CLIENT_SECRET

    async def get_token(self):
        """API Key를 사용하여 액세스 토큰 획득 (필요한 경우)"""
        # Akool API는 x-api-key 헤더를 직접 쓰거나, 토큰을 발급받아야 할 수 있음.
        # 최신 문서에 따르면 auth/token 엔드포인트를 통해 발급받는 방식이 권장됨.
        if self._token and time.time() < self._token_expiry:
            return self._token

        url = f"{self.base_url}/auth/token"
        payload = {
            "clientId": self.client_id,
            "clientSecret": self.client_secret
        }
        
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    self._token = data.get("token")
                    # 만료 시간 설정 (기본 24시간인 경우가 많음, 안전하게 설정)
                    self._token_expiry = time.time() + 3600 
                    return self._token
                else:
                    print(f"❌ [Akool] Token Error: {resp.text}")
                    return None
            except Exception as e:
                print(f"❌ [Akool] Auth Exception: {e}")
                return None

    async def create_talking_photo(self, image_url: str, audio_url: str, resolution: str = "720"):
        """Talking Photo 영상 생성 요청"""
        token = await self.get_token()
        if not token:
            raise Exception("Akool Authentication failed.")

        url = f"{self.base_url}/content/talking_photo/create"
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "talking_photo_url": image_url,
            "audio_url": audio_url,
            "resolution": resolution
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                return resp.json().get("data", {}).get("_id")
            else:
                raise Exception(f"Akool API Error: {resp.text}")

    async def get_job_status(self, job_id: str):
        """작업 상태 확인 및 결과 URL 반환"""
        token = await self.get_token()
        url = f"{self.base_url}/content/talking_photo/infodetail?_id={job_id}"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                # status: 1(대기), 2(진행), 3(완료), 4(실패)
                status = data.get("video_status")
                if status == 3:
                    return "success", data.get("video_url")
                elif status == 4:
                    return "failed", None
                else:
                    return "processing", None
            return "error", None

    async def generate_talking_avatar(self, local_image_path: str, local_audio_path: str):
        """로컬 파일을 사용하여 아바타 영상 생성 (업로드 -> 요청 -> 폴링)"""
        print(f"🎭 [Akool] Starting Talking Avatar for {os.path.basename(local_image_path)}")
        
        # 1. 파일 업로드 (Akool은 URL을 요구하므로 임시 호스팅 필요)
        # TODO: 실제 운영 환경에서는 GCS, S3 또는 전용 스토리지 사용 권장
        image_url = await self._upload_temp_file(local_image_path)
        audio_url = await self._upload_temp_file(local_audio_path)
        
        if not image_url or not audio_url:
            raise Exception("Failed to host assets for Akool.")

        # 2. 작업 생성
        job_id = await self.create_talking_photo(image_url, audio_url)
        print(f"⏳ [Akool] Job Created: {job_id}. Waiting for render...")

        # 3. 폴링 (최대 5분)
        for _ in range(60):
            await asyncio.sleep(5)
            status, video_url = await self.get_job_status(job_id)
            if status == "success":
                print(f"✅ [Akool] Render Complete: {video_url}")
                return await self._download_file(video_url)
            elif status == "failed":
                raise Exception("Akool rendering failed.")
                
        raise Exception("Akool rendering timed out.")

    async def _upload_temp_file(self, file_path: str):
        """임시 파일 호스팅 (catbox.moe 사용 예시)"""
        # [NOTICE] 보안이 중요한 프로젝트라면 자체 GCS/S3 버킷 사용 권장
        url = "https://catbox.moe/user/api.php"
        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(file_path, "rb") as f:
                files = {"fileToUpload": (os.path.basename(file_path), f)}
                data = {"reqtype": "fileupload"}
                resp = await client.post(url, data=data, files=files)
                if resp.status_code == 200:
                    return resp.text.strip()
        return None

    async def _download_file(self, url: str):
        """결과물 다운로드 및 바이트 반환"""
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.read()
        return None

akool_service = AkoolService()
