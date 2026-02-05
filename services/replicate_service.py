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

    async def generate_video_from_image(self, image_path: str, prompt: str = "Cinematic video, high quality, smooth motion", duration: float = 5.0, method: str = "standard"):
        """
        Replicate의 wan-video 모델을 사용하여 이미지 -> 비디오 생성
        - standard: 5초 생성 (Wan 2.1 한계)
        - extend: 5초 생성 후 마지막 프레임 따서 3초 추가 생성 (총 8초)
        - slowmo: 5초 생성 후 보간법으로 8초로 늘림
        """
        if not self.check_api_key():
            raise Exception("Replicate API Key is missing.")

        print(f"🎬 [Video Gen] Method: {method}, Image: {os.path.basename(image_path)}")

        try:
            if method == "extend":
                # 1. First 5 seconds
                first_part_data = await self._generate_basic(image_path, prompt, duration=5.0)
                first_path = self._save_temp_video(first_part_data, "part1.mp4")

                # 2. Extract last frame
                from services.video_service import video_service
                last_frame_path = first_path.replace(".mp4", "_last.png")
                if video_service.extract_last_frame(first_path, last_frame_path):
                    # 3. Generate next 3 seconds from last frame
                    second_part_data = await self._generate_basic(last_frame_path, prompt, duration=3.0)
                    second_path = self._save_temp_video(second_part_data, "part2.mp4")

                    # 4. Merge
                    final_path = first_path.replace("part1.mp4", "extended_8s.mp4")
                    video_service.concatenate_videos([first_path, second_path], final_path)
                    
                    with open(final_path, "rb") as f:
                        return f.read()
                return first_part_data

            elif method == "slowmo":
                # 1. Standard 5s generation
                video_data = await self._generate_basic(image_path, prompt, duration=5.0)
                temp_path = self._save_temp_video(video_data, "before_slowmo.mp4")
                
                # 2. Apply FFmpeg Slow-mo (Interpolation)
                from services.video_service import video_service
                output_path = temp_path.replace(".mp4", "_slowmo_8s.mp4")
                video_service.apply_slow_mo(temp_path, output_path, speed_ratio=0.625) # 5/8 = 0.625
                
                with open(output_path, "rb") as f:
                    return f.read()

            else: # Standard 5s
                return await self._generate_basic(image_path, prompt, duration=duration)

        except Exception as e:
            print(f"Replicate Service Error: {e}")
            raise e

    async def _generate_basic(self, image_path: str, prompt: str, duration: float = 5.0):
        """기본 Wan 2.1 생성 (최대 81프레임)"""
        fps = 16 if duration > 3.5 else 24
        num_frames = int(duration * fps)
        if num_frames > 81: num_frames = 81

        input_data = {
            "image": open(image_path, "rb"),
            "prompt": prompt,
            "num_frames": num_frames,
            "frames_per_second": fps,
            "resolution": "720p",
            "go_fast": True
        }

        loop = asyncio.get_event_loop()
        output = await loop.run_in_executor(None, self._run_replicate, input_data)
        
        if output:
            url = output[0] if isinstance(output, list) else output
            return await self._download_video(str(url))
        return None

    def _save_temp_video(self, data, filename):
        path = os.path.join(config.OUTPUT_DIR, f"temp_{int(time.time())}_{filename}")
        with open(path, "wb") as f:
            f.write(data)
        return path

    def _run_replicate(self, input_data):
        return replicate.run(
            "wan-video/wan-2.1-i2v-720p", # Use standard 720p model
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
