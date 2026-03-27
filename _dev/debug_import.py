import sys
import os

print(f"Executable: {sys.executable}")
print(f"CWD: {os.getcwd()}")
print("Sys Path:")
for p in sys.path:
    print(f"  - {p}")

try:
    import faster_whisper
    print(f"SUCCESS: faster_whisper imported from {faster_whisper.__file__}")
except ImportError as e:
    print(f"FAILURE: {e}")

try:
    import services.video_service
    print("SUCCESS: services.video_service imported")
except ImportError as e:
    print(f"FAILURE importing video_service: {e}")
