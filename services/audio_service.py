import os
from moviepy.editor import AudioFileClip, concatenate_audioclips

class AudioService:
    def cut_audio_segment(self, audio_path: str, remove_start: float, remove_end: float) -> str:
        """
        오디오 파일에서 특정 구간(remove_start ~ remove_end, 초 단위)을 제거하고
        덮어쓴 뒤, 변경된 파일 경로(동일)를 반환한다.
        (MoviePy 사용 - pydub 의존성 및 ffprobe 오류 해결 위함)
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        try:
            # 1. Load Audio
            clip = AudioFileClip(audio_path)
            
            # 2. Validation
            duration = clip.duration
            if remove_start < 0: remove_start = 0
            if remove_end > duration: remove_end = duration
            
            if remove_start >= remove_end:
                clip.close()
                return audio_path

            # 3. Slice and Concatenate
            # part1: 0 ~ start
            # part2: end ~ duration
            # subclip works efficiently without decoding everything immediately
            chunks = []
            if remove_start > 0:
                chunks.append(clip.subclip(0, remove_start))
            
            if remove_end < duration:
                chunks.append(clip.subclip(remove_end, duration))
            
            if not chunks:
                # 전체 삭제??? 
                clip.close()
                return audio_path # or empty?
            
            final_clip = concatenate_audioclips(chunks)
            
            # 4. Save to Temp File (to avoid file lock issues on overwrite)
            temp_path = audio_path + ".temp.mp3"
            
            # codec='libmp3lame' is standard for mp3
            final_clip.write_audiofile(temp_path, codec='libmp3lame', logger=None)
            
            # 5. Cleanup Resources
            # Close subclips and final clip
            for c in chunks:
                c.close()
            final_clip.close()
            clip.close()
            
            # 6. Overwrite Original
            if os.path.exists(audio_path):
                os.remove(audio_path)
            os.rename(temp_path, audio_path)
            
            return audio_path
            
        except Exception as e:
            print(f"[AudioService] Error processing audio: {e}")
            # Ensure cleanup if possible
            try:
                if 'clip' in locals(): clip.close()
            except: pass
            raise e

audio_service = AudioService()
