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
            base_master = "Vertical cinematic animation, 9:16 aspect ratio, 1080x1920, STRONG CONTINUOUS CAMERA MOVEMENT, subtle parallax depth effect, soft volumetric lighting, atmospheric particles, high quality anime webtoon style, dramatic color grading, film grain subtle, highly dynamic motion, characters breathing"
            
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
        import time
        from config import config
        
        target_size = "480x832" # Force Vertical 9:16 for Shorts
        use_image_path = image_path
        
        try:
            with Image.open(image_path) as img:
                w, h = img.size
                target_ratio = 480 / 832
                img_ratio = w / h
                
                # [강제 ZOOM-TO-FILL 크롭] 
                # 비율이 다르면 넘어가는 부분을 잘라내어 위/아래/좌/우 까맣게 나오는 레터박스 방지
                if abs(img_ratio - target_ratio) > 0.01:
                    if img_ratio > target_ratio:
                        # 이미지가 가로로 더 김 (좌우 크롭)
                        new_w = int(h * target_ratio)
                        left = (w - new_w) // 2
                        img_cropped = img.crop((left, 0, left + new_w, h))
                    else:
                        # 이미지가 세로로 더 김 (위아래 크롭)
                        new_h = int(w / target_ratio)
                        top = (h - new_h) // 2
                        img_cropped = img.crop((0, top, w, top + new_h))
                else:
                    img_cropped = img.copy()
                
                # 정확히 480x832 해상도로 리사이징
                img_cropped = img_cropped.resize((480, 832), Image.Resampling.LANCZOS)
                
                temp_filename = f"crop_{int(time.time()*1000)}.png"
                use_image_path = os.path.join(config.OUTPUT_DIR, temp_filename)
                img_cropped.save(use_image_path, "PNG")
                print(f"📐 [Video Gen] Zoom-to-Fill: Image cropped strictly to 9:16 (480x832) to prevent black bars.")
        except Exception as e:
            print(f"❌ [Video Gen] Cropping error, using original: {e}")
            pass

        with open(use_image_path, "rb") as img_file:
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

    async def generate_image(self, prompt: str, aspect_ratio: str = "1:1", num_outputs: int = 1):
        """
        Replicate를 사용하여 이미지 생성
        - 졸라맨/윔피 스타일: flux-dev (50스텝, anatomy 지시 준수율 높음)
        - 그 외: flux-schnell (빠름)
        """
        if not self.check_api_key():
            raise Exception("Replicate API Key is missing.")

        print(f"🎨 [Image Gen] Replicate: {prompt[:100]}... (Aspect Ratio: {aspect_ratio})")

        # 스타일 감지 (Wimpy Kid 키워드)
        wimpy_keywords = ["wimpy", "stick figure", "stickman", "졸라맨", "cyan tunic", "cyan long-sleeved", "teal tunic", "cyan sleeveless", "teal-blue hoodie", "teal blue hoodie"]
        is_wimpy = any(kw in prompt.lower() for kw in wimpy_keywords)

        # prompt_char(흰 배경 단일 캐릭터) vs prompt_en(통합 씬) 구분
        # "pure white background" + "isolated" 가 있으면 단일 캐릭터 이미지 → 팔 제한 적용
        # "youtube educational" 또는 씬 프롬프트면 → 팔 제한 없이 씬 품질만 강화
        is_char_only = (
            "pure white background" in prompt.lower() and
            "isolated" in prompt.lower()
        )
        is_scene_prompt = "youtube educational" in prompt.lower() or not is_char_only

        # 공통 suffix
        suffix = ", no text, no words, no letters"

        if is_wimpy and is_char_only:
            # 단일 캐릭터 이미지: 팔 제한 강제 적용
            arm_prefix = (
                "EXACTLY TWO ARMS ONLY. NO EXTRA ARMS. NO EXTRA HANDS. NO THIRD ARM. "
                "BOTH ARMS VISIBLE AND ATTACHED TO SHOULDERS. "
            )
            wimpy_suffix = (
                ", the character has exactly one left arm and one right arm, total two arms and two hands only,"
                " no third arm, no fourth arm, no duplicate limbs, no extra appendages,"
                " each arm connects directly from shoulder,"
                " full-body minimalist cartoon stick-figure, bold black outlines, flat 2D vector,"
                " white circular head with stylized dark brown swept-back hair with a slight front flip"
                " (NOT black hair NOT white hair NOT blue hair NOT teal hair — strictly DARK BROWN),"
                " dot eyes, wide arc smile,"
                " vibrant teal-blue hoodie with front pocket, long black sleeves with black cuffs,"
                " solid black trousers, white sneakers with black trim and laces,"
                " small rounded fist-shaped hands with solid black outlines (NOT white balls NOT white circles),"
                " pure white background, no background elements"
            )
            enforced_prompt = arm_prefix + prompt + suffix + wimpy_suffix
        elif is_wimpy and is_scene_prompt:
            # 통합 씬 이미지: 팔 제한 없이 씬 품질 강화
            scene_suffix = (
                ", YouTube educational cartoon style, clean thick black outlines,"
                " flat bold vibrant colors, layered scene depth, warm vibrant lighting"
            )
            enforced_prompt = prompt + suffix + scene_suffix
        else:
            enforced_prompt = prompt + suffix

        # 윔피 스타일은 Flux Dev (품질 우선), 그 외는 Flux Schnell
        if is_wimpy:
            model = "black-forest-labs/flux-dev"
            input_data = {
                "prompt": enforced_prompt,
                "aspect_ratio": aspect_ratio,
                "output_format": "png",
                "num_outputs": num_outputs,
                "num_inference_steps": 40,
                "guidance": 5.0
            }
        else:
            model = "black-forest-labs/flux-schnell"
            input_data = {
                "prompt": enforced_prompt,
                "aspect_ratio": aspect_ratio,
                "output_format": "png",
                "num_outputs": num_outputs
            }

        try:
            loop = asyncio.get_event_loop()
            output = await loop.run_in_executor(None, self._run_replicate_model, model, input_data)

            if output and len(output) > 0:
                # URL 리스트로 반환됨 -> 첫 번째 결과 다운로드
                url = str(output[0])
                image_bytes = await self._download_video(url)
                if image_bytes:
                    return [image_bytes] # List of bytes consistent with gemini_service
            return None
        except Exception as e:
            print(f"❌ [Replicate Image Gen] Error: {e}")
            raise e

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
