"""
영상 합성 서비스
- MoviePy + FFmpeg를 사용한 이미지+음성 합성
"""
import os
from typing import List, Optional


class VideoService:
    def __init__(self):
        from config import config
        self.output_dir = config.OUTPUT_DIR

    def create_slideshow(
        self,
        images: List[str],
        audio_path: Optional[str] = None,
        output_filename: str = "output.mp4",
        duration_per_image: float = 5.0,
        fps: int = 24,
        resolution: tuple = (1920, 1080), # 16:9 Long-form Standard
        title_text: Optional[str] = None
    ) -> str:
        """
        이미지 슬라이드쇼 영상 생성 (시네마틱 프레임 적용)
        """
        try:
            from moviepy.editor import (
                ImageClip, concatenate_videoclips,
                AudioFileClip, CompositeVideoClip
            )
            import numpy as np
        except ImportError:
            raise ImportError("moviepy가 설치되지 않았습니다. pip install moviepy")

        clips = []
        temp_files = [] # 나중에 삭제할 임시 파일들

        current_duration = 0.0
        
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

        for img_path in images:
            if os.path.exists(img_path):
                # 시네마틱 프레임 생성 (이미지 필터링) - 일단 프레임은 생성 (fallback 및 video input용)
                processed_img_path = self._create_cinematic_frame(img_path, resolution)
                temp_files.append(processed_img_path)
                
                clip = None
                
                # 초반 30초는 AI Video (Veo) 생성 시도 (비활성화)
                # if current_duration < 30.0:
                #     print(f"Generating AI Video for segment at {current_duration}s...")
                #     try:
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

                # Veo 실패하거나 30초 이후면 줌인 효과 (Ken Burns) 사용
                if clip is None:
                    if current_duration < 30.0:
                        # 30초 내인데 실패 시 -> 줌인
                         clip = self._create_zoom_clip(processed_img_path, duration_per_image, resolution)
                    else:
                        # 30초 이후 -> 정지 화상 (또는 줌인 계속? 일단 정지)
                        clip = ImageClip(processed_img_path).set_duration(duration_per_image)

                clips.append(clip)
                current_duration += duration_per_image

        if not clips:
            raise ValueError("유효한 이미지가 없습니다")

        # 클립 연결
        video = concatenate_videoclips(clips, method="compose")

        # 오디오 추가
        if audio_path and os.path.exists(audio_path):
            audio = AudioFileClip(audio_path)

            # 오디오 길이에 맞춰 비디오 조절
            if audio.duration > video.duration:
                # 비디오가 짧으면 마지막 이미지 연장
                last_clip = clips[-1].set_duration(
                    audio.duration - video.duration + duration_per_image
                )
                clips[-1] = last_clip
                video = concatenate_videoclips(clips, method="compose")

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
                    font_name="malgun.ttf"
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

        # 출력
        output_path = os.path.join(self.output_dir, output_filename)
        try:
            import datetime
            with open("c:/Users/kimse/Downloads/유튜브소재발굴기/롱폼생성기/debug_v2.log", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.datetime.now()}] calling writes_videofile code in video_service (720p safe mode)\n")

            # [FIX] Unique temp audio path to avoid conflicts/locks
            import uuid
            temp_audio_path = os.path.join(self.output_dir, f"temp_audio_{uuid.uuid4()}.mp3")
            
            video.write_videofile(
                output_path,
                fps=fps,
                codec="libx264",
                audio_codec="libmp3lame", # [REVERT] aac -> libmp3lame (mp3 확장자와 매칭)
                threads=1,
                preset="superfast",
                temp_audiofile=temp_audio_path,
                remove_temp=False 
            )
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            with open("c:/Users/kimse/Downloads/유튜브소재발굴기/롱폼생성기/debug_v2.log", "a", encoding="utf-8") as f:
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

    def _create_cinematic_frame(self, image_path: str, target_size: tuple) -> str:
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
        # 꽉 채우지 않고 여백을 둠 (너비의 90% 정도)
        fg_max_w = int(target_w * 0.90)
        fg_max_h = int(target_h * 0.80) # 상하 여백 확보
        
        fg = img.copy()
        fg.thumbnail((fg_max_w, fg_max_h), Image.Resampling.LANCZOS)
        
        # 배경 중앙에 합성
        bg.paste(fg, ((target_w - fg.width) // 2, (target_h - fg.height) // 2), fg)
        
        # [FIX] MoviePy 호환성을 위해 RGB로 변환 (알파 채널 제거)
        bg = bg.convert("RGB")

        # 저장
        temp_filename = f"frame_{uuid.uuid4()}.png"
        output_path = os.path.join(self.output_dir, temp_filename)
        bg.save(output_path)
        
        return output_path

        return output_path

    def generate_aligned_subtitles(self, audio_path: str, script_text: str = None) -> List[dict]:
        """
        Faster-Whisper를 사용하여 오디오 자막 생성 (정확한 타이밍)
        """
        try:
            from faster_whisper import WhisperModel
            import torch
        except ImportError:
            print("faster-whisper not installed. fallback to simple.")
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
            
            segments, info = model.transcribe(audio_path, beam_size=5, language="ko", word_timestamps=False)
            
            import re
            
            subtitles = []
            for segment in segments:
                raw_text = segment.text.strip()
                
                # [CLEAN] 지문 제거 (괄호, 대괄호, 별표 등)
                # 예: (음악), [소음], **강조**
                clean_text = re.sub(r'\([^)]*\)|\[[^\]]*\]|\*+[^*]+\*+', '', raw_text).strip()
                
                # 특수문자만 남은 경우 제거 (.,?! 등)
                if not clean_text or not re.search(r'[가-힣a-zA-Z0-9]', clean_text):
                    continue

                subtitles.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": clean_text
                })
            
            print(f"Generated {len(subtitles)} subtitle segments (Cleaned).")
            return subtitles
            
        except Exception as e:
            print(f"Whisper alignment failed: {e}")
            return []

    def _create_cinematic_frame(self, image_path: str, target_size: tuple) -> str:
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
        # 꽉 채우지 않고 여백을 둠 (너비의 90% 정도)
        fg_max_w = int(target_w * 0.90)
        fg_max_h = int(target_h * 0.80) # 상하 여백 확보
        
        fg = img.copy()
        fg.thumbnail((fg_max_w, fg_max_h), Image.Resampling.LANCZOS)
        
        # 배경 중앙에 합성
        bg.paste(fg, ((target_w - fg.width) // 2, (target_h - fg.height) // 2), fg)
        
        # 저장
        temp_filename = f"frame_{uuid.uuid4()}.png"
        output_path = os.path.join(self.output_dir, temp_filename)
        bg.save(output_path)
        
        return output_path

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
        font: str = "malgun.ttf",
        style_name: str = "Basic_White"
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
                    style_name=style_name
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
        final.write_videofile(
            output_path, 
            fps=video.fps,
            threads=1,
            codec="libx264",
            audio_codec="aac"
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
            "font_color": "white",
            "stroke_color": "black",
            "stroke_width_ratio": 0.1,
            "bg_color": None,
            "font_name": "malgun.ttf"
        },
        "Vlog_Yellow": {
            "font_color": "#FFD700", # Gold
            "stroke_color": "#4B0082", # Indigo
            "stroke_width_ratio": 0.08,
            "bg_color": None,
            "font_name": "malgunbd.ttf"
        },
        "Cinematic_Box": {
            "font_color": "white",
            "stroke_color": None,
            "stroke_width_ratio": 0,
            "bg_color": (0, 0, 0, 150),
            "bg_padding": 20,
            "font_name": "malgun.ttf"
        },
        "Cute_Pink": {
            "font_color": "#FF69B4", # HotPink
            "stroke_color": "white",
            "stroke_width_ratio": 0.12,
            "bg_color": None,
            "font_name": "malgunbd.ttf"
        },
        "Neon_Green": {
            "font_color": "#00FF00", # Lime
            "stroke_color": "black",
            "stroke_width_ratio": 0.15,
            "bg_color": None,
            "font_name": "arialbd.ttf"
        }
    }

    def _create_subtitle_image(self, text, width, font_size, font_color, font_name, style_name="Basic_White"):
        from PIL import Image, ImageDraw, ImageFont
        import textwrap
        import platform
        
        # 스타일 조회
        style = self.SUBTITLE_STYLES.get(style_name, self.SUBTITLE_STYLES["Basic_White"])
        
        final_font_color = style.get("font_color", font_color)
        stroke_color = style.get("stroke_color", "black")
        stroke_width_ratio = style.get("stroke_width_ratio", 0.1)
        bg_color = style.get("bg_color", None)
        
        # 폰트 로드
        font = None
        system = platform.system()
        try:
            target_font = style.get("font_name", font_name)
            if system == 'Windows':
                if not target_font.endswith('.ttf'): target_font += '.ttf'
                font_path = f"C:/Windows/Fonts/{target_font}"
                if not os.path.exists(font_path):
                     font_path = "C:/Windows/Fonts/malgun.ttf"
                font = ImageFont.truetype(font_path, font_size)
            else:
                 font = ImageFont.truetype("arial.ttf", font_size)
        except:
            font = ImageFont.load_default()

        # Balanced Wrapping Logic
        # 1. 텍스트 너비가 맥스 폭(너비 - 패딩)을 넘는지 확인
        safe_width = int(width * 0.9) # 좌우 5% 패딩
        
        def get_text_width(text, font):
            dummy_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
            return dummy_draw.textlength(text, font=font)

        total_width = get_text_width(text, font)
        
        wrapped_lines = []
        if total_width <= safe_width:
             wrapped_lines = [text]
        else:
            # 2. 넘는다면, 균형있게 나누기 (Balanced Wrapping)
            # 단순히 꽉 채우는게 아니라, 전체 길이를 라인 수로 나누어 목표 길이를 정함
            # 여기서는 최대 2~3줄 가정
            
            # 예상 라인 수
            est_lines = int(total_width / safe_width) + 1
            target_line_width = total_width / est_lines
            
            words = text.split(' ')
            current_line = []
            current_width = 0
            
            for word in words:
                word_width = get_text_width(word + " ", font)
                
                # 현재 라인에 단어를 더했을 때 목표치보다 현저히 크지 않은지 확인
                # 혹은 safe_width를 넘지 않는지 확인 (Hardware Limit)
                
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
        
        padding = style.get("bg_padding", 20)
        # 이미지 크기는 텍스트 박스 + 패딩만큼만 (add_subtitles에서 위치 잡음)
        # 하지만 _create_subtitle_image의 width 인자가 canvas width로 쓰이고 있었음.
        # 기존 로직: img_w = width
        # 변경: img_w = width (투명 캔버스 전체)로 유지하되 텍스트는 중앙 정렬.
        
        img_w = width
        img_h = text_h + (padding * 4) 
        
        img = Image.new('RGBA', (img_w, img_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        center_x = img_w // 2
        center_y = img_h // 2
        
        # 박스 그리기
        if bg_color:
            box_x0 = center_x - (text_w // 2) - padding
            box_y0 = center_y - (text_h // 2) - padding
            box_x1 = center_x + (text_w // 2) + padding
            box_y1 = center_y + (text_h // 2) + padding
            draw.rectangle([box_x0, box_y0, box_x1, box_y1], fill=bg_color)

        # 텍스트 그리기
        text_x = center_x - (text_w // 2)
        text_y = center_y - (text_h // 2)
        
        if stroke_color:
            stroke_width = max(1, int(font_size * stroke_width_ratio))
            draw.text((text_x, text_y), wrapped_text, font=font, fill=final_font_color, 
                      stroke_width=stroke_width, stroke_fill=stroke_color, align="center")
        else:
            draw.text((text_x, text_y), wrapped_text, font=font, fill=final_font_color, align="center")

        import uuid
        temp_filename = f"sub_{uuid.uuid4()}.png"
        output_path = os.path.join(self.output_dir, temp_filename)
        img.save(output_path)
        
        return output_path

    def create_preview_image(self, background_path, text, font_size, font_color, font_name, style_name="Basic_White", target_size=(1280, 720)):
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
                style_name=style_name
            )
            
            if sub_img_path and os.path.exists(sub_img_path):
                sub_img = Image.open(sub_img_path).convert("RGBA")
                
                # 3. 합성 (하단 배치)
                # 안전 영역 (Safe Area): 하단 5% (720px 기준 약 36px)
                bottom_margin = int(target_size[1] * 0.05)
                
                # Center X
                x = (bg.width - sub_img.width) // 2
                # Bottom Y
                y = bg.height - sub_img.height - bottom_margin
                
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

# 싱글톤 인스턴스
video_service = VideoService()
