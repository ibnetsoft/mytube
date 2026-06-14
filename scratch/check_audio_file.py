import os
import sys

# Ensure UTF-8 output
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass

def inspect_file(path):
    print(f"\n--- Inspecting {path} ---")
    if not os.path.exists(path):
        print("File does not exist!")
        return
    
    size = os.path.getsize(path)
    print(f"File Size: {size} bytes")
    if size == 0:
        print("WARNING: File is empty (0 bytes)!")
        return
        
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(path)
        print(f"Duration: {audio.duration_seconds:.3f}s")
        print(f"Channels: {audio.channels}")
        print(f"Frame Rate: {audio.frame_rate}Hz")
    except Exception as e:
        print(f"Failed to parse with pydub: {e}")
        
    try:
        from moviepy import AudioFileClip
        clip = AudioFileClip(path)
        print(f"MoviePy Duration: {clip.duration:.3f}s")
        clip.close()
    except Exception as e:
        print(f"Failed to parse with MoviePy: {e}")

inspect_file("output/test_actual_line1.mp3")
inspect_file("output/test_actual_line2.mp3")
