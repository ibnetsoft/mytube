"""
영상 합성 서비스
- MoviePy + FFmpeg를 사용한 이미지+음성 합성
"""
import os
import re
import datetime
import uuid
import json
import requests
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
        thumbnail_path: Optional[str] = None,  # [NEW] Baked-in Thumbnail (0.1s at start)
        template_overlay_path: Optional[str] = None, # [NEW] Persistent Overlay (Start to End)
        fade_in_flags: Optional[List[bool]] = None,  # [NEW] Fade-in effect per image
        image_effects: Optional[List[str]] = None,   # [NEW] Ken Burns Effects
        intro_video_path: Optional[str] = None,   # [NEW] Intro Video Prepend
        sfx_map: Optional[dict] = None,          # [NEW] Scene SFX Map {scene_num: sfx_path}
        focal_point_ys: Optional[List[float]] = None, # [NEW] Smart Focus Point (0.0 - 1.0)
        content_aspect_ratio: Optional[str] = None   # [NEW] '1:1', '3:4' etc.
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
            return clip.resize(newsize=new_size)

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
            except Exception: pass

        import numpy as np
        import requests 


        clips = []
        # DEBUG: Log incoming effects
        import datetime
        try:
            with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as df:
                 df.write(f"[{datetime.datetime.now()}] create_slideshow(PROJ={project_id}) Effects: {image_effects}\n")
        except Exception: pass
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

        # [FIX] Safe Image Loading for Windows Unicode Paths
        def _get_safe_image_clip(path, duration):
            try:
                import datetime
                # Use binary stream to avoid path encoding issues
                with open(path, "rb") as f:
                    from PIL import Image
                    import numpy as np
                    import io
                    data = f.read()
                    img_pil = Image.open(io.BytesIO(data))
                    if img_pil.mode not in ('RGB', 'RGBA'):
                        img_pil = img_pil.convert('RGB')
                    img_np = np.array(img_pil)
                    
                    sc = ImageClip(img_np).with_duration(duration).with_fps(fps)
                    # [DEBUG] Log successful load to debug.log
                    with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as _df:
                        _df.write(f"[{datetime.datetime.now()}] ✅ [Safe Load] Image Success: {os.path.basename(path)} ({img_pil.width}x{img_pil.height})\n")
                    return sc
            except Exception as e:
                import datetime
                with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as _df:
                    _df.write(f"[{datetime.datetime.now()}] ⚠️ [Safe Load] Failed to load image {path}: {str(e)}\n")
                # Fallback to direct path
                if os.path.exists(path):
                    try: 
                        sc = ImageClip(path).with_duration(duration).with_fps(fps)
                        with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as _df:
                            _df.write(f"[{datetime.datetime.now()}] ✅ [Safe Load] Image Fallback Success: {os.path.basename(path)}\n")
                        return sc
                    except Exception as fe:
                        with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as _df:
                            _df.write(f"[{datetime.datetime.now()}] ❌ [Safe Load] Image Fallback FAILED: {str(fe)}\n")
                return None

        # [FIX] Safe Video Loading for Windows Unicode Paths
        def _get_safe_video_clip(path):
            try:
                import datetime
                has_unicode = any(ord(c) > 127 for c in path)
                if has_unicode:
                    import shutil, tempfile
                    ext = os.path.splitext(path)[1]
                    temp_v = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
                    temp_v_path = temp_v.name
                    temp_v.close()
                    shutil.copy2(path, temp_v_path)
                    temp_files.append(temp_v_path)
                    with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as _df:
                        _df.write(f"[{datetime.datetime.now()}] 🔄 [Safe Load] Video Copy (Unicode): {os.path.basename(path)} -> {os.path.basename(temp_v_path)}\n")
                    return VideoFileClip(temp_v_path)
                return VideoFileClip(path)
            except Exception as e:
                import datetime
                with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as _df:
                    _df.write(f"[{datetime.datetime.now()}] ❌ [Safe Load] Video Load FAILED ({path}): {str(e)}\n")
                return None

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
                            processed_path = self._preprocess_video_with_ffmpeg(img_path, target_w, target_h, fps=fps, duration=dur)
                            # Disable remaining effects for video
                            if image_effects is not None and i < len(image_effects):
                                image_effects[i] = 'none'

                        temp_files.append(processed_path)
                        
                        # Load clean clip via safe loader
                        clip = _get_safe_video_clip(processed_path)
                        if clip:
                            clip = clip.without_audio()

                        # [FIX] FFMPEG already produced the video at the correct duration
                        # (-stream_loop -1 -t dur). Only use apply_loop if significantly shorter.
                        # apply_loop uses fl_time() wrapping which can cause black frames on VideoFileClip.
                        try:
                            import datetime
                            with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as _df:
                                _df.write(f"[{datetime.datetime.now()}] VideoAsset loaded: dur={clip.duration:.3f}s, target={dur:.3f}s, path={os.path.basename(processed_path)}\n")
                        except Exception:
                            pass
                        if clip.duration < dur - 0.5:
                            # Significantly shorter: need to loop (rare, fallback)
                            clip = apply_loop(clip, duration=dur)
                        elif clip.duration > dur + 0.1:
                            clip = clip.subclip(0, dur)
                        # else: duration is close enough, just set metadata below

                        clip = clip.with_duration(dur)
                        
                        # [NEW] Vertical/Letterbox Consistency for VIDEO assets
                        if is_vertical:
                            clip_ratio = clip.w / clip.h
                            target_ratio = target_w / target_h
                            if clip_ratio > target_ratio:
                                # Video is wider (e.g. 3:4 video in 9:16 frame) -> Fit Width
                                original_clip = clip
                                clip = clip.resized(width=target_w)
                                # Centered by default in CompositeVideoClip if we set position later, 
                                # but usually we set it manually or it defaults to center.
                                print(f"📱 [Letterbox Video] Scene {i+1}: Resized to fit width {target_w} (Ratio: {clip_ratio:.2f})")
                            else:
                                # Video is taller or same -> Fit Height (standard)
                                clip = clip.resized(height=target_h)
                                
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
                         import datetime
                         with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as _df:
                             _df.write(f"[{datetime.datetime.now()}] ❌ Scene[{i+1}] VIDEO FAILED to load, skipped: {os.path.basename(img_path)}\n")
                         continue # Skip this frame entirely if video failed to load
                else: 
                    # Image Processing (Cinematic Frame or Fit)
                    target_w, target_h = resolution
                    is_vertical = target_h > target_w
                    
                    # [DYNAMIC] Calculate Content Box Height for Shorts
                    content_h = target_h
                    if is_vertical:
                        ratio_val = 1.0 # Default 1:1
                        if content_aspect_ratio:
                            try:
                                num, den = map(int, content_aspect_ratio.split(':'))
                                ratio_val = num / den
                            except: pass
                        content_h = int(target_w / ratio_val)
                        content_h = min(content_h, target_h)
                        print(f"🎬 [Render] Scene {i+1} Bound: {content_aspect_ratio or '1:1'} ({target_w}x{content_h})")

                    # [NEW] Detect if pan is requested for images
                    is_tall_pan = False
                    is_wide_pan = False
                    eff_check = ""
                    if image_effects and i < len(image_effects):
                        eff_check = str(image_effects[i]).lower().replace(" ", "_")
                        if eff_check in ['pan_up', 'pan_down', 'scroll_down', 'scroll_up']:
                            is_tall_pan = True
                        if eff_check in ['pan_left', 'pan_right']:
                            is_wide_pan = True

                    dur = duration_per_image[i] if isinstance(duration_per_image, list) else duration_per_image

                    # [NEW] Aspect Ratio Awareness for Panning
                    # If the project is vertical (9:16/3:4/1:1) and the image is wider than the frame (e.g. 3:4 in 9:16),
                    # we must letterbox it to satisfy the user's request. 
                    # Wide/Tall panning effects for these cases would force cropping, so we suppress them.
                    from PIL import Image
                    try:
                        with Image.open(img_path) as im:
                            img_w, img_h = im.size
                            img_ratio = img_w / img_h
                            target_ratio = target_w / target_h
                            
                            if is_vertical and img_ratio > target_ratio:
                                # This image REQUIRES letterbox. Disable panning that forces fill/crop.
                                if is_wide_pan or is_tall_pan:
                                    print(f"⚠️ [Render] Scene {i}: Panning disabled to preserve Letterbox (Ratio: {img_ratio:.2f} > {target_ratio:.2f})")
                                    is_wide_pan = False
                                    is_tall_pan = False
                    except Exception: pass

                    if is_tall_pan:
                        # Use FFmpeg Preprocess for consistent Vertical Pan
                        pan_dir = "up" if eff_check in ['pan_up', 'scroll_up'] else "down"
                        print(f"↕️ [TallPan Image] idx={i}, effect={eff_check}, dir={pan_dir}, dur={dur:.1f}s")
                        processed_path = self._preprocess_video_tall_pan(
                            img_path, target_w, target_h, duration=dur, fps=fps, direction=pan_dir
                        )
                        clip = _get_safe_video_clip(processed_path)
                        if clip:
                            clip = clip.without_audio()
                        temp_files.append(processed_path)
                    
                    elif is_wide_pan:
                        # Use FFmpeg Preprocess for consistent Horizontal Pan
                        pan_dir = "left" if eff_check == 'pan_left' else "right"
                        print(f"↔️ [WidePan Image] idx={i}, effect={eff_check}, dir={pan_dir}, dur={dur:.1f}s")
                        processed_path = self._preprocess_video_wide_pan(
                            img_path, target_w, target_h, duration=dur, fps=fps, direction=pan_dir
                        )
                        clip = _get_safe_video_clip(processed_path)
                        if clip:
                            clip = clip.without_audio()
                        temp_files.append(processed_path)

                    elif is_vertical:
                        # [NEW] Smart focal point retrieval
                        focal_y = 0.5
                        if focal_point_ys and i < len(focal_point_ys):
                            focal_y = focal_point_ys[i]

                        # For Shorts/Vertical: Use Cinematic Frame (Fit Width + Smart Crop Focal Point)
                        processed_img_path = self._create_cinematic_frame(img_path, resolution, focal_point_y=focal_y, allow_tall=False, content_aspect_ratio=content_aspect_ratio)
                        temp_files.append(processed_img_path)
                        
                        # [FIX] Use Safe Image Loader
                        clip = _get_safe_image_clip(processed_img_path, dur)
                    else:
                        # For Landscape Project: Use Fill (Crop) as before
                        processed_img_path = self._resize_image_to_fill(img_path, resolution)
                        temp_files.append(processed_img_path)
                        # [FIX] Use Safe Image Loader
                        clip = _get_safe_image_clip(processed_img_path, dur)
                    
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
                except Exception: pass
                
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
                    except Exception: pass
                
                # [NEW] Normalize/Alias effects for unified motor control
                if safe_effect in ['scroll_down', 'tilt_down', 'pan_down_move']: 
                    safe_effect = 'pan_up'   # Camera moves Down = Look Bottom
                if safe_effect in ['scroll_up', 'tilt_up', 'pan_up_move']: 
                    safe_effect = 'pan_down' # Camera moves Up = Look Top

                if safe_effect and safe_effect != 'none':
                    effect = safe_effect

                # Ensure clip is valid before applying effects
                if clip is None:
                    print(f"⚠️ [Render] Clip for Img[{i+1}] is None. Skipping.")
                    continue
                
                # [DEBUG] Check clip state
                # [FIX v3] Explicit size logging for every scene item
                import datetime
                if clip:
                    with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as _df:
                         _df.write(f"[{datetime.datetime.now()}] Scene[{i+1}] Loaded: {clip.w}x{clip.h}, dur={clip.duration:.2f}s, item={os.path.basename(img_path)}\n")
                else:
                    with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as _df:
                         _df.write(f"[{datetime.datetime.now()}] Scene[{i+1}] FAILED to load: {img_path}\n")

                # [NEW] Handle positioning for TALL assets (Webtoon support)
                # If it's a tall image and no specific effect (or static), ensure we look at the focal point instead of just the top.
                if clip and (not effect or effect == 'none') and is_vertical and processed_img_path and 'tall' in os.path.basename(processed_img_path):
                    try:
                        cur_h = clip.h
                        # Calculate y_offset to center the focal point in the viewport
                        y_offset = int(target_h / 2 - (cur_h * focal_point_y))
                        # Clamp to ensure image covers the background
                        min_y = target_h - cur_h
                        max_y = 0
                        y_pos = max(min_y, min(max_y, y_offset))
                        # Wrap in composite with black background to fix the viewport size and prevent transparency issues
                        bg_base = ColorClip(size=(target_w, target_h), color=(0,0,0)).with_duration(dur)
                        clip = CompositeVideoClip([bg_base, clip.with_position((0, y_pos))], size=(target_w, target_h)).with_duration(dur)
                        print(f"  → Applied focal-point positioning to tall static item #{i+1} (y={y_pos})")
                    except Exception as pe:
                        print(f"Positioning Error: {pe}")
                
                if effect:
                    print(f"DEBUG_RENDER: Image[{i}] Applying Effect '{effect}' (FPS={fps}, Dur={dur}s)")

                    try:
                        w, h = target_w, target_h # [FIX] Use target viewport size, not clip size, because tall clips have clip.h > target_h
                        
                        if effect == 'zoom_in' or effect == 'zoom_out':
                            # [FIX] Use DYNAMIC content box instead of source image ratio
                            content_w, content_h = target_w, content_h # Inherit from session calculation
                            if is_vertical:
                                print(f"  🔒 [Zoom Protect] Constraint: {content_w}x{content_h}")

                            if effect == 'zoom_in':
                                # Center Zoom: 1.0 -> 1.15 (Tuned for better framing)
                                clip = vfx.resize(clip, lambda t: 1.0 + 0.15 * (t / dur))
                            else:
                                # Center Zoom Out: 1.15 -> 1.0
                                clip = vfx.resize(clip, lambda t: 1.15 - 0.15 * (t / dur))
                            
                            # [LOCK] Apply center-crop to keep content within its original 3:4/1:1 bounds
                            if is_vertical and content_h < h:
                                # We take a slice of the zoomed clip that matches the original content size
                                cx, cy = clip.w / 2, clip.h / 2
                                x1, y1 = cx - w/2, cy - content_h/2
                                x2, y2 = x1 + w, y1 + content_h
                                clip = clip.cropped(x1=x1, y1=y1, x2=x2, y2=y2)
                                print(f"  🔒 [Zoom Locked] Scene {i+1}: Trapped in {w}x{content_h} box")

                            # Safe Container with Explicit BG Layer
                            bg_base = ColorClip(size=(w,h), color=(0,0,0)).with_duration(dur)
                            clip = CompositeVideoClip([bg_base, clip.with_position('center')], size=(w,h)).with_duration(dur)
                            
                        elif effect.startswith('pan_'):
                            # [FIX v2] Tall image detection: use actual clip height vs viewport height.
                            # Do NOT rely on filename containing 'tall' — files get renamed (e.g. scene_001.jpg)
                            # and the 'tall' hint is lost. Instead, check if clip is actually taller than viewport.
                            is_tall_clip = (is_tall_pan and clip.h > h)
                            is_wide_clip = (is_wide_pan and clip.w > w)
                            
                            print(f"  [PAN DEBUG] effect={effect}, is_tall={is_tall_clip}, is_wide={is_wide_clip}")

                            if is_tall_clip and effect in ('pan_down', 'pan_up'):
                                # --- TRUE VERTICAL SCROLL ---
                                new_w, new_h = clip.w, clip.h
                                max_scroll = new_h - h
                                if max_scroll > 0:
                                    if effect == 'pan_down': # Top -> Bottom
                                        clip = clip.with_position(lambda t, _ms=max_scroll, _dur=dur, _x_off=int((w - new_w) / 2): (_x_off, int(0 - _ms * (t / _dur))))
                                    else: # pan_up: Bottom -> Top
                                        clip = clip.with_position(lambda t, _ms=max_scroll, _dur=dur, _x_off=int((w - new_w) / 2): (_x_off, int(-_ms + _ms * (t / _dur))))
                                    
                                    bg_base = ColorClip(size=(w,h), color=(0,0,0)).with_duration(dur)
                                    clip = CompositeVideoClip([bg_base, clip], size=(w, h)).with_duration(dur)
                                else:
                                    bg_base = ColorClip(size=(w,h), color=(0,0,0)).with_duration(dur)
                                    clip = clip.with_position(('center', 'center'))
                                    clip = CompositeVideoClip([bg_base, clip], size=(w, h)).with_duration(dur)

                            elif is_wide_clip and effect in ('pan_left', 'pan_right'):
                                # --- TRUE HORIZONTAL SCROLL ---
                                new_w, new_h = clip.w, clip.h
                                max_scroll = new_w - w
                                if max_scroll > 0:
                                    if effect == 'pan_right': # Left -> Right (Reveal contents on RIGHT)
                                        # Initial position: X=0 (Left aligned)
                                        # End position: X=-max_scroll (Right aligned)
                                        clip = clip.with_position(lambda t, _ms=max_scroll, _dur=dur, _y_off=int((h - new_h) / 2): (int(0 - _ms * (t / _dur)), _y_off))
                                    else: # pan_left: Right -> Left
                                        # Initial position: X=-max_scroll (Right aligned)
                                        # End position: X=0 (Left aligned)
                                        clip = clip.with_position(lambda t, _ms=max_scroll, _dur=dur, _y_off=int((h - new_h) / 2): (int(-_ms + _ms * (t / _dur)), _y_off))
                                    
                                    bg_base = ColorClip(size=(w,h), color=(0,0,0)).with_duration(dur)
                                    clip = CompositeVideoClip([bg_base, clip], size=(w, h)).with_duration(dur)
                                else:
                                    bg_base = ColorClip(size=(w,h), color=(0,0,0)).with_duration(dur)
                                    clip = clip.with_position(('center', 'center'))
                                    clip = CompositeVideoClip([bg_base, clip], size=(w, h)).with_duration(dur)
                            
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

                                # Wrap with solid background layer
                                bg_base = ColorClip(size=(w,h), color=(0,0,0)).with_duration(dur)
                                clip = CompositeVideoClip([bg_base, clip], size=(w, h)).with_duration(dur)

                    except Exception as e:
                        print(f"Effect Error: {e}")
                        try:
                            with open("debug_effects_trace.txt", "a", encoding="utf-8") as df:
                                df.write(f"Img[{i}] ERROR applying effect '{effect}': {str(e)}\n")
                        except Exception: pass
                        pass

                # [NEW] Scene SFX Handling
                if sfx_map:
                    s_idx = i + 1
                    sfx_p = sfx_map.get(s_idx) or sfx_map.get(str(s_idx))
                    if sfx_p and os.path.exists(sfx_p):
                         try:
                             from moviepy.audio.io.AudioFileClip import AudioFileClip
                             sfx_clip = AudioFileClip(sfx_p)
                             # Overlay SFX on the current clip's duration
                             if clip.audio:
                                 from moviepy.audio.AudioClip import CompositeAudioClip
                                 sfx_clip = sfx_clip.with_duration(min(sfx_clip.duration, dur))
                                 clip = clip.with_audio(CompositeAudioClip([clip.audio, sfx_clip]))
                             else:
                                 clip = clip.with_audio(sfx_clip.with_duration(min(sfx_clip.duration, dur)))
                             with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as _df:
                                 _df.write(f"[{datetime.datetime.now()}] 🔊 [SFX] Applied to Scene {i+1}: {os.path.basename(sfx_p)}\n")
                         except Exception as se:
                             print(f"SFX Overlay Error: {se}")

                # [FIX v4] FINAL WRAP FOR SCEENE - Ensure solid background even for 'none' effect
                if clip:
                    # If not already wrapped in a CompositeVideoClip (from effects logic), wrap it now
                    if not isinstance(clip, CompositeVideoClip):
                         bg_base = ColorClip(size=(target_w, target_h), color=(0,0,0)).with_duration(dur)
                         clip = CompositeVideoClip([bg_base, clip.with_position('center')], size=(target_w, target_h)).with_duration(dur)
                    
                    clips.append(clip)
                else:
                    # [NEW] Placeholder for missing scene asset — prevents timing shift/compression
                    print(f"⚠️ Scene {i+1} asset missing. Inserting black placeholder frame ({dur:.2f}s).")
                    black_placeholder = ColorClip(size=(target_w, target_h), color=(0,0,0)).with_duration(dur)
                    clips.append(black_placeholder)
                    with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as _df:
                         _df.write(f"[{datetime.datetime.now()}] ⚠️ Scene {i+1} clip is None, skipping\n")

                current_duration += dur

        if not clips and video is None:
            print("❌ [Render Error] No valid clips generated for video.")
            raise ValueError("유효한 이미지나 배경 동영상이 없습니다")

        # 클립 연결 (이미지가 있을 때만)
        if clips:
            print(f"🎬 [Final] Concatenating {len(clips)} clips into main sequence.")
            # Verify clips before concatenation
            valid_clips = []
            for _ii, _c in enumerate(clips):
                 if _c is not None and _c.w > 0 and _c.h > 0 and _c.duration > 0:
                     valid_clips.append(_c)
                 else:
                     details = f"{_c.w}x{_c.h}, dur={_c.duration:.2f}s" if _c else "None"
                     with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as _df:
                         _df.write(f"[{datetime.datetime.now()}] ⚠️ Invalid clip dropped at index {_ii}: {details}\n")
            
            if not valid_clips:
                if video is None:
                    print("❌ [CRITICAL] All clips are invalid and no background video exists!")
                    raise ValueError("유효한 클립이 생성되지 않았습니다.")
                else:
                    print("⚠️ [Render] All image clips were invalid, relying on background video.")
                    video_slideshow = None
            else:
                try:
                    import datetime
                    with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as _df:
                        _df.write(f"[{datetime.datetime.now()}] Concatenating {len(valid_clips)} clips. method=compose\n")
                    # Use method="compose" for mixed types (VideoAsset + Effects + Images)
                    video_slideshow = concatenate_videoclips(valid_clips, method="compose")
                except Exception as ce:
                    with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as _df:
                        _df.write(f"[{datetime.datetime.now()}] Concatenate (compose) FAILED, trying chain: {str(ce)}\n")
                    video_slideshow = concatenate_videoclips(valid_clips, method="chain")

            if video:
                 with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as _df:
                      _df.write(f"[{datetime.datetime.now()}] INFO: Preference check - keeping background video over slideshow.\n")
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
            except Exception:
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

            
        # [MOVED] Title overlay logic moved to after subtitles to ensure it's on top
        title_clip = None
        if title_text:
            try:
                # 제목용 텍스트 이미지 생성 (노란색, 조금 더 크게)
                # [FIXED] Scale title based on reference resolution
                t_size = int(70 * (video.w / 1920.0)) if video.w > video.h else 70
                title_img_path = self._create_subtitle_image(
                    text=title_text,
                    width=video.w,
                    font_size=t_size,
                    font_color="white", # [FIX] Gold to White
                    font_name=config.DEFAULT_FONT_PATH
                )
                if title_img_path:
                    temp_files.append(title_img_path)
                    title_clip = ImageClip(title_img_path)
                    
                    # [FIXED] Enforce Vertical Clamping for Shorts
                    # content_h is the safe box height. Center of it is target_h/2.
                    v_margin = (target_h - content_h) // 2
                    v_safe_min = v_margin if is_vertical else 50
                    
                    title_y = max(v_safe_min + 50, 150) # Fallback to at least safe zone
                    
                    title_clip = title_clip.with_position(("center", title_y)) 
                    title_clip = title_clip.with_duration(video.duration)
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
            
            # [FIX] 폰트 크기 = target resolution 기준으로 계산
            # video.h는 클립 원본 해상도(1920 등)일 수 있어 preview(target resolution 기준)와 불일치 발생
            font_size_percent = s_settings.get("subtitle_font_size") or s_settings.get("font_size", 5.0)
            # target resolution의 height 사용 (preview와 동일한 기준)
            target_h = resolution[1] if isinstance(resolution, (list, tuple)) and len(resolution) >= 2 else video.h
            target_w = resolution[0] if isinstance(resolution, (list, tuple)) and len(resolution) >= 2 else video.w

            if 0.1 <= float(font_size_percent) <= 20:
                # [FIXED] Use WIDTH as base for visual consistency in Shorts (9:16)
                # This prevents huge subtitles in vertical videos.
                base_h = target_w
                f_size = int(base_h * (float(font_size_percent) / 100.0))
            else:
                # 레거시 픽셀 모드
                f_size = int(float(font_size_percent))

            # [FIX] Handle 0 font size (Disable Subtitles)
            if f_size <= 0:
                print("DEBUG_RENDER: Subtitle font size 0 detected. Disabling subtitles.")
                subtitles = []

            print(f"DEBUG_RENDER: Font size: {font_size_percent}% → {f_size}px (target_h: {target_h}px, video.h: {video.h}px)")
            
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
                # [FIX] Scale stroke width: preview 기준 360px → target_h 기준으로 비례 확대
                scale_factor = target_h / 360.0
                s_stroke_width = s_stroke_width * scale_factor
                print(f"DEBUG_RENDER: Scaled Stroke Width: {raw_stroke_width} -> {s_stroke_width:.2f} (target_h={target_h}, factor={scale_factor:.2f})")
            
            # [LOG] Log the settings being used for the render
            try:
                with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as df:
                    df.write(f"[{datetime.datetime.now()}] RENDER_SETTINGS: font='{f_name}', color='{f_color}', style='{s_style}', stroke_color='{s_stroke_color}', stroke_enabled={s_stroke_enabled}, stroke_width={s_stroke_width}, bg_enabled={s_settings.get('bg_enabled')}\n")
            except Exception: pass

            for sub in subtitles:
                if not isinstance(sub, dict):
                    print(f"⚠️ [WARNING] Invalid subtitle format (not a dict): {sub}")
                    continue
                try:
                    # [NEW] Enhanced Background Logic
                    # [FIX] Support both key variants: 'subtitle_bg_enabled' (frontend) and 'bg_enabled' (legacy)
                    _bg_enabled_raw = s_settings.get("subtitle_bg_enabled") if s_settings.get("subtitle_bg_enabled") is not None else s_settings.get("bg_enabled", 1)
                    if _bg_enabled_raw is None:
                        _bg_enabled_raw = 1  # Default: bg enabled
                    bg_enabled = bool(int(_bg_enabled_raw) == 1)
                    final_bg = False
                    if bg_enabled:
                         bg_color_val = s_settings.get("subtitle_bg_color") or s_settings.get("bg_color", "#000000")
                         opacity = float(s_settings.get("subtitle_bg_opacity") or s_settings.get("bg_opacity", 0.5))
                         
                         # [FIX] Robust Color Conversion for BG
                         if isinstance(bg_color_val, str) and bg_color_val.startswith("#"):
                             try:
                                 hex_color = bg_color_val.lstrip('#')
                                 rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
                             except Exception:
                                 rgb = (0, 0, 0) # Fallback to black
                         else:
                             # Try parsing via _parse_color or default to black
                             parsed_c = self._parse_color(bg_color_val)
                             if isinstance(parsed_c, tuple):
                                 rgb = parsed_c[:3]
                             else:
                                 rgb = (0, 0, 0)
                                 
                         final_bg = (*rgb, int(opacity * 255))

                    bg_v_offset = int(s_settings.get("bg_v_offset") or 0)
                    txt_img_path = self._create_subtitle_image(
                        text=sub["text"],
                        width=target_w,
                        font_size=f_size,
                        font_color=f_color,
                        font_name=f_name,
                        style_name=s_style,
                        stroke_color=s_stroke_color,
                        stroke_width=s_stroke_width,
                        bg_color=final_bg,
                        line_spacing_ratio=float(s_settings.get("subtitle_line_spacing") or s_settings.get("line_spacing", 0.1)),
                        bg_v_offset=bg_v_offset
                    )
                    
                    if txt_img_path:
                        # 임시파일 추적 (나중에 삭제)
                        temp_files.append(txt_img_path)

                        # [FIX] Load via PIL/numpy array (same as _get_safe_image_clip)
                        # ImageClip(file_path) in MoviePy 1.0.3 may not handle RGBA masks correctly.
                        # Loading via numpy array + with_fps() ensures proper alpha compositing.
                        try:
                            from PIL import Image as _PIL_Sub
                            import numpy as _np_sub
                            with _PIL_Sub.open(txt_img_path) as _pil_sub:
                                _pil_sub_rgba = _pil_sub.convert('RGBA')
                                _sub_arr = _np_sub.array(_pil_sub_rgba)
                                txt_clip = ImageClip(_sub_arr).with_fps(fps)
                        except Exception as _sub_load_err:
                            print(f"[SUBTITLE] PIL load failed, fallback to path: {_sub_load_err}")
                            txt_clip = ImageClip(txt_img_path)
                        
                        # [FIX] Position Logic
                        # 1. Check for custom position in settings
                        # settings usually store 'subtitle_pos_y' as "123px" or "10%" string
                        custom_y = s_settings.get('subtitle_pos_y') or s_settings.get('pos_y') 
                        
                        y_pos = None
                        
                        if custom_y:
                            try:
                                cy_str = str(custom_y)
                                if cy_str.startswith("b:"):
                                    # 새 bottom% 포맷: b:5% → 아래에서 5% 떨어진 위치
                                    bottom_pct = float(cy_str[2:].replace("%", ""))
                                    # bottom% → y_pos (element top): target_h - bottom_px - clip_height
                                    bottom_px = int(target_h * (bottom_pct / 100))
                                    y_pos = target_h - bottom_px - txt_clip.h
                                elif "px" in cy_str:
                                    y_pos = None  # px는 무시
                                elif "%" in cy_str:
                                    pct = float(cy_str.replace("%", ""))
                                    y_pos = int(target_h * (pct / 100))
                                else:
                                    y_pos = int(float(cy_str))
                            except Exception:
                                y_pos = None

                        # [FIX] Anti-Letterbox Positioning Logic (RESTORED)
                        # We must keep text inside the SQUARE image area, NOT in the black bars.
                        if y_pos is None:
                            if target_h > target_w: # Vertical (Shorts)
                                 # 25% margin from bottom keeps it inside the 1:1 image area
                                 bottom_px = int(target_h * 0.25)
                                 y_pos = target_h - bottom_px - txt_clip.h
                            else: # Landscape
                                 bottom_px = int(target_h * 0.12)
                                 y_pos = target_h - bottom_px - txt_clip.h
                        
                        # Screen Boundary Safety (Final Clamp)
                        y_pos = max(10, min(target_h - txt_clip.h - 10, y_pos))

                        print(f"DEBUG_RENDER: Subtitle SYNCED y_pos={y_pos} (Center-Aligned)")

                        txt_clip = txt_clip.with_position(("center", y_pos))

                        txt_clip = txt_clip.with_start(sub["start"])
                        txt_clip = txt_clip.with_duration(sub["end"] - sub["start"])
                        subtitle_clips.append(txt_clip)
                except Exception as e:
                    print(f"Error creating subtitle clip for text '{sub.get('text', '')}': {e}")
                    import traceback
                    traceback.print_exc()
            
            # [NEW] Force Garbage Collection after heavy clip creation
            import gc
            gc.collect()

            print(f"[SUBTITLE] Total subtitle_clips created: {len(subtitle_clips)}")
            if subtitle_clips:
                # [FIX] Final composition with explicit black background to prevent transparency blackout
                # [TOPMOST] Ensure Title is appended AFTER subtitles to stay on top
                bg_final = ColorClip(size=(target_w, target_h), color=(0,0,0)).with_duration(video.duration)
                
                overlay_layers = subtitle_clips
                if title_clip:
                    overlay_layers.append(title_clip)
                    
                video = CompositeVideoClip([bg_final, video] + overlay_layers, size=(target_w, target_h))
                print(f"[SUBTITLE] CompositeVideoClip created with {len(subtitle_clips)} subtitle clips and Title overlay")
            elif title_clip:
                # No subtitles, but has title
                video = CompositeVideoClip([video, title_clip], size=(target_w, target_h))
                print(f"[TITLE] Title overlay applied (No subtitles)")

        # [NEW] Persistent Template Overlay (Shorts Template) - Topmost Layer
        if template_overlay_path and os.path.exists(template_overlay_path):
            print(f"Applying persistent template overlay: {template_overlay_path}")
            try:
                from PIL import Image as _PIL_Tmpl
                import numpy as _np_tmpl
                with _PIL_Tmpl.open(template_overlay_path) as _pil_tmpl:
                    _pil_tmpl_rgba = _pil_tmpl.convert('RGBA')
                    # Match resolution
                    target_w = resolution[0] if isinstance(resolution, (list, tuple)) and len(resolution) >= 2 else video.w
                    target_h = resolution[1] if isinstance(resolution, (list, tuple)) and len(resolution) >= 2 else video.h
                    
                    if _pil_tmpl_rgba.size != (target_w, target_h):
                        _pil_tmpl_rgba = _pil_tmpl_rgba.resize((target_w, target_h), _PIL_Tmpl.LANCZOS)
                    
                    _tmpl_arr = _np_tmpl.array(_pil_tmpl_rgba)
                    tmpl_clip = ImageClip(_tmpl_arr).with_duration(video.duration).with_fps(fps).with_position('center')
                    
                    # Layer on top
                    video = CompositeVideoClip([video, tmpl_clip], size=(target_w, target_h))
                    print("Shorts template overlay applied successfully.")
            except Exception as te:
                print(f"Failed to apply template overlay: {te}")

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
            except Exception:
                pass
        
        # [CLEANUP] 임시 오디오 파일 수동 삭제 시도 (실패 시 무시)
        try:
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
        except Exception:
            pass # 파일이 잠겨있으면 넘어감 (OS가 나중에 처리하거나 다음 재부팅 시 정리)

        return output_path

        
    def _create_cinematic_frame(self, image_path: str, target_size: tuple, template_path: str = None, focal_point_y: float = 0.5, allow_tall: bool = False, content_aspect_ratio: str = None):
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
            
            # Smart Resizing for Panning
            # If horizontal image (wide) and panning requested, fit to Height (1920)
            # If vertical image (tall) and panning requested, fit to Width (1080)
            
            if allow_tall and img_h > img_w * (target_h / target_w):
                # Tall image (Vertical Scroller)
                new_w = target_w
                new_h = int(new_w * (img_h / img_w))
                img_resized = img.resize((new_w, new_h), Image.LANCZOS)
                
                out_fn = f"cinematic_tall_{uuid.uuid4().hex[:8]}.jpg"
                out_path = os.path.join(config.OUTPUT_DIR, out_fn)
                img_resized.save(out_path, quality=90)
                return out_path

            # Allow Wide (Horizontal Scroller)
            # Check for wide image or specific hint (e.g. from fit_image_to_916)
            # We don't have an 'allow_wide' param yet, let's detect it based on img_w
            is_wide_source = img_w > img_h * (target_w / target_h)
            
            if is_wide_source and not (target_h > target_w):
                # Wide image -> Fit to HEIGHT (1920) to enable panning across width
                new_h = target_h
                new_w = int(new_h * (img_w / img_h))
                img_resized = img.resize((new_w, new_h), Image.LANCZOS)
                
                # If it's meaningfully wide (> 1080), return as-is for panning
                if new_w > target_w + 50:
                    out_fn = f"cinematic_wide_{uuid.uuid4().hex[:8]}.jpg"
                    out_path = os.path.join(config.OUTPUT_DIR, out_fn)
                    img_resized.save(out_path, quality=90)
                    return out_path
            
            # Aspect Fill Logic (Always fill the screen)
            img_ratio = img_w / img_h
            target_ratio = target_w / target_h

            # Aspect Fill Logic (Always fill the screen)
            img_ratio = img_w / img_h
            target_ratio = target_w / target_h

            if target_h > (target_w * 1.5): # 9:16 Shorts
                # [DYNAMIC] Match User-Selected Ratio
                content_w = target_w
                ratio_val = 1.0 # Default 1:1
                
                if content_aspect_ratio:
                    try:
                        num, den = map(int, content_aspect_ratio.split(':'))
                        ratio_val = num / den
                    except: pass
                
                content_h = int(content_w / ratio_val)
                # Clamp content_h to NOT exceed target_h
                content_h = min(content_h, target_h)
                
                # Resizing carefully to fill at least the designated box
                target_box_ratio = content_w / content_h
                
                # [FIXED] Aspect Fit Logic (Contain) - Ensure image stays inside the box without cropping
                if img_ratio > target_box_ratio: # Wide source compared to box -> Fit to Width
                    new_w = content_w
                    new_h = int(new_w / img_ratio)
                else: # Tall source compared to box -> Fit to Height
                    new_h = content_h
                    new_w = int(new_h * img_ratio)
                    
                img_resized = img.resize((new_w, new_h), Image.LANCZOS)
                
                # Center the fitted image inside the 9:16 target frame
                final_frame = Image.new('RGB', (target_w, target_h), (0, 0, 0))
                
                x_offset = (target_w - new_w) // 2
                y_offset = (target_h - new_h) // 2 # Center vertically in total frame
                
                final_frame.paste(img_resized, (x_offset, y_offset))
                
                out_fn = f"cinematic_framed_{uuid.uuid4().hex[:8]}.jpg"
                out_path = os.path.join(config.OUTPUT_DIR, out_fn)
                final_frame.save(out_path, quality=90)
                return out_path
            
            # Original Logic for Landscape/Standard
            if img_ratio > target_ratio:
                # Image is wider than target -> Fit to Height and Crop Left/Right
                new_h = target_h
                new_w = int(new_h * img_ratio)
                img_resized = img.resize((new_w, new_h), Image.LANCZOS)
                
                y_offset = 0
                x_offset = int(target_w / 2 - (new_w * focal_point_x))
                min_x = target_w - new_w
                max_x = 0
                x_offset = max(min_x, min(max_x, x_offset))
            else:
                # Image is taller/matches target -> Fit to Width and Crop Top/Bottom
                new_w = target_w
                new_h = int(new_w / img_ratio)
                img_resized = img.resize((new_w, new_h), Image.LANCZOS)
                
                x_offset = 0
                y_offset = int(target_h / 2 - (new_h * focal_point_y))
                min_y = target_h - new_h
                max_y = 0
                y_offset = max(min_y, min(max_y, y_offset))

            bg = Image.new('RGB', (target_w, target_h), (0, 0, 0))
            bg.paste(img_resized, (x_offset, y_offset))
            
            # Template Overlay
            if template_path and os.path.exists(template_path):
                 try:
                     tmpl = Image.open(template_path).convert("RGBA")
                     tmpl = tmpl.resize((target_w, target_h), Image.LANCZOS)
                     bg.paste(tmpl, (0, 0), tmpl)
                 except Exception: pass

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

    def composite_character_on_background(
        self,
        char_bytes: bytes,
        bg_bytes: bytes,
        aspect_ratio: str = "16:9",
        char_scale: float = 0.68,
    ) -> bytes:
        """
        캐릭터(흰 배경)와 배경 이미지를 자연스럽게 합성.
        1. numpy 기반 스마트 흰 배경 제거 + 부드러운 가장자리
        2. 발 아래 그림자(ambient shadow) 합성
        3. 배경 조명에 맞춘 색온도 보정
        """
        from PIL import Image, ImageFilter, ImageDraw, ImageEnhance
        import io
        import numpy as np

        ratio_map = {
            "16:9": (1280, 720),
            "9:16": (720, 1280),
            "1:1": (1024, 1024),
            "3:4": (960, 1280),
        }
        target_w, target_h = ratio_map.get(aspect_ratio, (1280, 720))

        # ── 배경 로드 & 크롭 ──────────────────────────────────
        bg = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")
        bg_ratio = bg.width / bg.height
        tgt_ratio = target_w / target_h
        if bg_ratio > tgt_ratio:
            new_h = target_h
            new_w = int(new_h * bg_ratio)
        else:
            new_w = target_w
            new_h = int(new_w / bg_ratio)
        bg = bg.resize((new_w, new_h), Image.Resampling.LANCZOS)
        left = (new_w - target_w) // 2
        top  = (new_h - target_h) // 2
        bg = bg.crop((left, top, left + target_w, top + target_h))

        # ── 캐릭터 로드 ──────────────────────────────────────
        char = Image.open(io.BytesIO(char_bytes)).convert("RGBA")
        arr = np.array(char, dtype=np.float32)  # H×W×4

        r, g, b, a = arr[:,:,0], arr[:,:,1], arr[:,:,2], arr[:,:,3]

        # 흰/밝은 배경 검출 (채도 낮고 밝은 픽셀)
        brightness  = (r + g + b) / 3.0
        max_rgb     = np.maximum(np.maximum(r, g), b)
        min_rgb     = np.minimum(np.minimum(r, g), b)
        saturation  = np.where(max_rgb > 0, (max_rgb - min_rgb) / max_rgb, 0.0)

        # 흰 배경: 밝기 ≥ 230 & 채도 < 0.12
        is_bg = (brightness >= 230) & (saturation < 0.12)

        # 배경에 가까운 픽셀 페이드 아웃 (소프트 마스크)
        soft_mask = np.ones_like(brightness)
        # 완전 배경 → 완전 투명
        soft_mask[is_bg] = 0.0
        # 경계 구간 (밝기 210~230, 채도 0.12~0.22) → 점진 페이드
        fade_zone = (brightness >= 210) & (brightness < 230) & (saturation < 0.22) & (~is_bg)
        fade_alpha = (brightness[fade_zone] - 210) / 20.0          # 0→1
        soft_mask[fade_zone] = np.clip(fade_alpha, 0.0, 1.0)

        new_alpha = (a / 255.0) * soft_mask
        arr[:,:,3] = np.clip(new_alpha * 255, 0, 255)
        char = Image.fromarray(arr.astype(np.uint8), "RGBA")

        # 알파 가장자리 부드럽게 (2px blur)
        rc, gc, bc, ac = char.split()
        ac = ac.filter(ImageFilter.GaussianBlur(radius=2))
        char = Image.merge("RGBA", (rc, gc, bc, ac))

        # ── 캐릭터 리사이즈 ──────────────────────────────────
        char_target_h = int(target_h * char_scale)
        char_target_w = int(char.width * (char_target_h / char.height))
        char = char.resize((char_target_w, char_target_h), Image.Resampling.LANCZOS)

        # ── 배치: 하단 중앙, 약간 위로 (발이 화면 끝에 붙지 않게) ──
        char_x = (target_w - char_target_w) // 2
        char_y = target_h - char_target_h - int(target_h * 0.04)

        # ── 발 아래 그림자 (ambient occlusion) ─────────────────
        shadow_layer = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        shadow_draw  = ImageDraw.Draw(shadow_layer)
        sx = char_x + char_target_w // 2
        sy = char_y + char_target_h + int(target_h * 0.01)
        srx = int(char_target_w * 0.38)
        sry = int(target_h * 0.04)
        shadow_draw.ellipse(
            [sx - srx, sy - sry, sx + srx, sy + sry],
            fill=(0, 0, 0, 90)
        )
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=14))

        # ── 배경 조명 색온도 샘플링 → 캐릭터 색온도 보정 ─────
        bg_arr = np.array(bg.convert("RGB"), dtype=np.float32)
        # 화면 하단 중앙 영역 평균 조명 색
        sample_x1 = max(0, target_w // 4)
        sample_x2 = min(target_w, 3 * target_w // 4)
        sample_y1 = max(0, 2 * target_h // 3)
        bg_sample = bg_arr[sample_y1:, sample_x1:sample_x2]
        mean_r = float(bg_sample[:,:,0].mean())
        mean_g = float(bg_sample[:,:,1].mean())
        mean_b = float(bg_sample[:,:,2].mean())
        mean_lum = (mean_r + mean_g + mean_b) / 3.0 + 1e-6
        # 캐릭터 밝기 조정 (배경 평균 밝기 기준 ±15% 범위로 부드럽게 맞춤)
        char_rgb = char.convert("RGB")
        char_lum = np.array(char_rgb, dtype=np.float32).mean()
        brightness_ratio = np.clip(mean_lum / (char_lum + 1e-6), 0.75, 1.25)
        if abs(brightness_ratio - 1.0) > 0.05:
            enhancer = ImageEnhance.Brightness(char)
            char = enhancer.enhance(float(brightness_ratio))

        # ── 합성 순서: 배경 → 그림자 → 캐릭터 ────────────────
        result = bg.copy()
        result.paste(shadow_layer, (0, 0), mask=shadow_layer)
        result.paste(char, (char_x, char_y), mask=char)

        out_buf = io.BytesIO()
        result.convert("RGB").save(out_buf, format="PNG")
        return out_buf.getvalue()

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
            except Exception: pass
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
            except Exception: pass
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
            # 1. 절대 한계: 70자 (문맥 단위 유지)
            # 2. 의미 분할: 문장부호 뒤 (조사/어미는 25자 이상일 때만 체크)
            # 3. 호흡 분할: 0.8초 이상 침묵

            MAX_CHARS_PER_BLOCK = 70   # 40→70: 문맥 단위 유지
            SOFT_LIMIT_CHARS = 25      # 12→25: 너무 짧게 끊기는 현상 방지
            MIN_SILENCE_GAP = 0.8      # 0.5→0.8: 짧은 호흡에도 끊기는 현상 방지

            # Heuristics — 조사 목록 축소 (문장 의미가 완결되는 어미/부호만)
            SEMANTIC_ENDINGS = ('고', '며', '니', '면', '요', '죠', '다', '까')
            SENTENCE_ENDINGS = ('.', '?', '!', '…')

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
            except Exception: pass

            print(f"Generated {len(subtitles)} subtitle segments (Cleaned & VAD & Aligned).")
            return subtitles
            
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            print(f"Whisper alignment failed: {e}")
            try:
                with open("debug_whisper_error.log", "w", encoding="utf-8") as f:
                    f.write(f"Error during generate_aligned_subtitles:\n{error_msg}")
            except Exception:
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
        except Exception:
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
        except Exception: pass
        
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
        project_id: Optional[int] = None,
        bg_v_offset: int = 0
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
                    stroke_width=current_stroke_width,  # [FIX] Use scaled width
                    bg_v_offset=bg_v_offset
                )
                
                if txt_img_path:
                    txt_clip = ImageClip(txt_img_path)
                    # [FIX] Force Absolute Bottom Positioning
                    # Ensure video object is available or passed correctly.
                    # If 'video' is a filepath string, we can't get .h from it directly.
                    # But add_subtitles is called with 'video' being a VideoFileClip usually.
                    if hasattr(video, 'h'):
                        # [FIX] Position Logic (Same as slideshow)
                        custom_y = s_settings.get('subtitle_pos_y') or s_settings.get('pos_y')
                        y_pos = None

                        if custom_y:
                            try:
                                cy_str = str(custom_y)
                                if cy_str.startswith("b:"):
                                    bottom_pct = float(cy_str[2:].replace("%", ""))
                                    bottom_px = int(video.h * (bottom_pct / 100))
                                    y_pos = video.h - bottom_px - txt_clip.h
                                elif "%" in cy_str:
                                    pct = float(cy_str.replace("%", ""))
                                    y_pos = int(video.h * (pct / 100))
                                else:
                                    y_pos = int(float(cy_str))
                            except Exception: pass

                        # [FIX] Anti-Letterbox Positioning Logic (RESTORED)
                        if y_pos is None:
                            if hasattr(video, 'w') and hasattr(video, 'h') and video.h > video.w: # Vertical
                                 bottom_px = int(video.h * 0.25)
                                 y_pos = video.h - bottom_px - txt_clip.h
                            else:
                                 bottom_y = int(video.h * 0.88)
                                 y_pos = bottom_y - txt_clip.h
                        
                        # Clamp
                        y_pos = max(10, min(video.h - txt_clip.h - 10, y_pos))
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
            # [FIX] Add explicit black background to prevent transparency blackout on some systems
            from moviepy.editor import ColorClip
            bg_base = ColorClip(size=(video.w, video.h), color=(0,0,0)).with_duration(video.duration)
            final = CompositeVideoClip([bg_base, video] + subtitle_clips, size=(video.w, video.h))
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
            except Exception: pass

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

    def _parse_color(self, color_str: Union[str, bool, tuple]) -> Optional[Union[tuple, str]]:
        """CSS style color string (hex, rgb, rgba) -> PIL tuple or base name"""
        if color_str is False:
            return None
            
        if not color_str:
            return "white"
        
        # Already a tuple (PIL format)
        if isinstance(color_str, (tuple, list)):
            return tuple(color_str)

        # Normalize and strip
        s_color = str(color_str).strip()
        
        # Robust logic for rgb() / rgba()
        # Extracts all numeric parts regardless of spacing/separators
        try:
            low_color = s_color.lower()
            if "rgb" in low_color:
                # [FIX] Handle common 'rgba(0,0,0,0.3)' format manually just in case regex fails
                if "0,0,0,0" in s_color.replace(" ",""):
                    # Common dark background.
                    nums = re.findall(r"([\d.]+)", s_color)
                    if len(nums) >= 4:
                        a_int = int(float(nums[3]) * 255)
                        return (0, 0, 0, a_int)

                # re.findall([\d.]+) will get all numbers in order: r, g, b, (a)
                nums = re.findall(r"([\d.]+)", s_color)
                if len(nums) >= 3:
                    r, g, b = nums[:3]
                    alpha = 255
                    if len(nums) >= 4:
                        try:
                            a_val = float(nums[3])
                            alpha = int(a_val * 255) if a_val <= 1.0 else int(a_val)
                        except Exception: pass
                    
                    return (int(r), int(g), int(b), min(255, max(0, alpha)))
        except Exception as e:
            print(f"DEBUG_COLOR: Parsing error on '{s_color}': {e}")
        
        return s_color
        
        return s_color

    def _create_subtitle_image(self, text, width, font_size, font_color, font_name, style_name="Basic_White", stroke_color=None, stroke_width_ratio=None, stroke_width=None, bg_color=None, line_spacing_ratio=0.1, bg_v_offset=0):
        from PIL import Image, ImageDraw, ImageFont
        import textwrap
        import platform
        import unicodedata
        import re

        # [FIX] Safety cleaning just in case (Include Unicode Brackets)
        if text:
            # 1. Strip Unicode curly quotes BEFORE NFKC (NFKC converts them to ASCII ' which we can't distinguish)
            text = re.sub(r"[\u2018\u2019\u201C\u201D\u2032\u2033\u0027\u0060]", '', text)
            # 2. Normalize Unicode (Full-width -> ASCII, etc.)
            text = unicodedata.normalize('NFKC', text)
            # 3. Regex Clean (Strip all brackets)
            text = re.sub(r'[()\[\]\{\}（）「」『』【】]', '', text)
            # 4. Newline Safety
            text = text.replace('\r', '').strip()
            
            # 4. [NEW] Auto-Fallback for Japanese Fonts
            if re.search(r'[\u3040-\u30ff]', text):
                ko_fonts = ["Gmarket", "Jalnan", "Monsori", "CookieRun", "Nanum", "Binggrae", "Mapo", "Netmarble", "Chosun", "-Core", "Gungsuh", "batang"]
                if any(k in font_name for k in ko_fonts):
                    print(f"DEBUG_RENDER: Japanese text detected in K-Font '{font_name}'. Falling back to NotoSansJP.")
                    font_name = "NotoSansJP"

            # 5. [NEW] Auto-Fallback for Korean Text in non-Korean fonts
            # NotoSansJP, Impact, Roboto etc. don't support Hangul → invisible glyphs
            if re.search(r'[\uAC00-\uD7A3\u1100-\u11FF\u3130-\u318F]', text):
                non_korean_fonts = ["NotoSansJP", "Impact", "Roboto", "Arial", "impact", "roboto", "ja"]
                if any(k in font_name for k in non_korean_fonts):
                    print(f"DEBUG_RENDER: Korean text detected in non-Korean font '{font_name}'. Falling back to malgun.")
                    font_name = "Malgun Gothic"
        
        # 스타일 조회
        style = self.SUBTITLE_STYLES.get(style_name, self.SUBTITLE_STYLES["Basic_White"])
        
        # [NEW] Parse Colors for PIL
        font_color = self._parse_color(font_color)
        stroke_color = self._parse_color(stroke_color) if stroke_color else None
        bg_color = self._parse_color(bg_color) if bg_color else None

        final_font_color = style.get("font_color", font_color)
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
            "GmarketSans": "GmarketSansTTFBold.ttf",
            "GmarketSansBold": "GmarketSansTTFBold.ttf",
            "GmarketSansMedium": "GmarketSansMedium.ttf",
            
            "나눔명조": "NanumMyeongjo.ttf",
            "NanumMyeongjo": "NanumMyeongjo.ttf",
            
            "쿠키런": "CookieRun-Regular.ttf",
            "CookieRun-Regular": "CookieRun-Regular.ttf",
            
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
            "NotoSansJP": "NotoSansJP-Bold.ttf",
            "ja": "NotoSansJP-Bold.ttf"
        }
        
        target_font_file = font_mapping.get(font_name, font_name)
        if not target_font_file.lower().endswith((".ttf", ".ttc", ".woff", ".otf")):
            target_font_file += ".ttf"

        print(f"🔍 [Font Resolve] Request: '{font_name}' -> File: '{target_font_file}'")

        _static_fonts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static", "fonts"))
        search_paths = [
            os.path.join(os.path.dirname(__file__), "..", "assets", "fonts"),
            _static_fonts_dir,
            "C:/Windows/Fonts",
            os.path.dirname(__file__)
        ]

        font_path = None
        for path in search_paths:
            candidate = os.path.join(path, target_font_file)
            if os.path.exists(candidate):
                font_path = candidate
                break

        # .ttf를 못 찾으면 동일 이름의 .woff 버전 시도 (PIL/FreeType은 woff 직접 로드 가능)
        if not font_path and target_font_file.lower().endswith(".ttf"):
            woff_file = target_font_file[:-4] + ".woff"
            for path in search_paths:
                candidate = os.path.join(path, woff_file)
                if os.path.exists(candidate):
                    font_path = candidate
                    break

        # 로컬에 없으면 CSS 미리보기와 동일한 CDN에서 woff 자동 다운로드 후 캐시
        if not font_path:
            _font_cdn_map = {
                "Jalnan.ttf":               "https://fastly.jsdelivr.net/gh/projectnoonnu/noonfonts_four@1.0/Jalnan.woff",
                "TmonMonsori.ttf":          "https://fastly.jsdelivr.net/gh/projectnoonnu/noonfonts_two@1.0/TmonMonsori.woff",
                "Pretendard-Bold.ttf":      "https://fastly.jsdelivr.net/gh/Project-Noonnu/noonfonts_2107@1.1/Pretendard-Bold.woff",
                "NanumSquareExtraBold.ttf": "https://fastly.jsdelivr.net/gh/projectnoonnu/noonfonts_seven@1.1/NanumSquareExtraBold.woff",
                "BinggraeMelona-Bold.ttf":  "https://fastly.jsdelivr.net/gh/projectnoonnu/noonfonts_twelve@1.1/BinggraeMelona-Bold.woff",
                "NetmarbleB.ttf":           "https://fastly.jsdelivr.net/gh/projectnoonnu/noonfonts_four@1.0/netmarbleB.woff",
                "ChosunIlboMyungjo.ttf":    "https://fastly.jsdelivr.net/gh/projectnoonnu/noonfonts_one@1.0/ChosunIlboMyungjo.woff",
                "MapoFlowerIsland.ttf":     "https://fastly.jsdelivr.net/gh/projectnoonnu/noonfonts_2001@1.1/MapoFlowerIsland.woff",
                "S-CoreDream-6Bold.ttf":    "https://fastly.jsdelivr.net/gh/projectnoonnu/noonfonts_six@1.2/S-CoreDream-6Bold.woff",
                "CookieRun-Regular.ttf":    "https://fastly.jsdelivr.net/gh/projectnoonnu/noonfonts_2001@1.1/CookieRun-Regular.woff",
                "NanumMyeongjo.ttf":        "https://fastly.jsdelivr.net/gh/projectnoonnu/noonfonts_2001@1.1/NanumMyeongjo.woff",
            }
            _cdn_url = _font_cdn_map.get(target_font_file)
            if _cdn_url:
                try:
                    import requests as _req
                    _woff_name = os.path.basename(_cdn_url.split("?")[0])
                    _save_path = os.path.join(_static_fonts_dir, _woff_name)
                    if not os.path.exists(_save_path):
                        print(f"[FONT] '{target_font_file}' not found. Downloading from CDN: {_woff_name}")
                        _r = _req.get(_cdn_url, timeout=15)
                        if _r.status_code == 200:
                            with open(_save_path, 'wb') as _f:
                                _f.write(_r.content)
                            print(f"[FONT] Downloaded and cached: {_save_path}")
                    if os.path.exists(_save_path):
                        font_path = _save_path
                except Exception as _dl_err:
                    print(f"[FONT] CDN download failed for '{target_font_file}': {_dl_err}")

        # [DEBUG] Font Path Logging
        try:
             with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as df:
                 df.write(f"[{datetime.datetime.now()}] FONT_DEBUG: target='{target_font_file}', found_path='{font_path}', search_paths={search_paths}\n")
        except Exception: pass

        # [FIX] Final fallback must be a RELIABLE Hangul font on Windows
        if not font_path or not os.path.exists(font_path):
             win_malgun = "C:/Windows/Fonts/malgun.ttf"
             win_malgun_bd = "C:/Windows/Fonts/malgunbd.ttf"
             if os.path.exists(win_malgun_bd):
                 font_path = win_malgun_bd
             elif os.path.exists(win_malgun):
                 font_path = win_malgun
             else:
                 # Try common locations in case drive is not C:
                 possible_malguns = [
                     os.path.join(os.environ.get('SystemRoot', 'C:/Windows'), 'Fonts', 'malgun.ttf'),
                     os.path.join(os.environ.get('SystemRoot', 'C:/Windows'), 'Fonts', 'gulim.ttc')
                 ]
                 for p in possible_malguns:
                     if os.path.exists(p):
                         font_path = p
                         break
             
        try:
            if font_path and os.path.exists(font_path):
                # [FIX] TTC Index Handling (Gungsuh is index 2 in batang.ttc)
                idx = 0
                if "batang.ttc" in font_path.lower() and ("gungsuh" in font_name.lower() or "궁서" in font_name):
                    idx = 2

                # [NEW] Try to find Bold variant if not Gungsuh
                final_font_path = font_path
                if "gungsuh" not in font_name.lower() and "궁서" not in font_name:
                    bold_variants = ["bd.ttf", "b.ttf", "-bold.ttf", "_bold.ttf", "bold.ttf", "B.ttf"]
                    for v in bold_variants:
                        test_p = font_path.replace(".ttf", v).replace(".TTF", v)
                        if os.path.exists(test_p):
                            final_font_path = test_p
                            break

                font = ImageFont.truetype(final_font_path, font_size, index=idx)
            else:
                # [FIX] Last-resort fallback to standard Windows/System fonts
                alt_fonts = ["C:/Windows/Fonts/malgun.ttf", "arial.ttf", "C:/Windows/Fonts/gulim.ttc"]
                font = None
                for af in alt_fonts:
                    try:
                        font = ImageFont.truetype(af, font_size)
                        print(f"✅ [Font Fallback Success] Used: {af}")
                        font_path = af
                        break
                    except Exception: continue

                if not font:
                    print(f"❌ [Font CRITICAL] All Hangul fonts failed. Using PIL default (Hangul will likely fail).")
                    font = ImageFont.load_default()
        except Exception as e:
             print(f"DEBUG_FONT: Font loading FAILED for '{font_name}': {e}")
             try:
                 font = ImageFont.load_default()
             except Exception:
                 pass

        # Balanced Wrapping Logic with Manual Newline Support
        safe_width = int(width * 0.9)

        # broken_space 조기 감지 - 줄바꿈 계산에도 동일한 공백 폭 적용
        def _check_broken_space(fnt):
            try:
                mask = fnt.getmask(' ')
                return any(p != 0 for p in mask)
            except Exception:
                return False
        _broken_space_early = _check_broken_space(font)

        def get_text_width(text, font):
            dummy_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
            if not _broken_space_early:
                return dummy_draw.textlength(text, font=font)
            # broken_space 폰트: 공백 폭을 폰트크기의 30%로 제한
            total = 0.0
            for ch in text:
                if ch in (' ', '\u00A0', '\u2009', '\u202F', '\u3000'):
                    total += min(dummy_draw.textlength(ch, font=font), font_size * 0.30)
                else:
                    total += dummy_draw.textlength(ch, font=font)
            return total

        # [FIX] Manual Newline Support - 사용자가 입력한 \n을 기준으로 먼저 분리
        manual_lines = text.split('\n')
        wrapped_lines = []
        
        # [MODIFIED] 폰트 크기로 인해 3줄로 분리되더라도 텍스트가 잘리는 것(누락)을 방지하도록 4줄까지 허용
        MAX_LINES = 4
        
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
                line_width = get_text_width(m_line, font)
                
                # [NEW] Strict 2-line wrap logic — prioritize filling the first line to avoid 3rd line
                if line_width <= safe_width * 2.0:
                    target_w = line_width * 0.55 # Favor slightly longer top line to keep 2nd line short
                    best_split_idx = -1
                    best_score = -9999
                    
                    particles = ('은', '는', '이', '가', '을', '를', '도', '에', '서', '의', '와', '과', '면', '고', '며', '니')
                    punctuations = ('.', ',', '!', '?', '…', ' ')

                    current_w = 0
                    for i in range(len(m_line)):
                        char = m_line[i]
                        char_w = get_text_width(char, font)
                        current_w += char_w
                        
                        # Check candidates for splitting AFTER this char
                        score = 0
                        if char in punctuations:
                            score = 100
                            if char == ' ': score = 50
                        elif char in particles:
                            score = 30
                        
                        if score > 0:
                            # Distance penalty (closer to target_w is better)
                            dist_penalty = abs(current_w - target_w) / font_size * 5.0
                            total_score = score - dist_penalty
                            
                            # Ensure both lines fit in safe_width
                            if current_w <= safe_width and (line_width - current_w) <= safe_width:
                                if total_score > best_score:
                                    best_score = total_score
                                    best_split_idx = i + 1
                    
                    if best_split_idx != -1:
                        wrapped_lines.append(m_line[:best_split_idx].strip())
                        wrapped_lines.append(m_line[best_split_idx:].strip())
                        continue

                # [Greedy Fallback] For 3+ lines or cases where balanced split failed
                cur = ""
                cur_w = 0
                force_break = False

                for i, ch in enumerate(m_line):
                    ch_w = get_text_width(ch, font)

                    if cur_w + ch_w > safe_width and cur:
                        # Character-based wrap for safety
                        wrapped_lines.append(cur)
                        cur = ch
                        cur_w = ch_w

                        if len(wrapped_lines) >= MAX_LINES:
                            # [FIX] Do NOT accumulate the rest of the line. 
                            # Truncate to avoid horizontal overflow.
                            remaining_text = m_line[i+1:]
                            if len(remaining_text) > 2:
                                if len(wrapped_lines[-1]) > 5:
                                    wrapped_lines[-1] = wrapped_lines[-1][:-1] + "..."
                            cur = ""
                            force_break = True
                            break
                    else:
                        cur += ch
                        cur_w += ch_w

                if not force_break:
                    if cur and len(wrapped_lines) < MAX_LINES:
                        wrapped_lines.append(cur)
                    elif cur:
                        # Last line safety
                        if get_text_width(wrapped_lines[-1] + cur, font) > safe_width:
                             wrapped_lines[-1] = (wrapped_lines[-1] + cur)[:int(len(wrapped_lines[-1])*0.9)] + "..."
                        else:
                             wrapped_lines[-1] += cur
                
        # [Final Safety Slice]
        wrapped_lines = wrapped_lines[:MAX_LINES]
        wrapped_text = "\n".join(wrapped_lines)

        # 텍스트 크기 측정
        dummy_img = Image.new('RGBA', (1, 1))
        dummy_draw = ImageDraw.Draw(dummy_img)
        bbox = dummy_draw.multiline_textbbox((0, 0), wrapped_text, font=font, align="center")
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        # Padding Logic Split (X, Y) — CSS preview 기준 동기화
        # CSS: padding: 0.30em 0.6em → horizontal = font_size * 0.6
        pad_x = int(font_size * 0.6)
        pad_y = 0

        # 세로 캔버스 여백 = CSS top/bottom padding (0.30em) 과 동일하게 설정
        # by0 = current_y - font_size*0.30 이므로 strip_pad_y >= 0.30 이어야 잘리지 않음
        strip_pad_y = font_size * 0.30

        if line_spacing_ratio is None:
            line_spacing_ratio = 0.1

        # 줄간격 계산 - CSS 미리보기 완전 일치
        # CSS: padding 0.30em, line-height 1, margin-bottom = lineSpacing_ratio * fontSize
        # 배경이 단일 사각형이므로 strip_pad_y 보정 불필요
        # full_line_height = font_size * (1 + line_spacing_ratio) 로 CSS와 동일
        line_spacing = int(font_size * line_spacing_ratio)
        
        # PIL의 multiline_text는 line_spacing을 줄 사이의 추가 간격으로 사용함.
        # 하지만 우리는 수동으로 current_y를 조절하므로 full_line_height를 정의.
        full_line_height = font_size + line_spacing

        # [FIX] Define missing variables for layout calculation
        line_count = len(wrapped_lines)
        ascent, descent = font.getmetrics()

        # 높이 계산
        total_text_h = font_size * line_count + line_spacing * (line_count - 1)

        # [NEW] Vertical Centering Correction (Visual Midpoint Sync)
        # Some fonts (NanumMyeongjo, GmarketSans) have asymmetric internal offsets in textbbox.
        # We use a reference string 'H가' to find the actual visual center of the font.
        ref_text = "H가"
        ref_bbox = dummy_draw.textbbox((0, 0), ref_text, font=font)
        ref_mask = font.getmask(ref_text)
        ref_ink = ref_mask.getbbox()
        v_offset = 0
        if ref_ink:
            text_center = (ref_bbox[1] + ref_bbox[3]) / 2
            ink_center = (ref_ink[1] + ref_ink[3]) / 2
            v_offset = ink_center - text_center
            # print(f"DEBUG_RENDER: Vertical Offset applied: {v_offset:.2f}px (Font={font_name})")

        # [NEW] Calculate offset margin needs to prevent background clipping when shifted
        safe_top = max(0, -(v_offset + bg_v_offset))
        safe_bot = max(0, v_offset + bg_v_offset)

        img_w = width
        actual_h = max(text_h, total_text_h)
        img_h = int(actual_h + strip_pad_y * 2 + final_stroke_width * 2 + descent + safe_top + safe_bot + 8)

        img = Image.new('RGBA', (img_w, img_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        center_x = img_w // 2

        # [FIX] Multi-line Background Support
        # Instead of one big box, draw per-line rounded strips

        # 텍스트 시작 위치: 이미지 상단 정렬 (stroke + bg패딩만큼 내려서 시작)
        # safe_top 마진을 추가하여 캔버스 위로 배경띠가 짤려나가는 현상 방지
        current_y = final_stroke_width + int(strip_pad_y) + safe_top
        
        # [FIX] 공백 글리프 깨짐 감지 (GmarketSans 등 일부 폰트의 space 문자가 □로 렌더링됨)
        def _has_broken_space_glyph(fnt):
            try:
                mask = fnt.getmask(' ')
                return any(p != 0 for p in mask)
            except Exception:
                return False

        broken_space = _has_broken_space_glyph(font)

        # [FIX] 쉼표·마침표 y보정: 일부 한국 디스플레이 폰트(GmarketSans 등)는
        # , . 글리프를 셀 상단에 배치(타이포그래피 어포스트로피 스타일)하여 위로 뜨는 문제 발생.
        # 기준 문자 '가' 잉크 하단과 비교해 차이만큼 아래로 내림.
        punct_y_fix = 0
        try:
            comma_mask = font.getmask(',')
            comma_ink = comma_mask.getbbox()   # (left, top, right, bottom) of ink pixels
            ref_mask   = font.getmask('가')
            ref_ink    = ref_mask.getbbox()
            if comma_ink and ref_ink:
                # comma_ink[3]: 쉼표 잉크 하단 / ref_ink[3]: '가' 잉크 하단
                # 쉼표 하단이 '가' 하단의 60% 미만이면 위로 뜨는 폰트로 판단
                if comma_ink[3] < ref_ink[3] * 0.6:
                    punct_y_fix = ref_ink[3] - comma_ink[3]
        except Exception:
            pass

        _PUNCT_CHARS = frozenset('.,')

        def _draw_line(drw, pos, txt, fnt, fill, sw=0, sf=None):
            """문자 단위 렌더링 (공백 보정 + 쉼표/마침표 y보정)"""
            anchor = 'lt'
            x, y = float(pos[0]), float(pos[1])
            for ch in txt:
                if ch in (' ', '\u00A0', '\u2009', '\u202F', '\u3000'):
                    raw_sp = drw.textlength(ch, font=fnt)
                    x += min(raw_sp, font_size * 0.30) if broken_space else raw_sp
                else:
                    # 쉼표·마침표는 y를 아래로 보정
                    ch_y = y + (punct_y_fix if ch in _PUNCT_CHARS else 0)
                    if sw > 0 and sf:
                        drw.text((x, ch_y), ch, font=fnt, fill=fill, stroke_width=sw, stroke_fill=sf, anchor=anchor)
                    else:
                        drw.text((x, ch_y), ch, font=fnt, fill=fill, anchor=anchor)
                    x += drw.textlength(ch, font=fnt)

        # 1단계: 모든 줄 측정
        line_data = []
        temp_y = current_y
        for line in wrapped_lines:
            if not line or not line.strip():
                line_data.append(None)
                temp_y += full_line_height
                continue
            s_width = int(max(1, round(final_stroke_width))) if final_stroke_width > 0.01 else 0
            l_bbox = draw.textbbox((0, 0), line, font=font, stroke_width=s_width, anchor='lt')
            if broken_space:
                lw = get_text_width(line, font)
            else:
                lw = l_bbox[2] - l_bbox[0]
            lx = center_x - (lw / 2)
            line_data.append((line, lx, lw, temp_y, s_width))
            temp_y += full_line_height

        # 2단계: 통 배경띠 (모든 줄을 하나의 사각형으로)
        if bg_color:
            _bg = bg_color
            if isinstance(_bg, str):
                import re as _re
                _nums = _re.findall(r'[\d.]+', _bg)
                if len(_nums) >= 4:
                    _a = float(_nums[3])
                    _bg = (int(float(_nums[0])), int(float(_nums[1])), int(float(_nums[2])), int(_a * 255) if _a <= 1.0 else int(_a))
                elif len(_nums) >= 3:
                    _bg = (int(float(_nums[0])), int(float(_nums[1])), int(float(_nums[2])), 178)
                else:
                    _bg = (0, 0, 0, 178)

            valid_lines = [d for d in line_data if d is not None]
            if valid_lines:
                # 가장 넓은 줄 기준 x범위 / 첫째~마지막 줄 기준 y범위
                min_lx = min(d[1] for d in valid_lines)
                max_rx = max(d[1] + d[2] for d in valid_lines)
                first_y = valid_lines[0][3]
                last_y = valid_lines[-1][3]

                bx0 = min_lx - pad_x
                bx1 = max_rx + pad_x
                # CSS padding: 0.30em 0.6em 과 동일 — 상하 0.30em 대칭
                by0 = (first_y + v_offset) + bg_v_offset - (font_size * 0.30)
                by1 = (last_y + v_offset) + bg_v_offset + (font_size * 1.30)

                try:
                    # CSS border-radius: 0.25em
                    r = int(font_size * 0.25)
                    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=r, fill=_bg)
                except (AttributeError, TypeError):
                    draw.rectangle([bx0, by0, bx1, by1], fill=_bg)

        # 3단계: 텍스트 그리기
        current_y = final_stroke_width + int(strip_pad_y) + safe_top
        for d in line_data:
            if d is None:
                current_y += full_line_height
                continue
            line, lx, lw, _, s_width = d
            # [FIX] Apply bg_v_offset to text as well to keep it centered within the scaled background box
            _draw_line(draw, (lx, (current_y + v_offset) + bg_v_offset), line, font, final_font_color, s_width, stroke_color if s_width > 0 else None)
            current_y += full_line_height

        import uuid
        temp_filename = f"sub_{uuid.uuid4()}.png"
        output_path = os.path.join(self.output_dir, temp_filename)
        img.save(output_path)
        img.close() # [FIX] Explicit Memory Free
        
        return output_path

    def create_preview_image(self, background_path, text, font_size, font_color, font_name, style_name="Basic_White", stroke_color=None, stroke_width=None, position_y=None, target_size=(1280, 720), bg_v_offset=0):
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
             except Exception:
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
                bg_color=None, # [FIX] Allow style-defined bg strip in preview (sync with render)
                bg_v_offset=bg_v_offset
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
                except Exception:
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
                except Exception:
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
                MAX_CHARS = 70   # 40→70: 문맥 단위 유지

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

                    # Grouping Logic — 문장부호(. ? !)에서만 끊음, 쉼표는 제외
                    is_end_char = word.strip().endswith(('.', '?', '!', '…'))
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
        # [MODIFIED] Grouping re-enabled for better readability (Requested: Long single lines)
        grouped_sentences = []
        current_group = ""
        MAX_GROUP_LEN = 25 # 자막 한 줄에 적당한 길이 (기존 40 -> 한 줄 지향 25로 축소)
        
        for s in raw_sentences:
            if not current_group:
                current_group = s
            else:
                # 합쳤을 때 너무 길지 않으면 병합
                if len(current_group) + len(s) + 1 <= MAX_GROUP_LEN:
                    current_group += " " + s
                else:
                    grouped_sentences.append(current_group)
                    current_group = s
        if current_group:
            grouped_sentences.append(current_group)
            
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

    def _preprocess_video_with_ffmpeg(self, input_path, width, height, fps=30, duration=None):
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
        # setpts=PTS-STARTPTS: 타임스탬프 0 기준 재설정 (Veo 등 비정상 PTS 영상 첫 프레임 검은화면 방지)
        vf_filter = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps},setpts=PTS-STARTPTS"

        cmd = [ffmpeg_exe, "-y"]

        is_video = input_path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm'))

        if is_video:
            # [FIX] -t를 출력 옵션으로 이동: 입력 PTS 기준이 아닌 실제 인코딩 시작점부터 카운트
            # Veo 등 영상은 PTS가 0이 아닌 값에서 시작 → -t를 입력 옵션으로 쓰면 첫 프레임이 검게 됨
            cmd.extend(["-stream_loop", "-1", "-i", input_path])
        else:
            cmd.extend(["-loop", "1", "-framerate", str(fps)])
            if duration is not None:
                cmd.extend(["-t", str(duration)])
            else:
                cmd.extend(["-t", "5"]) # Defaults to 5 seconds if not specified
            cmd.extend(["-i", input_path])

        out_args = [
            "-vf", vf_filter,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-an",
        ]
        if is_video and duration is not None:
            out_args.extend(["-t", str(duration)])
        out_args.append(output_path)
        cmd.extend(out_args)
        
        # Hide console window on Windows
        startupinfo = None
        if os.name == 'nt':
             startupinfo = subprocess.STARTUPINFO()
             startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
             
        print(f"DEBUG: Pre-processing video/image: {input_path} -> {output_path}")
        subprocess.run(cmd, check=True, startupinfo=startupinfo)
        return output_path

    def _preprocess_video_wide_pan(self, input_path, width, height, duration, fps=30, direction="right"):
        """
        [NEW] 가로로 긴 영상/이미지(예: 32:9)에 대해 Full-Travel Horizontal Pan 효과 적용.
        - Height를 프레임 높이에 맞게 확대 (Width는 비율 유지, 크롭 없음)
        - Left→Right 또는 Right→Left 전체 스크롤을 MoviePy에서 처리할 수 있도록 소스 준비
        """
        import subprocess
        import uuid
        import imageio_ffmpeg
        from PIL import Image
        import cv2

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        output_path = os.path.join(self.output_dir, f"video_wide_p_{uuid.uuid4()}.mp4")

        startupinfo = None
        if os.name == 'nt':
             startupinfo = subprocess.STARTUPINFO()
             startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
             
        try:
            cap = cv2.VideoCapture(input_path)
            orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            if orig_w <= 0 or orig_h <= 0: raise ValueError("Invalid dims")
        except Exception:
            try:
                img = Image.open(input_path)
                orig_w, orig_h = img.size
            except Exception:
                return self._preprocess_video_with_ffmpeg(input_path, width, height, fps, duration=duration)

        # height 기준으로 확대 시 새 너비 계산
        scale_factor = height / orig_h
        scaled_w = int(orig_w * scale_factor)

        if scaled_w <= width:
            return self._preprocess_video_with_ffmpeg(input_path, width, height, fps, duration=duration)

        vf_filter = f"scale={scaled_w}:{height}"
        is_video = input_path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm'))
        
        cmd = [ffmpeg_exe, "-y"]
        if is_video:
            cmd.extend(["-stream_loop", "-1", "-i", input_path])
        else:
            cmd.extend(["-loop", "1", "-framerate", str(fps), "-t", str(duration), "-i", input_path])

        out_args = ["-vf", vf_filter, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-pix_fmt", "yuv420p", "-an"]
        if is_video:
            out_args.extend(["-t", str(duration)])
        out_args.append(output_path)
        cmd.extend(out_args)
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
            except Exception:
                print(f"[TallPan] Final Fallback: {e}")
                # 최후 수단: 일반 preprocess로 fallback
                return self._preprocess_video_with_ffmpeg(input_path, width, height, fps, duration=duration)

        # width 기준으로 확대 시 새 높이 계산
        scale_factor = width / orig_w
        scaled_h = int(orig_h * scale_factor)

        if scaled_h <= height:
            # 충분히 길지 않으면 일반 처리
            print(f"[TallPan] Not tall enough (scaled_h={scaled_h} <= frame_h={height}), using normal preprocess.")
            return self._preprocess_video_with_ffmpeg(input_path, width, height, fps, duration=duration)

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
            # [FIX] -t 출력 옵션으로 이동 (입력 PTS 비정상 영상 첫 프레임 검은화면 방지)
            cmd.extend(["-stream_loop", "-1", "-i", input_path])
        else:
            # 이미지면 루프와 프레임레이트 옵션
            cmd.extend(["-loop", "1", "-framerate", str(fps), "-t", str(duration), "-i", input_path])

        out_args = ["-vf", vf_filter, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-pix_fmt", "yuv420p", "-an"]
        if is_video:
            out_args.extend(["-t", str(duration)])
        out_args.append(output_path)
        cmd.extend(out_args)

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
                    except Exception: pass
                    
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
            except Exception: pass
            return video_bytes

        except Exception as e:
            print(f"❌ Error creating motion video: {e}")
            import traceback
            traceback.print_exc()
            return None

    def auto_crop_image(self, image_path: str, border_color="auto", tolerance=15) -> str:
        """
        [FIXED] 이미지 안쪽 부분은 파먹지 않고, 이미지 가장자리의 레터박스(검은색/흰색 등)만 엄격하게 잘라냅니다.
        가로/세로 어느 한 방향으로라도 여백이 있으면 확실히 잘라내도록 로직을 강화했습니다.
        """
        import cv2
        import numpy as np
        import os
        try:
            # 한글 경로 지원을 위해 numpy로 읽기
            stream = open(image_path, "rb")
            bytes_img = bytearray(stream.read())
            img = cv2.imdecode(np.asarray(bytes_img, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
            stream.close()

            if img is None: return image_path

            h, w = img.shape[:2]
            if h < 10 or w < 10: return image_path

            if len(img.shape) == 3 and img.shape[2] == 4:
                img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            elif len(img.shape) == 3 and img.shape[2] == 3:
                img_bgr = img
            else:
                img_bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

            # [REFINED] 상하좌우 각기 다른 배경색이 있을 수 있음을 고려
            # 사이드 5px씩 샘플링해서 확실히 배경인지 판별
            top_bg = np.median(gray[0:5, :])
            bottom_bg = np.median(gray[-5:, :])
            left_bg = np.median(gray[:, 0:5])
            right_bg = np.median(gray[:, -5:])
            
            # 각 사이드 배경색에 대해 '유효 내용물' 마스크 생성
            def get_mask(val, g_img, tol=25):
                if val < 80: return g_img > (val + tol) # 어두운 배경 (검은색 테두리 등)
                else: return g_img < (val - tol) # 밝은 배경 (흰색 테두리 등)
            
            # [IMPROVED] 개별적으로 자르기 위해 각 방향 경계 탐색
            # 상단 경계
            top_mask = get_mask(top_bg, gray)
            valid_rows = np.where(np.any(top_mask, axis=1))[0]
            ymin = valid_rows[0] if len(valid_rows) > 0 else 0
            
            # 하단 경계
            bottom_mask = get_mask(bottom_bg, gray)
            valid_rows_b = np.where(np.any(bottom_mask, axis=1))[0]
            ymax = valid_rows_b[-1] if len(valid_rows_b) > 0 else h-1
            
            # 좌측 경계
            left_mask = get_mask(left_bg, gray)
            valid_cols = np.where(np.any(left_mask, axis=0))[0]
            xmin = valid_cols[0] if len(valid_cols) > 0 else 0
            
            # 우측 경계
            right_mask = get_mask(right_bg, gray)
            valid_cols_r = np.where(np.any(right_mask, axis=0))[0]
            xmax = valid_cols_r[-1] if len(valid_cols_r) > 0 else w-1
            
            # 너무 많이 잘라나가는 것 방지 (안전 장치)
            if (xmax - xmin) < w * 0.1 or (ymax - ymin) < h * 0.1:
                return image_path
            
            # 최종 크롭
            cropped = img[ymin:ymax+1, xmin:xmax+1]
            h_c, w_c = cropped.shape[:2]
            
            # [FORCE 2D FIT FIX] 자른 결과가 원본보다 유의미하게 작으면 덮어쓰기
            if h_c < h - 10 or w_c < w - 10:
                print(f"✂️ [Auto Crop] Removed borders: {w}x{h} -> {w_c}x{h_c} ({os.path.basename(image_path)})")
                _, encoded_img = cv2.imencode(os.path.splitext(image_path)[1], cropped)
                with open(image_path, "wb") as f:
                    encoded_img.tofile(f)
            
            return image_path
            
        except Exception as e:
            print(f"❌ [Video Service] Auto crop failed: {e}")
            return image_path

    def fit_image_to_916(self, image_path: str) -> str:
        """
        [NEW] AI 기반 파이프라인 3단계: 
        자르고 합쳐진 이미지를 쇼츠 비율(9:16) 1080x1920 캔버스에 보기 좋게 맞춥니다.
        """
        import cv2
        import numpy as np
        import os
        try:
            stream = open(image_path, "rb")
            bytes_img = bytearray(stream.read())
            img = cv2.imdecode(np.asarray(bytes_img, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
            stream.close()
            
            if img is None: return image_path
            
            h, w = img.shape[:2]
            target_w = 1080
            target_h = 1920
            
            ratio = h / float(w)
            target_ratio = target_h / float(target_w)
            
            if abs(ratio - target_ratio) < 0.05:
                # 이미 9:16 비율인 경우 크기만 변경
                result = cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
            elif ratio > target_ratio:
                # 9:16보다 '더 길쭉한' (Tall) 이미지: 너비를 1080으로 피팅하고 길이는 유지 (영상에서 세로 스크롤로 처리)
                scale = target_w / float(w)
                new_w = target_w
                new_h = int(h * scale)
                result = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
            else:
                # [RE-FIXED per USER Request] 
                # "가로형 이미지를 숏폼 세로 길이에 맞춰 꽉 채우고 좌우로 카메라 이동하게 해라"
                # 레터박스(검은배경) 금지. 가로폭은 길게 유지(Panning용).
                scale = target_h / float(h) # 세로를 1920에 맞춤
                new_h = target_h
                new_w = int(w * scale)
                
                # 너무 과도하게 크면 메모리 절약을 위해 제한 (가로 최대 4000px 정도)
                if new_w > 4320: 
                    new_w = 4320
                    new_h = int(new_w * (h / float(w)))
                
                result = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
                print(f"🎬 [Video Service] Wide Image Optimized for Panning: {new_w}x{new_h}")
            
            # 투명도(알파) 채널이 껴있으면 제거
            if len(result.shape) == 3 and result.shape[2] == 4:
                result = cv2.cvtColor(result, cv2.COLOR_BGRA2BGR)
                
            _, encoded_img = cv2.imencode(os.path.splitext(image_path)[1], result)
            with open(image_path, "wb") as f:
                encoded_img.tofile(f)
            print(f"📱 [Video Service] 9:16 Smart Fitting completed: {image_path} (final size: {result.shape[1]}x{result.shape[0]})")
            return image_path
            
        except Exception as e:
            print(f"❌ [Video Service] 9:16 Fit error: {e}")
            return image_path

    def auto_merge_continuous_images(self, image_paths: list[str], threshold: float = 20.0) -> list[str]:
        """
        [FIXED] 상/하체 등 하나의 이어지는 그림이 잘렸을 때(픽셀 경계선 일치 시)만 세로로 합성합니다.
        가짜 합성을 막고, 진짜 이어지는 컷들만 카메라 패닝(밑에서 위로 등)이 가능하도록 길게 복원합니다.
        단독 컷은 절대 합치지 않습니다! (나중에 3단계나 AI 아웃페인팅으로 채우기 위함)
        """
        import cv2
        import numpy as np
        import os

        if not image_paths or len(image_paths) < 2:
            return image_paths

        def load_image(path):
            try:
                stream = open(path, "rb")
                bytes = bytearray(stream.read())
                numpyarray = np.asarray(bytes, dtype=np.uint8)
                img = cv2.imdecode(numpyarray, cv2.IMREAD_UNCHANGED)
                stream.close()
                return img
            except Exception:
                return None

        def save_image(img, path):
            _, encoded_img = cv2.imencode(os.path.splitext(path)[1], img)
            with open(path, "wb") as f:
                encoded_img.tofile(f)

        merged_paths = []
        current_img = load_image(image_paths[0])
        current_path = image_paths[0]

        if current_img is None:
            return image_paths

        merged_paths.append(current_path)

        for i in range(1, len(image_paths)):
            next_path = image_paths[i]
            next_img = load_image(next_path)
            
            if next_img is None:
                merged_paths.append(next_path)
                current_img = None
                continue
                
            can_merge = False
            
            if current_img is not None:
                h1, w1 = current_img.shape[:2]
                h2, w2 = next_img.shape[:2]

                # 채널 일치 처리
                if len(current_img.shape) == 3 and current_img.shape[2] == 4:
                    current_img = cv2.cvtColor(current_img, cv2.COLOR_BGRA2BGR)
                elif len(current_img.shape) == 2:
                    current_img = cv2.cvtColor(current_img, cv2.COLOR_GRAY2BGR)
                    
                if len(next_img.shape) == 3 and next_img.shape[2] == 4:
                    next_img = cv2.cvtColor(next_img, cv2.COLOR_BGRA2BGR)
                elif len(next_img.shape) == 2:
                    next_img = cv2.cvtColor(next_img, cv2.COLOR_GRAY2BGR)

                # 좌우 폭 차이가 15% 이하일 때만 병합 검사 (같은 폭의 웹툰 컷이어야 함)
                if abs(w1 - w2) / max(w1, w2) <= 0.15:
                    target_w = max(w1, w2)
                    img1_eval = cv2.resize(current_img, (target_w, h1)) if w1 != target_w else current_img
                    img2_eval = cv2.resize(next_img, (target_w, h2)) if w2 != target_w else next_img
                    
                    # 맞닿는 경계선 5픽셀 단위 색상차 분석 (픽셀 일치도 100%에 가까울수록 이어지는 그림임)
                    bottom_edge = img1_eval[-5:, :]
                    top_edge = img2_eval[:5, :]
                    
                    diff = np.mean(np.abs(bottom_edge.astype(np.float32) - top_edge.astype(np.float32)))
                    if diff < threshold:
                        can_merge = True

            if can_merge:
                target_w = max(w1, w2)
                # 폭을 맞추기 위해 리사이즈
                img1_cat = cv2.resize(current_img, (target_w, int(h1 * (target_w / w1)))) if w1 != target_w else current_img
                img2_cat = cv2.resize(next_img, (target_w, int(h2 * (target_w / w2)))) if w2 != target_w else next_img
                
                # 시각적으로 이어지는 그림이므로 여백 없이 바로 타이트하게 붙임 (원상복구)
                merged_img = np.vstack((img1_cat, img2_cat))
                save_image(merged_img, current_path)
                current_img = merged_img
                print(f"🔗 [Video Service] Continuous Drawing Merged!: {current_path} + {next_path} (Diff: {diff:.2f})")
                
                try: os.remove(next_path)
                except Exception: pass
            else:
                merged_paths.append(next_path)
                current_img = next_img
                current_path = next_path
                
        return merged_paths

# 싱글톤 인스턴스
video_service = VideoService()
