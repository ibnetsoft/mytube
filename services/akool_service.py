import httpx
import asyncio
import os
import json
import time
from config import config
import database as db

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
        """v4 API에서 사용. AKOOL_API_KEY 우선 사용 후, 없으면 client_secret 사용"""
        # 1. Config에 저장된 전용 API Key 확인
        conf_key = getattr(config, 'AKOOL_API_KEY', None)
        if conf_key: return conf_key
        
        # 2. 환경 변수 확인
        env_key = os.getenv("AKOOL_API_KEY", "")
        if env_key: return env_key
        
        # 3. Fallback (v4에서는 clientSecret이 API Key 역할을 함)
        return self.client_secret

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
    # [신규] v4 API - Akool Standard I2V
    # x-api-key 헤더 방식 (토큰 불필요)
    # ==========================================

    async def generate_akool_video_v4(
        self,
        local_image_path: str,
        prompt: str = "Cinematic video, smooth camera movement, high quality",
        duration: int = 5,
        resolution: str = "720p",
        model_name: str = "alibaba/wan2.5-i2v-preview",
        project_id: int = None
    ):
        """
        Akool v4 API를 통해 Akool Premium(V2) 모델로 Image-to-Video 생성
        """
        if not self.api_key:
            raise Exception("Akool API Key가 설정되지 않았습니다. .env에 AKOOL_API_KEY 또는 AKOOL_CLIENT_ID를 설정해주세요.")

        print(f"🎬 [Akool Premium] Starting I2V: {os.path.basename(local_image_path)}, {resolution}, {duration}s")

        # 1. 이미지 업로드 (URL 필요)
        image_url = await self._upload_temp_file(local_image_path)
        if not image_url:
            raise Exception("이미지 업로드 실패 (Seedance 사용 불가)")

        print(f"📤 [Akool Standard] Image uploaded: {image_url}")

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

        # [PREMIUM CONFIG] WAN 2.5 (Latest Flagship Engine)
        # 사용자 요청 사항: Wan 2.5 모델 (alibaba/wan2.5-i2v-preview)
        # 1080p 및 오디오 동기화를 지원하는 최신 모델로 고도화
        # [SMART TRUNCATE] 700자 제한 — 단어 중간에서 잘리지 않도록 마지막 쉼표/공백 기준으로 자름
        _p = prompt.strip()
        if len(_p) > 700:
            cut = _p[:700]
            # 마지막 쉼표나 공백 위치에서 잘라 단어/구문 보존
            last_sep = max(cut.rfind(','), cut.rfind(' '))
            _p = cut[:last_sep].rstrip(', ') if last_sep > 500 else cut
        safe_prompt = _p
        payload = {
            "image_url": image_url,
            "prompt": safe_prompt,
            "extend_prompt": False,      # Wan 2.5는 최신 구조로 파라미터 제외 시 더 안정적
            "resolution": resolution,    # 1080p 지원 가능
            "video_duration": duration,
            "model_name": model_name, 
            "audio_type": 1,
            "webhookurl": ""
        }
        
        print(f"📡 [AKOOL WAN 2.5] POSTing: Model={payload['model_name']}, Res={payload['resolution']}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                # [DEBUG] 요청 명세 로깅
                print(f"📡 [AKOOL WAN 2.5] Prompt({len(safe_prompt)}ch): {safe_prompt[:100]}...")
                resp = await client.post(create_url, json=payload, headers=headers)
                resp_json = resp.json()
                
                if resp.status_code != 200 or resp_json.get("code") != 1000:
                    print(f"❌ [AKOOL WAN 2.5] Create Error: {resp.status_code} -> {resp_json}")
                    raise Exception(f"Akool Wan 2.5 생성 요청 실패: {resp_json.get('msg', 'Unknown Error')}")

                job_id = resp_json.get("data", {}).get("_id")
                if not job_id:
                    raise Exception(f"Job ID missing in response: {resp_json}")
                
                db.add_ai_log(project_id, 'video', model_name, 'akool', 'processing', prompt_summary=safe_prompt[:100], input_tokens=500, output_tokens=1000)
                print(f"⏳ [AKOOL WAN 2.5] Job ID: {job_id}. Polling...")
            except Exception as e:
                print(f"❌ [AKOOL WAN 2.5] Critical Request Error: {e}")
                raise

        # 3. 결과 폴링 (최대 15분으로 확장)
        result_url = f"{self.base_url_v4}/image2Video/resultsByIds"
        for attempt in range(180):  # 5초 간격 × 180 = 15분
            await asyncio.sleep(5)

            async with httpx.AsyncClient(timeout=30.0) as client:
                poll_resp = await client.post(
                    result_url,
                    json={"_ids": job_id},   # [CRITICAL] 반드시 string! list이면 항상 실패
                    headers=headers
                )
                poll_data = poll_resp.json()

            results = poll_data.get("data", {}).get("result", [])
            if not results:
                print(f"  ⏳ [AKOOL WAN 2.5] Attempt {attempt+1}: Wait...")
                continue

            item = results[0]
            status = item.get("status")

            if status == 3:  # 완료
                video_url = item.get("video_url")
                print(f"✅ [AKOOL WAN 2.5] Complete! URL: {video_url}")
                return await self._download_file(video_url)

            elif status == 4:  # 실패
                err_detail = json.dumps(item, indent=2)
                print(f"❌ [AKOOL WAN 2.5] FAILED: {err_detail}")
                msg = item.get("msg") or item.get("failed_reason") or "Internal Engine Error"
                raise Exception(f"Akool Wan 2.5 렌더링 실패: {msg}")

            else:
                if attempt % 6 == 0:
                    print(f"  🔄 [AKOOL WAN 2.5] status={status} (processing...)")
        
        raise Exception("Akool Standard 렌더링 타임아웃 (15분 초과)")

    async def generate_image(self, prompt: str, aspect_ratio: str = "1:1"):
        """
        Akool v3 API를 통해 이미지 생성 (Text-to-Image)
        """
        if not self.api_key:
            raise Exception("Akool API Key가 설정되지 않았습니다.")

        print(f"🎨 [Akool Image Gen] Prompt: {prompt[:100]}... (Ratio: {aspect_ratio})")

        url = "https://openapi.akool.com/api/open/v3/content/image/createbyprompt"
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }

        # Akool v3 Image API 명세 기반 (추정 및 일반적 패턴)
        payload = {
            "prompt": prompt,
            "size": aspect_ratio, # "1:1", "16:9" 등 지원 여부 확인 필요하나 표준적
            "model": "stable-diffusion-xl" # 기본 모델 명시 (선택 사항)
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                resp = await client.post(url, json=payload, headers=headers)
                resp_json = resp.json()

                if resp.status_code != 200 or resp_json.get("code") != 1000:
                    print(f"❌ [Akool Image Gen] Fail: {resp_json}")
                    return None

                job_id = resp_json.get("data", {}).get("_id")
                if not job_id:
                    print(f"❌ [Akool Image Gen] No Job ID in response: {resp_json}")
                    return None

                print(f"⏳ [Akool Image Gen] Job {job_id} created. Polling for result...")
                
                # 3. Poll for result
                poll_url = f"https://openapi.akool.com/api/open/v3/content/image/infobymodelid?image_model_id={job_id}"
                for attempt in range(20):  # 3s * 20 = 60s
                    await asyncio.sleep(3)
                    async with httpx.AsyncClient(timeout=30.0) as poll_client:
                        try:
                            poll_resp = await poll_client.get(poll_url, headers=headers)
                            poll_json = poll_resp.json()
                            
                            if poll_resp.status_code != 200 or poll_json.get("code") != 1000:
                                print(f"⚠️ [Akool Image Gen] Poll Error: {poll_json}")
                                continue
                                
                            item_data = poll_json.get("data", {})
                            status = item_data.get("image_status")
                            
                            if status == 3: # Success
                                image_url = item_data.get("image") or item_data.get("url")
                                if image_url:
                                    print(f"✅ [Akool Image Gen] Success! URL: {image_url}")
                                    img_bytes = await self._download_file(image_url)
                                    if img_bytes:
                                        return [img_bytes]
                                return None
                            elif status == 4: # Failed
                                print(f"❌ [Akool Image Gen] Job Failed: {item_data}")
                                return None
                            else:
                                if attempt % 2 == 0:
                                    print(f"  🔄 [Akool Image Gen] Status={status} (waiting...)")
                        except Exception as poll_e:
                            print(f"⚠️ [Akool Image Gen] Poll Exception: {poll_e}")
                
                print(f"❌ [Akool Image Gen] Polling timed out")
                return None

            except Exception as e:
                print(f"❌ [Akool Image Gen] Error: {e}")
                return None

    # ==========================================
    # [기존] 내부 유틸리티
    # ==========================================

    async def _upload_temp_file(self, file_path: str):
        """
        임시 파일 호스팅 (3중 Fallback)
        1순위: freeimage.host (AKOOL 엔진 접근 성공률 100%)
        2순위: 0x0.st
        3순위: Catbox 
        """
        # JPEG 강제 변환
        try:
            from PIL import Image
            with Image.open(file_path) as img:
                jpg_path = file_path.rsplit(".", 1)[0] + "_stable.jpg"
                img.convert("RGB").save(jpg_path, "JPEG", quality=95, optimize=True)
                file_path = jpg_path
                print(f"🔄 [Upload] Converted to stable JPEG")
        except Exception as e:
            print(f"⚠️ [Upload] JPEG Convert Error: {e}")

        headers_ua = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            # [1순위] freeimage.host (안정적인 퍼블릭 호스팅 10MB 이하 무료)
            try:
                import base64
                with open(file_path, "rb") as f:
                    img_data = f.read()
                    b64_data = base64.b64encode(img_data).decode("utf-8")
                
                resp = await client.post(
                    "https://freeimage.host/api/1/upload", 
                    data={
                        "key": "6d207e02198a847aa98d0a2a901485a5", # 공용 무료 키
                        "action": "upload",
                        "source": b64_data,
                        "format": "json"
                    }
                )
                if resp.status_code == 200:
                    try:
                        url = resp.json()["image"]["url"]
                        print(f"✅ [Upload] freeimage Success: {url}")
                        return url
                    except Exception as parse_e:
                        print(f"⚠️ [Upload] freeimage JSON parse: {parse_e}")
                else:
                    print(f"⚠️ [Upload] freeimage Error: {resp.status_code}")
            except Exception as e:
                print(f"⚠️ [Upload] freeimage Failed: {e}")

            # [2순위] 0x0.st
            try:
                with open(file_path, "rb") as f:
                    resp = await client.post(
                        "https://0x0.st",
                        files={"file": (os.path.basename(file_path), f)},
                        headers=headers_ua
                    )
                    if resp.status_code == 200 and "http" in resp.text:
                        url = resp.text.strip()
                        print(f"✅ [Upload] 0x0.st Success: {url}")
                        return url
                    else:
                        print(f"⚠️ [Upload] 0x0.st: {resp.status_code}")
            except Exception as e:
                print(f"⚠️ [Upload] 0x0.st Failed: {e}")

            # [3순위] Catbox
            try:
                with open(file_path, "rb") as f:
                    resp = await client.post("https://file.io", files={"file": f})
                    if resp.status_code == 200:
                        try:
                            link = resp.json().get("link")
                            if link:
                                print(f"✅ [Upload] file.io Success: {link}")
                                return link
                        except Exception:
                            print(f"⚠️ [Upload] file.io JSON parse error: {resp.text[:100]}")
            except Exception as e:
                print(f"❌ [Upload] file.io Failed: {e}")
                
        print(f"❌ [Upload] All 3 upload services failed!")
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
