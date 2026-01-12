import os
import sys

# Add project root to sys.path
sys.path.append(os.getcwd())

from services.video_service import VideoService

print("Initializing VideoService...")
service = VideoService()

audio_path = r"C:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\output\등산_20260106\tts_20260106_182429.mp3"

if not os.path.exists(audio_path):
    print(f"Audio file not found: {audio_path}")
    import glob
    mp3s = glob.glob(os.path.join(os.path.dirname(audio_path), "*.mp3"))
    if mp3s:
        audio_path = mp3s[0]
        print(f"Using alternative audio: {audio_path}")
    else:
        sys.exit(1)

# Dummy script text for alignment
script_text = """
나레이션: 늦가을, 산은 그 험준한 속살을 더욱 깊숙이 감추는 계절입니다.
아름다운 단풍은 등산객들을 유혹하지만, 해가 짧아지고 날씨가 변덕스러워지면서 조난 사고 또한 끊이지 않습니다.
민지: (한숨을 쉬며) 언제까지 이렇게 걸어야 해? 다리 아파 죽겠네.
정훈: 조금만 더 가면 정상이야. 힘내!
"""

print(f"Calling generate_aligned_subtitles with audio: {audio_path}")
try:
    subtitles = service.generate_aligned_subtitles(audio_path, script_text)
    print(f"Result: {len(subtitles)} subtitles")
    if subtitles:
        print(f"First sub: {subtitles[0]}")
    else:
        print("Result is empty list (Failed).")
except Exception as e:
    print(f"Exception caught in repro: {e}")
    import traceback
    traceback.print_exc()
