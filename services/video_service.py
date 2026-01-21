"""
영상 합성 서비스
- MoviePy + FFmpeg를 사용한 이미지+음성 합성
"""
import os
from typing import List, Optional, Union
from config import config


class VideoService:
    def __init__(self):
        self.output_dir = config.OUTPUT_DIR

    def create_slideshow(
        self,
        images: List[str],
        audio_path: Optional[str] = None,
        output_filename: str = "output.mp4",
        duration_per_image: Union[float, List[float]] = 5.0,
        fps: int = 24,
        resolution: tuple = (1920, 1080), # 16:9 Long-form Standard
        title_text: Optional[str] = None,
        project_id: Optional[int] = None,
        subtitles: Optional[List[dict]] = None,
        subtitle_settings: Optional[dict] = None,

        background_video_url: Optional[str] = None,
        thumbnail_path: Optional[str] = None,  # [NEW] Baked-in Thumbnail
        fade_in_flags: Optional[List[bool]] = None  # [NEW] Fade-in effect per image
    ) -> str:
        """
        이미지 슬라이드쇼 영상 생성 (시네마틱 프레임 적용)
        """
        try:
            from moviepy.editor import (
                ImageClip, concatenate_videoclips,
                AudioFileClip, CompositeVideoClip, VideoFileClip, vfx
            )
            import numpy as np
            import requests # For downloading background video
        except ImportError:
            raise ImportError("moviepy 또는 requests가 설치되지 않았습니다.")

        clips = []
        temp_files = [] # 나중에 삭제할 임시 파일들

        current_duration = 0.0
        
        # [NEW] Background Video Logic
        video = None # Base video clip
        
        # Audio Load First to determine duration
        audio = None
        if audio_path and os.path.exists(audio_path):
             audio = AudioFileClip(audio_path)
             
        # [NEW] Check for Template Image (Overlay)
        template_path = None
        try:
            # We need to import db here to avoid circular dependencies if not already imported
            import database as db
            
            p_settings = db.get_project_settings(project_id)
            if p_settings and p_settings.get('template_image_url'):
                t_url = p_settings.get('template_image_url')
                # Convert URL to local path
                # e.g. /static/templates/xxx.png -> static/templates/xxx.png
                if t_url.startswith("/static/"):
                    rel_path = t_url.lstrip("/")
                    # If running from app root, 'static' is usually at root.
                    # config.STATIC_DIR is usually absolute path.
                    # Let's map it: /static/templates -> config.STATIC_DIR/templates
                    # Assuming t_url format: /static/templates/filename
                    # config.STATIC_DIR usually points to the folder that is mounted as /static
                    # If config.STATIC_DIR is "C:/.../static", then we just join properly.
                    
                    # Safer way: split by /static/
                    part = t_url.split("/static/", 1)[1]
                    template_path = os.path.join(config.STATIC_DIR, part)
                    print(f"DEBUG: Using Template Image: {template_path}")
        except Exception as e:
            print(f"Failed to load template settings: {e}")
             
        if background_video_url:
             print(f"DEBUG: Using Background Video: {background_video_url}")
             try:
                 # 1. Download Video
                 local_video_path = os.path.join(self.output_dir, f"bg_video_{project_id or 'temp'}.mp4")
                 if not os.path.exists(local_video_path): # Cache check
                     print("Downloading video...")
                     r = requests.get(background_video_url, stream=True)
                     if r.status_code == 200:
                         with open(local_video_path, 'wb') as f:
                             for chunk in r.iter_content(chunk_size=8192):
                                 f.write(chunk)
                     else:
                         print(f"Failed to download video: {r.status_code}")
                 
                 # 2. Load & Process
                 if os.path.exists(local_video_path):
                     temp_files.append(local_video_path)
                     bg_clip = VideoFileClip(local_video_path)
                     
                     # 3. Loop to match Audio Duration
                     target_duration = audio.duration if audio else (len(images) * duration_per_image if images else 10)
                     
                     # Loop!
                     bg_clip = bg_clip.fx(vfx.loop, duration=target_duration)
                     
                     # 4. Resize/Crop to target resolution (1080p etc)
                     # Aspect Ratio Logic
                     target_w, target_h = resolution
                     
                     # Resize logic: Cover
                     bg_clip = bg_clip.resize(height=target_h) # Fit height first
                     if bg_clip.w < target_w:
                         bg_clip = bg_clip.resize(width=target_w) # Fit width if still small
                         
                     # Center Crop
                     bg_clip = bg_clip.crop(x1=bg_clip.w/2 - target_w/2, width=target_w, height=target_h)
                     
                     video = bg_clip
                     print(f"Background Video Prepared: {target_duration}s")
             
             except Exception as e:
                 print(f"Background Video Error: {e}")
                 # Fallback to images if failed
                 pass

        # Veo 통합을 위한 임시 헬퍼 (Sync -> Async 호출)
        def run_async(coro):
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 이미 루프가 돌고 있다면 (드문 경우), future로 실행해야 함.
                    # 하지만 여기서는 ThreadPoolExecutor 등에서 실행될 것이므로 새 루프 생성
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    res = new_loop.run_until_complete(coro)
                    new_loop.close()
                    return res
                return loop.run_until_complete(coro)
            except RuntimeError:
                # 루프가 없는 경우 (새 스레드 등)
                return asyncio.run(coro)

        from services.gemini_service import gemini_service
        import uuid

        for i, img_path in enumerate(images):
            if os.path.exists(img_path):
                # [CHANGED] Resize image to fill screen (no blur background)
                processed_img_path = self._resize_image_to_fill(img_path, resolution)
                temp_files.append(processed_img_path)
                
                clip = None
                
                # 초반 30초는 AI Video (Veo) 생성 시도 (비활성화)
                #         # 짧은 3~5초 영상 생성 요청 (Image-to-Video)
                #         video_bytes = run_async(gemini_service.generate_video(
                #             prompt="cinematic movement, slow motion", # 구체적인 프롬프트가 없으므로 일반적인 것 사용
                #             image_path=processed_img_path,
                #             duration_seconds=int(duration_per_image) # Veo는 보통 6초 고정이 많지만 요청 시도
                #         ))
                #         
                #         if video_bytes:
                #             # 임시 비디오 파일 저장
                #             temp_video_path = os.path.join(self.output_dir, f"veo_{uuid.uuid4()}.mp4")
                #             with open(temp_video_path, "wb") as f:
                #                 f.write(video_bytes)
                #             temp_files.append(temp_video_path)
                #             
                #             # 비디오 클립 로드 (소리 제거)
                #             from moviepy.editor import VideoFileClip
                #             veo_clip = VideoFileClip(temp_video_path).without_audio()
                #             
                #             # 길이 및 크기 조정
                #             # Veo 영상이 16:9가 아닐 수 있으므로 resize/crop 필요할 수 있음
                #             if resolution:
                #                 # 비율 유지하여 리사이즈 후 중앙 크롭 (VideoService._create_cinematic_frame 로직과 유사하게 처리 필요하지만)
                #                 # 여기서는 간단히 resize만 시도 (찌그러질 수 있음 - 개선 필요시 수정)
                #                 veo_clip = veo_clip.resize(newsize=resolution)
                #                 
                #             # 속도/길이 맞추기
                #             if veo_clip.duration < duration_per_image:
                #                 # 너무 짧으면 루프 또는 마지막 프레임 정지? 일단은 속도 조절로 맞춤 (슬로우모션 효과)
                #                 # speed = original_duration / target_duration (느리게) -> vfx.speedx
                #                 # 하지만 복잡하므로, 일단 길이만 명시 (부족하면 검은화면 될 수 있음)
                #                 pass 
                #             else:
                #                 veo_clip = veo_clip.subclip(0, duration_per_image)
                #                 
                #             clip = veo_clip.set_duration(duration_per_image)
                #             print(" -> Veo Video Generated Successfully")
                #     except Exception as e:
                #         print(f"Veo Generation Failed: {e}")
                #         clip = None

                # Get specific duration for this image
                dur = duration_per_image[i] if isinstance(duration_per_image, list) else duration_per_image

                # Veo 실패하거나 30초 이후면 줌인 효과 (Ken Burns) 사용
                if clip is None:
                    if current_duration < 30.0:
                        # 30초 내인데 실패 시 -> 줌인
                         clip = self._create_zoom_clip(processed_img_path, dur, resolution)
                    else:
                        # 30초 이후 -> 정지 화상 (또는 줌인 계속? 일단 정지)
                        clip = ImageClip(processed_img_path).set_duration(dur)

                # [NEW] Apply fade-in effect if requested
                if fade_in_flags and i < len(fade_in_flags) and fade_in_flags[i]:
                    fade_duration = min(1.0, dur * 0.3)  # Max 1초 또는 클립 길이의 30%
                    clip = clip.fadein(fade_duration)
                    print(f"  → Fade-in applied to image #{i+1} ({fade_duration:.2f}s)")

                clips.append(clip)
                current_duration += dur

        if not clips and video is None:
            raise ValueError("유효한 이미지나 배경 동영상이 없습니다")

        # 클립 연결 (이미지가 있을 때만)
        if clips:
            video_slideshow = concatenate_videoclips(clips, method="compose")
            if video:
                 # 배경 영상이 메인이므로, 슬라이드쇼는 무시하거나 오버레이? 
                 # 기획상: 반복영상 모드에선 이미지 안씀. 
                 # 하지만 이미지가 있으면 배경 영상 위에 얹을수도 있음. 
                 # 현재 로직: 배경 영상이 있으면 그것을 메인으로 씀. 이미지가 있으면 무시?
                 # -> 기획 수정: 배경 영상 모드일 땐 이미지가 없을 가능성이 높음.
                 # 만약 이미지가 있다면? 일단 배경 영상을 덮어쓰기보단, 배경 영상이 우선순위가 되도록 video 변수 유지
                 pass 
            else:
                 video = video_slideshow
        
        # 만약 video가 여전히 None이면 에러 (위 체크에서 걸러지겠지만 안전장치)
        if video is None:
             raise ValueError("영상 생성 실패 (소스 없음)")

        # 오디오 추가
        if audio_path and os.path.exists(audio_path):
            audio = AudioFileClip(audio_path)

            # 오디오 길이에 맞춰 비디오 조절
            # 오디오 길이에 맞춰 비디오 조절
            # [FIX] MoviePy's audio.duration might be inaccurate for variable bitrate or speed-changed audio.
            # Use pydub to verify actual duration if possible.
            check_duration = audio.duration
            try:
                import pydub
                check_duration = pydub.AudioSegment.from_file(audio_path).duration_seconds
            except:
                pass
            
            # Adjust video duration to match audio duration
            if audio.duration > video.duration:
                # Video is shorter than audio, extend last image
                # [FIX] Use pydub duration for check if available, or rely on moviepy's audio.duration
                # Use a tolerance (e.g. 1.0s) because visual slideshow doesn't need to be frame-perfect to audio end
                if check_duration > video.duration + 1.0:
                    print(f"DEBUG: Audio ({check_duration:.2f}s) is significantly longer than video ({video.duration:.2f}s). Extending last clip.")
                    # 비디오가 짧으면 마지막 이미지 연장
                    last_dur = duration_per_image[-1] if isinstance(duration_per_image, list) else duration_per_image
                    last_clip = clips[-1].set_duration(
                        check_duration - video.duration + last_dur
                    )
                    clips[-1] = last_clip
                    video = concatenate_videoclips(clips, method="compose")
                else:
                    print(f"DEBUG: Video ({video.duration:.2f}s) roughly matches Audio ({check_duration:.2f}s). Skipping extension.")
                
            elif video.duration > audio.duration + 0.5:
                # [FIX] Video is significantly longer than audio (Sync Issue Safety Net)
                print(f"DEBUG: Video ({video.duration}s) is longer than Audio ({audio.duration}s). Trimming video.")
                video = video.subclip(0, audio.duration)

            video = video.set_audio(audio)
            
        # 제목 오버레이 추가
        if title_text:
            try:
                # 제목용 텍스트 이미지 생성 (노란색, 조금 더 크게)
                title_img_path = self._create_subtitle_image(
                    text=title_text,
                    width=video.w,
                    font_size=70,
                    font_color="#FFD700", # Gold
                    font_name=config.DEFAULT_FONT_PATH
                )
                if title_img_path:
                    temp_files.append(title_img_path)
                    title_clip = ImageClip(title_img_path)
                    # 상단에서 약간 띄움 (100px)
                    from moviepy.video.fx.margin import margin
                    # margin 함수 대신 position으로 조정
                    # ("center", 100) -> 상단 100px 지점
                    title_clip = title_clip.set_position(("center", 150)) 
                    title_clip = title_clip.set_duration(video.duration)
                    
                video = CompositeVideoClip([video, title_clip])
            except Exception as e:
                print(f"제목 생성 실패: {e}")

        # [NEW] Shorts Thumbnail Baking (Insert 0.1s at start)
        # This is done AFTER composition but BEFORE subtitles to avoid subtitle on thumbnail?
        # Actually better to do it AT THE END of composition so it's clean.
        # But wait, we want it explicitly as the first frame provided to YouTube.
        if thumbnail_path and os.path.exists(thumbnail_path):
            print(f"Baking thumbnail into video: {thumbnail_path}")
            try:
                # 1. Prepare Thumbnail Clip
                # Use _create_cinematic_frame to ensure it fits resolution beautifully
                baked_thumb_path = self._create_cinematic_frame(thumbnail_path, resolution)
                temp_files.append(baked_thumb_path)
                
                thumb_clip = ImageClip(baked_thumb_path).set_duration(0.1) # 0.1s duration
                
                # 2. Concatenate [Thumb] + [Main Video]
                # Note: Concatenating CompositeVideoClip with ImageClip works.
                # Use 'compose' method to ensure format consistency
                video = concatenate_videoclips([thumb_clip, video], method="compose")
                
                # Update Audio: The thumb has no audio. 
                # concatenate handles audio automatically (silence for thumb).
                
            except Exception as e:
                print(f"Thumbnail baking failed: {e}")

        # [NEW] 단일 패스 자막 합성 (Single-pass Subtitle Overlay)
        if subtitles:
            print(f"DEBUG: Overlaying {len(subtitles)} subtitles in single-pass...")
            subtitle_clips = []
            
            # 스타일 설정 추출
            s_settings = subtitle_settings or {}
            print(f"DEBUG_RENDER: video_service received s_settings: {s_settings}")
            f_size = s_settings.get("font_size", 80)
            f_color = s_settings.get("font_color", "white")
            f_name = s_settings.get("font", config.DEFAULT_FONT_PATH)
            s_style = s_settings.get("style_name", "Basic_White")
            s_stroke_color = s_settings.get("subtitle_stroke_color")
            s_stroke_width = s_settings.get("subtitle_stroke_width")

            for sub in subtitles:
                try:
                    txt_img_path = self._create_subtitle_image(
                        text=sub["text"],
                        width=video.w,
                        font_size=f_size,
                        font_color=f_color,
                        font_name=f_name,
                        style_name=s_style,
                        stroke_color=s_stroke_color,
                        stroke_width=s_stroke_width
                    )
                    
                    if txt_img_path:
                        # 임시파일 추적 (나중에 삭제)
                        temp_files.append(txt_img_path)
                        
                        txt_clip = ImageClip(txt_img_path)
                        
                        # [FIX] Position Logic (Custom Y or Default Safe Area)
                        # position_y: 0~100 (Top to Bottom %). If None, use default safe margin.
                        custom_y_pct = s_settings.get("position_y") 
                        
                        if custom_y_pct is not None:
                            # [FIX] Handle pixels vs percent
                            # If string contains 'px', treat as absolute pixels from Top
                            y_pos = None
                            if isinstance(custom_y_pct, str) and 'px' in custom_y_pct:
                                try:
                                    y_pos = int(float(custom_y_pct.replace('px', '')))
                                except:
                                    y_pos = None
                            
                            if y_pos is None:
                                # Treat as Percentage (Center of text box at Y%)
                                # But let's assume if user gives 90%, they mean 90% from top.
                                try:
                                    pct = float(custom_y_pct)
                                    center_y = int(video.h * (pct / 100.0))
                                    y_pos = center_y - (txt_clip.h // 2)
                                except:
                                    # Default if parse fails
                                    y_pos = None

                            if y_pos is None:
                                 # Fallback
                                 margin_bottom = int(video.h * 0.15)
                                 y_pos = video.h - txt_clip.h - margin_bottom
                        else:
                            # Default: Bottom Safe Area (15% margin)
                            margin_bottom = int(video.h * 0.15)
                            y_pos = video.h - txt_clip.h - margin_bottom

                        # Screen Boundary Safety (Don't go off screen)
                        # Top limit
                        y_pos = max(0, y_pos)
                        # Bottom limit
                        y_pos = min(video.h - txt_clip.h, y_pos)

                        txt_clip = txt_clip.set_position(("center", y_pos))
                        txt_clip = txt_clip.set_start(sub["start"])
                        txt_clip = txt_clip.set_duration(sub["end"] - sub["start"])
                        subtitle_clips.append(txt_clip)
                except Exception as e:
                    print(f"Error creating subtitle clip for text '{sub.get('text', '')}': {e}")
                    import traceback
                    traceback.print_exc()

            if subtitle_clips:
                video = CompositeVideoClip([video] + subtitle_clips)

        # 출력
        output_path = os.path.join(self.output_dir, output_filename)
        # Custom Logger for Progress Tracking
        logger = 'bar'
        if project_id:
            try:
                from services.progress import RenderLogger
                # Single-pass Rendering (0-100%)
                logger = RenderLogger(project_id, start_pct=0, end_pct=100)
            except Exception as e:
                print(f"Logger init failed: {e}")

        try:
            import datetime
            with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.datetime.now()}] calling writes_videofile code in video_service (720p safe mode)\n")

            # [FIX] Unique temp audio path to avoid conflicts/locks
            import uuid
            temp_audio_path = os.path.join(self.output_dir, f"temp_audio_{uuid.uuid4()}.mp3")
            
            # [OPTIMIZE] Multi-threaded rendering & Single-pass Logger
            num_threads = os.cpu_count() or 1
            
            video.write_videofile(
                output_path,
                fps=fps,
                codec="libx264",
                audio_codec="libmp3lame",
                threads=num_threads,
                preset="ultrafast", # Speed prioritized, Single-pass means we don't worry about multi-encoding compression loss
                temp_audiofile=temp_audio_path,
                remove_temp=False,
                logger=logger
            )
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.datetime.now()}] Render Error: {e}\n{error_msg}\n")
            raise e

        # 리소스 정리
        video.close()
        for clip in clips:
            clip.close()
            
        # 임시 이미지 및 오디오 삭제
        for temp_path in temp_files:
            try:
                os.remove(temp_path)
            except:
                pass
        
        # [CLEANUP] 임시 오디오 파일 수동 삭제 시도 (실패 시 무시)
        try:
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
        except:
            pass # 파일이 잠겨있으면 넘어감 (OS가 나중에 처리하거나 다음 재부팅 시 정리)

        return output_path

    def _create_cinematic_frame(self, image_path: str, target_size: tuple, template_path: str = None) -> str:
        """
        이미지를 처리하여 시네마틱 프레임 생성 (블러 배경 + 중앙정렬)
        """
        from PIL import Image, ImageFilter, ImageEnhance
        import uuid
        
        target_w, target_h = target_size
        
        # 원본 열기
        img = Image.open(image_path).convert("RGBA")
        
        # 1. 배경 생성 (꽉 차게 리사이즈 + 블러 + 어둡게)
        bg = img.copy()
        
        # 비율 계산하여 꽉 차게 크롭/리사이즈 (Aspect Fill)
        bg_ratio = target_w / target_h
        img_ratio = img.width / img.height
        
        if img_ratio > bg_ratio:
            # 이미지가 더 납작함 -> 높이에 맞춤
            new_h = target_h
            new_w = int(new_h * img_ratio)
        else:
            # 이미지가 더 길쭉함 -> 너비에 맞춤
            new_w = target_w
            new_h = int(new_w / img_ratio)
            
        bg = bg.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # 중앙 크롭
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        bg = bg.crop((left, top, left + target_w, top + target_h))
        
        # 블러 및 밝기 조절
        bg = bg.filter(ImageFilter.GaussianBlur(radius=30))
        enhancer = ImageEnhance.Brightness(bg)
        bg = enhancer.enhance(0.6) # 40% 어둡게
        
        # 2. 전경 생성 (비율 유지하며 중앙 배치)
        # [Request] 좌우 여백 없이 꽉 채우기 (Fit Width), 하단 잘림 방지
        fg_max_w = target_w # 100% Width
        fg_max_h = target_h # 100% Height constraint (Aspect Ratio preserved by thumbnail)
        
        fg = img.copy()
        fg.thumbnail((fg_max_w, fg_max_h), Image.Resampling.LANCZOS)
        
        # 배경 중앙에 합성 (위로 10% 정도 올림 - 하단 UI 공간 확보)
        center_x = (target_w - fg.width) // 2
        center_y = (target_h - fg.height) // 2
        offset_y = int(target_h * 0.10) # 10% 상단 이동
        
        # 상단이 너무 잘리지 않도록 체크 (옵션)
        # if center_y - offset_y < 0: offset_y = center_y # 상단 딱 맞춤
        
        bg.paste(fg, (center_x, center_y - offset_y), fg)

        # [NEW] Template Overlay
        if template_path and os.path.exists(template_path):
            try:
                template = Image.open(template_path).convert("RGBA")
                template = template.resize((target_w, target_h), Image.Resampling.LANCZOS)
                bg.paste(template, (0, 0), template) # Alpha composite
            except Exception as e:
                print(f"Template Overlay Error: {e}")
        
        # [FIX] MoviePy 호환성을 위해 RGB로 변환 (알파 채널 제거)
        bg = bg.convert("RGB")

        # 저장
        output_path = os.path.join(self.output_dir, f"cinematic_{uuid.uuid4()}.jpg")
        bg.save(output_path, quality=95)
        
        return output_path

    def generate_aligned_subtitles(self, audio_path: str, script_text: str = None) -> List[dict]:
        """
        Faster-Whisper를 사용하여 오디오 자막 생성 (정확한 타이밍)
        """
        if not os.path.exists(audio_path):
            msg = f"Audio file not found: {audio_path}"
            print(msg)
            try:
                with open("debug_whisper_error.log", "a", encoding="utf-8") as f:
                    f.write(msg + "\n")
            except: pass
            return []

        try:
            from faster_whisper import WhisperModel
            # import torch # Not required for CPU inference with faster-whisper
        except ImportError as e:
            msg = f"faster-whisper not installed. fallback to simple. Error: {e}"
            print(msg)
            try:
                with open("debug_whisper_error.log", "a", encoding="utf-8") as f:
                    f.write(msg + "\n")
            except: pass
            return []

        print(f"Aligning subtitles for: {audio_path}")
        
        # 모델 로드 (첫 실행시 다운로드됨)
        # GPU 사용 가능시 cuda, 아니면 cpu
        # device = "cuda" if torch.cuda.is_available() else "cpu"
        # compute_type = "float16" if device == "cuda" else "int8"
        
        # 안전하게 CPU/int8로 시작 (호환성)
        device = "cpu"
        compute_type = "int8"
        
        try:
            # 모델 업그레이드 (tiny -> base or small) 및 한국어 명시
            # base가 tiny보다 훨씬 정확하며 속도도 준수함
            model = WhisperModel("base", device=device, compute_type=compute_type)
            
            # [IMPROVE] VAD 필터 켜기, 단어 타임스탬프 켜기 (정밀도 향상)
            segments, info = model.transcribe(
                audio_path, 
                beam_size=5, 
                language="ko", 
                word_timestamps=True, # 정밀 타이밍
                vad_filter=True,      # 무음 구간 제거 (환각 방지)
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            import re
            
            import re
            
            # Words flatten
            ai_words = []
            if hasattr(segments, '__iter__'):
                for segment in segments:
                    if segment.words:
                        ai_words.extend(segment.words)
                    else:
                        ai_words.append({
                            "start": segment.start,
                            "end": segment.end,
                            "word": segment.text.strip()
                        })
            
            # [FORCE ALIGNMENT] Script Text가 있는 경우, AI 타임스탬프에 텍스트를 강제 매핑
            final_words = []
            if script_text and len(script_text.strip()) > 10:
                print("Performing Script Alignment...")
                final_words = self._align_script_with_timestamps(script_text, ai_words)
            
            # 매칭 실패하거나 스크립트 없으면 AI 결과 그대로 사용
            if not final_words:
                final_words = [{"word": w.word, "start": w.start, "end": w.end} for w in ai_words]

            subtitles = []
            
            # Custom Segmentation Logic
            # Goal: Max ~40 chars, break on long pause (>0.8s) or punctuation
            current_sub = {"start": 0, "end": 0, "text": ""}
            MAX_CHARS = 40
            MAX_GAP = 0.8 # 말 빠르기 고려하여 조금 줄임

            if final_words:
                # 첫 단어 초기화
                current_sub["start"] = final_words[0]["start"]
                current_sub["end"] = final_words[0]["end"]
                current_sub["text"] = final_words[0]["word"]
                
                for i in range(1, len(final_words)):
                    word_obj = final_words[i]
                    word_text = word_obj["word"].strip()
                    
                    # Gap check
                    gap = word_obj["start"] - current_sub["end"]
                    
                    # Length check (temp)
                    temp_len = len(current_sub["text"]) + len(word_text) + 1
                    
                    # Break conditions
                    is_too_long = temp_len > MAX_CHARS
                    is_long_gap = gap > MAX_GAP
                    is_sentence_end = current_sub["text"].endswith(('.', '?', '!'))
                    
                    if is_long_gap or is_too_long or (is_sentence_end and len(current_sub["text"]) > 10):
                        # Commit current sub
                        # [FIX] Aggressive cleanup for unclosed brackets or artifacts
                        cleaned = re.sub(r'\([^)]*\)|\[[^\]]*\]|\*+[^*]+\*+', '', current_sub["text"])
                        cleaned = cleaned.replace('(', '').replace(')', '').replace('[', '').replace(']', '').strip()
                        if cleaned:
                            subtitles.append({
                                "start": current_sub["start"],
                                "end": current_sub["end"],
                                "text": cleaned
                            })
                        
                        # Start new sub
                        current_sub = {
                            "start": word_obj["start"],
                            "end": word_obj["end"],
                            "text": word_text
                        }
                    else:
                        # Append to current
                        current_sub["text"] += " " + word_text
                        current_sub["end"] = word_obj["end"]
                
                # Commit last sub
                cleaned = re.sub(r'\([^)]*\)|\[[^\]]*\]|\*+[^*]+\*+', '', current_sub["text"])
                cleaned = cleaned.replace('(', '').replace(')', '').replace('[', '').replace(']', '').strip()
                if cleaned:
                    subtitles.append({
                        "start": current_sub["start"],
                        "end": current_sub["end"],
                        "text": cleaned
                    })
            
            # [DEBUG] Log Final Subtitles
            try:
                with open("debug_alignment_REAL.txt", "a", encoding="utf-8") as f:
                    f.write(f"Final Subtitles (First 5): {subtitles[:5]}\n")
            except: pass

            print(f"Generated {len(subtitles)} subtitle segments (Cleaned & VAD & Aligned).")
            return subtitles
            
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            print(f"Whisper alignment failed: {e}")
            try:
                with open("debug_whisper_error.log", "w", encoding="utf-8") as f:
                    f.write(f"Error during generate_aligned_subtitles:\n{error_msg}")
            except:
                pass
            return []

    def _align_script_with_timestamps(self, script_text, ai_words):
        """
        Original Script의 단어들에 AI의 타임스탬프를 입히는 로직
        difflib을 사용하여 유사도 매칭 수행 (자모 분해 + Interpolation)
        """
        import difflib
        import re
        import unicodedata

        # 1. 스크립트 전처리 (지문 제거)
        clean_script = re.sub(r'\([^)]*\)|\[[^\]]*\]|\*\*.*?\*\*', '', script_text)
        script_tokens = clean_script.split()

        # [DEBUG] Log Inputs
        try:
            with open("debug_alignment_REAL.txt", "w", encoding="utf-8") as f:
                f.write(f"Script Tokens (First 20): {script_tokens[:20]}\n")
                f.write(f"AI Words (First 20): {[w.word for w in ai_words[:20]]}\n")
        except:
            pass
        
        # 2. AI Words 전처리
        ai_tokens_text = [w.word for w in ai_words]
        
        # 3. 매칭 준비 (Jamo Decomposition for better Hangul matching)
        def normalize_jamo(s):
            # NFD Normalization decomposes Hangul into Jamo
            # Remove non-alphanumeric, lower case
            s = re.sub(r'[^\w]', '', s).lower()
            return unicodedata.normalize('NFD', s)

        script_norm = [normalize_jamo(s) for s in script_tokens]
        ai_norm = [normalize_jamo(s) for s in ai_tokens_text]
        
        # [DEBUG] Log Norms
        try:
            with open("debug_alignment_REAL.txt", "a", encoding="utf-8") as f:
                f.write(f"Script Norm (6): {script_norm[6] if len(script_norm)>6 else 'N/A'}\n")
                f.write(f"AI Norm (6): {ai_norm[6] if len(ai_norm)>6 else 'N/A'}\n")
        except: pass
        
        matcher = difflib.SequenceMatcher(None, script_norm, ai_norm)
        
        aligned_pre = []
        
        # 4. Opcodes 처리 (Missing Words 확보)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                # 정확히 일치: 1:1 매핑
                for k in range(i2 - i1):
                    aligned_pre.append({
                        "word": script_tokens[i1 + k],
                        "start": ai_words[j1 + k].start,
                        "end": ai_words[j1 + k].end
                    })
            elif tag == 'replace':
                # 비슷: 구간 전체를 균등 배분
                len_script = i2 - i1
                len_ai = j2 - j1
                
                start_time = ai_words[j1].start
                end_time = ai_words[j2-1].end
                
                duration = end_time - start_time
                step = duration / len_script if len_script > 0 else 0
                
                for k in range(len_script):
                    aligned_pre.append({
                        "word": script_tokens[i1 + k],
                        "start": start_time + (step * k),
                        "end": start_time + (step * (k + 1))
                    })
            elif tag == 'delete':
                # Script에는 있는데 AI가 놓친 경우 (Missing)
                # Timestamp를 None으로 두고 나중에 보간
                for k in range(i2 - i1):
                    aligned_pre.append({
                        "word": script_tokens[i1 + k],
                        "start": None,
                        "end": None
                    })
            elif tag == 'insert':
                # AI가 엉뚱한 말을 추가한 경우 -> 무시 (Script 기준)
                pass
        
        # 5. Timestamp Interpolation (보간)
        # None 값을 앞뒤 유효한 타임스탬프로 채움
        n = len(aligned_pre)
        if n == 0:
            return []

        # (1) 앞쪽 None 채우기 (시작 0.0)
        first_valid_idx = -1
        for i in range(n):
            if aligned_pre[i]["start"] is not None:
                first_valid_idx = i
                break
        
        if first_valid_idx == -1:
            # 전체가 None인 경우 (매칭 대실패) - 대충 배분해야 함.. 
            # 일단 전체 길이를 알 수 없으므로 0~1초씩 할당 충격 요법
            for i in range(n):
                aligned_pre[i]["start"] = float(i)
                aligned_pre[i]["end"] = float(i+1)
            return aligned_pre
            
        if first_valid_idx > 0:
            # 0 ~ first까지 역산? 그냥 0부터 first_valid_start까지 균등 배분
            start_t = 0.0
            end_t = aligned_pre[first_valid_idx]["start"]
            duration = end_t - start_t
            step = duration / first_valid_idx
            
            for i in range(first_valid_idx):
                aligned_pre[i]["start"] = start_t + (step * i)
                aligned_pre[i]["end"] = start_t + (step * (i + 1))
                
        # (2) 중간/끝 None 채우기
        i = 0
        while i < n:
            if aligned_pre[i]["start"] is None:
                # 다음 유효 값 찾기
                j = i + 1
                while j < n and aligned_pre[j]["start"] is None:
                    j += 1
                
                # i 부터 j-1 까지가 None 구간
                if j < n:
                    # 중간 구멍
                    prev_end = aligned_pre[i-1]["end"] if i > 0 else 0.0
                    next_start = aligned_pre[j]["start"]
                    duration = next_start - prev_end
                    count = j - i
                    step = duration / count
                    
                    for k in range(count):
                        aligned_pre[i+k]["start"] = prev_end + (step * k)
                        aligned_pre[i+k]["end"] = prev_end + (step * (k + 1))
                else:
                    # 끝까지 구멍 (마지막 유효값 이후)
                    prev_end = aligned_pre[i-1]["end"] if i > 0 else 0.0
                    # 그냥 단어당 0.5초씩 할당 가정
                    for k in range(j - i):
                        aligned_pre[i+k]["start"] = prev_end + (k * 0.5)
                        aligned_pre[i+k]["end"] = prev_end + ((k + 1) * 0.5)
                
                i = j
            else:
                i += 1
                
        return aligned_pre



    def generate_simple_subtitles(self, script: str, duration: float) -> List[dict]:
        """
        대본을 문장 단위로 나누고 시간을 등분할하여 자막 데이터 생성 (MVP)
        """
        import re
        
        # 문장 단위로 분리 (마침표, 물음표, 느낌표 기준)
        sentences = re.split(r'(?<=[.?!])\s+', script.strip())
        sentences = [s for s in sentences if s.strip()]
        
        if not sentences:
            return []
            
        # 시간 등분할
        duration_per_sentence = duration / len(sentences)
        
        subtitles = []
        current_time = 0.0
        
        for text in sentences:
            end_time = current_time + duration_per_sentence
            
            # 너무 긴 문장은 줄바꿈 처리 (임시)
            if len(text) > 20:
                mid = len(text) // 2
                split_idx = text.find(' ', mid)
                if split_idx != -1:
                    text = text[:split_idx] + '\n' + text[split_idx+1:]
            
            subtitles.append({
                "start": current_time,
                "end": end_time,
                "text": text.strip()
            })
            current_time = end_time
            
        return subtitles

    def add_subtitles(
        self,
        video_path: str,
        subtitles: List[dict],
        output_filename: str = "output_with_subs.mp4",
        font_size: int = 50,
        font_color: str = "white",
        font: str = config.DEFAULT_FONT_PATH,
        style_name: str = "Basic_White",
        stroke_color: Optional[str] = None,
        stroke_width: Optional[float] = None,
        project_id: Optional[int] = None
    ) -> str:
        """
        영상에 자막 추가 (PIL 사용 - ImageMagick 불필요)
        """
        try:
            from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
        except ImportError:
            raise ImportError("moviepy가 설치되지 않았습니다")

        video = VideoFileClip(video_path)
        subtitle_clips = []

        for sub in subtitles:
            try:
                # PIL로 텍스트 이미지 생성
                txt_img_path = self._create_subtitle_image(
                    text=sub["text"],
                    width=video.w,
                    font_size=font_size,
                    font_color=font_color,
                    font_name=font,
                    style_name=style_name,
                    stroke_color=stroke_color,
                    stroke_width_ratio=stroke_width
                )
                
                if txt_img_path:
                    txt_clip = ImageClip(txt_img_path)
                    txt_clip = txt_clip.set_position(("center", "bottom")) # 하단 배치 (여백은 이미지 생성시 처리)
                    txt_clip = txt_clip.set_start(sub["start"])
                    txt_clip = txt_clip.set_duration(sub["end"] - sub["start"])
                    subtitle_clips.append(txt_clip)
                    
                    # 클립이 닫힐 때 임시 파일 삭제는 어려우므로, 
                    # process 종료 후 삭제되거나 OS 임시폴더 사용 권장.
                    # 여기서는 일단 리스트에 담아두고 나중에 삭제 시도
                    
            except Exception as e:
                print(f"자막 생성 실패: {e}")
                import traceback
                traceback.print_exc()

        if subtitle_clips:
            final = CompositeVideoClip([video] + subtitle_clips)
        else:
            final = video

        output_path = os.path.join(self.output_dir, output_filename)
        
        # Custom Logger for Progress Tracking
        logger = 'bar'
        if project_id:
            try:
                from services.progress import RenderLogger
                # Stage 2: Subtitle overlay (50-100%)
                logger = RenderLogger(project_id, start_pct=50, end_pct=100)
            except Exception as e:
                print(f"Logger init failed in add_subtitles: {e}")

        final.write_videofile(
            output_path, 
            fps=video.fps,
            threads=1,
            codec="libx264",
            audio_codec="aac",
            logger=logger # Apply custom logger
        )

        video.close()
        final.close()
        for clip in subtitle_clips:
            # ImageClip은 close 명시적으로 필요
            try: clip.close() 
            except: pass

        return output_path

    # 자막 스타일 정의
    SUBTITLE_STYLES = {
        "Basic_White": {
            "stroke_color": "black",
            "stroke_width_ratio": 0.15,
            "bg_color": None
        },
        "Basic_Black": {
            "stroke_color": None,
            "stroke_width_ratio": 0,
            "bg_color": None,
            "bg_padding_x": 20,
            "bg_padding_y": 10
        },
        "Vlog_Yellow": {
            "stroke_color": "#4B0082",
            "stroke_width_ratio": 0.08,
            "bg_color": None
        },
        "Cinematic_Box": {
            "stroke_color": None,
            "stroke_width_ratio": 0,
            "bg_color": (0, 0, 0, 150),
            "bg_padding_x": 20,
            "bg_padding_y": 0
        },
        "Cute_Pink": {
            "stroke_color": "white",
            "stroke_width_ratio": 0.12,
            "bg_color": None
        },
        "Neon_Green": {
            "stroke_color": "black",
            "stroke_width_ratio": 0.15,
            "bg_color": None
        }
    }

    def _create_subtitle_image(self, text, width, font_size, font_color, font_name, style_name="Basic_White", stroke_color=None, stroke_width_ratio=None, stroke_width=None):
        from PIL import Image, ImageDraw, ImageFont
        import textwrap
        import platform
        import unicodedata
        import re

        # [FIX] Safety cleaning just in case (Include Unicode Brackets)
        print(f"DEBUG_RENDER: Raw Text Input: '{text}'")
        if text:
            # 1. Normalize Unicode (Full-width -> ASCII, etc.)
            text = unicodedata.normalize('NFKC', text)
            # 2. Regex Clean (Strip all brackets)
            text = re.sub(r'[()\[\]\{\}（）「」『』【】]', '', text)
            # 3. Newline Safety
            text = text.replace('\r', '').strip()
            print(f"DEBUG_RENDER: Cleaned Text: '{text}'")
        
        # 스타일 조회
        style = self.SUBTITLE_STYLES.get(style_name, self.SUBTITLE_STYLES["Basic_White"])
        
        final_font_color = style.get("font_color", font_color)
        print(f"DEBUG_RENDER: _create_subtitle_image style='{style_name}' font_color='{font_color}' final='{final_font_color}'")
        stroke_color = stroke_color if stroke_color is not None else style.get("stroke_color", "black")
        
        # [FIX] Stroke Width Priority: Explicit(px) > Explicit(Ratio) > Style(Ratio)
        if stroke_width is not None:
             final_stroke_width = int(stroke_width)
        else:
             ratio = stroke_width_ratio if stroke_width_ratio is not None else style.get("stroke_width_ratio", 0.1)
             final_stroke_width = max(1, int(font_size * ratio)) if ratio > 0 else 0

        bg_color = style.get("bg_color", None)
        
        # 폰트 로드
        font = None
        
        # 폰트 매핑 (UI 이름 -> 실제 파일명)
        font_mapping = {
            "G 마켓 산스 (Bold)": "GmarketSansTTFBold.ttf",
            "G마켓 산스 (Bold)": "GmarketSansTTFBold.ttf",
            "Gmarket Sans (Bold)": "GmarketSansTTFBold.ttf",
            "GmarketSansBold": "GmarketSansTTFBold.ttf",
            "GmarketSansMedium": "GmarketSansTTFMedium.ttf",
            "GmarketSansLight": "GmarketSansTTFLight.ttf",
            
            "나눔명조": "NanumMyeongjo.ttf",
            "NanumMyeongjo": "NanumMyeongjo.ttf",
            
            "쿠키런 (Regular)": "CookieRun Regular.ttf",
            "CookieRun Regular": "CookieRun Regular.ttf",
            
            "맑은 고딕": "malgun.ttf",
            "Malgun Gothic": "malgun.ttf",
            "GmarketSans": "GmarketSansTTFBold.ttf", # Fallback
        }
        
        target_font_file = font_mapping.get(font_name, font_name)
        if not target_font_file.lower().endswith(".ttf"):
            target_font_file += ".ttf"

        search_paths = [
            os.path.join(os.path.dirname(__file__), "..", "assets", "fonts"),
            os.path.join(os.path.dirname(__file__), "..", "static", "fonts"), # [FIX] Add static fonts
            "C:/Windows/Fonts",
            os.path.dirname(__file__)
        ]
        
        font_path = None
        for path in search_paths:
            candidate = os.path.join(path, target_font_file)
            if os.path.exists(candidate):
                font_path = candidate
                break
        
        # G마켓 산스 없으면 malgunbd.ttf (굵은 고딕) 시도
        if not font_path and "Gmarket" in font_name:
             font_path = "C:/Windows/Fonts/malgunbd.ttf"
             
        # 그래도 없으면 기본
        if not font_path or not os.path.exists(font_path):
             font_path = "C:/Windows/Fonts/malgun.ttf"
             
        try:
            if font_path and os.path.exists(font_path):
                font = ImageFont.truetype(font_path, font_size)
            else:
                font = ImageFont.truetype("arial.ttf", font_size)
        except:
             try:
                 font = ImageFont.load_default()
             except:
                 pass

        # Balanced Wrapping Logic with Manual Newline Support
        # 1. 텍스트 너비가 맥스 폭(너비 - 패딩)을 넘는지 확인
        safe_width = int(width * 0.9) # 좌우 5% 패딩
        
        def get_text_width(text, font):
            dummy_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
            return dummy_draw.textlength(text, font=font)

        # [FIX] Manual Newline Support
        # 사용자가 입력한 엔터(\n)를 먼저 기준으로 나눈 뒤, 각 라인에 대해 길이 체크/줄바꿈 수행
        manual_lines = text.split('\n')
        wrapped_lines = []
        
        for m_line in manual_lines:
            m_line = m_line.strip()
            if not m_line:
                # 빈 줄 유지하고 싶다면:
                # wrapped_lines.append("") 
                continue
                
            line_width = get_text_width(m_line, font)
            
            if line_width <= safe_width:
                 wrapped_lines.append(m_line)
            else:
                # 2. 넘는다면, 균형있게 나누기 (Balanced Wrapping)
                # 단순히 꽉 채우는게 아니라, 전체 길이를 라인 수로 나누어 목표 길이를 정함
                
                # 예상 라인 수
                est_lines = int(line_width / safe_width) + 1
                target_line_width = line_width / est_lines
                
                words = m_line.split(' ')
                current_line = []
                current_width = 0
                
                for word in words:
                    word_width = get_text_width(word + " ", font)
                    
                    if current_width + word_width > safe_width:
                        # 무조건 줄바꿈 (화면 넘어감)
                        wrapped_lines.append(" ".join(current_line))
                        current_line = [word]
                        current_width = word_width
                    elif current_width + word_width > target_line_width * 1.2 and len(current_line) > 0:
                         # 목표 너비를 적당히(20%) 넘으면 줄바꿈 -> 균형 유도
                         wrapped_lines.append(" ".join(current_line))
                         current_line = [word]
                         current_width = word_width
                    else:
                        current_line.append(word)
                        current_width += word_width
                
                if current_line:
                    wrapped_lines.append(" ".join(current_line))
                
        wrapped_text = "\n".join(wrapped_lines)

        # 텍스트 크기 측정
        dummy_img = Image.new('RGBA', (1, 1))
        dummy_draw = ImageDraw.Draw(dummy_img)
        bbox = dummy_draw.multiline_textbbox((0, 0), wrapped_text, font=font, align="center")
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        # Padding Logic Split (X, Y)
        padding_default = style.get("bg_padding", 20)
        pad_x = style.get("bg_padding_x", padding_default)
        pad_y = style.get("bg_padding_y", padding_default)

        # 이미지 크기는 텍스트 박스 + Y패딩만큼만 (add_subtitles에서 위치 잡음)
        img_w = width
        img_h = text_h + (pad_y * 2) + 10 # 약간의 여유 10px
        
        img = Image.new('RGBA', (img_w, img_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        center_x = img_w // 2
        center_y = img_h // 2
        
        # 박스 그리기
        if bg_color:
            box_x0 = center_x - (text_w // 2) - pad_x
            box_y0 = center_y - (text_h // 2) - pad_y
            box_x1 = center_x + (text_w // 2) + pad_x
            box_y1 = center_y + (text_h // 2) + pad_y
            
            # [Fix] 폰트 렌더링 오차 등으로 박스가 살짝 작아보일 수 있으므로 최소 높이 보정
            if pad_y < 5: 
                # Tight fit인 경우에도 폰트 baseline 고려하여 살짝 하단 보정
                box_y1 += 5
                
            draw.rectangle([box_x0, box_y0, box_x1, box_y1], fill=bg_color)

        # 텍스트 그리기
        text_x = center_x - (text_w // 2)
        text_y = center_y - (text_h // 2)
        
        if stroke_color and final_stroke_width > 0:
            draw.text((text_x, text_y), wrapped_text, font=font, fill=final_font_color, 
                      stroke_width=final_stroke_width, stroke_fill=stroke_color, align="center")
        else:
            draw.text((text_x, text_y), wrapped_text, font=font, fill=final_font_color, align="center")

        import uuid
        temp_filename = f"sub_{uuid.uuid4()}.png"
        output_path = os.path.join(self.output_dir, temp_filename)
        img.save(output_path)
        
        return output_path

    def create_preview_image(self, background_path, text, font_size, font_color, font_name, style_name="Basic_White", stroke_color=None, stroke_width=None, position_y=None, target_size=(1280, 720)):
        """
        자막 확인용 미리보기 이미지 생성 (배경 + 자막 합성)
        """
        from PIL import Image
        import uuid

        # 1. 배경 생성 (없으면 검은색)
        if background_path and os.path.exists(background_path):
             # Cinematic Frame 로직 재사용 (이미지 path가 cinematic frame이면 그대로 사용, 아니면 변환)
             # 여기서는 단순하게 리사이즈/크롭만 해서 배경으로 씀 (속도 위해)
             try:
                 bg = Image.open(background_path).convert("RGBA")
                 # Aspect Ratio Preserve Resize & Crop logic similar to cinematic frame
                 target_w, target_h = target_size
                 bg_ratio = target_w / target_h
                 img_ratio = bg.width / bg.height
                 
                 if img_ratio > bg_ratio:
                     new_h = target_h
                     new_w = int(new_h * img_ratio)
                 else:
                     new_w = target_w
                     new_h = int(new_w / img_ratio)
                 
                 bg = bg.resize((new_w, new_h), Image.Resampling.LANCZOS)
                 left = (new_w - target_w) // 2
                 top = (new_h - target_h) // 2
                 bg = bg.crop((left, top, left + target_w, top + target_h))
             except:
                 bg = Image.new('RGBA', target_size, (0, 0, 0, 255))
        else:
            bg = Image.new('RGBA', target_size, (0, 0, 0, 255))

        # 2. 자막 이미지 생성
        try:
            sub_img_path = self._create_subtitle_image(
                text=text,
                width=target_size[0],
                font_size=font_size,
                font_color=font_color,
                font_name=font_name,
                style_name=style_name,
                stroke_color=stroke_color,
                stroke_width=stroke_width
            )
            
            if sub_img_path and os.path.exists(sub_img_path):
                sub_img = Image.open(sub_img_path).convert("RGBA")
                
                # 3. 합성 (위치 조정)
                # Center X
                x = (bg.width - sub_img.width) // 2
                
                if position_y is not None:
                    # User Percentage Position (0 ~ 100)
                    center_y = int(bg.height * (float(position_y) / 100.0))
                    y = center_y - (sub_img.height // 2)
                else:
                    # Default: Bottom Safe Area (15%)
                    bottom_margin = int(bg.height * 0.15)
                    y = bg.height - sub_img.height - bottom_margin
                
                # Screen Boundary Safety (Clamp)
                y = max(0, y)
                y = min(bg.height - sub_img.height, y)
                
                bg.paste(sub_img, (x, y), sub_img)
                
                # Clean up temp sub image
                try:
                    os.remove(sub_img_path)
                except:
                    pass
        except Exception as e:
            print(f"Preview Subtitle Error: {e}")

        # 4. 저장
        preview_filename = f"preview_sub_{uuid.uuid4()}.png"
        output_path = os.path.join(self.output_dir, preview_filename)
        bg.save(output_path)
        
        return output_path

    def _create_zoom_clip(self, image_path: str, duration: float, target_size: tuple):
        """
        Ken Burns 효과 (줌인)가 적용된 클립 생성
        """
        from moviepy.editor import ImageClip, CompositeVideoClip
        
        # 기본 이미지 클립
        img_clip = ImageClip(image_path).set_duration(duration)
        
        # 줌인 효과 (1.0 -> 1.15)
        # lambda t: 1 + 0.03 * t  (5초 동안 약 15% 확대)
        zoom_ratio = 0.03
        
        try:
            # resize 함수: t(시간)에 따라 크기 변경
            # ImageClip에 resize를 적용하면 모든 프레임을 다시 계산함
            zoomed_clip = img_clip.resize(lambda t: 1 + zoom_ratio * t)
            
            # 중앙 정렬하여 CompositeVideoClip으로 감싸기 (크롭 효과)
            # set_position("center")는 CompositeVideoClip 내에서 중앙 배치
            zoomed_clip = zoomed_clip.set_position("center")
            
            # 최종 크기를 target_size로 고정 (넘치는 부분 잘림 효과)
            final_clip = CompositeVideoClip([zoomed_clip], size=target_size)
            final_clip = final_clip.set_duration(duration)
            return final_clip
        except Exception as e:
            print(f"줌 효과 적용 실패: {e}")
            return img_clip

    def generate_simple_subtitles(self, script_text: str, duration: float) -> List[dict]:
        """
        대본을 시간(Duration)에 맞춰 균등 분할하여 자막 생성 (Fallback)
        줄바꿈 > 문장부호 > 길이 순으로 분할 시도하여 최소한의 덩어리로 나눔.
        """
        if not script_text:
            return []
            
        import re

        # 1. 줄바꿈으로 먼저 분리
        lines = [L.strip() for L in script_text.splitlines() if L.strip()]
        
        final_sentences = []
        
        for line in lines:
            # 2. 문장 부호로 분리 (. ? ! )
            # (?<=[.?!]) : lookbehind assertion, 문장부호를 포함하기 위해
            chunks = re.split(r'(?<=[.?!])\s+', line)
            for chunk in chunks:
                if not chunk.strip(): continue
                
                # 3. 너무 긴 문장은 강제 분할 (50자 기준)
                if len(chunk) > 50:
                     # 쉼표로 시도
                     sub_chunks = re.split(r'(?<=[,])\s+', chunk)
                     for sub in sub_chunks:
                         if len(sub) > 50:
                             # 그래도 길면 공백 기준 하드 컷 (약 30자)
                             words = sub.split(' ')
                             current_sent = ""
                             for w in words:
                                 if len(current_sent) + len(w) > 40:
                                     final_sentences.append(current_sent.strip())
                                     current_sent = w + " "
                                 else:
                                     current_sent += w + " "
                             if current_sent: final_sentences.append(current_sent.strip())
                         else:
                             if sub.strip(): final_sentences.append(sub.strip())
                else:
                    final_sentences.append(chunk.strip())
        
        if not final_sentences:
            return []
            
        count = len(final_sentences)
        duration_per_sentence = duration / count
        
        subtitles = []
        current_time = 0.0
        
        for sent in final_sentences:
            end_time = current_time + duration_per_sentence
            # 마지막 자막의 오차 보정은 하지 않음 (약간의 오차 허용)
            
            subtitles.append({
                "start": float(f"{current_time:.2f}"),
                "end": float(f"{end_time:.2f}"),
                "text": sent.strip()
            })
            current_time = end_time
            
        print(f"Generated {len(subtitles)} simple subtitles (Fallback).")
        return subtitles
    
    def merge_with_intro(self, intro_path: str, main_video_path: str, output_path: str) -> str:
        """
        인트로 영상과 메인 영상을 병합
        FFmpeg concat demuxer 사용
        """
        import subprocess
        from pathlib import Path
        import tempfile
        
        try:
            # 파일 존재 확인
            if not Path(intro_path).exists():
                print(f"Intro video not found: {intro_path}")
                return main_video_path
            
            if not Path(main_video_path).exists():
                raise FileNotFoundError(f"Main video not found: {main_video_path}")
            
            # concat.txt 파일 생성
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                concat_file = f.name
                # 절대 경로로 변환
                intro_abs = str(Path(intro_path).absolute()).replace('\\', '/')
                main_abs = str(Path(main_video_path).absolute()).replace('\\', '/')
                
                f.write(f"file '{intro_abs}'\n")
                f.write(f"file '{main_abs}'\n")
            
            # FFmpeg concat 명령
            cmd = [
                config.FFMPEG_PATH,
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c', 'copy',  # 재인코딩 없이 복사 (빠름)
                '-y',  # 덮어쓰기
                output_path
            ]
            
            print(f"Merging intro with main video...")
            print(f"Command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            # concat.txt 삭제
            Path(concat_file).unlink(missing_ok=True)
            
            if result.returncode != 0:
                print(f"FFmpeg error: {result.stderr}")
                # 병합 실패 시 원본 비디오 반환
                return main_video_path
            
            print(f"Successfully merged intro. Output: {output_path}")
            return output_path
            
        except Exception as e:
            print(f"Error merging intro: {e}")
            # 오류 발생 시 원본 비디오 반환
            return main_video_path

# 싱글톤 인스턴스
video_service = VideoService()
