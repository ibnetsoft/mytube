import replicate
import os
import aiohttp
import asyncio
import time
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
            # [USER MASTER SETTING APPLIED]
            base_master = "Vertical cinematic animation, 9:16 aspect ratio, 1080x1920, smooth camera movement, subtle parallax depth effect, soft volumetric lighting, atmospheric particles, high quality anime webtoon style, dramatic color grading, film grain subtle, slow cinematic motion, emotional pacing"
            
            if prompt:
                # 씬별 특정 프롬프트가 있으면 마스터와 결합
                base_prompt = f"{base_master}, {prompt}"
            else:
                base_prompt = base_master
            
            # Add strong motion keywords if not present
            motion_keywords = ["motion", "moving", "pan", "zoom", "walking", "running", "flying", "dynamic"]
            if not any(k in base_prompt.lower() for k in motion_keywords):
                base_prompt += ", dynamic movement, 4k"

            if method == "slowmo":
                # For 8s slowmo (interpolated from 5s), we need the source 5s to have clear movement.
                # Avoid "slow motion" in prompt because we are doing it in post-process.
                # Instead ask for "fluid motion".
                base_prompt += ", fluid motion, high frame rate style"

            if method == "extend":
                # 1. First 5 seconds
                first_part_data = await self._generate_basic(image_path, base_prompt, duration=5.0)
                first_path = self._save_temp_video(first_part_data, "part1.mp4")

                # 2. Extract last frame
                from services.video_service import video_service
                last_frame_path = first_path.replace(".mp4", "_last.png")
                if video_service.extract_last_frame(first_path, last_frame_path):
                    # 3. Generate next 3 seconds from last frame
                    second_part_data = await self._generate_basic(last_frame_path, base_prompt, duration=3.0)
                    second_path = self._save_temp_video(second_part_data, "part2.mp4")

                    # 4. Merge
                    final_path = first_path.replace("part1.mp4", "extended_8s.mp4")
                    video_service.concatenate_videos([first_path, second_path], final_path)
                    
                    with open(final_path, "rb") as f:
                        return f.read()
                return first_part_data

            elif method == "slowmo":
                # 1. Standard 5s generation
                video_data = await self._generate_basic(image_path, base_prompt, duration=5.0)
                temp_path = self._save_temp_video(video_data, "before_slowmo.mp4")
                
                # 2. Apply FFmpeg Slow-mo (Interpolation)
                from services.video_service import video_service
                output_path = temp_path.replace(".mp4", "_slowmo_8s.mp4")
                # 5s -> 8s means slowing down to 62.5% speed.
                video_service.apply_slow_mo(temp_path, output_path, speed_ratio=0.625) 
                
                with open(output_path, "rb") as f:
                    return f.read()

            else: # Standard 5s
                return await self._generate_basic(image_path, base_prompt, duration=duration)

        except Exception as e:
            print(f"Replicate Service Error: {e}")
            raise e

    async def _generate_basic(self, image_path: str, prompt: str, duration: float = 5.0):
        """기본 Wan 2.1 생성 (wavespeedai/wan-2.1-i2v-480p)"""
        from PIL import Image
        
        # [NEW] Detect Aspect Ratio for Wan 2.1 (480p)
        target_size = "832x480" # Default Landscape (16:9 approx)
        try:
            with Image.open(image_path) as img:
                w, h = img.size
                if h > w:
                    target_size = "480x832" # Vertical (9:16 approx)
                    print(f"📐 [Video Gen] Vertical Image Detected. Using {target_size}")
        except: pass

        with open(image_path, "rb") as img_file:
            input_data = {
                "image": img_file,
                "prompt": prompt,
                "size": target_size,
                "duration": 5, # Standard 5s
                "fast_mode": "Balanced"
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
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return replicate.run(
                    "wavespeedai/wan-2.1-i2v-480p",
                    input=input_data
                )
            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "throttled" in error_str or "rate limit" in error_str:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 5 + float(input_data.get("duration", 5)) # Initial wait: ~10s
                        print(f"⚠️ [Replicate] Rate Limit Hit (429). Waiting {wait_time}s before retry {attempt+1}/{max_retries}...")
                        time.sleep(wait_time)
                        continue
                print(f"❌ [Replicate] Error: {e}")
                raise e

    # [NEW] Audio Generation Methods
    async def generate_music(self, prompt: str, duration: int = 8):
        """Generate BGM using Meta's MusicGen"""
        if not self.check_api_key(): raise Exception("Replicate API Key missing")
        
        print(f"🎵 [Audio Gen] Music: {prompt} ({duration}s)")
        input_data = {
            "prompt": prompt,
            "duration": duration,
            "model_version": "stereo-large"
        }
        
        loop = asyncio.get_event_loop()
        output = await loop.run_in_executor(None, self._run_replicate_model, "meta/musicgen:b05b1dff1d8c6dc63d14b0cdb42135378dcb87f6373b0d3d341ede46e59e2b38", input_data)
        
        if output:
            return await self._download_video(str(output)) # Audio URL handling is same
        return None

    async def generate_sfx(self, prompt: str, duration: int = 5):
        """Generate SFX using AudioLDM"""
        if not self.check_api_key(): raise Exception("Replicate API Key missing")
        
        print(f"🔊 [Audio Gen] SFX: {prompt}")
        input_data = {
            "text": prompt,
            "duration": str(duration),
            "n_candidates": 1,
            "guidance_scale": 2.5
        }
        
        loop = asyncio.get_event_loop()
        # AudioLDM model
        output = await loop.run_in_executor(None, self._run_replicate_model, "haoheliu/audio-ldm:b613999cd14778be19f729227568165d77682de94132cc225c57b497b0959828", input_data)
        
        if output:
            return await self._download_video(str(output))
        return None

    async def outpaint_image(self, image_file, mask_file, prompt: str):
        """
        Extend/Outpaint image using SDXL Inpainting
        - image_file: File-like object or URL
        - mask_file: File-like object or URL (White=Inpaint, Black=Keep)
        """
        if not self.check_api_key(): raise Exception("Replicate API Key missing")
        
        print(f"🎨 [Image Gen] Outpainting: {prompt[:50]}...")

        # SDXL Inpainting Model
        model = "stability-ai/stable-diffusion-inpainting:c28b92a7ecd66eee1e7d03f0b0c608034f54817a5840e6c5u2e6522778377721" 
        # Using SD 2.0 Inpainting as it's stable and specific for inpainting tasks
        # Or switch to SDXL if needed for higher res: "diffusers/sdxl-inpainting-0.1"
        # Let's use a very standard one:
        
        input_data = {
            "prompt": prompt,
            "image": image_file,
            "mask": mask_file,
            "num_inference_steps": 30,
            "guidance_scale": 7.5,
            "scheduler": "K_EULER_ANCESTRAL"
        }
        
        loop = asyncio.get_event_loop()
        output = await loop.run_in_executor(None, self._run_replicate_model, model, input_data)
        
        if output and len(output) > 0:
            # Output is usually a list of URLs
            return str(output[0])
        return None

    def _run_replicate_model(self, model_id, input_data):
        """Generic runner for any model"""
        try:
            return replicate.run(model_id, input=input_data)
        except Exception as e:
            print(f"❌ [Replicate] Model Error ({model_id}): {e}")
            raise e

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
