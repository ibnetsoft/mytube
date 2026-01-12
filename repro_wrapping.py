import sys
import os
from PIL import Image, ImageDraw, ImageFont

def test_subtitle_wrapping():
    # Mock settings
    width = 1920
    font_size = 80
    font_path = "C:/Windows/Fonts/malgunbd.ttf"
    if not os.path.exists(font_path):
        font_path = "C:/Windows/Fonts/malgun.ttf"
    
    text = "아름다운 단풍은 등산객들을 유혹하지만, 해가 짧아지고 날씨가 변덕스러워지면서 조난 사고 또한 끊이지 않습니다."
    
    # Logic from video_service.py (Simplified copy)
    try:
        font = ImageFont.truetype(font_path, font_size)
    except:
        font = ImageFont.load_default()
        
    safe_width = int(width * 0.9)
    
    def get_text_width(text, font):
        dummy_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
        return dummy_draw.textlength(text, font=font)
        
    total_width = get_text_width(text, font)
    print(f"Total Width: {total_width}, Safe Width: {safe_width}")
    
    wrapped_lines = []
    if total_width <= safe_width:
        wrapped_lines = [text]
    else:
        est_lines = int(total_width / safe_width) + 1
        target_line_width = total_width / est_lines
        
        words = text.split(' ')
        current_line = []
        current_width = 0
        
        for word in words:
            word_width = get_text_width(word + " ", font)
            
            if current_width + word_width > safe_width:
                 wrapped_lines.append(" ".join(current_line))
                 current_line = [word]
                 current_width = word_width
            elif current_width + word_width > target_line_width * 1.2 and len(current_line) > 0:
                 wrapped_lines.append(" ".join(current_line))
                 current_line = [word]
                 current_width = word_width
            else:
                current_line.append(word)
                current_width += word_width
                
        if current_line:
            wrapped_lines.append(" ".join(current_line))
    
    print(f"Wrapped Lines: {len(wrapped_lines)}")
    for line in wrapped_lines:
        print(f"Line: {line}")
        
    wrapped_text = "\n".join(wrapped_lines)
    
    # Height Calc
    dummy_img = Image.new('RGBA', (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)
    bbox = dummy_draw.multiline_textbbox((0, 0), wrapped_text, font=font, align="center")
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    print(f"Text Height: {text_h}, BBox: {bbox}")
    
    pad_y = 20
    img_h = text_h + (pad_y * 2) + 10
    print(f"Image Height: {img_h}")
    
    img = Image.new('RGBA', (width, img_h), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)
    
    center_x = width // 2
    center_y = img_h // 2
    
    text_x = center_x - (text_w // 2)
    text_y = center_y - (text_h // 2)
    
    print(f"Draw Position: {text_x}, {text_y}")
    
    draw.text((text_x, text_y), wrapped_text, font=font, fill="white", align="center")
    
    img.save("debug_wrapping.png")
    print("Saved debug_wrapping.png")

if __name__ == "__main__":
    test_subtitle_wrapping()
