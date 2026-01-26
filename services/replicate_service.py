import replicate
import os
import aiohttp
import asyncio
from config import config

class ReplicateService:
    def __init__(self):
        self.api_key = os.getenv("REPLICATE_API_TOKEN") or config.REPLICATE_API_TOKEN if hasattr(config, 'REPLICATE_API_TOKEN') else None

    def check_api_key(self):
        if not self.api_key:
            # Fallback check
            self.api_key = os.getenv("REPLICATE_API_TOKEN")
        return bool(self.api_key)

    async def generate_video_from_image(self, image_path: str, prompt: str = "Cinematic video, high quality, smooth motion", motion_bucket_id: int = 127):
        """
        Replicate의 wan-video 모델을 사용하여 이미지 -> 비디오 생성
        """
        if not self.check_api_key():
            raise Exception("Replicate API Key is missing. Please set REPLICATE_API_TOKEN.")

        try:
            # [NEW] Wan-Video 파라미터 구성
            input_data = {
                "image": open(image_path, "rb"),
                "prompt": prompt,
                "go_fast": True,
                "num_frames": 81, # 81 frames for ~3.3s at 24fps
                "resolution": "720p",
                "sample_shift": 12,
                "optimize_prompt": False,
                "frames_per_second": 24
            }

            # 비동기 실행 (run_in_executor)
            loop = asyncio.get_event_loop()
            output = await loop.run_in_executor(None, self._run_replicate, input_data)
            
            # Replicate (Wan-Video) output은 보통 URL 리스트 또는 File object
            if output:
                video_url = output[0] if isinstance(output, list) else output
                # 다운로드
                return await self._download_video(str(video_url))
            else:
                raise Exception("No output from Replicate")

        except Exception as e:
            print(f"Replicate Error: {e}")
            raise e

    def _run_replicate(self, input_data):
        # [NEW] 최신 Wan 2.2 모델 적용 (User's request: 2.2)
        # 1.3/1.4 대비 획기적 성능, Cinematic 퀄리티
        return replicate.run(
            "wan-video/wan-2.2-i2v-fast",
            input=input_data
        )

    async def _download_video(self, url):
        """URL에서 비디오 다운로드 후 로컬 저장"""
        # [FIX] URL이 File object인 경우 처리
        if not url.startswith("http"):
             return url # 아마도 실제 데이터일 수 있음

        async with aiohttp.ClientSession() as session:
            async with session.get(str(url)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    return data
                else:
                    raise Exception(f"Failed to download video: {resp.status}")

replicate_service = ReplicateService()
