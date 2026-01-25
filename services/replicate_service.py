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

    async def generate_video_from_image(self, image_path: str, prompt: str = None, motion_bucket_id: int = 127):
        """
        Replicate의 stability-ai/stable-video-diffusion 모델을 사용하여 이미지 -> 비디오 생성
        """
        if not self.check_api_key():
            raise Exception("Replicate API Key is missing. Please set REPLICATE_API_TOKEN.")

        try:
            # 1. 파일 업로드 또는 URL 준비
            # Replicate는 URL 또는 파일 객체를 받음
            input_data = {
                "input_image": open(image_path, "rb"),
                "motion_bucket_id": motion_bucket_id, # 1-255, higher = more motion
                "cond_aug": 0.02,
                "decoding_t": 7,
                "frames_per_second": 24
            }

            # 비동기적으로 실행하고 싶지만 replicate python 클라이언트는 동기 호출이 기본
            # run_in_executor로 감싸서 실행
            loop = asyncio.get_event_loop()
            output = await loop.run_in_executor(None, self._run_replicate, input_data)
            
            # output is usually a list of URLs, e.g. ["https://...mp4"]
            if output:
                video_url = output
                # 다운로드
                return await self._download_video(video_url)
            else:
                raise Exception("No output from Replicate")

        except Exception as e:
            print(f"Replicate Error: {e}")
            raise e

    def _run_replicate(self, input_data):
        # Model: stability-ai/stable-video-diffusion:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b
        # Or luma/ray? SVD is safer/cheaper standard.
        return replicate.run(
            "stability-ai/stable-video-diffusion:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
            input=input_data
        )

    async def _download_video(self, url):
        """URL에서 비디오 다운로드 후 로컬 저장"""
        async with aiohttp.ClientSession() as session:
            async with session.get(str(url)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    return data
                else:
                    raise Exception(f"Failed to download video: {resp.status}")

replicate_service = ReplicateService()
