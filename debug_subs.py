import sys
import os

# 백엔드 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.video_service import video_service
from moviepy.editor import ColorClip

def test_subtitle_generation():
    print("Testing subtitle generation...")
    
    # 1. create dummy video (5 seconds, black background)
    dummy_video_path = "dummy_video.mp4"
    clip = ColorClip(size=(500, 500), color=(0,0,0), duration=5)
    clip.fps = 24
    clip.write_videofile(dummy_video_path, fps=24)
    
    # 2. create dummy subtitles
    subtitles = [
        {"start": 0, "end": 2, "text": "테스트 자막입니다 1"},
        {"start": 2, "end": 4, "text": "Testing Subtitles 2"},
    ]
    
    # 3. Add subtitles
    try:
        output = video_service.add_subtitles(
            video_path=dummy_video_path,
            subtitles=subtitles,
            output_filename="test_output_subs.mp4",
            font_size=50,
            font_color="yellow", # High contrast
            font="malgun.ttf"
        )
        print(f"Success! Output at: {output}")
    except Exception as e:
        print(f"Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_subtitle_generation()
