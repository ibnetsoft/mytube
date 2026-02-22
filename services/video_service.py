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

    def _get_video_info(self, path):
        """Helper to get video dimensions safely using ffmpeg (no ffprobe dependency)"""
        import imageio_ffmpeg
        import subprocess
        import re
        
        try:
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            # Just run ffmpeg -i to get metadata from stderr
            cmd = [ffmpeg_exe, "-i", path]
            
            startupinfo = None
            if os.name == 'nt':
                 startupinfo = subprocess.STARTUPINFO()
                 startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, startupinfo=startupinfo)
            output = res.stderr or ""
            # print(f"DEBUG PROBE {path}: {output[:100]}...") # Debug logging
            
            # Search in stderr for pattern like "Video: h264, ..., 1080x1920, ..."
            # Note: The output format can vary, but usually "Video:" line contains resolution
            # Standard: Stream #0:0: Video: h264 (Main), yuv420p, 1280x720, ...
            
            # Using robust regex to find resolution in Video stream line
            # Look for "Video:" then later digits 'x' digits
            match = re.search(r"Video:.*? (\d{2,5})x(\d{2,5})", output)
            if match:
                w, h = map(int, match.groups())
                return w, h
                
            # Fallback: simple search for likely resolution format if not on Video line (riskier but useful)
            match = re.search(r" (\d{3,5})x(\d{3,5}) ", output)
            if match:
                 w, h = map(int, match.groups())
                 return w, h
        except Exception as e:
            print(f"Probe Error for {path}: {e}")
            
        return None, None

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
        fade_in_flags: Optional[List[bool]] = None,  # [NEW] Fade-in effect per image
        image_effects: Optional[List[str]] = None,   # [NEW] Ken Burns Effects
        intro_video_path: Optional[str] = None,   # [NEW] Intro Video Prepend
        sfx_map: Optional[dict] = None,          # [NEW] Scene SFX Map {scene_num: sfx_path}
        focal_point_ys: Optional[List[float]] = None # [NEW] Smart Focus Point (0.0 - 1.0)
    ) -> str:
        """
        이미지 슬라이드쇼 영상 생성 (시네마틱 프레임 적용)
        """
        try:
            # MoviePy 2.x (Modern)
            from moviepy.video.VideoClip import ImageClip, VideoClip, ColorClip, TextClip
            from moviepy.video.io.VideoFileClip import VideoFileClip
            from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip, concatenate_videoclips
            from moviepy.audio.io.AudioFileClip import AudioFileClip
            from moviepy.audio.AudioClip import AudioClip
            
            # Effects (Classes in 2.0)
            from moviepy.video.fx.Resize import Resize
            from moviepy.video.fx.Loop import Loop
            from moviepy.video.fx.FadeIn import FadeIn
            from moviepy.video.fx.CrossFadeIn import CrossFadeIn
            MOVIEPY_V2 = True
            
        except ImportError:
            # MoviePy 1.x (Legacy)
            try:
                from moviepy.editor import (
                    ImageClip, VideoClip, ColorClip, TextClip,
                    VideoFileClip, CompositeVideoClip, concatenate_videoclips,
                    AudioFileClip
                )
                from moviepy.audio.AudioClip import AudioClip
                import moviepy.video.fx.all as vfx_all
                MOVIEPY_V2 = False
            except ImportError as e:
                print(f"CRITICAL: MoviePy Import Failed completely: {e}")
                raise ImportError(f"MoviePy 또는 Requests가 설치되지 않았습니다. (Error: {e})")

        # [PATCH] Uniform method names for v1 and v2 compatibility
        from moviepy.video.VideoClip import VideoClip
        from moviepy.audio.AudioClip import AudioClip
        
        # Define patches as independent functions to avoid recursion
        def _patch_with_duration(clip, t):
            if hasattr(clip, 'set_duration'): return clip.set_duration(t)
            return clip
        def _patch_with_position(clip, pos):
            if hasattr(clip, 'set_position'): return clip.set_position(pos)
            return clip
        def _patch_with_start(clip, t):
            if hasattr(clip, 'set_start'): return clip.set_start(t)
            return clip
        def _patch_with_end(clip, t):
            if hasattr(clip, 'set_end'): return clip.set_end(t)
            return clip
        def _patch_with_opacity(clip, op):
            if hasattr(clip, 'set_opacity'): return clip.set_opacity(op)
            return clip
        def _patch_with_fps(clip, fps):
            if hasattr(clip, 'set_fps'): return clip.set_fps(fps)
            return clip
        def _patch_with_audio(clip, audio):
            if hasattr(clip, 'set_audio'): return clip.set_audio(audio)
            return clip
        def _patch_with_subclip(clip, s=0, e=None):
            if hasattr(clip, 'subclipped'): return clip.subclipped(s, e)
            if hasattr(clip, 'subclip'): return clip.subclip(s, e)
            return clip

        for cls in [VideoClip, AudioClip, ImageClip, ColorClip, TextClip, VideoFileClip, CompositeVideoClip]:
            if not hasattr(cls, 'with_duration'): cls.with_duration = lambda self, t: _patch_with_duration(self, t)
            if not hasattr(cls, 'with_position'): cls.with_position = lambda self, pos: _patch_with_position(self, pos)
            if not hasattr(cls, 'with_start'): cls.with_start = lambda self, t: _patch_with_start(self, t)
            if not hasattr(cls, 'with_end'): cls.with_end = lambda self, t: _patch_with_end(self, t)
            if not hasattr(cls, 'with_opacity'): cls.with_opacity = lambda self, op: _patch_with_opacity(self, op)
            if not hasattr(cls, 'with_fps'): cls.with_fps = lambda self, fps: _patch_with_fps(self, fps)
            if not hasattr(cls, 'with_audio'): cls.with_audio = lambda self, audio: _patch_with_audio(self, audio)
            if not hasattr(cls, 'with_subclip'): cls.with_subclip = lambda self, s=0, e=None: _patch_with_subclip(self, s, e)

        # Compatibility Mocking for VFX
        class MockVFX:
            pass
        vfx = MockVFX()

        # [HELPER] FX Wrappers
        def apply_loop(clip, n=None, duration=None):
            if MOVIEPY_V2:
                return clip.with_effects([Loop(n=n, duration=duration)])
            return clip.fx(vfx_all.loop, n=n, duration=duration)

        def apply_resize(clip, new_size=None, height=None, width=None):
            # Normalization
            if height and not new_size: new_size = [None, height]
            if width and not new_size: new_size = [width, None]
            
            if MOVIEPY_V2:
                return clip.with_effects([Resize(new_size=new_size)])
            # 1.x has .resize() method (from moviepy.editor or VideoClip)
            return clip.resize(new_size=new_size)

        def apply_fadein(clip, duration):
            if MOVIEPY_V2:
                return clip.with_effects([FadeIn(duration=duration)])
            return clip.fx(vfx_all.fadein, duration)

        def apply_crossfadein(clip, duration):
            if MOVIEPY_V2:
                return clip.with_effects([CrossFadeIn(duration=duration)])
            return clip.fx(vfx_all.crossfadein, duration)

        # Assign to vfx for backward compatibility
        vfx.loop = apply_loop
        vfx.resize = apply_resize
        vfx.fadein = apply_fadein
        vfx.crossfadein = apply_crossfadein

        # Pillow Patch
        import PIL.Image
        if not hasattr(PIL.Image, 'ANTIALIAS'):
            try:
                PIL.Image.ANTIALIAS = PIL.Image.LANCZOS
            except: pass

        import numpy as np
        import requests 


        clips = []
        # DEBUG: Log incoming effects
        import datetime
        try:
            with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as df:
                 df.write(f"[{datetime.datetime.now()}] create_slideshow(PROJ={project_id}) Effects: {image_effects}\n")
        except: pass
        temp_files = [] # 나중에 삭제할 임시 파일들

        current_duration = 0.0
        
        # [NEW] Background Video Logic
        video = None # Base video clip
        
        # Audio Load First to determine duration
        audio = None
        if audio_path and os.path.exists(audio_path):
             try:
                 print(f"DEBUG: Loading Audio: {audio_path}")
                 audio = AudioFileClip(audio_path)
                 print(f"DEBUG: Audio Loaded. Duration: {audio.duration}")
             except Exception as ae:
                 print(f"ERROR: Audio Load Failed: {ae}")
                 # Critical? Maybe fallback to silent?
                 audio = None
             
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
        
        print("DEBUG: Template Load Complete")
             
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
                     bg_clip = apply_loop(bg_clip, duration=target_duration)
                     
                     # 4. Resize/Crop to target resolution (1080p etc)
                     # Aspect Ratio Logic
                     target_w, target_h = resolution
                     
                     # Resize logic: Cover
                     bg_clip = vfx.resize(bg_clip, height=target_h) # Fit height first
                     if bg_clip.w < target_w:
                         bg_clip = vfx.resize(bg_clip, width=target_w) # Fit width if still small
                         
                     # Center Crop
                     bg_clip = bg_clip.crop(x1=bg_clip.w/2 - target_w/2, width=target_w, height=target_h)
                     
                     video = bg_clip
                     print(f"Background Video Prepared: {target_duration}s")
             
             except Exception as e:
                 print(f"Background Video Error: {e}")
                 # Fallback to images if failed
                 pass
        
        print("DEBUG: Background Video Logic Complete")

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
                # [NEW] Check if it is a Video Asset (Motion)
                is_video_asset = img_path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))
                
                clip = None
                
                if is_video_asset:
                    try:
                        print(f"DEBUG_RENDER: Pre-processing Video Asset with FFMPEG: {img_path}")
                        # [FIX] FFMPEG Pre-process to avoid MoviePy Hangs
                        target_w, target_h = resolution
                        dur = duration_per_image[i] if isinstance(duration_per_image, list) else duration_per_image

                        # [NEW] Check if pan_down/pan_up is requested for this video asset
                        req_effect = ''
                        if image_effects and i < len(image_effects):
                            req_effect = str(image_effects[i]).lower().replace(" ", "_")

                        # [AUTO-CORRECT] Tall Video Detection (Force Pan)
                        vw, vh = self._get_video_info(img_path)
                        print(f"DEBUG: Video Probe '{os.path.basename(img_path)}': {vw}x{vh} (Target: {target_w}x{target_h})")
                        
                        if vw and vh:
                            var = vw / vh
                            tar = target_w / target_h
                            # If video is taller/narrower than target (e.g. 9:32 < 9:16), force pan
                            if var < tar: 
                                if req_effect not in ['pan_up', 'scroll_up', 'pan_down', 'scroll_down']:
                                    print(f"  ✨ [Auto-Pan] Tall Video Detected ({vw}x{vh}). Forcing 'pan_down'.")
                                    req_effect = 'pan_down'
                                    if image_effects and i < len(image_effects):
                                        image_effects[i] = 'pan_down'

                        is_tall_pan_video = req_effect in ['pan_down', 'pan_up', 'scroll_down', 'scroll_up']
                        is_tall_pan = is_tall_pan_video # [FIX] Sync variable name for panning logic below

                        if is_tall_pan_video:
                            # --- Full-Travel Pan for Tall Videos ---
                            pan_dir = "up" if req_effect in ['pan_up', 'scroll_up'] else "down"
                            print(f"↕️ [TallPan Video] effect={req_effect}, dir={pan_dir}, dur={dur:.1f}s")
                            processed_path = self._preprocess_video_tall_pan(
                                img_path, target_w, target_h, duration=dur, fps=fps, direction=pan_dir
                            )
                            # MoviePy with_position will handle the actual pan movement, do not disable the effect
                        else:
                            # --- Normal center-crop preprocess ---
                            processed_path = self._preprocess_video_with_ffmpeg(img_path, target_w, target_h, fps=fps)
                            # Disable remaining effects for video
                            if image_effects is not None and i < len(image_effects):
                                image_effects[i] = 'none'

                        temp_files.append(processed_path)
                        
                        # Load clean clip
                        clip = VideoFileClip(processed_path).without_audio()
                        
                        # Loop logic
                        if clip.duration < dur:
                            clip = apply_loop(clip, duration=dur)
                        else:
                            clip = clip.subclip(0, dur)
                            
                        clip = clip.with_duration(dur)
                        
                    except Exception as e:
                        print(f"Failed to load video asset {img_path}: {e}")
                        pass

                # [FIX] Logic to handle Video vs Image asset paths
                processed_img_path = None
                is_vertical = False  # [FIX] Initialize here to prevent UnboundLocalError for video assets
                if is_video_asset:
                    if clip is not None:
                         # Video asset loaded successfully, no further image processing needed for 'processed_img_path'
                         # The 'clip' variable already holds the VideoFileClip
                         pass 
                    else:
                         print(f"ERROR: Video asset failed to load. Skipping: {img_path}")
                         continue # Skip this frame entirely if video failed to load
                else: 
                    # Image Processing (Cinematic Frame or Fit)
                    target_w, target_h = resolution
                    is_vertical = target_h > target_w

                    if is_vertical:
                        # [NEW] Check if we need to preserve tall height for vertical panning
                        is_tall_pan = False
                        eff_check = ""
                        if image_effects and i < len(image_effects):
                             eff_check = str(image_effects[i]).lower().replace(" ", "_")
                             if eff_check in ['pan_up', 'pan_down', 'scroll_down', 'scroll_up']:
                                 is_tall_pan = True

                        # Extract duration early
                        dur = duration_per_image[i] if isinstance(duration_per_image, list) else duration_per_image

                        if is_tall_pan:
                             # Use FFmpeg Preprocess for consistent Pan effect on Images
                             pan_dir = "up" if eff_check in ['pan_up', 'scroll_up'] else "down"
                             print(f"↕️ [TallPan Image] effect={eff_check}, dir={pan_dir}, dur={dur:.1f}s")
                             processed_path = self._preprocess_video_tall_pan(
                                 img_path, target_w, target_h, duration=dur, fps=fps, direction=pan_dir
                             )
                             clip = VideoFileClip(processed_path).without_audio()
                             temp_files.append(processed_path)
                             # (MoviePy에서 with_position으로 실제 움직임을 줄 것이므로 effect를 'none'으로 지우지 않음)
                        else:
                             # [NEW] Smart focal point retrieval
                             focal_y = 0.5
                             if focal_point_ys and i < len(focal_point_ys):
                                 focal_y = focal_point_ys[i]
    
                             # For Shorts/Vertical: Use Cinematic Frame (Fit Width + Smart Crop Focal Point)
                             processed_img_path = self._create_cinematic_frame(img_path, resolution, focal_point_y=focal_y, allow_tall=False)
                             temp_files.append(processed_img_path)
                             
                             # Explicitly convert to VideoClip
                             clip = ImageClip(processed_img_path).with_duration(dur).with_fps(30)
                    else:
                        dur = duration_per_image[i] if isinstance(duration_per_image, list) else duration_per_image
                        # For Landscape: Use Fill (Crop) as before
                        processed_img_path = self._resize_image_to_fill(img_path, resolution)
                        temp_files.append(processed_img_path)
                        clip = ImageClip(processed_img_path).with_duration(dur).with_fps(30)
                    
                # [NEW] Apply fade-in effect if requested (Works for both Video and Image)
                if fade_in_flags and i < len(fade_in_flags) and fade_in_flags[i]:
                    dur = clip.duration
                    fade_duration = min(1.0, dur * 0.3)  # Max 1초 또는 클립 길이의 30%
                    try:
                        # 2.0 Compatible FadeIn
                        clip = vfx.fadein(clip, fade_duration)
                        print(f"  → Fade-in applied to item #{i+1} ({fade_duration:.2f}s)")
                    except Exception as e:
                        print(f"FadeIn Error: {e}")

                # [NEW] Apply Ken Burns Effects (Zoom/Pan) - Only for Images
                effect = None  # [FIX] Initialize to prevent UnboundLocalError
                safe_effect = 'none'
                if image_effects and i < len(image_effects):
                    safe_effect = str(image_effects[i]).lower().replace(" ", "_") # Normalize (zoom in -> zoom_in)
                
                try:
                    with open("debug_effects_trace.txt", "a", encoding="utf-8") as df:
                        df.write(f"Img[{i}] EffectRaw: {image_effects[i] if image_effects and i < len(image_effects) else 'N/A'} -> Safe: {safe_effect} (Dur:{dur}, FPS:{fps})\n")
                except: pass
                
                # Force disable effect ONLY for NORMAL Video clips. 
                # [FIX] Allow effects for images in Vertical (Shorts) mode, and also for TALL videos that need panning!
                if is_video_asset and not (safe_effect in ['pan_down', 'pan_up', 'scroll_down', 'scroll_up']):
                     safe_effect = 'none'

                # [NEW] Level 2: Gemini Vision 자동 분류
                # safe_effect == 'auto_classify' 또는 'auto' 일 때 Gemini로 분류
                if safe_effect in ('auto_classify', 'auto') and not is_video_asset:
                    try:
                        from services.gemini_service import gemini_service as _gs
                        import asyncio
                        # 동기 컨텍스트에서 async 함수 호출
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                import concurrent.futures
                                with concurrent.futures.ThreadPoolExecutor() as pool:
                                    future = pool.submit(asyncio.run, _gs.classify_asset_type(img_path))
                                    cls_result = future.result(timeout=30)
                            else:
                                cls_result = loop.run_until_complete(_gs.classify_asset_type(img_path))
                        except RuntimeError:
                            cls_result = asyncio.run(_gs.classify_asset_type(img_path))

                        rec_effect = cls_result.get("recommended_effect", "ken_burns")
                        # split_zoom → 이미 _detect_and_split_panels에서 처리되므로 ken_burns로 fallback
                        if rec_effect == "split_zoom":
                            rec_effect = "ken_burns"
                        # ken_burns → zoom_in으로 매핑
                        if rec_effect == "ken_burns":
                            rec_effect = "zoom_in"
                        safe_effect = rec_effect
                        print(f"  🤖 [AutoClassify] Img[{i+1}]: {cls_result['asset_type']} → {safe_effect} (conf={cls_result['confidence']:.2f}, src={cls_result['source']})")
                        # image_effects 배열도 업데이트 (is_tall_pan 재계산용)
                        if image_effects and i < len(image_effects):
                            image_effects[i] = safe_effect
                        # is_tall_pan 재계산
                        if not is_video_asset:
                            if safe_effect in ['pan_up', 'pan_down']:
                                is_tall_pan = True
                    except Exception as ce:
                        print(f"  ⚠️ [AutoClassify] Failed ({ce}), using zoom_in fallback")
                        safe_effect = 'zoom_in'

                if safe_effect == 'random':
                    import random
                    # [MODIFIED] Include vertical pans in random selection
                    safe_effect = random.choice(['zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'pan_up', 'pan_down'])
                    try:
                        with open("debug_effects_trace.txt", "a", encoding="utf-8") as df:
                            df.write(f"  -> Random Selection for Img[{i}]: {safe_effect}\n")
                    except: pass
                
                # [NEW] Normalize/Alias effects for unified motor control
                if safe_effect in ['scroll_down', 'tilt_down', 'pan_down_move']: 
                    safe_effect = 'pan_up'   # Camera moves Down = Look Bottom
                if safe_effect in ['scroll_up', 'tilt_up', 'pan_up_move']: 
                    safe_effect = 'pan_down' # Camera moves Up = Look Top

                if safe_effect and safe_effect != 'none':
                    effect = safe_effect

                # [NEW] Handle positioning for TALL assets (Webtoon support)
                # If it's a tall image and no specific effect (or static), ensure we look at the focal point instead of just the top.
                if (not effect or effect == 'none') and is_vertical and processed_img_path and 'tall' in os.path.basename(processed_img_path):
                    try:
                        cur_h = clip.h
                        # Calculate y_offset to center the focal point in the viewport
                        y_offset = int(target_h / 2 - (cur_h * focal_point_y))
                        # Clamp to ensure image covers the background
                        min_y = target_h - cur_h
                        max_y = 0
                        y_pos = max(min_y, min(max_y, y_offset))
                        clip = clip.with_position((0, y_pos))
                        # Wrap in composite to fix the viewport size
                        clip = CompositeVideoClip([clip], size=(target_w, target_h)).with_duration(dur)
                        print(f"  → Applied focal-point positioning to tall static item #{i+1} (y={y_pos})")
                    except Exception as pe:
                        print(f"Positioning Error: {pe}")
                
                if effect:
                    print(f"DEBUG_RENDER: Image[{i}] Applying Effect '{effect}' (FPS={fps}, Dur={dur}s)")

                    try:
                        w, h = target_w, target_h # [FIX] Use target viewport size, not clip size, because tall clips have clip.h > target_h
                        
                        if effect == 'zoom_in':
                            # Center Zoom: 1.0 -> 1.15 (Tuned for better framing)
                            clip = vfx.resize(clip, lambda t: 1.0 + 0.15 * (t / dur))
                            # Safe Container (2.0 uses with_position, with_duration)
                            clip = CompositeVideoClip([clip.with_position('center')], size=(w,h)).with_duration(dur)
                            
                        elif effect == 'zoom_out':
                            # Center Zoom Out: 1.15 -> 1.0
                            # [FIX] MoviePy 2.x Support: Use vfx.resize instead of .resize
                            clip = vfx.resize(clip, lambda t: 1.15 - 0.15 * (t / dur))
                            clip = CompositeVideoClip([clip.with_position('center')], size=(w,h)).with_duration(dur)
                            
                        elif effect.startswith('pan_'):
                            # [FIX v2] Tall image detection: use actual clip height vs viewport height.
                            # Do NOT rely on filename containing 'tall' — files get renamed (e.g. scene_001.jpg)
                            # and the 'tall' hint is lost. Instead, check if clip is actually taller than viewport.
                            is_tall_clip = (
                                is_tall_pan and
                                clip.h > h  # clip.h = actual clip pixel height, h = viewport height
                            )
                            print(f"  [PAN DEBUG] effect={effect}, is_tall_pan={is_tall_pan}, clip.h={clip.h}, viewport_h={h}, is_tall_clip={is_tall_clip}")

                            if is_tall_clip and effect in ('pan_down', 'pan_up'):
                                # --- TRUE VERTICAL SCROLL (세로 긴 이미지 전체를 스크롤) ---
                                # clip.h is the full tall image height (e.g. 3000px for a 1080x1920 target)
                                # w, h are the target viewport size
                                new_w, new_h = clip.w, clip.h
                                max_scroll = new_h - h  # total scrollable pixels

                                if max_scroll > 0:
                                    if effect == 'pan_down':
                                        # Top -> Bottom (image moves upward, revealing bottom)
                                        clip = clip.with_position(
                                            lambda t, _ms=max_scroll, _dur=dur, _x_off=int((w - new_w) / 2): (
                                                _x_off,
                                                int(0 - _ms * (t / _dur))
                                            )
                                        )
                                    else:  # pan_up
                                        # Bottom -> Top
                                        clip = clip.with_position(
                                            lambda t, _ms=max_scroll, _dur=dur, _x_off=int((w - new_w) / 2): (
                                                _x_off,
                                                int(-_ms + _ms * (t / _dur))
                                            )
                                        )
                                    clip = CompositeVideoClip([clip], size=(w, h)).with_duration(dur)
                                    print(f"  → [TRUE PAN] Tall scroll applied: effect={effect}, tall_h={new_h}px, viewport_h={h}px, scroll={max_scroll}px")
                                else:
                                    # Image height <= viewport height -> fallback center
                                    clip = clip.with_position(('center', 'center'))
                                    clip = CompositeVideoClip([clip], size=(w, h)).with_duration(dur)

                            else:
                                # --- STANDARD PAN (1.2x zoom + small movement) ---
                                pan_zoom = 1.2
                                clip = vfx.resize(clip, pan_zoom)
                                new_w, new_h = clip.w, clip.h

                                # Max movement range
                                max_x = new_w - w
                                max_y = new_h - h

                                # Centered fixed coords
                                center_y = -max_y / 2
                                center_x = -max_x / 2

                                if effect == 'pan_left':
                                    clip = clip.with_position(lambda t, _mx=max_x, _cy=center_y, _dur=dur: (int(0 - _mx * (t / _dur)), int(_cy)))

                                elif effect == 'pan_right':
                                    clip = clip.with_position(lambda t, _mx=max_x, _cy=center_y, _dur=dur: (int(-_mx + _mx * (t / _dur)), int(_cy)))

                                elif effect == 'pan_up':
                                    clip = clip.with_position(lambda t, _my=max_y, _cx=center_x, _dur=dur: (int(_cx), int(0 - _my * (t / _dur))))

                                elif effect == 'pan_down':
                                    clip = clip.with_position(lambda t, _my=max_y, _cx=center_x, _dur=dur: (int(_cx), int(-_my + _my * (t / _dur))))

                                # Wrap
                                clip = CompositeVideoClip([clip], size=(w, h)).with_duration(dur)

                    except Exception as e:
                        print(f"Effect Error: {e}")
                        try:
                            with open("debug_effects_trace.txt", "a", encoding="utf-8") as df:
                                df.write(f"Img[{i}] ERROR applying effect '{effect}': {str(e)}\n")
                        except: pass
                        pass

                clips.append(clip)
                
                # [NEW] Scene SFX Handling
                if sfx_map:
                    s_idx = i + 1
                    sfx_p = sfx_map.get(s_idx) or sfx_map.get(str(s_idx))
                    if sfx_p and os.path.exists(sfx_p):
                         try:
                             from moviepy.audio.io.AudioFileClip import AudioFileClip
                             sfx_clip = AudioFileClip(sfx_p)
                             # Overlay SFX on the current clip's duration
                             # MoviePy 2.x: CompositeAudioClip needed, or set_audio with addition
                             # For simplicity, we'll collect these overlays and apply at the end or track them.
                             # But here clips is a list of VideoClips.
                             # Let's attach it to the clip's audio.
                             if clip.audio:
                                 from moviepy.audio.AudioClip import CompositeAudioClip
                                 # Mix original audio (e.g. silence or background) with SFX
                                 # We need to ensure SFX doesn't exceed clip duration
                                 sfx_clip = sfx_clip.with_duration(min(sfx_clip.duration, dur))
                                 clip = clip.with_audio(CompositeAudioClip([clip.audio, sfx_clip]))
                             else:
                                 clip = clip.with_audio(sfx_clip.with_duration(min(sfx_clip.duration, dur)))
                             print(f"🔊 [SFX] Applied to Scene {i+1}: {os.path.basename(sfx_p)}")
                         except Exception as se:
                             print(f"SFX Overlay Error: {se}")

                current_duration += dur

        if not clips and video is None:
            raise ValueError("유효한 이미지나 배경 동영상이 없습니다")

        # 클립 연결 (이미지가 있을 때만)
        if clips:
            video_slideshow = concatenate_videoclips(clips, method="chain")
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
            # [FIX] Enhanced Audio Mixing (Narration + SFX + BGM)
            audio = AudioFileClip(audio_path)
            
            # [NEW] Background Music (BGM) Overlay
            bgm_path = subtitle_settings.get("bgm_path") # Passed through settings or direct param
            if bgm_path and os.path.exists(bgm_path):
                try:
                    bgm_clip = AudioFileClip(bgm_path).with_duration(audio.duration).with_volume(0.3) # 30% volume
                    from moviepy.audio.AudioClip import CompositeAudioClip
                    audio = CompositeAudioClip([audio, bgm_clip])
                    print(f"🎵 [BGM] Mixed into final: {os.path.basename(bgm_path)}")
                except Exception as bge:
                    print(f"BGM Mixing Error: {bge}")

            # 오디오 길이에 맞춰 비디오 조절
            check_duration = audio.duration
            try:
                import pydub
                check_duration = pydub.AudioSegment.from_file(audio_path).duration_seconds
            except:
                pass
            
            # Adjust video duration to match audio duration
            if audio.duration > video.duration:
                if check_duration > video.duration + 0.5:
                    print(f"DEBUG: Audio ({check_duration:.2f}s) is longer than video. Extending last clip.")
                    last_dur = duration_per_image[-1] if isinstance(duration_per_image, list) else duration_per_image
                    last_clip = clips[-1].with_duration(check_duration - video.duration + last_dur)
                    clips[-1] = last_clip
                    video = concatenate_videoclips(clips, method="compose")
                
            elif video.duration > audio.duration + 0.3:
                print(f"DEBUG: Video ({video.duration}s) is longer than Audio. Trimming.")
                video = video.with_subclip(0, audio.duration)

            video = video.with_audio(audio)

            
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
                    title_clip = title_clip.with_position(("center", 150)) 
                    title_clip = title_clip.with_duration(video.duration)
                    
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
                # [NEW] Check for focal point
                focal_y = 0.5
                # The 'i' variable is not available here, as this is for the single thumbnail.
                # If focal_point_ys is meant for the thumbnail, it should be passed directly or be the first element.
                # Assuming focal_point_ys is for the main image sequence, and thumbnail might have its own or default.
                # For now, we'll use a default focal_y for the thumbnail.
                
                # Use _create_cinematic_frame to ensure it fits resolution beautifully
                baked_thumb_path = self._create_cinematic_frame(thumbnail_path, resolution, focal_point_y=focal_y)
                temp_files.append(baked_thumb_path)
                
                thumb_clip = ImageClip(baked_thumb_path).with_duration(0.1) # 0.1s duration
                
                # [FIX] Ensure thumb_clip has silence to match main audio structure if needed
                from moviepy.audio.AudioClip import AudioClip
                silence = AudioClip(lambda t: 0, duration=0.1)
                thumb_clip = thumb_clip.with_audio(silence)
                
                # 2. Concatenate [Thumb] + [Main Video]
                # Use 'chain' method since resolutions are now identical
                video = concatenate_videoclips([thumb_clip, video], method="chain")
                
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
            
            # [CHANGED] 비율 기반 폰트 크기 (영상 높이의 %)
            font_size_percent = s_settings.get("font_size", 5.0)  # 기본 5%
            font_size_percent = s_settings.get("font_size", 5.0)
            v_h = video.h if hasattr(video, 'h') else (resolution[1] if isinstance(resolution, (list, tuple)) else 1080)
            f_size = int(v_h * (float(font_size_percent) / 100.0))
            # UI Slider is 1.0 ~ 15.0 (Percent)
            # DB might have 30 (Legacy Pixel? or Error?) -> Treat > 20 as Pixel
            if 0.1 <= font_size_percent <= 20:
                # Percentage mode (normal usage, 0.1% ~ 20%)
                # [FIX] Apply 1.0x scaling (Reduced from 1.3) specifically for clean look
                # UI Slider is 1.0 ~ 15.0 (Percent)
                f_size = int(video.h * (font_size_percent / 100) * 1.0)
                
                # [SAFETY] Limit font size based on width (especially for Shorts)
                # Ensure roughly 10 chars fit in width? No, just cap max pixel size.
                max_width_limit = int(video.w * 0.15) # Max 15% of width per character approx
                if f_size > max_width_limit:
                    f_size = max_width_limit
            else:
                # Pixel mode (Legacy or explicit large pixel values)
                # e.g. 30 -> 30px (Tiny, but safe)
                f_size = int(font_size_percent)
            
            # [FIX] Handle 0 font size (Disable Subtitles)
            if f_size <= 0:
                 print("DEBUG_RENDER: Subtitle font size 0 detected. Disabling subtitles.")
                 subtitles = []
            
            # [DEBUG] Force Log to file to confirm actual value
            try:
                with open("debug_font_size.txt", "a", encoding="utf-8") as df:
                    df.write(f"Timestamp: {datetime.datetime.now()}, Pct: {font_size_percent}, CalcSize: {f_size}, VideoH: {video.h}, Settings: {s_settings}\n")
            except:
                pass
            
            print(f"DEBUG_RENDER: Font size: {font_size_percent}% → {f_size}px (video height: {video.h}px)")
            
            # [FIX] Enhanced Settings Retrieval (Support both 'subtitle_' prefix and shorthand)
            f_color = s_settings.get("subtitle_base_color") or s_settings.get("font_color", "white")
            f_name = s_settings.get("subtitle_font") or s_settings.get("font", config.DEFAULT_FONT_PATH)
            s_style = s_settings.get("style_name", "Basic_White")
            
            s_stroke_color = s_settings.get("subtitle_stroke_color") or s_settings.get("stroke_color", "black")
            
            # Stroke Width Logic
            raw_stroke_width = s_settings.get("subtitle_stroke_width")
            if raw_stroke_width is None:
                raw_stroke_width = s_settings.get("stroke_width", 3.0) # Default if completely missing
            s_stroke_width = float(raw_stroke_width)
            
            s_stroke_enabled = int(s_settings.get("subtitle_stroke_enabled", 0))
            if s_stroke_width > 0:
                s_stroke_enabled = 1
            
            if not s_stroke_enabled:
                s_stroke_width = 0.0
            else:
                # [FIX] Scale stroke width based on resolution to match HTML Preview
                # Preview box is approx 360-400px high. Render is 1080px+.
                # Scale Factor = Video Height / 360
                scale_factor = v_h / 360.0
                s_stroke_width = s_stroke_width * scale_factor
                print(f"DEBUG_RENDER: Scaled Stroke Width: {raw_stroke_width} -> {s_stroke_width:.2f} (Factor: {scale_factor:.2f})")
            
            # [LOG] Log the settings being used for the render
            try:
                with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as df:
                    df.write(f"[{datetime.datetime.now()}] RENDER_SETTINGS: font='{f_name}', color='{f_color}', style='{s_style}', stroke_color='{s_stroke_color}', stroke_enabled={s_stroke_enabled}, stroke_width={s_stroke_width}, bg_enabled={s_settings.get('bg_enabled')}\n")
            except: pass

            for sub in subtitles:
                if not isinstance(sub, dict):
                    print(f"⚠️ [WARNING] Invalid subtitle format (not a dict): {sub}")
                    continue
                try:
                    # [NEW] Enhanced Background Logic
                    bg_enabled = bool(int(s_settings.get("bg_enabled", 1)) == 1)
                    final_bg = False
                    if bg_enabled:
                         hex_color = s_settings.get("bg_color", "#000000")
                         opacity = float(s_settings.get("bg_opacity", 0.5))
                         # Convert Hex to RGB then add Opacity
                         hex_color = hex_color.lstrip('#')
                         rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
                         final_bg = (*rgb, int(opacity * 255))

                    txt_img_path = self._create_subtitle_image(
                        text=sub["text"],
                        width=video.w,
                        font_size=f_size,
                        font_color=f_color,
                        font_name=f_name,
                        style_name=s_style,
                        stroke_color=s_stroke_color,
                        stroke_width=s_stroke_width,
                        bg_color=final_bg,
                        line_spacing_ratio=float(s_settings.get("subtitle_line_spacing") or s_settings.get("line_spacing", 0.1))
                    )
                    
                    if txt_img_path:
                        # 임시파일 추적 (나중에 삭제)
                        temp_files.append(txt_img_path)
                        
                        txt_clip = ImageClip(txt_img_path)
                        
                        # [FIX] Position Logic
                        # 1. Check for custom position in settings
                        # settings usually store 'subtitle_pos_y' as "123px" or "10%" string
                        custom_y = s_settings.get('subtitle_pos_y') or s_settings.get('pos_y') 
                        
                        y_pos = None
                        
                        if custom_y:
                            try:
                                if "px" in str(custom_y):
                                    y_pos = int(float(str(custom_y).replace("px", "")))
                                elif "%" in str(custom_y):
                                    pct = float(str(custom_y).replace("%", ""))
                                    y_pos = int(video.h * (pct / 100))
                                else:
                                    y_pos = int(float(custom_y))
                            except:
                                y_pos = None

                        # 2. If no custom pos, use Default (11/16ths rule for Shorts, or Bottom Margin for others)
                        if y_pos is None:
                            # 11/16 is approx 0.6875.
                            # Standard Lower Third is often around 70-80%.
                            # User requested 11/16ths specifically.
                            target_ratio = video.h * (11/16)
                            y_pos = int(target_ratio)

                        # Ensure it stays on screen (bottom padding)
                        if y_pos + txt_clip.h > video.h:
                             y_pos = video.h - txt_clip.h - 50 # Safety buffer

                        txt_clip = txt_clip.with_position(("center", y_pos))

                        txt_clip = txt_clip.with_start(sub["start"])
                        txt_clip = txt_clip.with_duration(sub["end"] - sub["start"])
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

            # [NEW] Prepend Intro Video
            if intro_video_path and os.path.exists(intro_video_path):
                print(f"DEBUG: Prepending Intro Video: {intro_video_path}")
                try:
                    intro_clip = VideoFileClip(intro_video_path)
                    
                    # Resize/Crop to match main video resolution
                    target_w, target_h = resolution
                    
                    # Aspect Ratio Match
                    if abs((intro_clip.w / intro_clip.h) - (target_w / target_h)) > 0.01:
                        # Ratio mismatch -> Use _create_cinematic_frame logic but for video?
                        # Simplest: Resize & Crop
                        intro_ratio = intro_clip.w / intro_clip.h
                        target_ratio = target_w / target_h
                        
                        if intro_ratio > target_ratio:
                            intro_clip = vfx.resize(intro_clip, height=target_h)
                        else:
                            intro_clip = vfx.resize(intro_clip, width=target_w)
                        
                        # Center Crop
                        intro_clip = intro_clip.crop(x1=intro_clip.w/2 - target_w/2, y1=intro_clip.h/2 - target_h/2, width=target_w, height=target_h)
                    else:
                        # Direct Resize
                        intro_clip = vfx.resize(intro_clip, new_size=(target_w, target_h))
                    
                    # Concatenate [Intro] + [Main Video]
                    video = concatenate_videoclips([intro_clip, video], method="chain")
                    print(f"Intro Video successfully prepended. New total duration: {video.duration:.2f}s")
                    
                except Exception as e:
                    print(f"Intro Video failed to prepend: {e}")

            # [FIX] Unique temp audio path to avoid conflicts/locks
            import uuid
            # [FIX] Render Video and Audio Separately to prevent FFMPEG Hangs on Windows
            import imageio_ffmpeg
            import subprocess
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            
            temp_video_path = output_path.replace(".mp4", "_noaudio.mp4")
            temp_audio_export_path = os.path.join(self.output_dir, f"temp_audio_export_{uuid.uuid4()}.wav")
            
            # 1. Render Video (No Audio)
            print(f"DEBUG: Rendering video only to {temp_video_path}")
            video.write_videofile(
                temp_video_path,
                fps=fps,
                codec="libx264",
                audio=False, # [KEY FIX] Disable Audio Rendering in Muxer
                threads=1, # [FIX] Hardcoded to 1
                preset="medium", 
                logger=None 
            )
            
            # 2. Export Audio
            if video.audio:
                print(f"DEBUG: Exporting audio to {temp_audio_export_path}")
                # Use WAV for maximum stability in intermediate pass
                # [FIX] MoviePy 2.0: explicitly provide 'fps' (sample rate) as attribute is removed
                video.audio.write_audiofile(temp_audio_export_path, fps=44100, codec="pcm_s16le", logger=None)
                
                # 3. Merge
                print(f"DEBUG: Merging video and audio...")
                cmd = [
                    ffmpeg_exe, "-y",
                    "-i", temp_video_path,
                    "-i", temp_audio_export_path,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-shortest",
                    output_path
                ]
                # Hide console window on Windows
                startupinfo = None
                if os.name == 'nt':
                     startupinfo = subprocess.STARTUPINFO()
                     startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
                subprocess.run(cmd, check=True, startupinfo=startupinfo)
                
                # Cleanup
                if os.path.exists(temp_audio_export_path): os.remove(temp_audio_export_path)
            else:
                # No audio, just rename video
                print("DEBUG: No audio found, renaming video file.")
                if os.path.exists(output_path): os.remove(output_path)
                os.rename(temp_video_path, output_path)
                
            if os.path.exists(temp_video_path): os.remove(temp_video_path)
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

        
    def _create_cinematic_frame(self, image_path: str, target_size: tuple, template_path: str = None, focal_point_y: float = 0.5, allow_tall: bool = False):
        """
        [MODIFIED] Vertical Aspect Ratio Logic 2.0
        - If allow_tall=True -> No Crop vertically (Keep full height for Panning)
        """
        from PIL import Image
        import uuid
        
        try:
            target_w, target_h = target_size
            img = Image.open(image_path)
            
            # Convert to RGB
            if img.mode != 'RGB':
                img = img.convert('RGB')

            img_w, img_h = img.size
            
            # Always Fit to Width
            new_w = target_w
            new_h = int(new_w * (img_h / img_w))
            
            # High-quality Resize
            img_resized = img.resize((new_w, new_h), Image.LANCZOS)
            
            if allow_tall and new_h > target_h:
                # [NEW] Skip cropping onto target_h background. Just return the resized full tall image.
                out_fn = f"cinematic_tall_{uuid.uuid4().hex[:8]}.jpg"
                out_path = os.path.join(config.OUTPUT_DIR, out_fn)
                img_resized.save(out_path, quality=90)
                return out_path

            # Create Black Background
            bg = Image.new('RGB', (target_w, target_h), (0, 0, 0))
            
            x_offset = (target_w - new_w) // 2
            
            if new_h > target_h:
                # Tall image (needs cropping)
                y_offset = int(target_h / 2 - (new_h * focal_point_y))
                # Clamp to avoid gaps
                min_y = target_h - new_h
                max_y = 0
                y_offset = max(min_y, min(max_y, y_offset))
            else:
                # Wide/Short image (needs letterbox)
                y_offset = (target_h - new_h) // 2

            bg.paste(img_resized, (x_offset, y_offset))
            
            # Template Overlay
            if template_path and os.path.exists(template_path):
                 try:
                     tmpl = Image.open(template_path).convert("RGBA")
                     tmpl = tmpl.resize((target_w, target_h), Image.LANCZOS)
                     bg.paste(tmpl, (0, 0), tmpl)
                 except: pass

            # Save to temp
            temp_name = f"cinematic_{uuid.uuid4()}.jpg"
            save_path = os.path.join(self.output_dir, temp_name)
            bg.save(save_path, quality=95)
            
            return save_path

        except Exception as e:
            print(f"Cinematic Frame Error: {e}")
            return image_path

    def _resize_image_to_fill(self,image_path: str, target_size: tuple) -> str:
        """
        이미지를 화면에 꽉 차게 리사이즈 (블러 배경 없이)
        """
        from PIL import Image
        import uuid
        
        target_w, target_h = target_size
        
        # 원본 열기
        img = Image.open(image_path).convert("RGB")
        
        # 비율 계산하여 꽉 차게 크롭/리사이즈 (Aspect Fill)
        img_ratio = img.width / img.height
        target_ratio = target_w / target_h
        
        if img_ratio > target_ratio:
            # 이미지가 더 납작함 -> 높이에 맞춤 후 좌우 크롭
            new_h = target_h
            new_w = int(new_h * img_ratio)
        else:
            # 이미지가 더 길쭉함 -> 너비에 맞춤 후 상하 크롭
            new_w = target_w
            new_h = int(new_w / img_ratio)
            
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # 중앙 크롭
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        img = img.crop((left, top, left + target_w, top + target_h))
        
        # 저장
        output_path = os.path.join(self.output_dir, f"filled_{uuid.uuid4()}.jpg")
        img.save(output_path, quality=95)
        
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
                final_words = []
                for w in ai_words:
                    if hasattr(w, 'word'):
                        final_words.append({"word": w.word, "start": w.start, "end": w.end})
                    elif isinstance(w, dict):
                        final_words.append({"word": w.get("word", ""), "start": w.get("start", 0), "end": w.get("end", 0)})

            # [IMPROVED] Smart Semantic Segmentation (2-Line Limit Rule)
            # 1. 절대 한계: 40자 (2줄 초과 방지)
            # 2. 의미 분할: 조사/어미 뒤, 문장부호 뒤
            # 3. 호흡 분할: 0.5초 이상 침묵
            
            MAX_CHARS_PER_BLOCK = 40
            SOFT_LIMIT_CHARS = 12     # 이 길이 넘으면 조사/어미 체크 시작 (조금 더 자주 끊기게 수정)
            MIN_SILENCE_GAP = 0.5
            
            # Heuristics
            SEMANTIC_ENDINGS = ('은', '는', '이', '가', '을', '를', '에', '서', '로', '에게', '고', '며', '니', '면', '지', '나', '해', '돼', '요', '죠')
            SENTENCE_ENDINGS = ('.', '?', '!', ',', '…')

            if final_words:
                current_words = []
                current_block_start = final_words[0]["start"]
                
                for i, word_obj in enumerate(final_words):
                    word_text = word_obj["word"].strip()
                    word_start = word_obj["start"]
                    word_end = word_obj["end"]
                    
                    # 0. Calculate Gap from previous
                    prev_end = final_words[i-1]["end"] if i > 0 else word_start
                    gap = word_start - prev_end
                    
                    # Current text accumulated with new word
                    temp_ws = current_words + [word_obj]
                    temp_text = " ".join([w["word"] for w in temp_ws]).strip()
                    temp_len = len(temp_text)
                    
                    should_break = False
                    
                    # Rule 1: Silence Gap (Long pause)
                    if gap > MIN_SILENCE_GAP and current_words:
                        should_break = True
                        
                    # Rule 2: Hard Limit (Max Chars)
                    elif temp_len > MAX_CHARS_PER_BLOCK:
                        should_break = True
                        
                    # Rule 3: Semantic Soft Break & Punctuation
                    # 현재 블록이 어느정도 찼고(SOFT_LIMIT), 이전 단어가 조사/어미/문장부호로 끝났다면 끊어줌
                    elif current_words and len(" ".join([w["word"] for w in current_words])) > SOFT_LIMIT_CHARS:
                         last_w = current_words[-1]["word"].strip()
                         # 문장부호 체크
                         if last_w.endswith(SENTENCE_ENDINGS):
                             should_break = True
                         else:
                             # 조사/어미 체크 (특수문자 제거 후)
                             clean_last = re.sub(r'[^\w가-힣]', '', last_w)
                             if clean_last.endswith(SEMANTIC_ENDINGS):
                                 should_break = True
                
                    if should_break:
                        # Commit Current Block
                        block_text = " ".join([w["word"] for w in current_words]).strip()
                        # Brackets clean
                        block_text = re.sub(r'\([^)]*\)|\[[^\]]*\]|\*+[^*]+\*+', '', block_text).strip()
                        
                        # [Quality] Ensure start < end
                        c_end = prev_end
                        if c_end <= current_block_start: c_end = current_block_start + 0.1
                        
                        if block_text:
                            subtitles.append({
                                "start": current_block_start,
                                "end": c_end,
                                "text": block_text
                            })
                        
                        # Start New Block
                        current_words = [word_obj]
                        current_block_start = word_start
                    else:
                        current_words.append(word_obj)
                        
                # Commit Final Block
                if current_words:
                    block_text = " ".join([w["word"] for w in current_words]).strip()
                    block_text = re.sub(r'\([^)]*\)|\[[^\]]*\]|\*+[^*]+\*+', '', block_text).strip()
                    if block_text:
                        subtitles.append({
                            "start": current_block_start,
                            "end": final_words[-1]["end"],
                            "text": block_text
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
                # [FIX] Scale Stroke Width for Add Subtitles (Post-processing)
                current_stroke_width = stroke_width
                if current_stroke_width is None:
                     current_stroke_width = 0.0
                else:
                     # Scale if video object exists
                     if hasattr(video, 'h'):
                         scale_factor = video.h / 360.0 # Match create_slideshow logic
                         current_stroke_width = float(current_stroke_width) * scale_factor
                
                txt_img_path = self._create_subtitle_image(
                    text=sub["text"],
                    width=video.w,
                    font_size=font_size,
                    font_color=font_color,
                    font_name=font,
                    style_name=style_name,
                    stroke_color=stroke_color,
                    stroke_width=current_stroke_width  # [FIX] Use scaled width
                )
                
                if txt_img_path:
                    txt_clip = ImageClip(txt_img_path)
                    # [FIX] Force Absolute Bottom Positioning
                    # Ensure video object is available or passed correctly.
                    # If 'video' is a filepath string, we can't get .h from it directly.
                    # But add_subtitles is called with 'video' being a VideoFileClip usually.
                    if hasattr(video, 'h'):
                        bottom_margin = int(video.h * 0.08)
                        y_pos = video.h - txt_clip.h - bottom_margin
                        txt_clip = txt_clip.with_position(("center", y_pos))
                    else:
                        # Fallback if video is not a clip object
                        txt_clip = txt_clip.with_position(("center", 0.90), relative=True)
                    
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

    def _create_subtitle_image(self, text, width, font_size, font_color, font_name, style_name="Basic_White", stroke_color=None, stroke_width_ratio=None, stroke_width=None, bg_color=None, line_spacing_ratio=0.1):
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
             final_stroke_width = float(stroke_width)
        else:
             ratio = stroke_width_ratio if stroke_width_ratio is not None else style.get("stroke_width_ratio", 0.1)
             final_stroke_width = max(1, int(font_size * ratio)) if ratio > 0 else 0

        # [FIX] Allow bg_color override (Support explicit False to disable)
        if bg_color is False:
             bg_color = None
        elif bg_color is None:
             bg_color = style.get("bg_color", None)
        # else: use the passed bg_color (e.g. from main.py)
        
        # 폰트 로드
        font = None
        
        # 폰트 매핑 (UI 이름 -> 실제 파일명)
        font_mapping = {
            "GmarketSans": "GmarketSansTTFBold.ttf", # Fallback
            "GmarketSansBold": "GmarketSansTTFBold.ttf",
            
            "나눔명조": "NanumMyeongjo.ttf",
            "NanumMyeongjo": "NanumMyeongjo.ttf",
            
            "쿠키런": "CookieRun Regular.ttf",
            "CookieRun-Regular": "CookieRun Regular.ttf",
            
            "맑은 고딕": "malgun.ttf",
            "Malgun Gothic": "malgun.ttf",

            # [NEW] 추가 서체 매핑
            "TmonMonsori": "TmonMonsori.ttf",
            "Jalnan": "Jalnan.ttf",
            "Pretendard-Bold": "Pretendard-Bold.ttf",
            "NanumSquareExtraBold": "NanumSquareExtraBold.ttf",
            "BinggraeMelona-Bold": "BinggraeMelona-Bold.ttf",
            "NetmarbleB": "NetmarbleB.ttf",
            "ChosunIlboMyungjo": "ChosunIlboMyungjo.ttf",
            "MapoFlowerIsland": "MapoFlowerIsland.ttf",
            "S-CoreDream-6Bold": "S-CoreDream-6Bold.ttf",
            "Gungsuh": "batang.ttc",
            "gungsuh": "batang.ttc",
            "궁서": "batang.ttc",
            "궁서체": "batang.ttc",
            
            # [NEW] Multilingual Fonts
            "Impact": "impact.ttf",
            "Roboto": "Roboto-Bold.ttf",
            "NotoSansJP": "msgothic.ttc", # Fallback to standard Windows font
            "ja": "msgothic.ttc"
        }
        
        target_font_file = font_mapping.get(font_name, font_name)
        if not target_font_file.lower().endswith((".ttf", ".ttc")):
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
        
        # [DEBUG] Font Path Logging
        try:
             with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as df:
                 df.write(f"[{datetime.datetime.now()}] FONT_DEBUG: target='{target_font_file}', found_path='{font_path}', search_paths={search_paths}\n")
        except: pass
        
        # G마켓 산스 없으면 malgunbd.ttf (굵은 고딕) 시도
        if not font_path and "Gmarket" in font_name:
             font_path = "C:/Windows/Fonts/malgunbd.ttf"
             
        # 그래도 없으면 기본
        if not font_path or not os.path.exists(font_path):
             font_path = "C:/Windows/Fonts/malgun.ttf"
             
        try:
            if font_path and os.path.exists(font_path):
                # [FIX] TTC Index Handling (Gungsuh is index 2 in batang.ttc)
                idx = 0
                if "batang.ttc" in font_path.lower() and ("gungsuh" in font_name.lower() or "궁서" in font_name):
                    idx = 2
                
                log_msg = f"DEBUG_FONT: Loading '{font_name}' from '{font_path}' with index {idx}"
                print(log_msg)
                try:
                    with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as df:
                        df.write(f"[{datetime.datetime.now()}] {log_msg}\n")
                except: pass

                font = ImageFont.truetype(font_path, font_size, index=idx)
                
                success_msg = f"DEBUG_FONT: Successfully loaded {font.getname()}"
                print(success_msg)
                try:
                    with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as df:
                        df.write(f"[{datetime.datetime.now()}] {success_msg}\n")
                except: pass
            else:
                fail_msg = f"DEBUG_FONT: Font path not found for '{font_name}'. Falling back."
                print(fail_msg)
                try:
                    with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as df:
                        df.write(f"[{datetime.datetime.now()}] {fail_msg}\n")
                except: pass
                font = ImageFont.truetype("arial.ttf", font_size)
        except Exception as e:
             print(f"DEBUG_FONT: Font loading FAILED for '{font_name}': {e}")
             try:
                 font = ImageFont.load_default()
             except:
                 pass

        # Balanced Wrapping Logic with Manual Newline Support
        # [FIX] 프리뷰와 렌더링 일치를 위한 개선
        # - 이미 \n으로 나뉜 텍스트는 최대한 존중
        # - 픽셀 너비 초과 시에만 단어 단위로 줄바꿈 (화면 넘침 방지)
        safe_width = int(width * 0.9)
        
        def get_text_width(text, font):
            dummy_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
            return dummy_draw.textlength(text, font=font)

        # [FIX] Manual Newline Support - 사용자가 입력한 \n을 기준으로 먼저 분리
        manual_lines = text.split('\n')
        wrapped_lines = []
        
        # [MODIFIED] Max lines increased to 3 for better accessibility
        MAX_LINES = 3
        
        for m_line in manual_lines:
            m_line = m_line.strip()
            if not m_line:
                continue
            
            # 이미 최대 줄 수에 도달하면 중단
            if len(wrapped_lines) >= MAX_LINES:
                break
                
            line_width = get_text_width(m_line, font)
            
            if line_width <= safe_width:
                wrapped_lines.append(m_line)
            else:
                # [FIX] 픽셀 너비 초과 - 단어 단위로 줄바꿈
                words = m_line.split(' ')
                current_line = []
                current_width = 0
                
                for word in words:
                    # Skip empty words
                    if not word: continue
                    
                    word_width = get_text_width(word + " ", font)
                    
                    if current_width + word_width > safe_width and current_line:
                        wrapped_lines.append(" ".join(current_line))
                        current_line = [word]
                        current_width = word_width
                        
                        # [FIX] If we reached limit, stop and add rest to last line (but limited)
                        if len(wrapped_lines) >= MAX_LINES:
                            # Don't break immediately, let's join the rest of the words for the last allowed line
                            # Actually, if we are at MAX_LINES, we replace the last line with current+remaining
                            remaining = words[words.index(word):]
                            wrapped_lines[-1] = " ".join(current_line + remaining)
                            break
                    else:
                        current_line.append(word)
                        current_width += word_width
                else:
                    # for-else: break 없이 끝난 경우
                    if current_line and len(wrapped_lines) < MAX_LINES:
                        wrapped_lines.append(" ".join(current_line))
                    elif current_line and len(wrapped_lines) >= MAX_LINES:
                        # Append to last line
                        wrapped_lines[-1] += " " + " ".join(current_line)
                
        # [Final Safety Slice]
        wrapped_lines = wrapped_lines[:MAX_LINES]
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

        # [FIX] 높이 계산 - 줄 수에 비례하여 충분한 공간 확보 + Stroke 공간 추가
        line_count = len(wrapped_lines)
        ascent, descent = font.getmetrics()
        
        # [CHANGED] More robust height calculation: (LineHeight * Count) + Spacing + Stroke + Padding
        # This is more reliable than multiline_textbbox for some fonts
        total_text_h = (ascent + descent) * line_count + (int((ascent + descent) * line_spacing_ratio) * (line_count - 1))
        
        vertical_safety = int(font_size * 0.8) # Increased from 0.5 to 0.8
        
        img_w = width
        # Use max of measured height and calculated height for safety
        actual_h = max(text_h, total_text_h)
        img_h = int(actual_h + (pad_y * 2) + final_stroke_width * 6 + vertical_safety)
        
        img = Image.new('RGBA', (img_w, img_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        center_x = img_w // 2
        center_y = img_h // 2
        
        # [FIX] Multi-line Background Support
        # Instead of one big box, draw per-line rounded strips
        
        # [DEBUG] Log wrapped lines for troubleshooting
        print(f"DEBUG_SUBTITLE: wrapped_lines count = {len(wrapped_lines)}, lines = {wrapped_lines}")
        
        # Calculate Starting Y (Top of Text Block)
        current_y = center_y - (text_h // 2)
        
        # Font Metrics for consistent spacing
        try:
            ascent, descent = font.getmetrics()
            line_height_font = ascent + descent
        except:
             # Fallback
             line_height_font = font.getbbox('A')[3]
        
        line_spacing = int(line_height_font * line_spacing_ratio) # [FIX] Use user-controlled ratio (Default 0.1)
        
        # [FIX] Precision Vertical Alignment
        # Calculate background per line using actual text boundaries
        
        # Consistent total height calculation regardless of background
        full_line_height = line_height_font + line_spacing
        
        for idx, line in enumerate(wrapped_lines):
            if not line or not line.strip():
                current_y += full_line_height
                continue
                
            # Measure Precise line dimensions
            s_width = int(max(1, round(final_stroke_width))) if final_stroke_width > 0.01 else 0
            l_bbox = draw.textbbox((0, 0), line, font=font, stroke_width=s_width)
            lw = l_bbox[2] - l_bbox[0]
            lh = l_bbox[3] - l_bbox[1]
            
            # Calculate actual line_x to center the text
            line_x = center_x - (lw / 2)
            
            # Draw Background (per line)
            if bg_color:
                # [FIX] Tighter vertical positioning to prevent merging into one block
                # bg_h should be just enough to cover the font height
                bg_h = line_height_font * 1.05 # Reduced from 1.2 to 1.05
                offset_y = (bg_h - line_height_font) / 2
                
                # bx0, bx1 (Horizontal)
                bx0 = line_x - pad_x
                bx1 = line_x + lw + pad_x
                
                # by0, by1 (Vertical) - Tightly around the font
                by0 = current_y - offset_y
                by1 = current_y + line_height_font + offset_y
                
                draw.rounded_rectangle([bx0, by0, bx1, by1], radius=10, fill=bg_color)
            
            # 2. Draw Text (Always at the same current_y)
            if s_width > 0:
                draw.text((line_x, current_y), line, font=font, fill=final_font_color, 
                          stroke_width=s_width, stroke_fill=stroke_color)
            else:
                draw.text((line_x, current_y), line, font=font, fill=final_font_color)
                
            # Next Line
            current_y += full_line_height

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
                stroke_width=stroke_width,
                bg_color=False # [FIX] Explicitly disable bg strip for preview by default
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

    def generate_subtitles_from_metadata(self, audio_path: str) -> List[dict]:
        """
        TTS 생성시 만들어진 메타데이터(.vtt 또는 .json)를 이용하여 자막 생성
        (Whisper 없이도 정확한 싱크 가능)
        """
        import os
        import json
        import re

        if not audio_path:
            return []

        base_path = os.path.splitext(audio_path)[0]
        vtt_path = base_path + ".vtt"
        json_path = base_path + "_alignment.json"

        # 1. Edge TTS (.vtt) - Sentence/Word boundaries
        if os.path.exists(vtt_path):
            print(f"DEBUG: Found VTT metadata: {vtt_path}")
            subtitles = []
            
            def parse_vtt_time(t_str):
                # 00:00:00.000
                try:
                    parts = t_str.strip().split(':')
                    if len(parts) == 3:
                        h = int(parts[0])
                        m = int(parts[1])
                        s = float(parts[2])
                        return h * 3600 + m * 60 + s
                    elif len(parts) == 2:
                        m = int(parts[0])
                        s = float(parts[1])
                        return m * 60 + s
                    return 0.0
                except:
                    return 0.0

            try:
                with open(vtt_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                blocks = re.split(r'\n\s*\n', content)
                for block in blocks:
                    lines = block.strip().splitlines()
                    if not lines: continue
                    
                    time_line = None
                    text_lines = []
                    for line in lines:
                        if '-->' in line:
                            time_line = line
                        elif time_line and not line.startswith('NOTE') and not line.startswith('WEBVTT'): 
                            text_lines.append(line)
                    
                    if time_line and text_lines:
                        times = time_line.split('-->')
                        start = parse_vtt_time(times[0])
                        end = parse_vtt_time(times[1])
                        text = " ".join(text_lines).strip()
                        if text:
                            subtitles.append({"start": start, "end": end, "text": text})
                
                if subtitles:
                    print(f"DEBUG: Loaded {len(subtitles)} subtitles from VTT.")
                    return subtitles
            except Exception as e:
                print(f"Failed to parse VTT: {e}")

        # 2. ElevenLabs (.json) - Word-level alignment
        if os.path.exists(json_path):
            print(f"DEBUG: Found Alignment JSON: {json_path}")
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                if not data: return []

                subtitles = []
                current_block = []
                current_start = 0.0
                current_chars = 0
                MAX_CHARS = 40
                
                # Check format: Is it list of {word, start, end}?
                # Yes, tts_service saves it that way.
                
                for i, item in enumerate(data):
                    word = item.get('word', '')
                    start = item.get('start', 0.0)
                    end = item.get('end', 0.0)
                    
                    if not current_block:
                        current_start = start
                    
                    current_block.append(word)
                    current_chars += len(word)
                    
                    # Grouping Logic
                    is_end_char = word.strip().endswith(('.', '?', '!'))
                    is_long = current_chars > MAX_CHARS
                    is_last = (i == len(data) - 1)
                    
                    if is_end_char or is_long or is_last:
                        # Reconstruct sentence
                        text = "".join(current_block)
                        # Fix spacing if words don't have spaces (ElevenLabs returns raw chars sometimes?)
                        # Actually tts_service _chars_to_words_alignment constructs words.
                        # If words lack spaces, join with space.
                        # But better: just join with space and strip.
                        if " " not in text and len(current_block) > 1:
                             text = " ".join(current_block)
                        
                        subtitles.append({
                            "start": current_start,
                            "end": end,
                            "text": text.strip()
                        })
                        current_block = []
                        current_chars = 0
                
                if subtitles:
                    print(f"DEBUG: Loaded {len(subtitles)} subtitles from Alignment JSON.")
                    return subtitles
                    
            except Exception as e:
                print(f"Failed to parse Alignment JSON: {e}")

        return []
        """
        Ken Burns 효과 (줌인)가 적용된 클립 생성
        """
        from moviepy import ImageClip, CompositeVideoClip
        
        # 기본 이미지 클립
        img_clip = ImageClip(image_path).with_duration(duration)
        
        # 줌인 효과 (1.0 -> 1.15)
        # lambda t: 1 + 0.03 * t  (5초 동안 약 15% 확대)
        zoom_ratio = 0.03
        
        try:
            # resize 함수: t(시간)에 따라 크기 변경
            # ImageClip에 resize를 적용하면 모든 프레임을 다시 계산함
            zoomed_clip = vfx.resize(img_clip, lambda t: 1 + zoom_ratio * t)
            
            # 중앙 정렬하여 CompositeVideoClip으로 감싸기 (크롭 효과)
            # set_position("center")는 CompositeVideoClip 내에서 중앙 배치
            zoomed_clip = zoomed_clip.with_position("center")
            
            # 최종 크기를 target_size로 고정 (넘치는 부분 잘림 효과)
            final_clip = CompositeVideoClip([zoomed_clip], size=target_size)
            final_clip = final_clip.with_duration(duration)
            return final_clip
        except Exception as e:
            print(f"줌 효과 적용 실패: {e}")
            return img_clip

    def generate_smart_subtitles(self, script_text: str, duration: float) -> List[dict]:
        """
        대본을 지능적으로 분할하고 시간을 배분 (글자수 비례 + 문장 병합)
        """
        if not script_text:
            return []
            
        import re
        
        # 1. Atomic Split (split by punctuation)
        raw_sentences = []
        lines = [L.strip() for L in script_text.splitlines() if L.strip()]
        for line in lines:
            # 문장 부호 뒤 공백 기준 분리
            parts = re.split(r'(?<=[.?!])\s+', line)
            for p in parts:
                if p.strip():
                    raw_sentences.append(p.strip())
        
        if not raw_sentences:
            return []
            
        # 2. Grouping (Merge short sentences) - 자막 퀄리티 향상
        # [MODIFIED] Grouping causes Image Count mismatch (6 images vs 5 subtitles).
        # Disabling grouping to ensure 1 Sentence = 1 Subtitle = 1 Image.
        # Proportional Timing will still handle "Short/Long" duration naturally.
        grouped_sentences = raw_sentences
        
        # grouped_sentences = []
        # current_group = ""
        # MAX_GROUP_LEN = 40 # 자막 한 줄에 적당한 길이 (유튜브 숏츠 기준)
        
        # for s in raw_sentences:
        #     if not current_group:
        #         current_group = s
        #     else:
        #         # 합쳤을 때 너무 길지 않으면 병합
        #         if len(current_group) + len(s) + 1 <= MAX_GROUP_LEN:
        #             current_group += " " + s
        #         else:
        #             grouped_sentences.append(current_group)
        #             current_group = s
        # if current_group:
        #     grouped_sentences.append(current_group)
            
        # 3. Proportional Timing (글자 수 비례 시간 배분)
        # 기존: n등분 (짧은 말도 길게 나옴) -> 수정: 글자 수 비례
        total_chars = sum(len(s.replace(" ", "")) for s in grouped_sentences) # 공백 제외 글자수 기준이 더 정확
        if total_chars == 0:
            return []
            
        char_duration = duration / total_chars
        
        subtitles = []
        current_time = 0.0
        
        for text in grouped_sentences:
            # 공백 제외 길이로 계산
            pure_len = len(text.replace(" ", ""))
            s_duration = pure_len * char_duration
            
            start_t = current_time
            end_t = current_time + s_duration
            
            if end_t > duration:
                end_t = duration
            
            subtitles.append({
                "start": float(f"{start_t:.2f}"), # 소수점 2자리 깔끔하게
                "end": float(f"{end_t:.2f}"),
                "text": text
            })
            current_time = end_t
            
        # 마지막 오차 보정
        if subtitles:
            subtitles[-1]["end"] = duration
            
        print(f"DEBUG: Generated {len(subtitles)} smart subtitles (Weighted Split).")
        return subtitles
    
    def merge_with_intro(self, intro_path: str, main_video_path: str, output_path: str) -> str:
        """
        인트로 영상과 메인 영상을 병합
        FFmpeg concat demuxer 사용
        """
        return self.concatenate_videos([intro_path, main_video_path], output_path)

    def concatenate_videos(self, video_paths: List[str], output_path: str) -> str:
        """
        여러 비디오 파일을 하나로 합칩니다.
        """
        import subprocess
        from pathlib import Path
        import tempfile
        
        try:
            valid_paths = [p for p in video_paths if Path(p).exists()]
            if not valid_paths:
                return ""
            if len(valid_paths) == 1:
                import shutil
                shutil.copy2(valid_paths[0], output_path)
                return output_path

            # concat.txt 파일 생성
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                concat_file = f.name
                for p in valid_paths:
                    abs_p = str(Path(p).absolute()).replace('\\', '/')
                    f.write(f"file '{abs_p}'\n")
            
            # FFmpeg concat 명령
            cmd = [
                config.FFMPEG_PATH,
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c', 'copy',
                '-y',
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
            Path(concat_file).unlink(missing_ok=True)
            
            if result.returncode != 0:
                print(f"Concatenate error: {result.stderr}")
                return valid_paths[0]
            
            return output_path
        except Exception as e:
            print(f"Error concatenating: {e}")
            return video_paths[0] if video_paths else ""

    def extract_last_frame(self, video_path: str, output_image_path: str) -> bool:
        """
        비디오의 마지막 프레임을 이미지로 추출합니다. (영상 연장용)
        """
        import subprocess
        try:
            # -sseof -1: 마지막 1초 지점부터 탐색하여 마지막 프레임 찾기
            cmd = [
                config.FFMPEG_PATH,
                '-sseof', '-1',
                '-i', video_path,
                '-update', '1',
                '-q:v', '1', # Best quality
                '-frames:v', '1',
                '-y',
                output_image_path
            ]
            result = subprocess.run(cmd, capture_output=True)
            return result.returncode == 0
        except Exception as e:
            print(f"Extract frame error: {e}")
            return False

    def apply_slow_mo(self, video_path: str, output_path: str, speed_ratio: float = 0.625) -> str:
        """
        영상 속도를 늦춰 길이를 늘립니다. (보간법 사용)
        0.625 ratio: 5초 -> 8초
        """
        import subprocess
        try:
            # setpts: 속도 조절
            # minterpolate: 프레임 보간 (부드러운 움직임)
            # r=fps (원본 fps 유지)
            # Simplified Slow-mo (setpts only) for stability
            # minterpolate is too heavy and often fails on Windows/Replicate environments
            cmd = f'"{config.FFMPEG_PATH}" -y -i "{video_path}" -filter:v "setpts={1/speed_ratio}*PTS" -r 24 "{output_path}"'
            
            print(f"Applying Slow-mo (ratio {speed_ratio})... CMD: {cmd}")
            # Use shell=True for string command on Windows to handle quotes properly
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            if result.returncode != 0:
                print(f"Slow-mo error: {result.stderr}")
                return video_path
            return output_path
        except Exception as e:
            print(f"Slow-mo exception: {e}")
            return video_path

    def _preprocess_video_with_ffmpeg(self, input_path, width, height, fps=30):
        """
        Use FFMPEG CLI to resize, crop, and re-encode video to target resolution.
        This bypasses MoviePy's heavy resizing and decoding issues.
        """
        import subprocess
        import uuid
        import imageio_ffmpeg
        
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        output_path = os.path.join(self.output_dir, f"video_prep_{uuid.uuid4()}.mp4")
        
        # Scale to cover (Access Aspect Ratio)
        # force_original_aspect_ratio=increase ensures it covers the box
        # crop=w:h cuts the center
        # fps for consistency
        vf_filter = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps}"
        
        cmd = [
            ffmpeg_exe, "-y",
            "-i", input_path,
            "-vf", vf_filter,
            "-c:v", "libx264",
            # [SAFE MODE] Use ultrafast preset for pre-processing stability
            "-preset", "ultrafast",
            "-crf", "23",
            "-an", # No Audio
            output_path
        ]
        
        # Hide console window on Windows
        startupinfo = None
        if os.name == 'nt':
             startupinfo = subprocess.STARTUPINFO()
             startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
             
        print(f"DEBUG: Pre-processing video: {input_path} -> {output_path}")
        subprocess.run(cmd, check=True, startupinfo=startupinfo)
        return output_path

    def _preprocess_video_tall_pan(self, input_path, width, height, duration, fps=30, direction="down"):
        """
        [NEW] 세로로 긴 영상(예: 9:32)에 대해 Full-Travel Pan 효과 적용.
        - Width를 프레임 너비에 맞게 확대 (Height는 비율 유지, 크롭 없음)
        - Top→Bottom 또는 Bottom→Top 전체 스크롤을 FFmpeg crop 필터로 구현
        - 출력: 지정된 width x height 해상도의 pan 영상 mp4

        direction: "down" (위→아래) or "up" (아래→위)
        """
        import subprocess
        import uuid
        import imageio_ffmpeg
        from PIL import Image

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        output_path = os.path.join(self.output_dir, f"video_tall_pan_{uuid.uuid4()}.mp4")

        import cv2
        cmd_probe = [ffmpeg_exe, "-i", input_path] # Keep for print/debug if needed
        
        startupinfo = None
        if os.name == 'nt':
             startupinfo = subprocess.STARTUPINFO()
             startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
             
        try:
            # Use OpenCV to get accurate video dimensions
            cap = cv2.VideoCapture(input_path)
            orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            
            if orig_w <= 0 or orig_h <= 0:
                raise ValueError(f"CV2 returned invalid dimensions: {orig_w}x{orig_h}")
                
                     
        except Exception as e:
            print(f"[TallPan] probe failed ({e}), trying PIL fallback...")
            try:
                img = Image.open(input_path)
                orig_w, orig_h = img.size
            except:
                print(f"[TallPan] Final Fallback: {e}")
                # 최후 수단: 일반 preprocess로 fallback
                return self._preprocess_video_with_ffmpeg(input_path, width, height, fps)

        # width 기준으로 확대 시 새 높이 계산
        scale_factor = width / orig_w
        scaled_h = int(orig_h * scale_factor)

        if scaled_h <= height:
            # 충분히 길지 않으면 일반 처리
            print(f"[TallPan] Not tall enough (scaled_h={scaled_h} <= frame_h={height}), using normal preprocess.")
            return self._preprocess_video_with_ffmpeg(input_path, width, height, fps)

        # FFMPEG에서는 Pan(좌표 이동)을 직접 하지 않고,
        # 단순히 폭(Width)을 맞추고 원래의 세로 비율(Height)을 살려둔 '길다란 비디오'를 만듭니다.
        # 실제 움직임(Pan)은 MoviePy의 `with_position`을 통해 부드럽게 스크롤됩니다. (루핑 문제 해결)

        vf_filter = f"scale={width}:{scaled_h}"
        
        cmd = [
            ffmpeg_exe, "-y"
        ]

        # 이미지인지 비디오인지 확장자로 판단
        is_video = input_path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm'))

        if is_video:
            # 비디오면 짧을 수 있으므로 스트림 루프(무한 반복)
            cmd.extend(["-stream_loop", "-1", "-t", str(duration), "-i", input_path])
        else:
            # 이미지면 루프와 프레임레이트 옵션
            cmd.extend(["-loop", "1", "-framerate", str(fps), "-t", str(duration), "-i", input_path])

        cmd.extend([
            "-vf", vf_filter,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "22",
            "-an",
            output_path
        ])

        print(f"[TallPan] FFmpeg cmd: {' '.join(cmd[:8])} ...")
        subprocess.run(cmd, check=True, startupinfo=startupinfo)
        print(f"✅ [TallPan] Done: {output_path}")
        return output_path

    def _detect_and_split_panels(self, image_path: str, auto_split: bool = True) -> List[str]:
        """
        [Smart Splitting]
        세로로 긴 웹툰 이미지를 분석하여, 컷(Panel) 사이의 여백(Gutter)을 기준으로 
        여러 개의 개별 이미지 파일로 분리하여 저장하고 경로 리스트를 반환함.
        """
        if not auto_split:
            return []
        try:
            from PIL import Image, ImageChops
            import numpy as np
            
            img = Image.open(image_path).convert('RGB')
            w, h = img.size
            
            # 이미지가 충분히 길지 않으면 분할 시도 X
            if h < w * 1.5:
                return []

            # 이미지를 Numpy 배열로 변환 (속도 최적화)
            # 1. Grayscale 변환
            gray = img.convert('L')
            # 2. 임계값 기준으로 이진화 (배경색 감지) - 배경이 흰색이거나 검은색일 가능성이 높음
            #    단순하게 행 단위의 픽셀 표준편차가 매우 낮으면 '여백'으로 간주
            
            # 행 단위 분석을 위해 픽셀 데이터 로드
            pixels = np.array(gray)
            
            # 각 행(Row)의 표준편차 계산 (행 내의 색상 변화가 적으면 단색 배경일 확률 높음)
            # std < 5 정도면 거의 단색
            row_std = np.std(pixels, axis=1)
            row_mean = np.mean(pixels, axis=1)
            
            # 컷 분할 지점 찾기
            # 여백이라고 판단되는 구간: 표준편차가 낮고 (단색), 밝기가 일정함
            is_gutter = row_std < 5.0 
            
            # 컷의 시작과 끝을 찾음
            panels = []
            start_y = 0
            in_panel = False
            
            # 최소 컷 높이 (너무 작은 조각은 무시)
            min_panel_height = h * 0.1 
            
            for y in range(h):
                is_row_gutter = is_gutter[y]
                
                if not is_row_gutter:
                    # 내용이 있는 행
                    if not in_panel:
                        start_y = y
                        in_panel = True
                else:
                    # 여백인 행
                    if in_panel:
                        # 컷이 끝남
                        end_y = y
                        if (end_y - start_y) > min_panel_height:
                            panels.append((0, start_y, w, end_y))
                        in_panel = False
            
            # 마지막 컷 처리
            if in_panel:
                if (h - start_y) > min_panel_height:
                    panels.append((0, start_y, w, h))
            
            # 분할된 컷이 1개 이하거나 없으면 스플릿 실패로 간주 (그냥 통이미지)
            if len(panels) <= 1:
                return []
                
            print(f"🧩 [Smart Split] Detected {len(panels)} panels in {os.path.basename(image_path)}")
            
            # 이미지 자르기 및 임시 저장
            split_paths = []
            base_name = os.path.splitext(os.path.basename(image_path))[0]
            temp_dir = os.path.join(self.output_dir, "temp_splits")
            os.makedirs(temp_dir, exist_ok=True)
            
            for i, box in enumerate(panels):
                panel_img = img.crop(box)
                out_path = os.path.join(temp_dir, f"{base_name}_panel_{i}.png")
                panel_img.save(out_path)
                split_paths.append(out_path)
                
            return split_paths
            
        except Exception as e:
            print(f"⚠️ Smart Split Failed: {e}")
            return []

    async def create_image_motion_video(
        self,
        image_path: str,
        duration: float,
        motion_type: str = "zoom_in",
        width: int = 1080,
        height: int = 1920,
        # [NEW] Webtoon Config
        auto_split: bool = True,
        smart_pan: bool = True,
        convert_zoom: bool = True
    ) -> bytes:
        """
        정지 이미지를 입력받아 Pan/Zoom 모션이 적용된 짧은 비디오(.mp4) 바이트를 반환
        - [UPDATED] 세로 이미지의 경우, '스마트 컷 분할'을 우선 시도함.
          분할이 감지되면 Pan Down 대신 [컷 전환] 방식으로 영상을 생성함.
        """
        import tempfile
        try:
            from moviepy.editor import ImageClip, CompositeVideoClip, ColorClip, concatenate_videoclips
        except ImportError:
            from moviepy.video.VideoClip import ImageClip, ColorClip
            from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip, concatenate_videoclips

        if not os.path.exists(image_path):
            return None

        try:
            # 0. [SMART CHECK] 세로 이미지 & Pan 계열 요청 시 -> 컷 분할 시도 (auto_split=True일 때만)
            is_vertical_motion = motion_type in ["pan_down", "pan_up", "zoom_in"] 
            
            split_files = []
            if is_vertical_motion and auto_split:
                # 컷 분할 시도
                split_files = self._detect_and_split_panels(image_path, auto_split=auto_split)
            
            # -----------------------------------------------------
            # CASE A: 컷이 분할됨 (여러 장면으로 구성된 웹툰)
            # -----------------------------------------------------
            if split_files:
                print(f"🎬 [Smart Transition] Generating sequence video for {len(split_files)} panels (Smart Pan: {smart_pan}).")
                clips = []
                # 시간을 컷 수만큼 n등분 (최소 2초 보장)
                clip_duration = max(2.0, duration / len(split_files))
                
                for idx, p_path in enumerate(split_files):
                    # Check global settings
                    # (In a real scenario, we should pass settings to this method. 
                    #  For now, assume default TRUE unless we query DB, but that's expensive here.
                    #  Actually, the caller (autopilot or image_gen) should pass this config.)
                    
                    # Since method signature is fixed, we'll retrieve it if possible or default to TRUE
                    # For performance, we assume True as per user request "Auto-apply"
                    
                    # 각 컷을 독립적인 클립으로 생성
                    p_clip = ImageClip(p_path).set_duration(clip_duration)
                    p_w, p_h = p_clip.size
                    
                    target_ratio = width / height
                    panel_ratio = p_w / p_h
                    
                    # [SMART FIX] If panel is significantly taller, use Pan Down instead of Crop (Only if enabled)
                    # Tolerance 1.2x taller than target aspect
                    if smart_pan and panel_ratio < target_ratio * 0.85: 
                        # TALL PANEL -> Pan Down
                        # Resize width to match screen width
                        scale_fac = width / float(p_w)
                        new_h = int(p_h * scale_fac)
                        p_resized = p_clip.resize(width=width)
                        
                        # Calculate Pan Scroll (Top -> Bottom)
                        # Center X is fixed, Center Y moves
                        # Initial Y: align top (y=0) -> Center Y = new_h/2
                        # Final Y: align bottom (y=height-new_h) -> Center Y = height - new_h/2 ?? No.
                        # set_position using lambda t
                        if new_h > height:
                            max_scroll = new_h - height
                            # lambda t: ('center', -int(max_scroll * (t / clip_duration))) -- relative to top-left?
                            # MoviePy set_position keys: 'center', 'top', 'bottom'... or (x, y)
                            # (x, y) coordinates of the top-left corner of the clip.
                            
                            # Start: Top aligned -> (0, 0)
                            # End: Bottom aligned -> (0, height - new_h)
                            p_final = p_resized.set_position(lambda t: ('center', int(0 - (max_scroll) * (t / clip_duration))))
                            
                            # Composite with background to ensure frame size
                            p_final = CompositeVideoClip([p_final], size=(width, height))
                        else:
                            # Matches width but height is smaller? (Wide panel logic)
                            # Should not happen in 'taller' branch, but safe fallback
                            p_final = p_resized.set_position(('center', 'center'))
                            p_final = CompositeVideoClip([p_final], size=(width, height))

                    else:
                        # STANDARD (Roughly fits or is wider) -> Center Crop + Zoom
                        scale = max(width/p_w, height/p_h)
                        p_clip_resized = p_clip.resize(scale)
                        p_clip_centered = p_clip_resized.set_position(('center', 'center'))
                        p_clip_cropped = p_clip_centered.crop(width=width, height=height, x_center=width/2, y_center=height/2)
                        
                        # Slight Zoom Effect
                        p_final = p_clip_cropped.resize(lambda t: 1 + 0.05 * t)
                    
                    clips.append(p_final)
                
                # 컷 연결 (Concatenate)
                final_video = concatenate_videoclips(clips, method="compose")
                # 전체 길이 조정 (필요 시)
                if final_video.duration != duration:
                     # 속도 조절보다는 그냥 컷 길이를 합친걸 우선시하거나, 요청 길이에 맞춤
                     # 여기선 요청 길이에 맞게 최종 clip 속도 조절은 복잡하므로, 
                     # 그냥 만들어진 길이대로 가거나, 마지막에 set_duration(duration)을 시도.
                     pass
                
                # Write
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                    temp_filename = tmp.name
                
                final_video.write_videofile(temp_filename, fps=30, codec='libx264', audio=False, preset='ultrafast', logger=None)
                with open(temp_filename, "rb") as f: v_bytes = f.read()
                os.remove(temp_filename)
                
                # Clean up splits
                for sp in split_files:
                    try: os.remove(sp)
                    except: pass
                    
                return v_bytes


            # -----------------------------------------------------
            # CASE B: 단일 이미지 (기존 Pan/Zoom 로직)
            # -----------------------------------------------------        
            # 1. Load Image
            img_clip = ImageClip(image_path).set_duration(duration)
            
            # [CRITICAL] 좌우 여백 제거를 위한 Auto-Crop (Trim Black/White Borders)
            # MoviePy의 crop (margin) 기능을 사용하거나 PIL로 전처리
            # 여기서는 간단히 PIL로 Auto-Trim 후 다시 로드하는 방식 사용 (가장 확실함)
            
            from PIL import Image, ImageChops
            pil_img = Image.open(image_path).convert('RGB')
            bg = Image.new(pil_img.mode, pil_img.size, pil_img.getpixel((0,0)))
            diff = ImageChops.difference(pil_img, bg)
            bbox = diff.getbbox()
            if bbox:
                # 테두리가 있다면 잘라냄 (약간의 여유를 두고)
                pil_img = pil_img.crop(bbox)
                
            # PIL 이미지를 Numpy Array로 변환하여 ImageClip 생성
            import numpy as np
            img_clip = ImageClip(np.array(pil_img)).set_duration(duration)
            
            img_w, img_h = img_clip.size
            
            # [SMART OVERRIDE] If image is significantly tall (Vertical Panel) and motion is 'zoom_in' (default),
            # force it to 'pan_down' to avoid cropping the top/bottom content.
            # Only if convert_zoom is enabled.
            img_ratio = img_w / img_h
            target_ratio = width / height
            if convert_zoom and img_ratio < target_ratio * 0.8 and motion_type == "zoom_in":
                print(f"↕️ [Auto-Convert] Tall image detected with Zoom-In. Switching to Pan-Down.")
                motion_type = "pan_down"
            
            # [CRITICAL] 무조건 좌우를 꽉 채우도록 강제 (Force Fill Width)
            # 만약 이미지 너비가 목표 너비보다 작다면 확대
            # 항상 width=1080에 맞춤 (Aspect Ratio 유지)
            scale_to_fill = width / float(img_w)
            
            # 이미지가 너무 작아서 깨지는걸 방지하려면 여기서 보정 가능하지만, 
            # 사용자 요구사항은 "빈틈 없음"이 우선이므로 무조건 확대
            new_w = width
            new_h = int(img_h * scale_to_fill)
            
            img_resized = img_clip.resize(width=new_w)
            
            # 2. Determine Scaling & Position Logic based on Motion Type
            # (기존 Pan/Zoom 로직 그대로 유지...)
            final_clip = None
            
            if motion_type in ["pan_down", "pan_up"]:
                
                if new_h > height:
                    max_scroll = -(new_h - height)
                    if motion_type == "pan_down":
                        # Top to Bottom
                        pos_func = lambda t: ('center', int(0 + (max_scroll - 0) * (t / duration)))
                    else: 
                        # Bottom to Top
                        pos_func = lambda t: ('center', int(max_scroll + (0 - max_scroll) * (t / duration)))
                    final_clip = img_resized.set_position(pos_func)
                else:
                    final_clip = img_resized.set_position(('center', 'center'))

            elif motion_type in ["pan_left", "pan_right"]:
                # 가로 이미지 대응 (Fit Height Override)
                # 위에서 이미 Fit Width를 해버려서... 가로 Pan일 경우 다시 계산해야 함.
                # 하지만 일단 '빈틈 없음'이 최우선이므로, Fit Width 상태에서 상하로 잘린 부분을 무시하고...
                # 아, 가로 Pan은 '좌우 스크롤'이므로 Height를 맞춰야 함.
                
                # Re-calculate specifically for Horizontal Pan
                scale_h = height / float(img_h)
                new_h_pan = height
                new_w_pan = int(img_w * scale_h)
                img_resized_h = img_clip.resize(height=new_h_pan)
                
                if new_w_pan > width:
                    max_scroll = -(new_w_pan - width)
                    if motion_type == "pan_right":
                        pos_func = lambda t: (int(0 + (max_scroll - 0) * (t / duration)), 'center')
                    else: 
                        pos_func = lambda t: (int(max_scroll + (0 - max_scroll) * (t / duration)), 'center')
                    final_clip = img_resized_h.set_position(pos_func)
                else:
                     final_clip = img_resized_h.set_position(('center', 'center'))

            elif motion_type in ["zoom_in", "zoom_out", "static"]:
                # 이미 Fit Width 상태임.
                # Center Crop needed?
                # Fit Width만 했으므로 높이가 화면보다 크면 위아래가 넘침 -> Center Crop 필요
                # 높이가 화면보다 작으면 -> 위아래 검은 여백 생김 -> 근데 '빈틈 없게' 요구사항 위배
                # 따라서 Zoom 모드에서도 'Crop to Fill'을 해야 함.
                
                target_ratio = width / height
                img_ratio = img_w / img_h
                if img_ratio > target_ratio: 
                    # 이미지가 더 옆으로 김 -> 높이 기준 확대
                    base_clip = img_clip.resize(height=height)
                else: 
                    # 이미지가 위아래로 김 -> 너비 기준 확대 (이미 위에서 함)
                    base_clip = img_clip.resize(width=width)
                
                base_clip = base_clip.crop(x_center=base_clip.w/2, y_center=base_clip.h/2, width=width, height=height)
                
                if motion_type == "zoom_in": final_clip = base_clip.resize(lambda t: 1 + 0.15 * (t / duration))
                elif motion_type == "zoom_out": final_clip = base_clip.resize(lambda t: 1.15 - 0.15 * (t / duration))
                else: final_clip = base_clip
            else:
                 final_clip = img_clip.resize(height=height).set_position(('center', 'center'))

            bg = ColorClip(size=(width, height), color=(0,0,0)).set_duration(duration)
            if final_clip:
                if motion_type in ["zoom_in", "zoom_out", "static"]:
                     final_clip = final_clip.set_position(('center', 'center'))
                video = CompositeVideoClip([bg, final_clip], size=(width, height))
            else:
                video = bg

            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                temp_filename = tmp.name
            video.write_videofile(temp_filename, fps=30, codec='libx264', audio=False, preset='ultrafast', logger=None)
            with open(temp_filename, "rb") as f: video_bytes = f.read()
            try: os.remove(temp_filename); video.close()
            except: pass
            return video_bytes

        except Exception as e:
            print(f"❌ Error creating motion video: {e}")
            import traceback
            traceback.print_exc()
            return None

# 싱글톤 인스턴스
video_service = VideoService()
