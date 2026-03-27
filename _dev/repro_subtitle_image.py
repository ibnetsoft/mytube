from services.video_service import VideoService
import os

vs = VideoService()
try:
    print("Testing subtitle generation...")
    path = vs._create_subtitle_image(
        text="자, 이제부터 25초 안에 여러분을 신맞고 고수로 만들어줄 초고속 꿀팁, 대방출합니다!",
        width=720,
        font_size=10,
        font_color="white",
        font_name="malgun.ttf",
        style_name="Basic_White"
    )
    print(f"Success: {path}")
    if os.path.exists(path):
        print("File exists.")
        # os.remove(path)
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
