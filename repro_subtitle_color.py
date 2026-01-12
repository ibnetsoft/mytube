import sys
import os
from PIL import Image

# Add current dir to path to import services
sys.path.append(os.getcwd())

from services.video_service import VideoService

def test_subtitle_color():
    service = VideoService()
    
    output_path = "debug_subtitle_white.png"
    
    # Test with #ffffff and Custom style (scenarios from DB)
    path = service._create_subtitle_image(
        text="테스트 자막입니다.",
        width=1920,
        font_size=80,
        font_color="#ffffff",  # DB value
        font_name="Malgun Gothic",
        style_name="Custom",   # DB value
        stroke_color="black",
        stroke_width_ratio=0.15
    )
    
    print(f"Generated image at: {path}")
    
    # Analyze the center pixel color to see if it's white or pink
    if path and os.path.exists(path):
        img = Image.open(path)
        # Crop center to find text color
        w, h = img.size
        center_pixel = img.getpixel((w//2, h//2))
        print(f"Center pixel color: {center_pixel}")
        
        # Check if approx white
        if center_pixel[0] > 200 and center_pixel[1] > 200 and center_pixel[2] > 200:
            print("Result: WHITE (Correct)")
        # Check if pink (255, 0, 255)
        elif center_pixel[0] > 200 and center_pixel[1] < 100 and center_pixel[2] > 200:
            print("Result: PINK (Incorrect/Bug reproduced)")
        else:
            print("Result: OTHER")

if __name__ == "__main__":
    test_subtitle_color()
