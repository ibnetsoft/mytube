
try:
    from faster_whisper import WhisperModel
    print("faster_whisper imported successfully")
except ImportError as e:
    print(f"faster_whisper ImportError: {e}")

try:
    import torch
    print("torch imported successfully")
except ImportError as e:
    print(f"torch ImportError: {e}")
