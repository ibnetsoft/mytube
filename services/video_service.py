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
        resolution: tuple = (1080, 1920) # 9:16 Shorts Standard
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

        for img_path in images:
            if os.path.exists(img_path):
                # 시네마틱 프레임 생성 (이미지 필터링)
                processed_img_path = self._create_cinematic_frame(img_path, resolution)
                temp_files.append(processed_img_path)
                
                clip = ImageClip(processed_img_path)
                clip = clip.set_duration(duration_per_image)
                clips.append(clip)

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

        # 출력
        output_path = os.path.join(self.output_dir, output_filename)
        video.write_videofile(
            output_path,
            fps=fps,
            codec="libx264",
            audio_codec="aac"
        )

        # 리소스 정리
        video.close()
        for clip in clips:
            clip.close()
            
        # 임시 이미지 삭제
        for temp_path in temp_files:
            try:
                os.remove(temp_path)
            except:
                pass

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
        
        # 저장
        temp_filename = f"frame_{uuid.uuid4()}.png"
        output_path = os.path.join(self.output_dir, temp_filename)
        bg.save(output_path)
        
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
        font_size: int = 40,
        font_color: str = "white"
    ) -> str:
        """
        영상에 자막 추가
        """
        try:
            from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
            import moviepy.config as mp_config
        except ImportError:
            raise ImportError("moviepy가 설치되지 않았습니다")

        # Windows ImageMagick 경로 문제 방지 (필요 시 설정)
        # mp_config.change_settings({"IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"})

        video = VideoFileClip(video_path)
        subtitle_clips = []

        # 폰트 설정 (Windows 기본 한글 폰트)
        font = "Malgun-Gothic-Bold" # 맑은 고딕 볼드

        for sub in subtitles:
            try:
                txt_clip = TextClip(
                    sub["text"],
                    fontsize=font_size,
                    color=font_color,
                    font=font,
                    stroke_color="black",
                    stroke_width=2,
                    method='caption', # 자동 줄바꿈 지원
                    size=(video.w * 0.9, None) # 너비 제한
                )
                txt_clip = txt_clip.set_position(("center", "bottom"))
                txt_clip = txt_clip.set_start(sub["start"])
                txt_clip = txt_clip.set_duration(sub["end"] - sub["start"])
                subtitle_clips.append(txt_clip)
            except Exception as e:
                print(f"자막 생성 실패: {e}")
                pass

        if subtitle_clips:
            final = CompositeVideoClip([video] + subtitle_clips)
        else:
            final = video

        output_path = os.path.join(self.output_dir, output_filename)
        final.write_videofile(
            output_path, 
            fps=video.fps,
            codec="libx264",
            audio_codec="aac"
        )

        video.close()
        final.close()

        return output_path


# 싱글톤 인스턴스
video_service = VideoService()
