import sys
import os
from PIL import Image, ImageDraw, ImageFont

def test_subtitle_artifact():
    # Settings from User/DB
    font_path = "C:/Windows/Fonts/GmarketSansBold.ttf"
    if not os.path.exists(font_path):
        font_path = "C:/Windows/Fonts/malgunbd.ttf" # Fallback
        
    font_size = 80
    stroke_width = 12 # 0.15 * 80
    text_clean = "아름다운 단풍은 등산객들을"
    text_with_parens = "( 아름다운 단풍은 등산객들을 )"
    
    # Create Canvas
    width = 1920
    height = 300
    
    def render(text, filename):
        img = Image.new('RGBA', (width, height), (0, 0, 0, 255))
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(font_path, font_size)
        
        # Draw text
        # Center
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]
        
        x = (width - text_w) // 2
        y = (height - text_h) // 2
        
        draw.text((x, y), text, font=font, fill="white", stroke_width=stroke_width, stroke_fill="black")
        
        img.save(filename)
        print(f"Saved {filename}")

    render(text_clean, "debug_artifact_clean.png")
    render(text_with_parens, "debug_artifact_parens.png")
    
if __name__ == "__main__":
    test_subtitle_artifact()
