import httpx
import asyncio
import os
import time
from config import config

# ============================================================
# Akool Service
# - v1 API: Talking Avatar (기존 방식, Bearer Token)
# - v4 API: Image2Video with Seedance 1.5 Pro (신규, x-api-key)
#
# Seedance 모델 정보 (Akool AI Model Docs):
#   - value: "seedance-1-0-lite-i2v-250428"  ← 가장 저렴
#   - resolution: "480p"(3cr), "720p"(5cr), "1080p"(10cr)
#   - duration: 5 or 10 seconds
#   - status: 1=pending, 2=processing, 3=done, 4=failed
#   - API Docs: https://docs.akool.com/ai-tools-suite/image2video
# ============================================================

class AkoolService:
    def __init__(self):
        self.base_url = "https://openapi.akool.com/api/v1"
        self.base_url_v4 = "https://openapi.akool.com/api/open/v4"
        self._token = None
        self._token_expiry = 0

    @property
    def client_id(self):
        return getattr(config, 'AKOOL_CLIENT_ID', None) or os.getenv("AKOOL_CLIENT_ID", "")

    @property
    def client_secret(self):
        return getattr(config, 'AKOOL_CLIENT_SECRET', None) or os.getenv("AKOOL_CLIENT_SECRET", "")

    @property
    def api_key(self):
        """v4 API에서 사용. AKOOL_API_KEY 또는 AKOOL_CLIENT_ID를 fallback으로 사용"""
        return (
            getattr(config, 'AKOOL_API_KEY', None) or
            os.getenv("AKOOL_API_KEY", "") or
            self.client_id
        )

    # ==========================================
    # [기존] v1 API - Bearer Token 인증
    # ==========================================

    async def get_token(self):
        """API Key를 사용하여 액세스 토큰 획득 (필요한 경우)"""
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
                status = data.get("video_status")
                if status == 3:
                    return "success", data.get("video_url")
                elif status == 4:
                    return "failed", None
                else:
                    return "processing", None
            return "error", None

    async def generate_talking_avatar(self, local_image_path: str, local_audio_path: str):
        """로컬 파일을 사용하여 아바타 영상 생성 (업로드 → 요청 → 폴링)"""
        print(f"🎭 [Akool] Starting Talking Avatar for {os.path.basename(local_image_path)}")

        image_url = await self._upload_temp_file(local_image_path)
        audio_url = await self._upload_temp_file(local_audio_path)

        if not image_url or not audio_url:
            raise Exception("Failed to host assets for Akool.")

        job_id = await self.create_talking_photo(image_url, audio_url)
        print(f"⏳ [Akool] Job Created: {job_id}. Waiting for render...")

        for _ in range(60):
            await asyncio.sleep(5)
            status, video_url = await self.get_job_status(job_id)
            if status == "success":
                print(f"✅ [Akool] Render Complete: {video_url}")
                return await self._download_file(video_url)
            elif status == "failed":
                raise Exception("Akool rendering failed.")

        raise Exception("Akool rendering timed out.")

    # ==========================================
    # [신규] v4 API - Seedance 1.5 Pro I2V
    # x-api-key 헤더 방식 (토큰 불필요)
    # ==========================================

    async def generate_seedance_video(
        self,
        local_image_path: str,
        prompt: str = "Cinematic video, smooth camera movement, high quality",
        duration: int = 5,
        resolution: str = "720p",
        model_value: str = "seedance-1-0-lite-i2v-250428"
    ):
        """
        Akool v4 API를 통해 Seedance 1.5 Pro로 Image-to-Video 생성
        
        Args:
            local_image_path: 로컬 이미지 파일 경로
            prompt: 영상 생성 프롬프트
            duration: 영상 길이 (5 or 10)
            resolution: 해상도 "480p"(저렴), "720p"(기본), "1080p"
            model_value: Akool 모델 식별자
                - "seedance-1-0-lite-i2v-250428" (Seedance Lite, 가장 저렴)
                - "AkoolImage2VideoFastV1" (Akool 기본)
        
        Returns:
            bytes: 다운로드된 비디오 데이터
        """
        if not self.api_key:
            raise Exception("Akool API Key가 설정되지 않았습니다. .env에 AKOOL_API_KEY 또는 AKOOL_CLIENT_ID를 설정해주세요.")

        print(f"🎬 [Seedance] Starting I2V: {os.path.basename(local_image_path)}, {resolution}, {duration}s")

        # 1. 이미지 업로드 (URL 필요)
        image_url = await self._upload_temp_file(local_image_path)
        if not image_url:
            raise Exception("이미지 업로드 실패 (Seedance 사용 불가)")

        print(f"📤 [Seedance] Image uploaded: {image_url}")

        # 2. 영상 생성 요청 (v4 API)
        create_url = f"{self.base_url_v4}/image2Video/createBySourcePrompt"
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }

        negative_prompt = (
            "blurry, distorted, missing fingers, unnatural pose, extra limbs, "
            "bad anatomy, low quality, flickering, subtitles, logo, static, worst quality, ugly"
        )

        payload = {
            "image_url": image_url,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "extend_prompt": True,
            "resolution": resolution,
            "video_length": duration,
            "model": model_value,   # Seedance 모델 지정
            "webhookurl": ""
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(create_url, json=payload, headers=headers)
            resp_data = resp.json()
            print(f"📊 [Seedance] Create Response: {resp.status_code} → {resp_data}")

            if resp.status_code != 200 or resp_data.get("code") != 1000:
                raise Exception(f"Seedance 생성 요청 실패: {resp_data.get('msg', resp.text)}")

            job_id = resp_data.get("data", {}).get("_id")
            if not job_id:
                raise Exception(f"Seedance job ID를 받지 못했습니다: {resp_data}")

        print(f"⏳ [Seedance] Job ID: {job_id}. 폴링 시작...")

        # 3. 결과 폴링 (최대 10분)
        result_url = f"{self.base_url_v4}/image2Video/resultsByIds"
        for attempt in range(120):  # 5초 간격 × 120 = 10분
            await asyncio.sleep(5)

            async with httpx.AsyncClient(timeout=30.0) as client:
                poll_resp = await client.post(
                    result_url,
                    json={"_ids": job_id},
                    headers=headers
                )
                poll_data = poll_resp.json()

            results = poll_data.get("data", {}).get("result", [])
            if not results:
                print(f"  ⏳ [Seedance] Attempt {attempt+1}: No result yet...")
                continue

            item = results[0]
            status = item.get("status")

            if status == 3:  # 완료
                video_url = item.get("video_url")
                print(f"✅ [Seedance] Complete! Video URL: {video_url}")
                return await self._download_file(video_url)

            elif status == 4:  # 실패
                raise Exception(f"Seedance 렌더링 실패: {item}")

            else:
                if attempt % 6 == 0:  # 30초마다 로그
                    print(f"  🔄 [Seedance] Attempt {attempt+1}: status={status} (1=pending, 2=processing, 3=done)")

        raise Exception("Seedance 렌더링 타임아웃 (10분 초과)")

    # ==========================================
    # [기존] 내부 유틸리티
    # ==========================================

    async def _upload_temp_file(self, file_path: str):
        """임시 파일 호스팅 (catbox.moe 사용)"""
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

    # ==========================================
    # [기존] 이전 버전 I2V (하위 호환)
    # ==========================================

    async def create_image_to_video(self, image_url: str, prompt: str = None, duration: int = 5):
        """Akool Image-to-Video 생성 (구 버전, 하위 호환)"""
        token = await self.get_token()
        if not token:
            raise Exception("Akool Authentication failed.")

        url = f"{self.base_url}/content/video/create"
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "image_url": image_url,
            "prompt": prompt or "cinematic motion, high quality",
            "duration": duration,
            "model": "wan_2.1" if prompt else "general"
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                return resp.json().get("data", {}).get("_id")
            else:
                print(f"⚠️ [Akool] I2V Create failed: {resp.text}")
                raise Exception(f"Akool I2V Error: {resp.text}")

    async def generate_i2v(self, local_image_path: str, prompt: str):
        """로컬 파일 → Akool I2V 영상 생성 (구 버전, 하위 호환)"""
        print(f"🎞️ [Akool] Starting Image-to-Video for {os.path.basename(local_image_path)}")

        image_url = await self._upload_temp_file(local_image_path)
        if not image_url:
            raise Exception("Failed to host image for Akool I2V")

        job_id = await self.create_image_to_video(image_url, prompt)
        print(f"⏳ [Akool] I2V Job {job_id} Started. Waiting...")

        for _ in range(60):
            await asyncio.sleep(5)
            status, video_url = await self.get_job_status(job_id)

            if status == "success":
                print(f"✅ [Akool] I2V Render Complete: {video_url}")
                return await self._download_file(video_url)
            elif status == "failed":
                raise Exception("Akool I2V rendering failed.")

        raise Exception("Akool I2V timed out.")


akool_service = AkoolService()
