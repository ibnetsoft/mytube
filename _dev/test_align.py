
import sys
import os

# Add current dir to sys.path
sys.path.append(os.getcwd())

from services.video_service import video_service

target_audio = r"c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\output\test_subtitle_audio.mp3"
if not os.path.exists(target_audio):
    # Try finding any mp3
    for root, dirs, files in os.walk(r"c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\output"):
        for f in files:
            if f.endswith(".mp3") and "tts" in f:
                target_audio = os.path.join(root, f)
                break
        if target_audio: break

print(f"Testing alignment on: {target_audio}")

try:
    subs = video_service.generate_aligned_subtitles(target_audio)
    print(f"Subtitles count: {len(subs)}")
    if not subs:
        print("Result is empty list []")
    else:
        print(subs[:2])
except Exception as e:
    import traceback
    traceback.print_exc()
