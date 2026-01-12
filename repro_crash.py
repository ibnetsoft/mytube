import os
import sys
from PIL import Image, ImageDraw, ImageFont

# Mocking the _create_subtitle_image logic from video_service.py
def create_subtitle_image_mock(text, width=1920, font_size=80):
    try:
        font_path = "C:/Windows/Fonts/malgunbd.ttf"
        try:
            font = ImageFont.truetype(font_path, font_size)
        except:
            font = ImageFont.load_default()
            
        safe_width = int(width * 0.9)
        
        def get_text_width(text, font):
            dummy_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
            return dummy_draw.textlength(text, font=font)

        # 1. Cleaning Logic
        if text:
            text = text.replace('(', '').replace(')', '').replace('[', '').replace(']', '').replace('{', '').replace('}', '')
            # Full-width Unicode
            text = text.replace('（', '').replace('）', '').replace('【', '').replace('】', '').replace('「', '').replace('」', '').replace('『', '').replace('』', '')
            text = text.strip()
            
        if not text:
            print("Text is empty after cleaning.")
            return None # Should handle this?
            
        # 2. Manual Newline Logic
        manual_lines = text.split('\n')
        wrapped_lines = []
        
        for m_line in manual_lines:
            m_line = m_line.strip()
            if not m_line: continue
            
            line_width = get_text_width(m_line, font)
            if line_width <= safe_width:
                 wrapped_lines.append(m_line)
            else:
                 # Balanced Wrapping (Simplified)
                 wrapped_lines.append(m_line)
        
        wrapped_text = "\n".join(wrapped_lines)
        
        # 3. Size Calculation (Potential Crash Point?)
        dummy_img = Image.new('RGBA', (1, 1))
        dummy_draw = ImageDraw.Draw(dummy_img)
        bbox = dummy_draw.multiline_textbbox((0, 0), wrapped_text, font=font, align="center")
        # if wrapped_text is empty string?
        
        print(f"BBox: {bbox}")
        return "Success"
        
    except Exception as e:
        print(f"CRASH: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print("Test 1: Normal Text")
    create_subtitle_image_mock("Hello World")
    
    print("\nTest 2: Only Brackets")
    create_subtitle_image_mock("(Hello) [World]")
    
    print("\nTest 3: Only Unicode Brackets")
    create_subtitle_image_mock("（Hello） 【World】")
    
    print("\nTest 4: Empty String")
    create_subtitle_image_mock("")
    
    print("\nTest 5: Newlines Only")
    create_subtitle_image_mock("\n\n")

    print("\nTest 6: Empty Wrapped Text (Cleaning results in empty lines)")
    create_subtitle_image_mock("()")
