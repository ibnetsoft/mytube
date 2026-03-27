import imageio_ffmpeg
print(f"FFmpeg path: {imageio_ffmpeg.get_ffmpeg_exe()}")

try:
    from pydub import AudioSegment
    AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
    print("Set pydub converter successfully.")
except Exception as e:
    print(f"Pydub setup failed: {e}")
