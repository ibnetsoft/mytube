
import os
import glob
import struct

def inspect_wav(filepath):
    print(f"--- Inspecting: {filepath} ---")
    if not os.path.exists(filepath):
        print("File not found.")
        return

    size = os.path.getsize(filepath)
    print(f"Size: {size} bytes")
    
    if size < 44:
        print("Error: File too small for WAV header.")
        return

    with open(filepath, "rb") as f:
        header = f.read(12)
        print(f"Header (hex): {header.hex()}")
        print(f"Header (ascii): {header}")
        
        if header.startswith(b'RIFF') and header.endswith(b'WAVE'):
            print("VALID WAV HEADER detected.")
        else:
            print("INVALID WAV HEADER.")

# 1. Inspect Test Output
inspect_wav("gemini_tts_gemini-2.5-flash-preview-tts.wav")

# 2. Inspect Last App Output
list_of_files = glob.glob('output/tts_*.wav') 
if list_of_files:
    latest_file = max(list_of_files, key=os.path.getctime)
    inspect_wav(latest_file)
else:
    print("No app output .wav files found.")
